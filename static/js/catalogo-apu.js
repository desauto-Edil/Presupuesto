/* ============================================================
   catalogo-apu.js — Catálogo APU: filtros, formulario de ítem y
   constructor de paquetes (Fase 3.A).

   Los valores económicos (valor diario, aporte, total) SIEMPRE vienen del
   backend (apps.presupuestos.economia vía endpoints de previsualización).
   Este archivo no multiplica ni divide importes.
   ============================================================ */
(function () {
  "use strict";

  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments, self = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  }

  function norm(s) {
    return (s || "").toString().toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  function esc(s) {
    return (s == null ? "" : String(s)).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ══════════════════════════════════════════════════════════
     1. Catálogo: búsqueda y filtros (cliente)
     ══════════════════════════════════════════════════════════ */
  function initCatalogo(root) {
    var q = root.querySelector("#capuQ");
    var searchWrap = root.querySelector("[data-capu-search-wrap]");
    var segBtns = root.querySelectorAll("[data-capu-tipo]");
    var catSel = root.querySelector("#capuCat");
    var estSel = root.querySelector("#capuEstado");
    var filterBtn = root.querySelector(".capu-filter-btn");
    var filterCount = root.querySelector("[data-capu-filter-count]");
    var scopes = root.querySelectorAll("[data-capu-scope]");
    var tipo = "";

    scopes.forEach(function (sc) {
      sc.querySelectorAll("[data-capu-row]").forEach(function (r) {
        r._search = norm(r.dataset.search);
        r._cats = (r.dataset.cats || "").split(",").filter(Boolean);
      });
    });

    function syncCategorias() {
      if (!catSel) return;
      Array.prototype.forEach.call(catSel.options, function (o) {
        if (!o.value) return;
        o.hidden = !!tipo && o.dataset.tipo !== tipo;
      });
      var sel = catSel.options[catSel.selectedIndex];
      if (sel && sel.hidden) catSel.value = "";
    }

    function apply() {
      var term = norm(q ? q.value.trim() : "");
      var cat = catSel ? catSel.value : "";
      var est = estSel ? estSel.value : "";
      if (searchWrap) searchWrap.classList.toggle("has-value", !!term);
      var nFiltros = (cat ? 1 : 0) + (est ? 1 : 0);
      if (filterBtn) filterBtn.classList.toggle("has-filters", nFiltros > 0);
      if (filterCount) filterCount.textContent = nFiltros || "";

      scopes.forEach(function (sc) {
        var rows = sc.querySelectorAll("[data-capu-row]");
        var visibles = 0;
        rows.forEach(function (r) {
          var ok = (!term || r._search.indexOf(term) !== -1) &&
                   (!tipo || r.dataset.tipo === tipo) &&
                   (!cat || r._cats.indexOf(cat) !== -1) &&
                   (!est || r.dataset.estado === est);
          r.hidden = !ok;
          if (ok) visibles++;
        });
        var badge = sc.querySelector("[data-capu-visible]");
        if (badge) badge.textContent = (visibles === rows.length) ? rows.length : (visibles + " de " + rows.length);
        var empty = sc.querySelector("[data-capu-noresults]");
        if (empty) empty.hidden = !(rows.length && !visibles);
        var table = sc.querySelector(".capu-table-scroll");
        if (table) table.hidden = rows.length > 0 && !visibles;
      });
    }

    segBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        segBtns.forEach(function (x) { x.classList.toggle("active", x === b); x.setAttribute("aria-selected", x === b); });
        tipo = b.dataset.capuTipo || "";
        syncCategorias();
        apply();
      });
    });
    if (q) {
      q.addEventListener("input", debounce(apply, 80));
      q.addEventListener("keydown", function (e) { if (e.key === "Escape") { q.value = ""; apply(); } });
    }
    [catSel, estSel].forEach(function (s) { if (s) s.addEventListener("change", apply); });
    root.querySelectorAll("[data-capu-clear]").forEach(function (b) {
      b.addEventListener("click", function () { q.value = ""; apply(); q.focus(); });
    });
    root.querySelectorAll("[data-capu-reset]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (q) q.value = "";
        if (catSel) catSel.value = "";
        if (estSel) estSel.value = "";
        segBtns.forEach(function (x, i) { x.classList.toggle("active", i === 0); });
        tipo = "";
        syncCategorias();
        apply();
      });
    });
    // Atajo "/" para buscar
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && q && document.activeElement && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
        e.preventDefault(); q.focus();
      }
    });
    apply();
  }

  /* ══════════════════════════════════════════════════════════
     2. Formulario de ítem: previsualización del valor diario
     ══════════════════════════════════════════════════════════ */
  function initItemForm(root) {
    var url = root.dataset.previewUrl;
    var vb = root.querySelector("#id_valor_base");
    var vida = root.querySelector("#id_vida_util_dias");
    var box = root.querySelector("[data-capu-calc]");
    var out = root.querySelector("[data-capu-calc-value]");
    if (!url || !vb || !vida || !box || !out) return;
    var seq = 0;

    var refresh = debounce(function () {
      var my = ++seq;
      box.classList.add("is-loading");
      var qs = "?valor_base=" + encodeURIComponent(vb.value) + "&vida_util_dias=" + encodeURIComponent(vida.value);
      fetch(url + qs, { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (my !== seq) return;
          if (d.calculable) {
            out.classList.remove("is-na");
            out.innerHTML = esc(d.valor_diario_fmt) + " <small>/ día</small>";
          } else {
            out.classList.add("is-na");
            out.textContent = d.motivo === "pendiente"
              ? "No disponible · vida útil pendiente"
              : "No disponible · revisa los valores";
          }
        })
        .catch(function () {})
        .finally(function () { if (my === seq) box.classList.remove("is-loading"); });
    }, 220);

    vb.addEventListener("input", refresh);
    vida.addEventListener("input", refresh);
    refresh();  // alinea el valor mostrado con los datos del formulario (p. ej. tras un error)
  }

  /* ══════════════════════════════════════════════════════════
     3. Constructor de paquetes
     ══════════════════════════════════════════════════════════ */
  function initBuilder(root) {
    var ITEMS = JSON.parse(document.getElementById("capu-items").textContent);
    var filas = JSON.parse(document.getElementById("capu-filas").textContent) || [];
    var byId = {};
    ITEMS.forEach(function (it) { byId[it.id] = it; });

    var form = root.querySelector("form");
    var tipoSel = root.querySelector("#id_tipo_apu");
    var hidden = root.querySelector("input[name=componentes]");
    var list = root.querySelector("[data-capu-comp-list]");
    var head = root.querySelector("[data-capu-comp-head]");
    var addBtn = root.querySelector("[data-capu-add]");
    var addHint = root.querySelector("[data-capu-add-hint]");
    var summary = root.querySelector("[data-capu-summary]");
    var totalEl = root.querySelector("[data-capu-total]");
    var nEl = root.querySelector("[data-capu-n]");
    var pendEl = root.querySelector("[data-capu-pend]");
    var pendNote = root.querySelector("[data-capu-pend-note]");
    var previewUrl = root.dataset.previewUrl;
    var csrf = (form.querySelector("[name=csrfmiddlewaretoken]") || {}).value;
    var tipoLabels = {};
    Array.prototype.forEach.call(tipoSel.options, function (o) { tipoLabels[o.value] = o.textContent; });

    var modalEl = document.getElementById("capuPicker");
    var modal = window.bootstrap ? new bootstrap.Modal(modalEl) : null;
    var pickQ = modalEl.querySelector("#capuPickQ");
    var pickList = modalEl.querySelector("[data-capu-pick-list]");
    var pickTitle = modalEl.querySelector("[data-capu-pick-tipo]");

    var ultimo = null;        // última previsualización del backend
    var nuevo = null;         // id recién agregado (para resaltar)
    var seq = 0;

    function tipo() { return tipoSel.value; }

    /* ── Render de componentes ── */
    function render() {
      list.innerHTML = "";
      head.hidden = !filas.length;
      if (!filas.length) {
        list.innerHTML =
          '<div class="capu-comp-empty">' +
          '<div class="capu-empty__icon"><i class="bi bi-diagram-3"></i></div>' +
          '<div class="capu-empty__title" style="font-size:14px;">Sin componentes</div>' +
          '<p class="capu-empty__text" style="margin-bottom:0;">' +
          (tipo() ? "Agrega ítems existentes del catálogo y define su cantidad."
                  : "Elige primero el Tipo APU del paquete para ver los ítems compatibles.") +
          "</p></div>";
      }
      var prev = ultimo && ultimo.filas ? ultimo.filas : [];
      filas.forEach(function (f, idx) {
        var it = byId[f.item] || { nombre: "Ítem #" + f.item, categoria: "", codigo: "", calculable: false };
        var p = prev[idx] && String(prev[idx].item) === String(f.item) ? prev[idx] : null;
        var row = document.createElement("div");
        row.className = "capu-comp" + (it.calculable ? "" : " is-pending") + (nuevo === f.item ? " is-new" : "");
        row.dataset.idx = idx;
        row.innerHTML =
          '<div class="capu-comp__order">' +
            '<button type="button" data-move="-1" aria-label="Subir"' + (idx === 0 ? " disabled" : "") + '><i class="bi bi-chevron-up"></i></button>' +
            '<button type="button" data-move="1" aria-label="Bajar"' + (idx === filas.length - 1 ? " disabled" : "") + '><i class="bi bi-chevron-down"></i></button>' +
          "</div>" +
          '<div class="capu-comp__main" style="min-width:0;">' +
            '<div class="capu-comp__name" title="' + esc(it.nombre) + '">' + esc(it.nombre) + "</div>" +
            '<div class="capu-comp__sub">' +
              (it.codigo ? '<span class="capu-code">' + esc(it.codigo) + "</span><span>·</span>" : "") +
              "<span>" + esc(it.categoria) + "</span>" +
              (it.activo === false ? '<span class="capu-state capu-state--off">Inactivo</span>' : "") +
            "</div>" +
          "</div>" +
          '<div class="capu-comp__vd"><span class="capu-comp__label">Valor diario</span>' +
            (it.calculable ? "<span>" + esc(it.valor_diario_fmt) + "</span>"
                           : '<span class="capu-na" title="El ítem no tiene vida útil configurada">Pendiente</span>') +
          "</div>" +
          '<div class="capu-comp__op">×</div>' +
          '<div class="capu-comp__qty"><span class="capu-comp__label">Cantidad</span>' +
            '<input type="text" inputmode="decimal" value="' + esc(f.cantidad) + '" aria-label="Cantidad de ' + esc(it.nombre) + '"></div>' +
          '<div class="capu-comp__op">=</div>' +
          '<div class="capu-comp__aporte"><span class="capu-comp__label">Aporte</span><span data-aporte>' +
            (p && p.aporte_fmt ? esc(p.aporte_fmt) : (it.calculable ? "…" : '<span class="capu-muted" style="font-weight:600;">No disponible</span>')) +
          "</span></div>" +
          '<div class="capu-comp__del"><button type="button" class="capu-icon-btn danger" data-remove aria-label="Quitar ' + esc(it.nombre) + '"><i class="bi bi-x-lg"></i></button></div>' +
          (p && p.error ? '<div class="capu-comp__err">' + esc(p.error) + "</div>" : "");
        if (p && p.error) row.querySelector("input").classList.add("is-invalid");
        list.appendChild(row);
      });
      nuevo = null;
      syncAdd();
      syncSummary();
    }

    function syncAdd() {
      var t = tipo();
      var compatibles = ITEMS.filter(function (it) { return it.tipo_apu === t && it.activo; });
      addBtn.disabled = !t;
      if (addHint) {
        addHint.hidden = !(t && !compatibles.length);
      }
    }

    function syncSummary() {
      var pend = filas.filter(function (f) { var it = byId[f.item]; return !it || !it.calculable; }).length;
      nEl.textContent = filas.length;
      pendEl.textContent = pend;
      pendEl.parentElement.hidden = !pend;
      pendNote.hidden = !pend;
      if (!filas.length) {
        totalEl.classList.add("is-na");
        totalEl.textContent = "Sin componentes";
      } else if (ultimo && ultimo.calculable && ultimo.total_fmt) {
        totalEl.classList.remove("is-na");
        totalEl.innerHTML = esc(ultimo.total_fmt) + " <small>/ día</small>";
      } else if (pend) {
        totalEl.classList.add("is-na");
        totalEl.textContent = "No disponible";
      } else if (ultimo && ultimo.error) {
        totalEl.classList.add("is-na");
        totalEl.textContent = "No se pudo calcular";
      } else if (ultimo && !ultimo.calculable) {
        totalEl.classList.add("is-na");
        totalEl.textContent = "Revisa las cantidades";
      } else {
        totalEl.classList.add("is-na");
        totalEl.textContent = "Calculando…";
      }
    }

    /* ── Previsualización en backend ── */
    var preview = debounce(function () {
      var my = ++seq;
      if (!filas.length) { ultimo = null; syncSummary(); return; }
      summary.classList.add("is-loading");
      list.querySelectorAll("[data-aporte]").forEach(function (a) { a.style.opacity = ".45"; });
      fetch(previewUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ componentes: filas })
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (my !== seq) return;
          ultimo = d;
          (d.filas || []).forEach(function (p, idx) {
            var row = list.querySelector('.capu-comp[data-idx="' + idx + '"]');
            if (!row) return;
            var a = row.querySelector("[data-aporte]");
            a.style.opacity = "";
            var it = byId[filas[idx] && filas[idx].item] || {};
            a.innerHTML = p.aporte_fmt ? esc(p.aporte_fmt)
              : '<span class="capu-muted" style="font-weight:600;">' + (it.calculable ? "—" : "No disponible") + "</span>";
            var inp = row.querySelector("input");
            inp.classList.toggle("is-invalid", !!p.error);
            var err = row.querySelector(".capu-comp__err");
            if (p.error) {
              if (!err) { err = document.createElement("div"); err.className = "capu-comp__err"; row.appendChild(err); }
              err.textContent = p.error;
            } else if (err) { err.remove(); }
          });
          syncSummary();
        })
        .catch(function () {
          if (my !== seq) return;
          ultimo = { error: true };
          list.querySelectorAll("[data-aporte]").forEach(function (a) { a.style.opacity = ""; a.textContent = "—"; });
          syncSummary();
        })
        .finally(function () { if (my === seq) summary.classList.remove("is-loading"); });
    }, 200);

    /* ── Eventos de la lista ── */
    list.addEventListener("input", function (e) {
      if (e.target.tagName !== "INPUT") return;
      var idx = +e.target.closest(".capu-comp").dataset.idx;
      filas[idx].cantidad = e.target.value;
      preview();
    });
    list.addEventListener("click", function (e) {
      var row = e.target.closest(".capu-comp");
      if (!row) return;
      var idx = +row.dataset.idx;
      var mv = e.target.closest("[data-move]");
      if (mv) {
        var to = idx + (+mv.dataset.move);
        if (to < 0 || to >= filas.length) return;
        var tmp = filas[idx]; filas[idx] = filas[to]; filas[to] = tmp;
        if (ultimo && ultimo.filas) { var t2 = ultimo.filas[idx]; ultimo.filas[idx] = ultimo.filas[to]; ultimo.filas[to] = t2; }
        render();
        var btn = list.querySelector('.capu-comp[data-idx="' + to + '"] [data-move="' + mv.dataset.move + '"]');
        if (btn && !btn.disabled) btn.focus();
        return;
      }
      if (e.target.closest("[data-remove]")) {
        filas.splice(idx, 1);
        if (ultimo && ultimo.filas) ultimo.filas.splice(idx, 1);
        render();
        preview();
      }
    });

    /* ── Cambio de Tipo APU ── */
    var tipoPrevio = tipo();
    tipoSel.addEventListener("change", function () {
      if (filas.length && tipo() !== tipoPrevio) {
        var ok = window.confirm(
          "El paquete solo admite ítems de un Tipo APU. Al cambiar el tipo se quitarán los " +
          filas.length + " componente(s) actuales. ¿Continuar?");
        if (!ok) { tipoSel.value = tipoPrevio; return; }
        filas = []; ultimo = null;
      }
      tipoPrevio = tipo();
      render();
    });

    /* ── Selector de ítems ── */
    function renderPicker() {
      var t = tipo();
      var term = norm(pickQ.value.trim());
      var enPaquete = {};
      filas.forEach(function (f) { enPaquete[f.item] = true; });
      pickTitle.textContent = tipoLabels[t] || "";
      var candidatos = ITEMS.filter(function (it) { return it.tipo_apu === t && (it.activo || enPaquete[it.id]); });
      if (!candidatos.length) {
        pickList.innerHTML =
          '<div class="capu-empty" style="border:none;">' +
          '<div class="capu-empty__icon"><i class="bi bi-box"></i></div>' +
          '<div class="capu-empty__title">No hay ítems de este tipo</div>' +
          '<p class="capu-empty__text">Un paquete solo puede usar ítems existentes y compatibles. ' +
          "Agrega primero un ítem de " + esc(tipoLabels[t] || "este tipo") + " al catálogo.</p>" +
          '<a class="btn btn-outline-primary btn-sm" href="' + esc(root.dataset.itemCreateUrl) + '" target="_blank" rel="noopener">' +
          '<i class="bi bi-plus-lg"></i> Agregar ítem</a></div>';
        return;
      }
      var vis = candidatos.filter(function (it) {
        return !term || norm(it.nombre + " " + it.codigo + " " + it.categoria).indexOf(term) !== -1;
      });
      if (!vis.length) {
        pickList.innerHTML =
          '<div class="capu-empty capu-empty--search" style="margin:8px;">' +
          '<div class="capu-empty__icon"><i class="bi bi-search"></i></div>' +
          '<div class="capu-empty__title">Sin resultados</div>' +
          '<p class="capu-empty__text" style="margin-bottom:0;">Ningún ítem compatible coincide con «' + esc(pickQ.value) + "».</p></div>";
        return;
      }
      var html = "", cat = null;
      vis.forEach(function (it) {
        if (it.categoria !== cat) { cat = it.categoria; html += '<div class="capu-pick-group">' + esc(cat) + "</div>"; }
        var ya = !!enPaquete[it.id];
        html +=
          '<button type="button" class="capu-pick" data-pick="' + it.id + '"' + (ya ? " disabled" : "") + ">" +
            "<span><div class=\"capu-pick__name\">" + esc(it.nombre) + "</div>" +
            '<div class="capu-pick__sub">' + (it.codigo ? '<span class="capu-code">' + esc(it.codigo) + "</span><span>·</span>" : "") + "<span>" + esc(it.unidad) + "</span>" +
            (ya ? "<span>· Ya está en el paquete</span>" : "") + "</div></span>" +
            '<span class="capu-pick__vd">' + (it.calculable ? esc(it.valor_diario_fmt) + " <small>/ día</small>"
              : '<span class="capu-na">Pendiente</span>') + "</span>" +
            '<span class="capu-pick__add"><i class="bi bi-' + (ya ? "check-lg" : "plus-lg") + '"></i></span>' +
          "</button>";
      });
      pickList.innerHTML = html;
    }

    pickList.addEventListener("click", function (e) {
      var b = e.target.closest("[data-pick]");
      if (!b || b.disabled) return;
      var id = +b.dataset.pick;
      if (filas.some(function (f) { return +f.item === id; })) return;
      filas.push({ item: id, cantidad: "1" });
      nuevo = id;
      render();
      preview();
      renderPicker();
      var again = pickList.querySelector('[data-pick="' + id + '"]');
      if (again) again.classList.add("is-added");
    });
    pickQ.addEventListener("input", debounce(renderPicker, 60));
    addBtn.addEventListener("click", function () {
      if (!tipo()) { tipoSel.focus(); return; }
      pickQ.value = "";
      renderPicker();
      if (modal) modal.show();
    });
    modalEl.addEventListener("shown.bs.modal", function () { pickQ.focus(); });

    /* ── Envío ── */
    form.addEventListener("submit", function (e) {
      var invalida = list.querySelector("input.is-invalid");
      if (invalida) {
        e.preventDefault();
        invalida.focus();
        return;
      }
      hidden.value = JSON.stringify(filas.map(function (f) { return { item: +f.item, cantidad: String(f.cantidad).trim() }; }));
      var btn = form.querySelector("[type=submit]");
      if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando…'; }
    });

    render();
    preview();
  }

  /* ══════════════════════════════════════════════════════════
     4. Subsistema: paquetes APU por TipoAPU (Fase 3.B)
     Toda validación está en backend; aquí solo se orquesta la UI.
     ══════════════════════════════════════════════════════════ */
  function initSubsistemaPaquetes(root) {
    var urls = {
      disponibles: root.dataset.urlDisponibles,
      agregar: root.dataset.urlAgregar,
      quitar: root.dataset.urlQuitar,
      mover: root.dataset.urlMover,
      crear: root.dataset.urlCrear
    };
    var csrfEl = document.querySelector("#formSubsistema [name=csrfmiddlewaretoken]") ||
                 document.querySelector("[name=csrfmiddlewaretoken]");
    var csrf = csrfEl ? csrfEl.value : "";
    var toast = root.querySelector("[data-capu-toast]");
    var resumen = root.querySelector("[data-capu-cfg-resumen]");

    // Los modales viven dentro del <form> principal: se mueven al <body> para
    // evitar envíos accidentales (Enter) y problemas de apilamiento.
    var picker = document.getElementById("capuPaquetePicker");
    var confirmQuitar = document.getElementById("capuQuitarConfirm");
    [picker, confirmQuitar].forEach(function (m) { if (m && m.parentElement !== document.body) document.body.appendChild(m); });
    var pickerModal = window.bootstrap ? bootstrap.Modal.getOrCreateInstance(picker) : null;
    var quitarModal = window.bootstrap ? bootstrap.Modal.getOrCreateInstance(confirmQuitar) : null;
    var pickQ = picker.querySelector("[data-capu-pick-q]");
    var pickList = picker.querySelector("[data-capu-pick-list]");
    var pickTipo = picker.querySelector("[data-capu-pick-tipo]");
    var pickConfirm = picker.querySelector("[data-capu-pick-confirm]");
    var crearLink = picker.querySelector("[data-capu-crear]");

    var tipoActual = null, disponibles = [], pendienteAgregar = null, pendienteQuitar = null;
    var toastTimer;

    function bloque(tipo) { return root.querySelector('[data-capu-cfg-tipo="' + tipo + '"]'); }

    function aviso(msg, nivel) {
      if (!toast || !msg) return;
      toast.className = "capu-cfg-toast msg-bar msg-" + (nivel || "success");
      toast.textContent = msg;
      toast.hidden = false;
      clearTimeout(toastTimer);
      toastTimer = setTimeout(function () { toast.hidden = true; }, 6000);
    }

    function post(url, datos) {
      var fd = new FormData();
      Object.keys(datos).forEach(function (k) { fd.append(k, datos[k]); });
      return fetch(url, {
        method: "POST", body: fd, credentials: "same-origin",
        headers: { "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" }
      }).then(function (r) {
        return r.json().catch(function () { return { ok: false, mensaje: "No se pudo completar la operación." }; });
      });
    }

    function aplicar(d, resaltarPaquete) {
      if (d.html_tipo) {
        var viejo = bloque(d.tipo);
        if (viejo) {
          var tmp = document.createElement("div");
          tmp.innerHTML = d.html_tipo.trim();
          var nuevo = tmp.firstElementChild;
          viejo.replaceWith(nuevo);
          if (resaltarPaquete) {
            var card = nuevo.querySelector('[data-paquete="' + resaltarPaquete + '"]');
            if (card) card.classList.add("is-new");
          } else {
            nuevo.classList.add("is-updated");
          }
        }
      }
      if (d.html_resumen && resumen) resumen.innerHTML = d.html_resumen;
      aviso(d.mensaje, d.ok === false ? "error" : "success");
    }

    function urlCon(base, id) { return base.replace(/\/0\/(quitar|mover)\/$/, "/" + id + "/$1/"); }

    /* ── Selector ── */
    function renderPicker() {
      var term = norm(pickQ.value.trim());
      var b = bloque(tipoActual);
      var label = b ? b.dataset.label : "";
      if (!disponibles.length) {
        pickList.innerHTML =
          '<div class="capu-empty" style="border:none;">' +
          '<div class="capu-empty__icon"><i class="bi bi-stack"></i></div>' +
          '<div class="capu-empty__title">No hay paquetes de ' + esc(label) + "</div>" +
          '<p class="capu-empty__text">Los paquetes se crean en el Catálogo APU agrupando ítems existentes. ' +
          "Después podrás seleccionarlos aquí.</p>" +
          '<a class="btn btn-outline-primary btn-sm" href="' + esc(crearLink.href) + '" target="_blank" rel="noopener">' +
          '<i class="bi bi-box-arrow-up-right"></i> Crear paquete</a>' +
          '<div class="mt-2"><button type="button" class="btn btn-link btn-sm" data-capu-recargar>Actualizar lista</button></div></div>';
        return;
      }
      var vis = disponibles.filter(function (p) { return !term || norm(p.nombre + " " + p.descripcion).indexOf(term) !== -1; });
      if (!vis.length) {
        pickList.innerHTML =
          '<div class="capu-empty capu-empty--search" style="margin:8px;">' +
          '<div class="capu-empty__icon"><i class="bi bi-search"></i></div>' +
          '<div class="capu-empty__title">Sin resultados</div>' +
          '<p class="capu-empty__text" style="margin-bottom:0;">Ningún paquete coincide con «' + esc(pickQ.value) + "».</p></div>";
        return;
      }
      pickList.innerHTML = vis.map(function (p) {
        return '<button type="button" class="capu-pick" data-pick-paquete="' + p.id + '"' + (p.asignado ? " disabled" : "") + ">" +
          '<span><div class="capu-pick__name">' + esc(p.nombre) + "</div>" +
          '<div class="capu-pick__sub"><span>' + p.n_componentes + " componente" + (p.n_componentes === 1 ? "" : "s") + "</span>" +
          (p.n_pendientes ? '<span class="capu-na" style="font-size:11.5px;">· ' + p.n_pendientes + " pendiente" + (p.n_pendientes === 1 ? "" : "s") + "</span>" : "") +
          (p.asignado ? "<span>· Ya asignado</span>" : "") + "</div>" +
          (p.descripcion ? '<div class="capu-pick__desc">' + esc(p.descripcion) + "</div>" : "") + "</span>" +
          '<span class="capu-pick__vd">' + (p.valor_fmt ? esc(p.valor_fmt) + " <small>/ día</small>"
            : '<span class="capu-na">' + (p.n_componentes ? "No disponible" : "Sin componentes") + "</span>") + "</span>" +
          '<span class="capu-pick__add"><i class="bi bi-' + (p.asignado ? "check-lg" : "plus-lg") + '"></i></span></button>';
      }).join("");
    }

    function cargarDisponibles() {
      pickList.innerHTML = '<div class="p-4 text-center capu-muted"><span class="spinner-border spinner-border-sm"></span> Cargando paquetes…</div>';
      return fetch(urls.disponibles + "?tipo=" + encodeURIComponent(tipoActual), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) { disponibles = d.paquetes || []; renderPicker(); })
        .catch(function () { pickList.innerHTML = '<div class="p-4 text-center capu-na">No se pudo cargar la lista.</div>'; });
    }

    function abrirPicker(tipo) {
      tipoActual = tipo;
      var b = bloque(tipo);
      pickTipo.textContent = b ? b.dataset.label : "";
      pickQ.value = "";
      pickConfirm.hidden = true;
      pendienteAgregar = null;
      crearLink.href = urls.crear + "?tipo=" + encodeURIComponent(tipo);
      cargarDisponibles();
      if (pickerModal) pickerModal.show();
    }

    function agregar(paqueteId) {
      var btn = pickList.querySelector('[data-pick-paquete="' + paqueteId + '"]');
      if (btn) { btn.disabled = true; btn.querySelector(".capu-pick__add").innerHTML = '<span class="spinner-border spinner-border-sm"></span>'; }
      post(urls.agregar, { tipo: tipoActual, paquete: paqueteId }).then(function (d) {
        aplicar(d, d.ok === false ? null : paqueteId);
        if (d.ok !== false) {
          disponibles.forEach(function (p) { if (String(p.id) === String(paqueteId)) p.asignado = true; });
        }
        renderPicker();
      });
    }

    pickList.addEventListener("click", function (e) {
      if (e.target.closest("[data-capu-recargar]")) { cargarDisponibles(); return; }
      var b = e.target.closest("[data-pick-paquete]");
      if (!b || b.disabled) return;
      var blq = bloque(tipoActual);
      // Transición consciente: primer paquete en un tipo que hoy usa la configuración individual.
      if (blq && blq.dataset.fuente === "sia" && blq.dataset.nEfectivos === "0") {
        pendienteAgregar = b.dataset.pickPaquete;
        picker.querySelector("[data-capu-confirm-tipo]").textContent = blq.dataset.label;
        var nS = +blq.dataset.nSia;
        picker.querySelector("[data-capu-confirm-n]").textContent = nS + (nS === 1 ? " ítem" : " ítems");
        pickConfirm.hidden = false;
        pickConfirm.scrollIntoView({ block: "nearest" });
        return;
      }
      agregar(b.dataset.pickPaquete);
    });
    picker.querySelector("[data-capu-confirm-ok]").addEventListener("click", function () {
      pickConfirm.hidden = true;
      if (pendienteAgregar) agregar(pendienteAgregar);
      pendienteAgregar = null;
    });
    picker.querySelector("[data-capu-confirm-cancel]").addEventListener("click", function () {
      pickConfirm.hidden = true; pendienteAgregar = null;
    });
    pickQ.addEventListener("input", debounce(renderPicker, 60));
    pickQ.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
    picker.addEventListener("shown.bs.modal", function () { pickQ.focus(); });

    /* ── Quitar ── */
    function quitar(asigId) {
      var card = root.querySelector('[data-capu-quitar][data-asig="' + asigId + '"]');
      if (card) card.closest(".capu-pkg-row").classList.add("is-busy");
      post(urlCon(urls.quitar, asigId), {}).then(function (d) { aplicar(d); });
    }
    confirmQuitar.querySelector("[data-capu-quitar-ok]").addEventListener("click", function () {
      if (quitarModal) quitarModal.hide();
      if (pendienteQuitar) quitar(pendienteQuitar);
      pendienteQuitar = null;
    });

    /* ── Delegación en la sección ── */
    root.addEventListener("click", function (e) {
      var add = e.target.closest("[data-capu-add-paquete]");
      if (add) { abrirPicker(add.closest("[data-capu-cfg-tipo]").dataset.capuCfgTipo); return; }

      var q = e.target.closest("[data-capu-quitar]");
      if (q) {
        var blq = q.closest("[data-capu-cfg-tipo]");
        var ultimo = q.dataset.efectivo === "1" && blq.dataset.nEfectivos === "1";
        if (!ultimo) { quitar(q.dataset.asig); return; }
        var nSia = +blq.dataset.nSia;
        confirmQuitar.querySelector("[data-capu-quitar-texto]").innerHTML =
          "<p>Es el último paquete activo de <strong>" + esc(blq.dataset.label) + "</strong>.</p><p class=\"mb-0\">" +
          (nSia
            ? "Al quitarlo, este tipo volverá a usar su configuración individual anterior (" + nSia + " ítem" + (nSia === 1 ? "" : "s") + ")."
            : "Al quitarlo, este tipo quedará sin configuración y los APU nuevos no tendrán recursos de este tipo.") +
          " El paquete «" + esc(q.dataset.nombre) + "» seguirá en el catálogo.</p>";
        pendienteQuitar = q.dataset.asig;
        if (quitarModal) quitarModal.show();
        return;
      }

      var mv = e.target.closest("[data-capu-mover]");
      if (mv && !mv.disabled) {
        mv.closest(".capu-pkg-row").classList.add("is-busy");
        post(urlCon(urls.mover, mv.dataset.asig), { direccion: mv.dataset.capuMover }).then(function (d) {
          d.mensaje = d.ok === false ? d.mensaje : "";
          aplicar(d);
        });
      }
    });
  }

  /* ══════════════════════════════════════════════════════════
     5. APU del proyecto: "Configurar APU" (Fase 3.C)
     Edición local de ESTE APU. Cada cambio se guarda en backend
     (APUService) y el panel se vuelve a pintar con los importes que
     devuelve el servidor. Al cerrar, si hubo cambios, se recarga la
     vista de consulta en la misma pestaña.
     ══════════════════════════════════════════════════════════ */
  function initAPUConfigurador(root) {
    var TIPOS = ["MANO_DE_OBRA", "HERRAMIENTAS_EQUIPOS", "TRANSPORTE", "ADMINISTRACION"];
    var d = root.dataset;
    var bloqueado = d.bloqueado === "1";
    var csrf = (root.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";
    var body = root.querySelector("[data-apu-cfg-body]");
    var toast = root.querySelector("[data-apu-cfg-toast]");
    var costoEl = root.querySelector("[data-apu-cfg-costo]");
    var valorEl = root.querySelector("[data-apu-cfg-valor]");
    var tabs = root.querySelectorAll("[data-apu-cfg-tab]");
    var drawer = window.bootstrap ? bootstrap.Offcanvas.getOrCreateInstance(root) : null;

    var picker = document.getElementById("apuPaquetePicker");
    var quitarEl = document.getElementById("apuQuitarPaquete");
    [picker, quitarEl].forEach(function (m) { if (m && m.parentElement !== document.body) document.body.appendChild(m); });
    var pickerModal = window.bootstrap ? bootstrap.Modal.getOrCreateInstance(picker) : null;
    var quitarModal = window.bootstrap ? bootstrap.Modal.getOrCreateInstance(quitarEl) : null;
    var pickQ = picker.querySelector("[data-apu-pick-q]");
    var pickList = picker.querySelector("[data-apu-pick-list]");
    var pickConfirm = picker.querySelector("[data-apu-pick-confirm]");

    var tipoActual = TIPOS[0], huboCambios = false, disponibles = [], conversion = null;
    var pendienteAgregar = null, pendienteQuitar = null, toastTimer;

    function urlId(base, id) { return base.replace(/\/0\/([a-z-]+)\/$/, "/" + id + "/$1/"); }

    function aviso(msg, ok) {
      if (!toast || !msg) return;
      toast.className = "capu-cfg-toast msg-bar msg-" + (ok === false ? "error" : "success");
      toast.textContent = msg;
      toast.hidden = false;
      clearTimeout(toastTimer);
      toastTimer = setTimeout(function () { toast.hidden = true; }, 6000);
    }

    function marcarTab(tipo) {
      tabs.forEach(function (t) {
        var activo = t.dataset.apuCfgTab === tipo;
        t.classList.toggle("active", activo);
        t.setAttribute("aria-selected", activo ? "true" : "false");
        if (activo && t.parentElement.scrollWidth > t.parentElement.clientWidth) {
          t.parentElement.scrollLeft = t.offsetLeft - 8;
        }
      });
    }

    function cargar(tipo) {
      tipoActual = tipo;
      marcarTab(tipo);
      body.classList.add("is-loading");
      return fetch(d.urlTipo.replace("TIPO", tipo), { credentials: "same-origin" })
        .then(function (r) { return r.text(); })
        .then(function (html) { body.innerHTML = html; })
        .catch(function () { body.innerHTML = '<div class="p-4 capu-na">No se pudo cargar la configuración.</div>'; })
        .finally(function () { body.classList.remove("is-loading"); });
    }

    function aplicar(res) {
      if (res.html) body.innerHTML = res.html;
      if (res.totales) {
        [[costoEl, res.totales.total_costo], [valorEl, res.totales.total_valor_venta]].forEach(function (p) {
          if (!p[0] || p[0].textContent === p[1]) return;
          p[0].textContent = p[1];
          p[0].classList.add("is-updated");
          setTimeout(function () { p[0].classList.remove("is-updated"); }, 1400);
        });
      }
      if (res.ok !== false) huboCambios = true;
      aviso(res.mensaje, res.ok);
    }

    function post(url, datos) {
      var fd = new FormData();
      Object.keys(datos || {}).forEach(function (k) { fd.append(k, datos[k]); });
      return fetch(url, {
        method: "POST", body: fd, credentials: "same-origin",
        headers: { "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" }
      }).then(function (r) {
        return r.json().then(function (j) { j._status = r.status; return j; })
          .catch(function () { return { ok: false, mensaje: "No se pudo completar la operación.", _status: r.status }; });
      });
    }

    /* ── Abrir desde la vista (general o por pestaña) ── */
    function tipoContexto() {
      var pane = document.querySelector(".apu-tab-pane.active[data-tipo]");
      var t = pane ? pane.dataset.tipo : "";
      return TIPOS.indexOf(t) !== -1 ? t : TIPOS[0];
    }
    document.querySelectorAll("[data-apu-config-open]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var t = btn.dataset.apuConfigOpen || tipoContexto();
        cargar(t);
        if (drawer) drawer.show();
      });
    });
    tabs.forEach(function (t) { t.addEventListener("click", function () { cargar(t.dataset.apuCfgTab); }); });

    var abriendoSueltos = false;
    function recargarVista() {
      var pane = document.querySelector('.apu-tab-pane[data-tipo="' + tipoActual + '"]');
      if (pane && window.history && history.replaceState) {
        history.replaceState(null, "", window.location.pathname + window.location.search + "#" + pane.id);
      }
      window.location.reload();
    }
    root.addEventListener("hidden.bs.offcanvas", function () {
      if (abriendoSueltos) return;       // se abre el modal de ítems adicionales
      if (huboCambios) recargarVista();
    });

    /* ── Edición de componentes (cantidad / precio / porcentaje) ── */
    function guardarCampo(input) {
      if (bloqueado) return;
      var valor = input.value.trim();
      if (valor === (input.dataset.original || "")) return;
      if (!valor) { input.value = input.dataset.original || ""; return; }
      var row = input.closest("[data-linea]");
      row.classList.add("is-saving");
      var datos = {};
      datos[input.dataset.campo] = valor;
      post(row.dataset.url || urlId(d.urlComponente, row.dataset.linea), datos).then(function (res) {
        if (res.ok === false) {
          row.classList.remove("is-saving");
          input.classList.add("is-invalid");
          aviso(res.mensaje, false);
          return;
        }
        aplicar(res);
        var nuevo = body.querySelector('[data-linea="' + row.dataset.linea + '"]');
        if (nuevo) nuevo.classList.add("is-saved");
      });
    }
    body.addEventListener("focusin", function (e) {
      var inp = e.target.closest("input[data-campo]");
      if (inp && inp.dataset.original === undefined) inp.dataset.original = inp.value.trim();
    });
    body.addEventListener("input", function (e) {
      if (e.target.matches("input[data-campo]")) e.target.classList.remove("is-invalid");
    });
    body.addEventListener("keydown", function (e) {
      var inp = e.target.closest("input[data-campo]");
      if (!inp) return;
      if (e.key === "Enter") { e.preventDefault(); inp.blur(); }
      if (e.key === "Escape") { inp.value = inp.dataset.original || inp.value; inp.blur(); }
    });
    body.addEventListener("focusout", function (e) {
      var inp = e.target.closest("input[data-campo]");
      if (inp) guardarCampo(inp);
    });

    /* ── Acciones del panel ── */
    body.addEventListener("click", function (e) {
      var rendRest = e.target.closest("[data-apu-rend-restablecer]");
      if (rendRest) {
        rendRest.disabled = true;
        post(rendRest.closest("[data-url]").dataset.url, { restablecer: "1" }).then(aplicar);
        return;
      }
      var rest = e.target.closest("[data-apu-restablecer]");
      if (rest) {
        rest.disabled = true;
        post(urlId(d.urlRestablecer, rest.dataset.apuRestablecer), {}).then(aplicar);
        return;
      }
      if (e.target.closest("[data-apu-add-paquete]")) { abrirPicker(); return; }
      var q = e.target.closest("[data-apu-quitar-paquete]");
      if (q) {
        pendienteQuitar = q.dataset.apuQuitarPaquete;
        quitarEl.querySelector("[data-apu-quitar-texto]").innerHTML =
          "<p>Se quitará «<strong>" + esc(q.dataset.nombre) + "</strong>» y sus componentes <strong>solo de este APU</strong>, " +
          "y se recalculará el tipo.</p><p class=\"mb-0\">El paquete maestro, el subsistema y los demás APU no cambian. " +
          "Los ítems adicionales se conservan.</p>";
        if (quitarModal) quitarModal.show();
        return;
      }
      var s = e.target.closest("[data-apu-sueltos]");
      if (s) {
        var modalEl = document.querySelector(s.dataset.apuSueltos);
        if (!modalEl) return;
        abriendoSueltos = true;
        root.addEventListener("hidden.bs.offcanvas", function abrir() {
          root.removeEventListener("hidden.bs.offcanvas", abrir);
          abriendoSueltos = false;
          // El modal existente guarda con su propio POST (solo líneas sin paquete).
          modalEl.addEventListener("hidden.bs.modal", function alCerrar() {
            modalEl.removeEventListener("hidden.bs.modal", alCerrar);
            if (huboCambios) recargarVista();
          });
          bootstrap.Modal.getOrCreateInstance(modalEl).show();
        });
        if (drawer) drawer.hide();
      }
    });

    quitarEl.querySelector("[data-apu-quitar-ok]").addEventListener("click", function () {
      if (quitarModal) quitarModal.hide();
      if (!pendienteQuitar) return;
      body.classList.add("is-loading");
      post(urlId(d.urlEliminar, pendienteQuitar), {}).then(function (res) {
        body.classList.remove("is-loading");
        aplicar(res);
      });
      pendienteQuitar = null;
    });

    /* ── Selector de paquetes ── */
    function renderPicker() {
      var term = norm(pickQ.value.trim());
      if (!disponibles.length) {
        pickList.innerHTML =
          '<div class="capu-empty" style="border:none;"><div class="capu-empty__icon"><i class="bi bi-stack"></i></div>' +
          '<div class="capu-empty__title">No hay paquetes disponibles</div>' +
          '<p class="capu-empty__text">No hay paquetes activos de este tipo que no estén ya en el APU. ' +
          "Los paquetes se crean en el Catálogo APU.</p></div>";
        return;
      }
      var vis = disponibles.filter(function (p) { return !term || norm(p.nombre + " " + p.descripcion).indexOf(term) !== -1; });
      if (!vis.length) {
        pickList.innerHTML = '<div class="capu-empty capu-empty--search" style="margin:8px;"><div class="capu-empty__title">Sin resultados</div></div>';
        return;
      }
      pickList.innerHTML = vis.map(function (p) {
        var bloqueaPend = p.n_pendientes > 0;
        return '<button type="button" class="capu-pick" data-pick="' + p.id + '"' + (bloqueaPend ? " disabled" : "") + ">" +
          '<span><div class="capu-pick__name">' + esc(p.nombre) + "</div>" +
          '<div class="capu-pick__sub"><span>' + p.n_componentes + " componente" + (p.n_componentes === 1 ? "" : "s") + "</span>" +
          (bloqueaPend ? '<span class="capu-na" style="font-size:11.5px;">· ' + p.n_pendientes + " sin vida útil: no se puede agregar</span>" : "") +
          "</div>" + (p.descripcion ? '<div class="capu-pick__desc">' + esc(p.descripcion) + "</div>" : "") + "</span>" +
          '<span class="capu-pick__vd">' + (p.valor_fmt ? esc(p.valor_fmt) + " <small>/ día</small>" : '<span class="capu-na">No disponible</span>') + "</span>" +
          '<span class="capu-pick__add"><i class="bi bi-' + (bloqueaPend ? "slash-circle" : "plus-lg") + '"></i></span></button>';
      }).join("");
    }

    function abrirPicker() {
      var panel = body.querySelector("[data-apu-cfg-panel]");
      picker.querySelector("[data-apu-pick-tipo]").textContent = panel ? panel.dataset.label : "";
      pickQ.value = "";
      pickConfirm.hidden = true;
      pendienteAgregar = null;
      pickList.innerHTML = '<div class="p-4 text-center capu-muted"><span class="spinner-border spinner-border-sm"></span> Cargando paquetes…</div>';
      fetch(d.urlDisponibles + "?tipo=" + encodeURIComponent(tipoActual), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (res) { disponibles = res.paquetes || []; conversion = res.conversion; renderPicker(); })
        .catch(function () { pickList.innerHTML = '<div class="p-4 capu-na">No se pudo cargar la lista.</div>'; });
      if (pickerModal) pickerModal.show();
    }

    function agregar(id, confirmar) {
      var datos = { paquete_id: id };
      if (confirmar) datos.confirmar_conversion = "1";
      pickList.classList.add("is-loading");
      post(d.urlAgregar, datos).then(function (res) {
        pickList.classList.remove("is-loading");
        if (res._status === 409 && res.requiere_conversion) {
          conversion = { lineas: res.lineas || [] };
          mostrarConversion(id);
          return;
        }
        aplicar(res);
        if (res.ok !== false && pickerModal) pickerModal.hide();
      });
    }

    function mostrarConversion(id) {
      pendienteAgregar = id;
      var cont = picker.querySelector("[data-apu-pick-lineas]");
      var l = (conversion && conversion.lineas) || [];
      cont.innerHTML = l.length
        ? '<div class="mt-2">Se reemplazarán estas líneas de la estructura anterior:<ul>' +
          l.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></div>"
        : "";
      pickConfirm.hidden = false;
      pickConfirm.scrollIntoView({ block: "nearest" });
    }

    pickList.addEventListener("click", function (e) {
      var b = e.target.closest("[data-pick]");
      if (!b || b.disabled) return;
      if (conversion) { mostrarConversion(b.dataset.pick); return; }
      agregar(b.dataset.pick, false);
    });
    picker.querySelector("[data-apu-confirm-ok]").addEventListener("click", function () {
      pickConfirm.hidden = true;
      if (pendienteAgregar) agregar(pendienteAgregar, true);
      pendienteAgregar = null;
    });
    picker.querySelector("[data-apu-confirm-cancel]").addEventListener("click", function () {
      pickConfirm.hidden = true; pendienteAgregar = null;
    });
    pickQ.addEventListener("input", debounce(renderPicker, 60));
    pickQ.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
    picker.addEventListener("shown.bs.modal", function () { pickQ.focus(); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var c = document.querySelector("[data-capu-catalogo]");
    if (c) initCatalogo(c);
    var f = document.querySelector("[data-capu-item-form]");
    if (f) initItemForm(f);
    var b = document.querySelector("[data-capu-builder]");
    if (b) initBuilder(b);
    var sp = document.querySelector("[data-capu-subsistema]");
    if (sp) initSubsistemaPaquetes(sp);
    var ac = document.querySelector("[data-apu-config]");
    if (ac) initAPUConfigurador(ac);
  });
})();
