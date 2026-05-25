"""
Flask application entry point for the Odoo Leave Management system.

All Odoo communication is done via OdooClient (XML-RPC).
No local database is used; Odoo is the single source of truth.
"""

from functools import wraps

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
    jsonify,
)

import config
from odoo_client import OdooClient, OdooError

app = Flask(__name__)
app.secret_key = config.SECRET_KEY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client() -> OdooClient:
    """Build an authenticated OdooClient from the current session."""
    client = OdooClient(
        url=session['url'],
        db=session['db'],
        username=session['username'],
        password=session['password'],
    )
    client.uid = session['uid']
    return client


def login_required(f):
    """Decorator — redirect to /login when no active session exists."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'uid' not in session:
            flash('Please sign in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def manager_required(f):
    """Decorator — redirect employees away from manager-only views."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_manager'):
            flash('Access denied: manager privileges required.', 'danger')
            return redirect(url_for('employee_dashboard'))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# PWA — service worker must be served from root scope
# ---------------------------------------------------------------------------

@app.route('/sw.js')
def service_worker():
    return send_from_directory(app.static_folder, 'sw.js',
                               mimetype='application/javascript')


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'uid' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        url = request.form.get('url', '').strip().rstrip('/')
        db = request.form.get('db', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not all([url, db, username, password]):
            flash('All fields are required.', 'danger')
            return render_template('login.html', url=url, db=db, username=username)

        client = OdooClient(url=url, db=db, username=username, password=password)
        try:
            uid = client.authenticate()
            employee = client.get_employee(uid)
            is_mgr = client.is_manager(uid)
        except OdooError as exc:
            flash(str(exc), 'danger')
            return render_template('login.html', url=url, db=db, username=username)

        session.clear()
        session['uid'] = uid
        session['url'] = url
        session['db'] = db
        session['username'] = username
        session['password'] = password
        session['employee_id'] = employee['id']
        session['employee_name'] = employee['name']
        session['is_manager'] = is_mgr

        flash(f'Welcome, {employee["name"]}!', 'success')
        return redirect(url_for('index'))

    # Pre-fill URL/DB from config defaults so the form is convenient
    return render_template(
        'login.html',
        url=config.ODOO_URL,
        db=config.ODOO_DB,
        username='',
    )


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been signed out.', 'info')
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# Index — smart redirect
# ---------------------------------------------------------------------------

@app.route('/')
@login_required
def index():
    if session.get('is_manager'):
        return redirect(url_for('manager_dashboard'))
    return redirect(url_for('employee_dashboard'))


# ---------------------------------------------------------------------------
# Employee routes
# ---------------------------------------------------------------------------

@app.route('/employee/dashboard')
@login_required
def employee_dashboard():
    client = _get_client()
    employee_id = session['employee_id']

    try:
        balances = client.get_all_leave_balances(employee_id)
        all_leaves = client.get_my_leaves(employee_id)
        recent_leaves = all_leaves[:5]
    except OdooError as exc:
        flash(f'Could not load dashboard data: {exc}', 'danger')
        balances, recent_leaves = [], []

    return render_template(
        'employee/dashboard.html',
        balances=balances,
        recent_leaves=recent_leaves,
    )


@app.route('/employee/apply', methods=['GET', 'POST'])
@login_required
def employee_apply():
    client = _get_client()
    employee_id = session['employee_id']

    if request.method == 'POST':
        leave_type_id = request.form.get('leave_type_id', type=int)
        date_from = request.form.get('date_from', '').strip()
        date_to = request.form.get('date_to', '').strip()
        reason = request.form.get('reason', '').strip()

        if not all([leave_type_id, date_from, date_to]):
            flash('Leave type, start date, and end date are required.', 'danger')
        elif date_to < date_from:
            flash('End date must be on or after start date.', 'danger')
        else:
            try:
                leave_id = client.create_leave(
                    employee_id=employee_id,
                    leave_type_id=leave_type_id,
                    date_from=date_from,
                    date_to=date_to,
                    reason=reason or 'Leave request',
                )
                client.confirm_leave(leave_id)
                flash('Your leave request has been submitted successfully.', 'success')
                return redirect(url_for('employee_history'))
            except OdooError as exc:
                flash(f'Failed to submit leave request: {exc}', 'danger')

    try:
        leave_types = client.get_leave_types()
    except OdooError as exc:
        flash(f'Could not load leave types: {exc}', 'danger')
        leave_types = []

    return render_template('employee/apply_leave.html', leave_types=leave_types)


@app.route('/employee/history')
@login_required
def employee_history():
    client = _get_client()
    employee_id = session['employee_id']

    try:
        leaves = client.get_my_leaves(employee_id)
    except OdooError as exc:
        flash(f'Could not load leave history: {exc}', 'danger')
        leaves = []

    return render_template('employee/leave_history.html', leaves=leaves)


# ---------------------------------------------------------------------------
# API endpoint — leave balance (used by apply_leave.html JS)
# ---------------------------------------------------------------------------

@app.route('/api/leave-balance')
@login_required
def api_leave_balance():
    leave_type_id = request.args.get('leave_type_id', type=int)
    if not leave_type_id:
        return jsonify({'error': 'leave_type_id is required'}), 400

    client = _get_client()
    employee_id = session['employee_id']

    try:
        balance = client.get_leave_balance(employee_id, leave_type_id)
        return jsonify({'balance': balance})
    except OdooError as exc:
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# Manager routes
# ---------------------------------------------------------------------------

@app.route('/manager/dashboard')
@login_required
@manager_required
def manager_dashboard():
    client = _get_client()
    manager_employee_id = session['employee_id']

    try:
        pending_leaves = client.get_pending_leaves_for_manager(manager_employee_id)
    except OdooError as exc:
        flash(f'Could not load pending requests: {exc}', 'danger')
        pending_leaves = []

    return render_template(
        'manager/dashboard.html',
        pending_leaves=pending_leaves,
    )


@app.route('/manager/leave/<int:leave_id>')
@login_required
@manager_required
def manager_leave_detail(leave_id):
    client = _get_client()

    try:
        leave = client.get_leave_by_id(leave_id)
    except OdooError as exc:
        flash(f'Could not load leave request: {exc}', 'danger')
        return redirect(url_for('manager_dashboard'))

    # Verify this leave belongs to a subordinate
    manager_employee_id = session['employee_id']
    try:
        subordinate_ids = [
            e['id']
            for e in client.get_employees_under_manager(manager_employee_id)
        ]
    except OdooError:
        subordinate_ids = []

    emp_id = leave.get('employee_id', {})
    if isinstance(emp_id, dict):
        emp_id = emp_id.get('id')
    if emp_id not in subordinate_ids:
        flash('You do not have permission to view this leave request.', 'danger')
        return redirect(url_for('manager_dashboard'))

    return render_template('manager/leave_detail.html', leave=leave)


@app.route('/manager/leave/<int:leave_id>/approve', methods=['POST'])
@login_required
@manager_required
def manager_approve_leave(leave_id):
    client = _get_client()

    try:
        client.approve_leave(leave_id)
        flash('Leave request approved successfully.', 'success')
    except OdooError as exc:
        flash(f'Could not approve leave request: {exc}', 'danger')

    return redirect(url_for('manager_dashboard'))


@app.route('/manager/leave/<int:leave_id>/refuse', methods=['POST'])
@login_required
@manager_required
def manager_refuse_leave(leave_id):
    client = _get_client()
    reason = request.form.get('reason', '').strip()

    try:
        client.refuse_leave(leave_id, reason=reason)
        flash('Leave request refused.', 'warning')
    except OdooError as exc:
        flash(f'Could not refuse leave request: {exc}', 'danger')

    return redirect(url_for('manager_dashboard'))


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
