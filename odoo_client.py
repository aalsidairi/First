"""
Odoo XML-RPC client for the Leave Management application.
Communicates with Odoo via the standard xmlrpc.client library.
"""

import xmlrpc.client
from datetime import datetime


class OdooError(Exception):
    """Raised when an Odoo operation fails."""
    pass


class OdooClient:
    """
    Wraps Odoo XML-RPC endpoints.

    Two endpoints are used:
      - /xmlrpc/2/common  — unauthenticated calls such as `authenticate`
      - /xmlrpc/2/object  — model method calls (requires uid + password)
    """

    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url.rstrip('/')
        self.db = db
        self.username = username
        self.password = password
        self.uid: int | None = None

        # Proxy objects — created once per client instance
        self._common = xmlrpc.client.ServerProxy(
            f'{self.url}/xmlrpc/2/common', allow_none=True
        )
        self._object = xmlrpc.client.ServerProxy(
            f'{self.url}/xmlrpc/2/object', allow_none=True
        )

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------

    def authenticate(self) -> int:
        """
        Authenticate against Odoo.  Returns uid on success or raises
        OdooError on bad credentials / connection failure.
        """
        try:
            uid = self._common.authenticate(
                self.db, self.username, self.password, {}
            )
        except Exception as exc:
            raise OdooError(f'Cannot reach Odoo server: {exc}') from exc

        if not uid:
            raise OdooError('Invalid username or password.')

        self.uid = uid
        return uid

    def call(self, model: str, method: str, args: list, kwargs: dict = None) -> any:
        """
        Execute an arbitrary Odoo model method via execute_kw.
        Raises OdooError on any Fault or transport error.
        """
        if kwargs is None:
            kwargs = {}
        if self.uid is None:
            raise OdooError('Client is not authenticated. Call authenticate() first.')
        try:
            return self._object.execute_kw(
                self.db, self.uid, self.password,
                model, method, args, kwargs
            )
        except xmlrpc.client.Fault as fault:
            raise OdooError(f'Odoo error [{fault.faultCode}]: {fault.faultString}') from fault
        except Exception as exc:
            raise OdooError(f'Communication error: {exc}') from exc

    # ------------------------------------------------------------------
    # Employee helpers
    # ------------------------------------------------------------------

    def get_employee(self, uid: int) -> dict:
        """
        Return the hr.employee record linked to the given res.users uid.
        Raises OdooError if no employee record is found.
        """
        records = self.call(
            'hr.employee', 'search_read',
            [[['user_id', '=', uid]]],
            {
                'fields': [
                    'id', 'name', 'job_title', 'department_id',
                    'parent_id', 'user_id', 'image_128',
                ],
                'limit': 1,
            }
        )
        if not records:
            raise OdooError(
                'No employee record is linked to this user account. '
                'Please ask your HR administrator to create one.'
            )
        return records[0]

    def get_employees_under_manager(self, manager_employee_id: int) -> list:
        """
        Return all hr.employee records whose parent_id is manager_employee_id.
        """
        return self.call(
            'hr.employee', 'search_read',
            [[['parent_id', '=', manager_employee_id]]],
            {'fields': ['id', 'name', 'job_title', 'department_id']}
        )

    def is_manager(self, uid: int) -> bool:
        """
        Return True when the employee linked to *uid* has at least one
        direct report (i.e. is listed as parent_id for some employee).
        """
        employee = self.get_employee(uid)
        subordinates = self.call(
            'hr.employee', 'search_count',
            [[['parent_id', '=', employee['id']]]]
        )
        return subordinates > 0

    # ------------------------------------------------------------------
    # Leave type helpers
    # ------------------------------------------------------------------

    def get_leave_types(self) -> list:
        """
        Return active leave types available for requests.
        """
        return self.call(
            'hr.leave.type', 'search_read',
            [[['active', '=', True], ['requires_allocation', '!=', 'yes']]],
            {'fields': ['id', 'name', 'requires_allocation', 'leave_validation_type']}
        ) or self.call(
            'hr.leave.type', 'search_read',
            [[['active', '=', True]]],
            {'fields': ['id', 'name', 'requires_allocation', 'leave_validation_type']}
        )

    def get_leave_balance(self, employee_id: int, leave_type_id: int) -> float:
        """
        Return the virtual remaining days for a given leave type / employee.
        Falls back to 0.0 if the field is unavailable (e.g. no allocation).
        """
        try:
            # Read virtual_remaining_leaves with employee context
            records = self.call(
                'hr.leave.type', 'read',
                [[leave_type_id]],
                {
                    'fields': ['virtual_remaining_leaves', 'max_leaves', 'leaves_taken'],
                    'context': {'employee_id': employee_id},
                }
            )
            if records:
                return float(records[0].get('virtual_remaining_leaves') or 0.0)
        except OdooError:
            pass
        return 0.0

    def get_all_leave_balances(self, employee_id: int) -> list:
        """
        Return a list of leave types with balance info for an employee.
        Each dict has: id, name, remaining, max_leaves, leaves_taken.
        """
        try:
            leave_types = self.call(
                'hr.leave.type', 'search_read',
                [[['active', '=', True]]],
                {
                    'fields': [
                        'id', 'name', 'virtual_remaining_leaves',
                        'max_leaves', 'leaves_taken',
                    ],
                    'context': {'employee_id': employee_id},
                }
            )
            result = []
            for lt in (leave_types or []):
                result.append({
                    'id': lt['id'],
                    'name': lt['name'],
                    'remaining': float(lt.get('virtual_remaining_leaves') or 0.0),
                    'max_leaves': float(lt.get('max_leaves') or 0.0),
                    'leaves_taken': float(lt.get('leaves_taken') or 0.0),
                })
            return result
        except OdooError:
            return []

    # ------------------------------------------------------------------
    # Leave request helpers
    # ------------------------------------------------------------------

    _LEAVE_FIELDS = [
        'id', 'name', 'holiday_status_id', 'employee_id',
        'date_from', 'date_to', 'number_of_days',
        'state', 'create_date', 'description',
    ]

    @staticmethod
    def _state_label(state: str) -> str:
        return {
            'draft': 'Draft',
            'confirm': 'Pending',
            'validate1': 'Partially Approved',
            'validate': 'Approved',
            'refuse': 'Refused',
        }.get(state, state.title())

    @staticmethod
    def _format_leave(record: dict) -> dict:
        """Enrich a raw hr.leave record with display-friendly fields."""
        record['state_label'] = OdooClient._state_label(record.get('state', ''))
        # Flatten many2one tuples → {'id': x, 'name': y}
        for field in ('holiday_status_id', 'employee_id'):
            val = record.get(field)
            if isinstance(val, (list, tuple)) and len(val) == 2:
                record[field] = {'id': val[0], 'name': val[1]}
        return record

    def get_my_leaves(self, employee_id: int) -> list:
        """Return all leave requests for the given employee, newest first."""
        records = self.call(
            'hr.leave', 'search_read',
            [[['employee_id', '=', employee_id]]],
            {
                'fields': self._LEAVE_FIELDS,
                'order': 'create_date desc',
            }
        )
        return [self._format_leave(r) for r in (records or [])]

    def get_pending_leaves_for_manager(self, manager_employee_id: int) -> list:
        """
        Return leave requests that are in 'confirm' or 'validate1' state
        for any employee whose parent_id is manager_employee_id.
        """
        subordinate_ids = [
            e['id']
            for e in self.get_employees_under_manager(manager_employee_id)
        ]
        if not subordinate_ids:
            return []

        records = self.call(
            'hr.leave', 'search_read',
            [[
                ['employee_id', 'in', subordinate_ids],
                ['state', 'in', ['confirm', 'validate1']],
            ]],
            {
                'fields': self._LEAVE_FIELDS,
                'order': 'create_date asc',
            }
        )
        return [self._format_leave(r) for r in (records or [])]

    def get_all_team_leaves(self, manager_employee_id: int) -> list:
        """
        Return ALL leave requests for subordinates (any state), newest first.
        Used to give managers a full view.
        """
        subordinate_ids = [
            e['id']
            for e in self.get_employees_under_manager(manager_employee_id)
        ]
        if not subordinate_ids:
            return []

        records = self.call(
            'hr.leave', 'search_read',
            [[['employee_id', 'in', subordinate_ids]]],
            {
                'fields': self._LEAVE_FIELDS,
                'order': 'create_date desc',
            }
        )
        return [self._format_leave(r) for r in (records or [])]

    def get_leave_by_id(self, leave_id: int) -> dict:
        """Return a single hr.leave record by ID."""
        records = self.call(
            'hr.leave', 'read',
            [[leave_id]],
            {'fields': self._LEAVE_FIELDS}
        )
        if not records:
            raise OdooError(f'Leave request #{leave_id} not found.')
        return self._format_leave(records[0])

    def create_leave(
        self,
        employee_id: int,
        leave_type_id: int,
        date_from: str,
        date_to: str,
        reason: str,
    ) -> int:
        """
        Create a new hr.leave record in draft state and return its ID.

        date_from / date_to must be 'YYYY-MM-DD' strings; this method
        converts them to full-day datetime strings expected by Odoo.
        """
        # Odoo hr.leave uses datetime fields; cover full days
        dt_from = f'{date_from} 07:00:00'
        dt_to = f'{date_to} 18:00:00'

        vals = {
            'holiday_status_id': leave_type_id,
            'employee_id': employee_id,
            'date_from': dt_from,
            'date_to': dt_to,
            'name': reason or 'Leave request',
        }
        leave_id = self.call('hr.leave', 'create', [vals])
        if not leave_id:
            raise OdooError('Failed to create leave request.')
        return leave_id

    def confirm_leave(self, leave_id: int) -> bool:
        """Move a draft leave to 'confirm' (awaiting approval)."""
        self.call('hr.leave', 'action_confirm', [[leave_id]])
        return True

    def approve_leave(self, leave_id: int) -> bool:
        """
        Approve a leave request.  Tries action_validate() first; if Odoo
        requires two-step approval (validate1 → validate) it calls
        action_validate() a second time.
        """
        leave = self.get_leave_by_id(leave_id)
        state = leave.get('state', '')

        if state == 'validate1':
            # Second approval step
            self.call('hr.leave', 'action_validate', [[leave_id]])
        elif state in ('confirm', 'draft'):
            # Attempt direct validation; some Odoo configs allow this
            try:
                self.call('hr.leave', 'action_validate', [[leave_id]])
            except OdooError:
                # Two-step: first confirm then validate
                self.call('hr.leave', 'action_confirm', [[leave_id]])
                self.call('hr.leave', 'action_validate', [[leave_id]])
        else:
            self.call('hr.leave', 'action_validate', [[leave_id]])

        return True

    def refuse_leave(self, leave_id: int, reason: str = '') -> bool:
        """Refuse a leave request, optionally attaching a reason."""
        # action_refuse accepts an optional reason via context or direct field
        try:
            self.call(
                'hr.leave', 'action_refuse',
                [[leave_id]],
                {'context': {'refuse_reason': reason}} if reason else {}
            )
        except OdooError:
            # Fallback: write reason then refuse
            if reason:
                self.call('hr.leave', 'write', [[leave_id], {'name': reason}])
            self.call('hr.leave', 'action_refuse', [[leave_id]])
        return True
