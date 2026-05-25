/* ============================================================
   LeavePortal — main.js
   Handles:
     - Sidebar toggle (desktop collapse + mobile drawer)
     - Leave balance fetch on apply form
     - Date validation on apply form
     - Refuse reason toggle on manager detail page
   ============================================================ */

(function () {
  'use strict';

  /* ----------------------------------------------------------
     Sidebar toggle
     ---------------------------------------------------------- */
  var sidebar      = document.getElementById('sidebar');
  var toggleBtn    = document.getElementById('sidebarToggle');
  var overlay      = null;

  function isMobile() {
    return window.innerWidth < 768;
  }

  function createOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', closeMobileSidebar);
    return overlay;
  }

  function openMobileSidebar() {
    if (!sidebar) return;
    sidebar.classList.add('mobile-open');
    createOverlay().classList.add('active');
  }

  function closeMobileSidebar() {
    if (!sidebar) return;
    sidebar.classList.remove('mobile-open');
    if (overlay) overlay.classList.remove('active');
  }

  function toggleDesktopSidebar() {
    if (!sidebar) return;
    sidebar.classList.toggle('collapsed');
    // Persist preference
    try {
      localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed') ? '1' : '0');
    } catch (e) { /* ignore */ }
  }

  // Restore desktop preference
  if (sidebar && !isMobile()) {
    try {
      if (localStorage.getItem('sidebarCollapsed') === '1') {
        sidebar.classList.add('collapsed');
      }
    } catch (e) { /* ignore */ }
  }

  if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
      if (isMobile()) {
        if (sidebar && sidebar.classList.contains('mobile-open')) {
          closeMobileSidebar();
        } else {
          openMobileSidebar();
        }
      } else {
        toggleDesktopSidebar();
      }
    });
  }

  // Close mobile sidebar on resize to desktop
  window.addEventListener('resize', function () {
    if (!isMobile()) {
      closeMobileSidebar();
    }
  });

  /* ----------------------------------------------------------
     Apply Leave Form — balance fetch & date validation
     (only runs on the apply leave page)
     ---------------------------------------------------------- */
  var applyForm      = document.getElementById('applyLeaveForm');

  if (applyForm) {
    var leaveTypeSelect  = document.getElementById('leave_type_id');
    var dateFromInput    = document.getElementById('date_from');
    var dateToInput      = document.getElementById('date_to');
    var balanceIndicator = document.getElementById('balanceIndicator');
    var balanceSpinner   = document.getElementById('balanceSpinner');
    var balanceText      = document.getElementById('balanceText');
    var durationPreview  = document.getElementById('durationPreview');
    var durationTextEl   = document.getElementById('durationText');
    var reasonTextarea   = document.getElementById('reason');
    var reasonCount      = document.getElementById('reasonCount');
    var dateToFeedback   = document.getElementById('dateToFeedback');
    var balanceTimer     = null;

    /* ---- Set today as min date ---- */
    var todayISO = new Date().toISOString().split('T')[0];
    if (dateFromInput) dateFromInput.min = todayISO;
    if (dateToInput)   dateToInput.min   = todayISO;

    /* ---- Leave balance fetch ---- */
    function fetchBalance(typeId) {
      if (!typeId || !balanceIndicator) return;

      balanceIndicator.classList.remove('d-none');
      if (balanceSpinner) balanceSpinner.classList.remove('d-none');
      if (balanceText)    balanceText.textContent = 'Loading…';

      clearTimeout(balanceTimer);
      balanceTimer = setTimeout(function () {
        fetch('/api/leave-balance?leave_type_id=' + encodeURIComponent(typeId))
          .then(function (res) { return res.json(); })
          .then(function (data) {
            if (balanceSpinner) balanceSpinner.classList.add('d-none');
            if (!balanceText) return;
            if (data.error) {
              balanceText.innerHTML =
                '<span class="text-danger"><i class="bi bi-exclamation-circle me-1"></i>' +
                escapeHtml(data.error) + '</span>';
            } else {
              var days = parseFloat(data.balance);
              var colorClass = days > 5 ? 'text-success' : days > 0 ? 'text-warning' : 'text-danger';
              var icon = days > 0 ? 'bi-calendar2-check' : 'bi-calendar2-x';
              balanceText.innerHTML =
                '<span class="' + colorClass + '">' +
                '<i class="bi ' + icon + ' me-1"></i>' +
                'Available balance: <strong>' + days.toFixed(1) + ' day' + (days !== 1 ? 's' : '') + '</strong>' +
                '</span>';
            }
          })
          .catch(function () {
            if (balanceSpinner) balanceSpinner.classList.add('d-none');
            if (balanceText)
              balanceText.innerHTML = '<span class="text-muted small">Balance unavailable.</span>';
          });
      }, 350);
    }

    if (leaveTypeSelect) {
      leaveTypeSelect.addEventListener('change', function () {
        fetchBalance(this.value);
      });
    }

    /* ---- Date range logic ---- */
    function calcWorkingDays(from, to) {
      var days = 0;
      var cur  = new Date(from);
      var end  = new Date(to);
      while (cur <= end) {
        var wd = cur.getDay();
        if (wd !== 0 && wd !== 6) days++;
        cur.setDate(cur.getDate() + 1);
      }
      return days;
    }

    function updateDuration() {
      if (!dateFromInput || !dateToInput || !durationPreview || !durationTextEl) return;

      var from = dateFromInput.value;
      var to   = dateToInput.value;

      if (!from || !to) {
        durationPreview.classList.add('d-none');
        return;
      }

      if (to < from) {
        durationPreview.classList.add('d-none');
        if (dateToInput.setCustomValidity)
          dateToInput.setCustomValidity('End date must be on or after start date.');
        if (dateToFeedback)
          dateToFeedback.textContent = 'End date must be on or after the start date.';
        return;
      }

      if (dateToInput.setCustomValidity) dateToInput.setCustomValidity('');
      if (dateToFeedback) dateToFeedback.textContent = 'Please select an end date.';

      var working = calcWorkingDays(from, to);
      durationPreview.classList.remove('d-none');
      durationTextEl.textContent =
        'Approximately ' + working + ' working day' + (working !== 1 ? 's' : '') +
        ' (' + from + ' to ' + to + ')';
    }

    if (dateFromInput) {
      dateFromInput.addEventListener('change', function () {
        if (dateToInput && dateToInput.value && dateToInput.value < this.value) {
          dateToInput.value = this.value;
        }
        if (dateToInput) dateToInput.min = this.value;
        updateDuration();
      });
    }

    if (dateToInput) {
      dateToInput.addEventListener('change', updateDuration);
    }

    /* ---- Reason counter ---- */
    if (reasonTextarea && reasonCount) {
      reasonTextarea.addEventListener('input', function () {
        reasonCount.textContent = this.value.length;
      });
    }

    /* ---- Bootstrap form validation ---- */
    applyForm.addEventListener('submit', function (e) {
      if (!applyForm.checkValidity()) {
        e.preventDefault();
        e.stopPropagation();
      }
      applyForm.classList.add('was-validated');
    });
  }

  /* ----------------------------------------------------------
     Manager — leave detail page (refuse toggle)
     (only runs on manager leave detail page)
     ---------------------------------------------------------- */
  var refuseToggleBtn = document.getElementById('refuseToggleBtn');
  var refuseSection   = document.getElementById('refuseSection');
  var cancelRefuseBtn = document.getElementById('cancelRefuseBtn');
  var approveForm     = document.getElementById('approveForm');
  var refuseForm      = document.getElementById('refuseForm');

  if (refuseToggleBtn && refuseSection) {
    refuseToggleBtn.addEventListener('click', function () {
      refuseSection.classList.remove('d-none');
      refuseToggleBtn.disabled = true;
      var refuseReason = document.getElementById('refuseReason');
      if (refuseReason) refuseReason.focus();
    });
  }

  if (cancelRefuseBtn && refuseSection && refuseToggleBtn) {
    cancelRefuseBtn.addEventListener('click', function () {
      refuseSection.classList.add('d-none');
      refuseToggleBtn.disabled = false;
      var refuseReason = document.getElementById('refuseReason');
      if (refuseReason) refuseReason.value = '';
    });
  }

  if (approveForm) {
    approveForm.addEventListener('submit', function () {
      var approveBtn = document.getElementById('approveBtn');
      if (approveBtn) approveBtn.disabled = true;
      if (refuseToggleBtn) refuseToggleBtn.disabled = true;
    });
  }

  if (refuseForm) {
    refuseForm.addEventListener('submit', function () {
      var confirmRefuseBtn = document.getElementById('confirmRefuseBtn');
      if (confirmRefuseBtn) confirmRefuseBtn.disabled = true;
      if (cancelRefuseBtn) cancelRefuseBtn.disabled = true;
    });
  }

  /* ----------------------------------------------------------
     Utilities
     ---------------------------------------------------------- */
  function escapeHtml(str) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(str));
    return d.innerHTML;
  }

})();
