/* ==========================================================================
   Fase 3.D — Presupuesto: modal "Personalizar presentación".

   - Solo feedback: suma/pendiente/exceso de cantidades con enteros escalados
     (BigInt × 10^4), sin float. El backend vuelve a validar todo con Decimal.
   - No calcula dinero: P.U. y total llegan ya formateados desde el servidor.
   - Guarda la presentación COMPLETA en un POST (sin guardado parcial).
   ========================================================================== */
(function () {
  "use strict";

  const DEC = 4;
  const ESCALA = 10n ** BigInt(DEC);

  // "1912,125" | "1912.125" → BigInt escalado; null si no es válido.
  function parseCantidad(texto) {
    const t = String(texto || "").trim().replace(/\s/g, "");
    if (!t) return null;
    if (t.includes(",") && t.includes(".")) return null;
    const m = /^(\d+)(?:[.,](\d+))?$/.exec(t);
    if (!m) return null;
    const frac = m[2] || "";
    if (frac.length > DEC) return null;
    return BigInt(m[1]) * ESCALA + BigInt((frac + "0".repeat(DEC)).slice(0, DEC));
  }

  // BigInt escalado → "1.912,125" (mismo formato que el filtro cantidad_fmt).
  function fmtCantidad(n) {
    const neg = n < 0n;
    if (neg) n = -n;
    const ent = (n / ESCALA).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    const frac = (n % ESCALA).toString().padStart(DEC, "0").replace(/0+$/, "");
    return (neg ? "-" : "") + ent + (frac ? "," + frac : "");
  }

  function csrf(root) {
    const el = root.querySelector("input[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function init() {
    const modalEl = document.querySelector("[data-pr-modal]");
    const dataEl = document.getElementById("prItemsData");
    if (!modalEl || !dataEl || !window.bootstrap) return;

    const items = {};
    JSON.parse(dataEl.textContent).forEach(function (it) { items[it.apu_id] = it; });
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    const $ = function (sel) { return modalEl.querySelector(sel); };
    const $$ = function (sel) { return Array.from(modalEl.querySelectorAll(sel)); };
    const tpl = document.getElementById("prLineaTpl");
    const lista = $("[data-pr-lineas]");
    const check = $("[data-pr-check]");
    const btnGuardar = $("[data-pr-guardar]");
    const btnReset = $("[data-pr-restablecer]");

    let actual = null;      // ítem abierto
    let modo = "una";
    let guardando = false;

    function setModo(nuevo) {
      modo = nuevo;
      $$("[data-pr-modo]").forEach(function (b) {
        const on = b.dataset.prModo === modo;
        b.classList.toggle("active", on);
        b.setAttribute("aria-checked", on ? "true" : "false");
      });
      $("[data-pr-desglose]").hidden = modo !== "desglose";
      if (modo === "desglose" && !lista.children.length) {
        agregarLinea({ nombre: "", descripcion: "", cantidad: "" });
        agregarLinea({ nombre: "", descripcion: "", cantidad: "" });
      }
      actualizar();
    }

    function agregarLinea(datos) {
      const nodo = tpl.content.firstElementChild.cloneNode(true);
      nodo.querySelector("[data-campo=nombre]").value = datos.nombre || "";
      nodo.querySelector("[data-campo=descripcion]").value = datos.descripcion || "";
      nodo.querySelector("[data-campo=cantidad]").value = (datos.cantidad || "").replace(".", ",");
      nodo.querySelectorAll("[data-pr-unidad]").forEach(function (u) { u.textContent = actual.unidad; });
      lista.appendChild(nodo);
      renumerar();
      return nodo;
    }

    function renumerar() {
      const filas = Array.from(lista.children);
      filas.forEach(function (f, i) {
        f.querySelector("[data-pr-num]").textContent = i + 1;
        f.querySelector("[data-pr-up]").disabled = i === 0;
        f.querySelector("[data-pr-down]").disabled = i === filas.length - 1;
      });
    }

    function actualizar() {
      if (!actual) return;
      const eco = parseCantidad(actual.cantidad);
      let dist = 0n;
      let invalidas = false;
      Array.from(lista.children).forEach(function (f) {
        const inp = f.querySelector("[data-campo=cantidad]");
        const v = parseCantidad(inp.value);
        const mal = inp.value.trim() !== "" && (v === null || v <= 0n);
        inp.classList.toggle("is-invalid", mal);
        if (mal) invalidas = true;
        if (v !== null && v > 0n) dist += v;
      });
      const diff = eco - dist;
      $("[data-pr-check-eco]").textContent = fmtCantidad(eco);
      $("[data-pr-check-dist]").textContent = fmtCantidad(dist);
      $("[data-pr-check-diff-label]").textContent = diff < 0n ? "Exceso" : "Pendiente";
      $("[data-pr-check-diff]").textContent = fmtCantidad(diff < 0n ? -diff : diff);
      check.classList.toggle("is-ok", diff === 0n);
      check.classList.toggle("is-falta", diff > 0n);
      check.classList.toggle("is-exceso", diff < 0n);

      // Feedback: con desglose, Guardar solo si cuadra (el backend decide).
      btnGuardar.disabled = guardando || (modo === "desglose" && (diff !== 0n || invalidas || lista.children.length < 2));
    }

    function limpiarErrores() {
      $("[data-pr-errores]").hidden = true;
      $$("[data-pr-linea]").forEach(function (f) {
        f.classList.remove("is-invalid");
        const e = f.querySelector("[data-pr-linea-error]");
        e.hidden = true; e.textContent = "";
      });
    }

    function mostrarErrores(data) {
      const errores = (data && data.errores) || [(data && data.mensaje) || "No se pudo guardar."];
      const cont = $("[data-pr-errores-texto]");
      cont.innerHTML = "";
      const ul = document.createElement("ul");
      ul.className = "mb-0";
      errores.forEach(function (m) { const li = document.createElement("li"); li.textContent = m; ul.appendChild(li); });
      cont.appendChild(ul);
      $("[data-pr-errores]").hidden = false;
      const filas = Array.from(lista.children);
      Object.entries((data && data.lineas) || {}).forEach(function ([idx, msg]) {
        const f = filas[Number(idx)];
        if (!f) return;
        f.classList.add("is-invalid");
        const e = f.querySelector("[data-pr-linea-error]");
        e.textContent = msg; e.hidden = false;
      });
    }

    function abrir(apuId, btn) {
      actual = items[apuId];
      if (!actual) return;
      limpiarErrores();
      guardando = false;
      $("[data-pr-titulo]").textContent = actual.nombre_comercial || actual.nombre_original;
      $("[data-pr-origen-nombre]").textContent = actual.nombre_original;
      $("[data-pr-origen-cantidad]").textContent = fmtCantidad(parseCantidad(actual.cantidad));
      $("[data-pr-origen-pu]").textContent = btn.dataset.pu || "";
      $("[data-pr-origen-total]").textContent = btn.dataset.total || "";
      $$("[data-pr-unidad]").forEach(function (u) { u.textContent = actual.unidad; });

      const nombre = $("[data-pr-nombre]");
      const desc = $("[data-pr-descripcion]");
      nombre.value = actual.nombre_comercial;
      nombre.placeholder = actual.nombre_original;
      desc.value = actual.descripcion_comercial;
      desc.placeholder = actual.descripcion_original || "Sin descripción";

      lista.innerHTML = "";
      actual.lineas.forEach(agregarLinea);
      setModo(actual.lineas.length ? "desglose" : "una");

      btnReset.hidden = !actual.personalizado;
      btnReset.classList.remove("is-confirm");
      $("[data-pr-restablecer-texto]").textContent = "Restablecer original";
      modal.show();
    }

    function payload() {
      return {
        modo: modo,
        nombre_comercial: $("[data-pr-nombre]").value,
        descripcion_comercial: $("[data-pr-descripcion]").value,
        lineas: modo === "desglose" ? Array.from(lista.children).map(function (f) {
          return {
            nombre: f.querySelector("[data-campo=nombre]").value,
            descripcion: f.querySelector("[data-campo=descripcion]").value,
            cantidad: f.querySelector("[data-campo=cantidad]").value,
          };
        }) : [],
      };
    }

    function enviar(url, cuerpo) {
      guardando = true;
      btnGuardar.disabled = true;
      return fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf(modalEl),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify(cuerpo || {}),
        credentials: "same-origin",
      }).then(function (r) {
        return r.json().catch(function () { return { ok: false, mensaje: "Respuesta inesperada del servidor." }; });
      }).then(function (data) {
        if (data.ok) {
          window.location.hash = "pr-item-" + actual.apu_id;
          window.location.reload();
          return;
        }
        guardando = false;
        mostrarErrores(data);
        actualizar();
      }).catch(function () {
        guardando = false;
        mostrarErrores({ mensaje: "No se pudo conectar con el servidor." });
        actualizar();
      });
    }

    // ── Eventos ──────────────────────────────────────────────────────────
    document.querySelectorAll("[data-pr-personalizar]").forEach(function (btn) {
      btn.addEventListener("click", function () { abrir(Number(btn.dataset.prPersonalizar), btn); });
    });
    $$("[data-pr-modo]").forEach(function (b) {
      b.addEventListener("click", function () { setModo(b.dataset.prModo); });
    });
    $("[data-pr-add]").addEventListener("click", function () {
      agregarLinea({ nombre: "", descripcion: "", cantidad: "" }).querySelector("[data-campo=nombre]").focus();
      actualizar();
    });
    lista.addEventListener("input", actualizar);
    lista.addEventListener("click", function (ev) {
      const fila = ev.target.closest("[data-pr-linea]");
      if (!fila) return;
      if (ev.target.closest("[data-pr-up]") && fila.previousElementSibling) {
        lista.insertBefore(fila, fila.previousElementSibling);
      } else if (ev.target.closest("[data-pr-down]") && fila.nextElementSibling) {
        lista.insertBefore(fila.nextElementSibling, fila);
      } else if (ev.target.closest("[data-pr-del]")) {
        fila.remove();
      } else {
        return;
      }
      renumerar();
      actualizar();
    });
    btnGuardar.addEventListener("click", function () {
      if (!actual || guardando) return;
      limpiarErrores();
      enviar(modalEl.dataset.urlGuardar.replace(/\/0\/$/, "/" + actual.apu_id + "/"), payload());
    });
    btnReset.addEventListener("click", function () {
      if (!actual || guardando) return;
      if (!btnReset.classList.contains("is-confirm")) {
        btnReset.classList.add("is-confirm");
        $("[data-pr-restablecer-texto]").textContent = "¿Restablecer? Se perderá la personalización";
        return;
      }
      enviar(modalEl.dataset.urlRestablecer.replace(/\/0\/restablecer\/$/, "/" + actual.apu_id + "/restablecer/"));
    });

    // Volver al ítem tras recargar
    if (window.location.hash.indexOf("#pr-item-") === 0) {
      const el = document.querySelector(window.location.hash);
      if (el) el.scrollIntoView({ block: "center" });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
