/* ============================================================
   sidebar.js — Toggle de visibilidad del menú lateral
   ============================================================ */
(function () {
  "use strict";

  var STORAGE_KEY = "sidebarCollapsed";

  var body    = document.body;
  var sidebar = document.querySelector(".sidebar");
  var trigger = document.getElementById("sidebarToggle");

  if (!sidebar || !trigger) return;

  /* ── Restaurar estado guardado ── */
  if (localStorage.getItem(STORAGE_KEY) === "1") {
    body.classList.add("sidebar-collapsed");
  }

  /* ── Toggle al hacer clic ── */
  trigger.addEventListener("click", function () {
    var collapsed = body.classList.toggle("sidebar-collapsed");
    localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    trigger.setAttribute("aria-expanded", !collapsed);
  });

})();
