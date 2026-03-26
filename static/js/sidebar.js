/* ============================================================
   sidebar.js — Menú flotante (overlay)
   ============================================================ */
(function () {
  "use strict";

  var body     = document.body;
  var trigger  = document.getElementById("sidebarToggle");
  var closeBtn = document.getElementById("sidebarClose");
  var backdrop = document.getElementById("sidebarBackdrop");
  var sidebar  = document.getElementById("appSidebar");

  if (!trigger) return;

  function openSidebar() {
    body.classList.add("sidebar-open");
    trigger.setAttribute("aria-expanded", "true");
  }

  function closeSidebar() {
    body.classList.remove("sidebar-open");
    trigger.setAttribute("aria-expanded", "false");
  }

  /* Botón hamburguesa — abre/cierra */
  trigger.addEventListener("click", function () {
    if (body.classList.contains("sidebar-open")) {
      closeSidebar();
    } else {
      openSidebar();
    }
  });

  /* Botón ✕ dentro del sidebar — siempre cierra */
  if (closeBtn) {
    closeBtn.addEventListener("click", closeSidebar);
  }

  /* Clic en el backdrop cierra */
  if (backdrop) {
    backdrop.addEventListener("click", closeSidebar);
  }

  /* Escape cierra */
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeSidebar();
  });

  /* Navegar a un enlace cierra el overlay */
  if (sidebar) {
    sidebar.querySelectorAll("a.nav-item").forEach(function (link) {
      link.addEventListener("click", closeSidebar);
    });
  }

})();
