/* ============================================================
   catalogos.js — Lógica del módulo Catálogos
   ============================================================ */
(function () {
  "use strict";

  /* ── Dropdown "+ Nuevo" ── */
  var dropWrap = document.querySelector('.cat-dropdown-wrap');
  var dropTrig = dropWrap && dropWrap.querySelector('.cat-dropdown-trigger');

  if (dropTrig) {
    dropTrig.addEventListener('click', function (e) {
      e.stopPropagation();
      dropWrap.classList.toggle('open');
      this.setAttribute('aria-expanded', dropWrap.classList.contains('open'));
    });
    document.addEventListener('click', function () {
      dropWrap.classList.remove('open');
      dropTrig.setAttribute('aria-expanded', 'false');
    });
  }

  /* ── Panel unidades (colapsable) ── */
  var unBtn   = document.getElementById('unidadesToggleBtn');
  var unPills = document.getElementById('unidadesPills');
  var unLabel = document.getElementById('unidadesToggleLabel');
  var unChev  = document.getElementById('unidadesChevron');

  if (unBtn && unPills) {
    unBtn.addEventListener('click', function () {
      var isOpen = unPills.classList.toggle('open');
      unBtn.setAttribute('aria-expanded', isOpen);
      if (unLabel) unLabel.textContent = isOpen ? 'Ocultar' : 'Mostrar';
      if (unChev)  unChev.style.transform = isOpen ? 'rotate(180deg)' : '';
    });
  }

  /* ── Toggle productos por categoría ── */
  document.querySelectorAll('.cat-card__toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var targetId = this.dataset.target;
      var panel    = document.getElementById(targetId);
      if (!panel) return;
      var isOpen = panel.classList.toggle('open');
      this.classList.toggle('open', isOpen);
      this.setAttribute('aria-expanded', isOpen);
      // Actualiza texto del botón (primer nodo de texto)
      var textNode = this.firstChild;
      if (textNode && textNode.nodeType === 3) {
        textNode.textContent = isOpen ? 'Ocultar ' : 'Ver lista ';
      }
    });
  });

  /* ── Búsqueda + filtro ── */
  var searchInput = document.getElementById('catSearch');
  var chips = document.querySelectorAll('.cat-chip');
  var cards = document.querySelectorAll('.cat-card');
  var activeFilter = 'all';

  function applyFilter() {
    var q = (searchInput ? searchInput.value : '').toLowerCase().trim();
    cards.forEach(function (card) {
      var name   = (card.dataset.name   || '').toLowerCase();
      var status = (card.dataset.status || '');
      var textMatch = !q || name.includes(q);
      if (!textMatch && q) {
        card.querySelectorAll('.cat-prod-item').forEach(function (item) {
          if ((item.dataset.prodName || '').includes(q)) textMatch = true;
        });
      }
      var statusMatch = activeFilter === 'all' || status === activeFilter;
      card.style.display = (textMatch && statusMatch) ? '' : 'none';
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', applyFilter);
  }

  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(function (c) { c.classList.remove('active'); });
      this.classList.add('active');
      activeFilter = this.dataset.filter;
      applyFilter();
    });
  });

  /* ── Modal "+ Producto" desde tarjeta (pre-selecciona categoría) ── */
  var modalProductoEl = document.getElementById('modalProducto');
  if (modalProductoEl) {
    modalProductoEl.addEventListener('show.bs.modal', function (e) {
      var btn = e.relatedTarget;
      if (!btn) return;
      var catPk = btn.dataset.categoriaPk;
      if (catPk) {
        var sel = modalProductoEl.querySelector('[name="categoria"]');
        if (sel) sel.value = catPk;
      }
    });
  }

  /* ── Modal detalle de producto ── */
  var modalDetalleEl = document.getElementById('modalDetalleProd');
  if (modalDetalleEl) {
    modalDetalleEl.addEventListener('show.bs.modal', function (e) {
      var item = e.relatedTarget;
      if (!item) return;
      var d = item.dataset;

      setText('detalleProdNombre',   d.prodNombre   || '—');
      setText('detalleProdCodigo',   d.prodCodigo   || '—');
      setText('detalleProdCategoria',d.prodCategoria|| '—');
      setText('detalleProdProveedor',d.prodProveedor|| '—');
      setText('detalleProdUnidad',   d.prodUnidad   || '—');
      setText('detalleProdMarca',    d.prodMarca    || '—');
      setText('detalleProdMoneda',   d.prodMoneda   || '');

      // Precio formateado
      var precio = parseFloat((d.prodPrecio || '').replace(/,/g, ''));
      var precioEl = document.getElementById('detalleProdPrecio');
      if (precioEl) {
        precioEl.textContent = precio > 0
          ? '$' + precio.toLocaleString('es-CO', {minimumFractionDigits: 0})
          : 'Sin precio';
      }

      // Estado
      var estadoEl = document.getElementById('detalleProdEstado');
      if (estadoEl) {
        var activo = d.prodActivo === 'Activo';
        estadoEl.textContent = activo ? 'Activo' : 'Inactivo';
        estadoEl.className = 'prod-detail-badge ' +
          (activo ? 'prod-detail-badge--active' : 'prod-detail-badge--inactive') +
          ' ms-auto';
      }

      // Botón editar — apunta a la URL de edición del producto
      var editBtn = document.getElementById('detalleProdEditUrl');
      if (editBtn) {
        editBtn.href = d.prodEditUrl || '#';
      }
    });
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  /* ── Preview de imagen en modal categoría ── */
  var imgInput   = document.querySelector('#modalCategoria [name="imagen"]');
  var imgPreview = document.getElementById('catImgPreview');

  if (imgInput && imgPreview) {
    imgInput.addEventListener('change', function () {
      if (this.files && this.files[0]) {
        var reader = new FileReader();
        reader.onload = function (ev) {
          imgPreview.src = ev.target.result;
          imgPreview.classList.add('visible');
        };
        reader.readAsDataURL(this.files[0]);
      } else {
        imgPreview.src = '';
        imgPreview.classList.remove('visible');
      }
    });
  }

})();
