/* ============================================================
   Imperandina — Modal & UI helpers
   ============================================================ */

(function () {
  "use strict";

  /* ── DELETE MODAL ── */
  const deleteModal = document.getElementById("deleteModal");
  if (deleteModal) {
    deleteModal.addEventListener("show.bs.modal", function (e) {
      const btn = e.relatedTarget;
      if (!btn) return;
      const name = btn.dataset.deleteName || "este elemento";
      const url  = btn.dataset.deleteUrl  || "#";
      deleteModal.querySelector("#deleteItemName").textContent = name;
      deleteModal.querySelector("#deleteForm").action = url;
    });
  }

  /* ── GENERIC EDIT MODAL (populated from data-field-* attrs) ──
     Usage on button:
       data-bs-toggle="modal"
       data-bs-target="#editSistemaModal"
       data-edit-url="/sistemas/1/editar/"
       data-field-codigo="PG"
       data-field-nombre="PowerGrip"
       ...
  ── */
  document.querySelectorAll("[data-edit-url]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const modalId = btn.dataset.bsTarget;
      if (!modalId) return;
      const modal = document.querySelector(modalId);
      if (!modal) return;

      const form = modal.querySelector("form");
      if (form) form.action = btn.dataset.editUrl;

      // Populate each field-* attribute
      Object.keys(btn.dataset).forEach(function (key) {
        if (!key.startsWith("field")) return;
        // convert camelCase fieldRazonSocial → razon_social
        const fieldName = camelToSnake(key.slice(5));
        const el = form && form.querySelector('[name="' + fieldName + '"]');
        if (!el) return;
        if (el.type === "checkbox") {
          el.checked = btn.dataset[key] === "True" || btn.dataset[key] === "true";
        } else if (el.tagName === "SELECT") {
          el.value = btn.dataset[key];
        } else {
          el.value = btn.dataset[key] || "";
        }
      });
    });
  });

  /* ── SUBSISTEMA FILTER (ingenieria/sistema_list) ── */
  const filtroSubsistema = document.getElementById("filtroSistema");
  if (filtroSubsistema) {
    filtroSubsistema.addEventListener("change", function () {
      const val = this.value;
      document.querySelectorAll("[data-sistema-id]").forEach(function (row) {
        if (!val || row.dataset.sistemaId === val) {
          row.style.display = "";
        } else {
          row.style.display = "none";
        }
      });
    });
  }

  /* ── AUTO DISMISS MESSAGES ── */
  setTimeout(function () {
    document.querySelectorAll(".msg-bar[data-auto-dismiss]").forEach(function (el) {
      el.style.transition = "opacity 0.5s";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 500);
    });
  }, 3500);

  /* ── HELPER: camelCase → snake_case ── */
  function camelToSnake(str) {
    return str
      .replace(/([A-Z])/g, function (m) { return "_" + m.toLowerCase(); })
      .replace(/^_/, "");
  }

  /* ── INLINE QTY SAVE (despiece) ── */
  document.querySelectorAll(".qty-ajuste-field").forEach(function (input) {
    input.addEventListener("change", function () {
      const pk   = input.dataset.pk;
      const url  = input.dataset.url;
      const val  = input.value;
      const csrf = document.querySelector("[name=csrfmiddlewaretoken]");
      if (!url || !csrf) return;
      const fd = new FormData();
      fd.append("csrfmiddlewaretoken", csrf.value);
      fd.append("cantidad_ajustada", val);
      fd.append("_inline", "1");
      fetch(url, { method: "POST", body: fd })
        .then(function (r) {
          input.classList.toggle("border-success", r.ok);
          input.classList.toggle("border-danger", !r.ok);
          setTimeout(function () {
            input.classList.remove("border-success", "border-danger");
          }, 2000);
        })
        .catch(function () { input.classList.add("border-danger"); });
    });
  });

})();
