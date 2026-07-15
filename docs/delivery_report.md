# Informe de entrega — Tareas 1–19

**Fecha:** 2026-05-14
**`manage.py check`:** `System check identified no issues (0 silenced).`

---

## Resumen de cambios por tarea

### T1 — Modelo versioning de proyecto
- **`apps/presupuestos/services/proyecto_service.py`**: nueva función `clonar_proyecto_como_version(proyecto_base, usuario)`. Copia todos los campos financieros y de metadatos del proyecto base. `Proyecto.save()` gestiona `version` y `es_version_actual` automáticamente.

### T2 — Vista clonar proyecto
- **`apps/comercial/views.py`**: nueva clase `ClonarProyectoComoVersionView`. Valida que el proyecto tenga solicitud vinculada, llama al service, redirige a `proyecto_detail` con mensaje de éxito.
- **`apps/comercial/urls.py`**: `path("proyectos/<int:pk>/clonar/", ...)` → `comercial:proyecto_clonar`.

### T3 — Botones clone / nueva vacía en proyecto_detail
- **`templates/comercial/proyecto_detail.html`**: reemplaza el botón "+ Nueva versión" por dos: "Clonar versión" (POST con confirm) y "+ Nueva vacía" (link a `crear_proyecto_desde_solicitud`). Solo visibles si el proyecto tiene solicitud.

### T4 — Filtrado de clientes por unidad de negocio
- **`apps/comercial/forms.py`**: `SolicitudForm.__init__` acepta `unidad_negocio=None`; filtra el queryset de `cliente` y valida en `clean_cliente`.
- **`apps/comercial/views.py`**: `SolicitudCreateView`, `SolicitudUpdateView`, `SolicitudListView`, `DashboardView` pasan `unidad_negocio` desde `request.session`.

### T5 — Tarjetas compactas en catálogo de sistemas
- **`templates/ingenieria/calculador_sistemas.html`**: grid `minmax(220px, 1fr)`, gap 10px, fuentes reducidas, `line-clamp: 2` en nombre y descripción.

### T6+T7 — Layout dos columnas + imagen técnica en selección de subsistema
- **`templates/ingenieria/calculador_seleccionar.html`**: nuevo layout `.sub-body-cols` (grid `1fr 220px`). Columna derecha muestra `sub.imagen_tecnica` o placeholder. No requiere migración (campo `imagen_tecnica` ya existía en `Subsistema`).

### T8 — Barra de búsqueda en APU
- **`templates/presupuestos/apu_detail.html`**: input de búsqueda sobre la tabla. Funciones JS `apuFiltrar()` / `apuLimpiar()` filtran filas `tr[id^="apu-linea-"]:not(.apu-cat-detail)` en tiempo real.

### T9 — Consolidación multi-despiece al generar APU
- **`apps/presupuestos/views/__init__.py`** (`APUGenerarDesdeDespiece.post`): en lugar de sincronizar solo el despiece actual, recopila **todos** los `DespieceMaestro` guardados del proyecto, acumula cantidades por `componente_codigo` y sincroniza el consolidado a `DespieceLinea`. Productos ausentes en cualquier despiece se eliminan.

### T10 — Sin duplicados en regeneración de APU
- **`apps/presupuestos/services/apu_service.py`** (`APUService.generar_materiales`): al inicio elimina líneas `tipo=MATERIALES, despiece_linea__isnull=False` antes de regenerar. Usa `despiece_linea IS NOT NULL` como marcador de líneas auto-generadas; sin nueva migración.

### T11 — Formularios compactos
- **`static/css/imperandina.css`**: añade `.form-grid-2` y `.form-grid-3` (CSS Grid, responsive). Reduce padding `.form-page-body` de 22px a 18px.
- **`templates/comercial/proyecto_form.html`**: variables financieras reorganizadas en dos bloques de 3 columnas en lugar de tres bloques de 2 columnas.

### T12+T13 — Modal "Crear proyecto" desde solicitud_detail
- **`templates/comercial/_modal_crear_proyecto.html`**: partial Bootstrap modal con `ProyectoFromSolicitudForm`, layout 3-columnas para variables financieras, enlace "Abrir formulario completo" como fallback.
- **`apps/comercial/views.py`** (`SolicitudDetailView.get_context_data`): inyecta `proyecto_form` y `proxima_version` en el contexto.
- **`templates/comercial/solicitud_detail.html`**: botones topbar, panel Proyectos y empty-state cambian a `data-bs-toggle="modal"`. Se incluye el partial con `{% include %}`.

### T14 — Historial colapsable (sesión anterior)
- **`templates/comercial/solicitud_detail.html`**: panel con preview de 3 eventos + "Ver N más" expandible. Header clickeable con chevron animado.

### T15 — Historial al fondo de solicitud_detail
- **`templates/comercial/solicitud_detail.html`**: el panel Historial se mueve fuera del `det-grid`, aparece como bloque ancho completo debajo de las dos columnas.

### T16 — Revisión de rutas
- `manage.py shell` confirma que las 11 rutas críticas resuelven correctamente (ver `test_guide.md`).

### T17 — Validaciones obligatorias
- **`templates/ingenieria/calculador_seleccionar.html`**: listener `submit` verifica que haya un radio `subsistema_pk` seleccionado; si no, muestra alert y cancela el envío.
- Validación "no APU desde despiece sin proyecto" ya existía en `APUGenerarDesdeDespiece`.
- Validación "no versión sin solicitud" cubierta por `ClonarProyectoComoVersionView`.

---

## Archivos modificados (resumen)

| Archivo | Tipo de cambio |
|---|---|
| `apps/comercial/forms.py` | Filtrado unidad de negocio en SolicitudForm |
| `apps/comercial/views.py` | ClonarProyectoComoVersionView, inyección unidad_negocio, proyecto_form en context |
| `apps/comercial/urls.py` | Ruta proyecto_clonar |
| `apps/presupuestos/services/proyecto_service.py` | clonar_proyecto_como_version() |
| `apps/presupuestos/services/apu_service.py` | Limpieza de duplicados en generar_materiales() |
| `apps/presupuestos/views/__init__.py` | Consolidación multi-despiece en APUGenerarDesdeDespiece |
| `static/css/imperandina.css` | form-grid-2, form-grid-3, padding reducido |
| `templates/comercial/proyecto_detail.html` | Botones clonar / nueva vacía |
| `templates/comercial/proyecto_form.html` | Layout 3 columnas financiero |
| `templates/comercial/solicitud_detail.html` | Modal, historial al fondo |
| `templates/comercial/_modal_crear_proyecto.html` | Nuevo partial |
| `templates/presupuestos/apu_detail.html` | Barra de búsqueda |
| `templates/ingenieria/calculador_sistemas.html` | Cards compactas |
| `templates/ingenieria/calculador_seleccionar.html` | Dos columnas, imagen, validación submit |
