(function () {
  'use strict';

  /* ---- Sidebar mobile toggle ---- */
  var sidebarToggle = document.getElementById('sidebarToggle');
  var sidebar       = document.getElementById('sidebar');

  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', function () {
      sidebar.classList.toggle('open');
    });

    document.addEventListener('click', function (e) {
      if (!sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    });
  }

  /* ---- Auto-dismiss alerts after 5 seconds ---- */
  var alerts = document.querySelectorAll('.alert.alert-success, .alert.alert-info');
  alerts.forEach(function (alert) {
    setTimeout(function () {
      var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });

  /* ---- Confirm before approve / refuse actions ---- */
  var approveBtn = document.getElementById('approveBtn');
  if (approveBtn) {
    approveBtn.closest('form').addEventListener('submit', function (e) {
      if (!confirm('Approve this leave request?')) {
        e.preventDefault();
      }
    });
  }

})();
