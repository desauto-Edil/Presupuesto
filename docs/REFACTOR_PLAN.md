# AndinaCost — Plan de refactor (Fases 0–2 aplicadas · inventario activo)

Este documento es **inventario vivo**. Lo que ya se hizo queda marcado
como DONE. Lo que sigue siendo "detección, no eliminación" se mantiene
intacto hasta confirmar uso en datos reales y obtener visto bueno
explícito.

---

## 0. Estado por fase

| Fase | Estado | Resumen |
|---|---|---|
| **Fase 0** — Seguridad y config | ✅ DONE | `.env` vía decouple, CACHES (locmem/redis), `.env.example`, `.gitignore` revisado. |
| **Fase 1** — Base `apps/common/` | ✅ DONE | `cache.py`, `formula_evaluator.py`, `dto.py`, `patterns.py`. |
| **Fase 2A** — Confirm delete centralizado | ✅ DONE | `partials/_confirm_delete_modal.html` + wrapper. |
| **Fase 2B** — Piloto partial form | ✅ DONE | `catalogos/_unidad_form.html`. |
| **Fase 2C** — Replicación partial form | ✅ DONE | Categoría, TipoProyecto, Producto. |
| **Fase 2D** — Service Layer | ✅ DONE | `SubsistemaService` (extraído de views) + `ProyectoService` comercial (capa preparada sin tocar `save()`). |
| **Fase 2E** — Facades semilla | ✅ DONE | `DespieceFacade`, `APUFacade` (no adoptadas por vistas todavía). |
| **Fase 3** — Adopción de facades + extracción de templates monstruo | ⏳ pendiente | Requiere tests de regresión. |
| **Fase 4** — Eliminación auditada de legacy | ⏳ pendiente | Requiere análisis de DB real. |
| **Fase 5** — Cableado de signals + `recalculo_diferido()` | ⏳ pendiente | — |

---

---

## 1. Templates posiblemente obsoletos

| Archivo | Líneas | Sospecha | Acción propuesta |
|---|---|---|---|
| `templates/ingenieria/despiece_maestro_nuevo.html` | 639 | Convive con `despiece_maestro.html` (1614). Nombre "_nuevo" sugiere borrador o variante. | Comparar contra `despiece_maestro.html`, decidir cuál es canónico, mover el otro a `legacy/`. |
| `templates/presupuestos/proyectosistema_list.html` | 58 | Funcionalidad cercana a `despiece_list.html`. | Verificar si está enrutada y con qué nombre. |
| `templates/ingenieria/despiece_list.html` (283) vs `templates/presupuestos/despiece_list.html` (145) | — | Dos listados de despiece conviven. | Distinguir alcance (maestro vs proyecto) en nombre o consolidar. |

---

## 2. Rutas duplicadas o sospechosas

| Patrón | App | Observación |
|---|---|---|
| `despiece_list` y `despieces_guardados` | `ingenieria` | Ambos `path()` apuntan a la misma view. Quedarse con uno. |
| URLs comentadas de `CuadrillaPreset*` | `presupuestos` | Las vistas están importadas pero las rutas comentadas. Decidir: reactivar o eliminar el bloque. |
| `presupuestos:despiece_list` vs `ingenieria:despiece_list` | ambas | Misma `url_name` en dos namespaces — confunde en `{% url %}`. |

---

## 3. Imports / código comentado

- `apps/presupuestos/urls.py`: bloque comentado de cuadrilla presets.
- `imperandina/settings.py` → `LOGGING.loggers`: entradas `"core"` y `"core.services"` apuntan a una app que **ya no está en INSTALLED_APPS**. Dejarlas no rompe nada pero contamina la config.

---

## 4. Middleware duplicado

`imperandina/settings.py:79-89` declara `django.contrib.sessions.middleware.SessionMiddleware` **dos veces** (líneas 81 y 87). La segunda parece introducida por error junto con `AuthCustomMiddleware`. Django no lanza error pero procesa la sesión dos veces por request.

Acción propuesta (en una fase posterior con tests): quitar la segunda ocurrencia.

---

## 5. Loggers de apps inexistentes

En `LOGGING.loggers`:
- `"core"` y `"core.services"` declaran handlers para una app que **no está en INSTALLED_APPS**. No causan error porque ningún módulo emite log con esos names en el código actual, pero deben eliminarse o redirigirse a `apps`.

---

## 6. Modelos legacy

| Modelo | App | Estado | Plan |
|---|---|---|---|
| `CapaConsumo` | `ingenieria` | DEPRECATED en docstring | Auditar referencias en DB de producción; si N=0 → drop con migración. |
| `ReglaCalculo` | `ingenieria` | Legacy del flujo anterior de despiece | Idem. |
| `DependenciaTecnica` | `ingenieria` | Legacy | Idem. |
| `APUProyecto` (alias `= APU`) | `presupuestos` | Compatibilidad | Mantener hasta que `imports` externos a `apps/` lo dejen de usar. |
| `DespieceLinea.regla` / `.dependencia_tecnica` | `presupuestos` | FKs LEGADO | Marcar como nullable/SET_NULL si no lo están y planear quita. |

---

## 7. Vistas no utilizadas / dudosas

- `CuadrillaPresetCreate/Update/Delete/Detail` importadas en `presupuestos/urls.py` pero **sin `path()` activo**.
- `_render_apu_pdf` y helpers PDF en `presupuestos/views/__init__.py` son lógica de presentación que debería migrar a `presupuestos/pdf/`. No es "vista no utilizada", es "vista mal ubicada".

---

## 8. Plan de extracción de templates monstruo (NO ejecutar todavía)

### 8.1 `templates/ingenieria/despiece_maestro.html` (1614 líneas)
**Partials a extraer**:
- `_modal_detalle_calculo.html` — modal "Detalle del cálculo" con chips `Etiqueta (variable) = valor`.
- `_modal_buscar_producto.html` — buscador reutilizable de productos.
- `_consolidaciones_section.html` — sección de líneas consolidadas con botones `Ver origen` y `Fórmulas`.
- `_variables_entrada_section.html`.
- `_checkpoint_panel.html` (ya existe — verificar que esté usado).
- `_despiece_lineas_table.html` (ya existe).

**JS a extraer a `static/js/despiece_maestro.js`**:
- `calcular()`, `guardar()`, `eliminar()`.
- `verDetalle(...)`, `verDetalleConsolidada(cid)` (Fix 7 reciente).
- Lógica de `getVariables()` / sincronización de progreso.
- Render dinámico de filas y consolidaciones.

### 8.2 `templates/ingenieria/subsistema_form.html` (1481 líneas)
**Partials**:
- `_table_variables.html` (sin la columna "Valor por defecto" — Fix 1).
- `_table_subconjuntos.html`.
- `_table_componentes.html` (código autogenerado readonly — Fix 3).
- `_table_productos_tecnicos.html`.
- `_select_unidad_medida.html` — dropdown reutilizable del catálogo (Fix 2).

**JS a extraer a `static/js/subsistema_form.js`**:
- Generación de códigos numéricos secuenciales.
- Add/remove dinámico de filas.
- Validación de fórmulas en vivo.

### 8.3 `templates/presupuestos/apu_detail.html` (1401 líneas)
**Partials**:
- `_apu_subtotales.html` — bloque de subtotales por tipo.
- `_apu_lineas_table.html` — por sección (MO, herramientas, transporte, admin, materiales).
- `_apu_aiu_modalidades.html` — modal de modalidades AIU.

**JS a extraer a `static/js/apu_detail.js`**:
- Edición inline de líneas.
- Cambio de modalidad AIU.
- Recálculo en vivo.

---

## 9. Pendientes de auditoría (datos reales)

- Cuántos `DespieceLinea` en producción tienen `regla_id` o `dependencia_tecnica_id` no nulos.
- Cuántos `CapaConsumo` hay en uso.
- Si la ruta `/calculador/guardados/` recibe tráfico real distinto de `/calculador/despieces/`.

---

## 10. Reglas para esta fase

1. **No** eliminar templates, rutas, modelos ni imports.
2. **No** renombrar archivos.
3. **No** mover código entre apps.
4. **Solo** documentar y dejar la base de `apps/common/` lista para que las siguientes fases la adopten.

---

## 11. Fase 2 — qué cambió (resumen ejecutable)

### 11.1 Templates
- **Nuevo** `templates/partials/_confirm_delete_modal.html` (parametrizado).
- **Refactor** `templates/confirm_delete.html` → wrapper que delega en el partial.
- **Nuevos partials de form**:
  - `templates/catalogos/_unidad_form.html`
  - `templates/catalogos/_categoria_form.html`
  - `templates/catalogos/_producto_form.html`
  - `templates/comercial/_tipoproyecto_form.html`
- **Wrappers reducidos** (sin cambio visible):
  - `catalogos/unidad_form.html` 58 → 21
  - `catalogos/categoria_form.html` 67 → 22
  - `catalogos/producto_form.html` 206 → 65
  - `comercial/tipoproyecto_form.html` 49 → 22

### 11.2 Servicios
- **Nuevo** `apps/ingenieria/services/subsistema_service.py` con:
  `guardar_variables`, `guardar_subconjuntos_componentes`, `guardar_reglas_apu`,
  `guardar_m2m_consumo`, `guardar_productos_tecnicos_componentes_quimicos`,
  `parsear_opciones`, `proximo_codigo_numerico`.
- **Refactor** `apps/ingenieria/views/__init__.py` 666 → 487 líneas
  (helpers `_guardar_*`, `_parsear_opciones`, `_proximo_codigo_numerico`
  ya no viven en la vista; se importan del service).
- **Nuevo** `apps/comercial/services/proyecto_service.py` con:
  `generar_consecutivo`, `crear_proyecto_desde_solicitud`,
  `crear_version_desde_proyecto`, `marcar_versiones_anteriores`.
  **Sin tocar `Proyecto.save()`** — capa preparada para futuro.

### 11.3 Facades semilla
- **Nuevo** `apps/ingenieria/services/despiece_facade.py` — `DespieceFacade`.
- **Nuevo** `apps/presupuestos/services/apu_facade.py` — `APUFacade`.
- Cero adopción en vistas en esta fase.

### 11.4 Lo que NO se tocó (intencional)
- `Proyecto.save()`, `Subsistema.save()` y cualquier `save()` con efectos.
- Modelos, migraciones, signals (`APULinea`).
- Lógica de cálculo (despiece, APU, productos).
- `despiece_maestro.html`, `subsistema_form.html`, `apu_detail.html`.
- `SessionMiddleware` duplicado en `settings.py` (documentado, sin cambio).
- Loggers `core` / `core.services` (documentados, sin cambio).
- Modelos legacy (`CapaConsumo`, `ReglaCalculo`, `DependenciaTecnica`).
- Rutas duplicadas (`despiece_list` vs `despieces_guardados`).
- Vistas/URLs comentadas de `CuadrillaPreset*`.

---

## 12. Próximos pasos sugeridos (cuando se apruebe)

1. **Tests de regresión mínimos** antes de Fase 3:
   - 1 test que ejercite crear+editar Subsistema con variables, subconjuntos y reglas APU.
   - 1 test que ejercite cálculo de despiece maestro.
   - 1 test que ejercite generación de APU desde despiece.
2. **Adopción progresiva de Facades** en vistas (sustituir `DespieceMaestroService(...)` por `DespieceFacade.calcular_maestro(...)`).
3. **Migración de `Proyecto.save()`** hacia `ProyectoService.crear_proyecto_desde_solicitud`.
4. **Extracción de `despiece_maestro.html`** en partials + JS externo (ver §8.1).
5. **Auditoría de modelos legacy** en datos reales (ver §6).

---

## 13. Fase 3 — progresivo (3A-3D aplicados)

### 13.A Verificación inicial (Fase 3A — DONE)
- `python manage.py check` limpio.
- Smoke render OK en `unidad_form`, `categoria_form`, `tipoproyecto_form` (CREATE + UPDATE).
- Cabeceras `{% comment %}…{% endcomment %}` confirmadas en los 5 partials de form.

### 13.B Diagnóstico `despiece_maestro.html` (Fase 3B — DONE)
- Mapa de 17 secciones (1614 líneas, `<style>`=289, `<script>`=1029).
- Identificadas 6 secciones de **bajo riesgo** extraíbles (notas, modal detalle,
  modal origen, offcanvas resumen + FAB, breadcrumb, topbar).
- Secciones **no tocar**: panel variables, panel resultado, modal consolidar,
  bloque `<script>` global, selección de productos.

### 13.C Primer partial extraído (Fase 3C — DONE)
- **Nuevo** `templates/ingenieria/partials/_despiece_notas.html`
  (incluye su propio `{% if notas_tecnicas %}`).
- **`despiece_maestro.html`**: 9 líneas reemplazadas por
  `{% include "ingenieria/partials/_despiece_notas.html" %}`.
- Reducción neta: **-8 líneas** en el template monstruo (1614 → 1606).
- Render byte-equivalente verificado:
  - con `notas_tecnicas` → HTML útil idéntico (norm-whitespace).
  - sin `notas_tecnicas` → ambos rinden vacío.
- Cero JS movido. Cero CSS movido. Cero ID/clase tocado.

### 13.D Primera adopción de `DespieceFacade` (Fase 3D — DONE)
- **Archivo**: `apps/ingenieria/views/calculador.py`.
- **Vista**: `CalcularDespieceMaestroView.post` (línea ~370).
- **Antes**:
  ```python
  svc = DespieceMaestroService(dm)
  try:
      resultados = svc.calcular()
  ```
- **Después**:
  ```python
  # Fase 3D — primera adopción de DespieceFacade.
  try:
      resultados = DespieceFacade.calcular_maestro(dm)
  ```
- **Por qué es equivalente**: la facade es un wrapper estático
  (`DespieceMaestroService(despiece).calcular()`); no captura excepciones;
  `svc` no se usaba para nada más después de `.calcular()`.
- **Import añadido**: `from apps.ingenieria.services.despiece_facade import DespieceFacade`
  (se conserva el import del service para los otros dos call-sites no migrados).
- **Call-sites NO migrados todavía** y por qué:
  - `DespieceMaestroView.get_context_data` (~línea 194): usa
    `get_variables_para_subconjuntos()`, método aún no expuesto en la facade.
  - `GuardarDespieceMaestroView.post` (~línea 438): encadena `calcular() + guardar()`
    sobre el mismo `svc`; migrarlo crearía dos instancias de service y aunque
    es funcionalmente equivalente, no es "wrapper idéntico". Se hará en una
    fase posterior cuando la facade exponga un método combinado.

### 13.E Verificación final
- `python manage.py check` → System check identified no issues (0 silenced).
- Render-diff del partial: idéntico.

### 13.K Séptimo partial extraído — Modal "Consolidar materiales" (Fase 3K — DONE)
- **Nuevo** `templates/ingenieria/partials/_modal_consolidar.html`
  (63 líneas, ~18 LOC efectivas, resto cabecera documental detallada).
- Cierra el frente de extracción de modales del Despiece Maestro.
- **`despiece_maestro.html`**: 18 líneas (modal completo, comentario incluido)
  reemplazadas por `{% include "ingenieria/partials/_modal_consolidar.html" %}`.
- Reducción acumulada en el template monstruo desde Fase 3: **1614 → 1519** (-95).
- **4 IDs preservados** (todos críticos para el JS):
  - `#modalConsolidar` — instanciado por `new bootstrap.Modal(...).show()` línea 1009
    y cerrado por `bootstrap.Modal.getInstance(...).hide()` línea 1005.
  - `#modalConsolidarLabel` — referenciado por `aria-labelledby`.
  - `#modalConsolidarBody` — slot poblado vía `innerHTML` en línea 983.
  - `#btnConfirmarConsolidacion` — el JS le **reasigna `.onclick = ...`** en
    cada apertura (línea 1002). El ID debe estar presente en el DOM antes
    de que el JS lo busque; preservado idénticamente.
- **#inputLabelConsolidacion** NO está en este partial — se inserta vía
  `innerHTML` por el JS al rellenar el body. No movido, no tocado.
- Clases preservadas: `modal fade`, `modal-dialog modal-lg`, `modal-content`,
  `modal-header`, `modal-title`, `modal-body`, `modal-footer`, `btn-close`,
  `data-bs-dismiss="modal"`, `btn btn-secondary`, `btn btn-success`,
  `bi bi-layers`, `bi bi-check2`.
- Atributos preservados: `tabindex="-1"`, `aria-labelledby="modalConsolidarLabel"`,
  `aria-hidden="true"`.
- Verificación contra duplicación (4 IDs en `despiece_maestro.html`):
  **0/0/0/0** ✅. En el partial: 1/1/1/1 ✅.
- Cero JS movido. Cero CSS movido.
- `python manage.py check` → System check identified no issues (0 silenced).

### 13.J Sexto partial extraído — Breadcrumb (Fase 3J — DONE)
- **Nuevo** `templates/ingenieria/partials/_despiece_breadcrumb.html`
  (45 líneas, ~10 LOC efectivas, resto cabecera documental).
- Segunda extracción de contenido **dentro de un `{% block %}`** (patrón
  validado en 3I).
- **`despiece_maestro.html`**: contenido del `{% block breadcrumb %}` (10 LOC)
  reemplazado por:
  ```django
  {% block breadcrumb %}
    {% include "ingenieria/partials/_despiece_breadcrumb.html" %}
  {% endblock %}
  ```
- Reducción acumulada en el template monstruo desde Fase 3: **1614 → 1536** (-78).
- **Variables Django preservadas**: `despiece.proyecto`,
  `despiece.proyecto.solicitud`, `despiece.proyecto.solicitud.pk`,
  `despiece.proyecto.solicitud.consecutivo`, `despiece.proyecto.pk`,
  `despiece.proyecto.consecutivo`, `despiece.subsistema.sistema.codigo`,
  `despiece.subsistema.codigo`.
- **URLs inversas preservadas**: `comercial:solicitud_list`,
  `comercial:solicitud_detail`, `comercial:proyecto_detail`.
- Estilos inline preservados: `style="color:inherit;text-decoration:none;"`
  (3 ocurrencias en los `<a>`).
- Verificación contra duplicación (template principal): **0/0/0**
  (`comercial:solicitud_list` = 0, `comercial:solicitud_detail` = 0,
  literal "Despiece rápido" = 0). ✅
- Cero JS movido. Cero IDs introducidos.
- `python manage.py check` → System check identified no issues (0 silenced).

### 13.I Quinto partial extraído — Topbar de acciones (Fase 3I — DONE)
- **Nuevo** `templates/ingenieria/partials/_despiece_topbar_actions.html`
  (47 líneas, ~18 LOC efectivas, resto cabecera documental).
- Primera extracción de contenido **dentro de un `{% block %}`** (no del `content` libre).
- **`despiece_maestro.html`**: contenido del `{% block topbar_actions %}` (18 líneas) reemplazado por:
  ```django
  {% block topbar_actions %}
    {% include "ingenieria/partials/_despiece_topbar_actions.html" %}
  {% endblock %}
  ```
- Reducción acumulada en el template monstruo desde Fase 3: **1614 → 1545** (-69).
- **Variables Django preservadas**: `proyecto`, `proyecto.pk`, `proyecto.consecutivo`,
  `despiece`, `despiece.esta_guardado`, `despiece.estado`, `apu_pk`.
- **URLs inversas preservadas**: `comercial:proyecto_detail`, `ingenieria:despiece_list`,
  `presupuestos:apu_detail`.
- Cero `id=` introducidos o tocados. Cero `onclick`. Cero JavaScript.
- Verificación post-edición: ninguna duplicación del topbar; las 5 referencias
  restantes a esas URLs en `despiece_maestro.html` son de bloques distintos
  (breadcrumb línea 13 — pendiente para 3J; panel de acciones inferior líneas
  430-446 — pendiente para fase posterior).
- `python manage.py check` → System check identified no issues (0 silenced).

### 13.H Cuarto partial extraído — FAB + Offcanvas "Resumen" (Fase 3H — DONE)
- **Nuevo** `templates/ingenieria/partials/_despiece_resumen_offcanvas.html`
  (60 líneas, ~17 LOC efectivas, resto cabecera documental).
- **`despiece_maestro.html`**: 17 líneas (FAB + offcanvas completo, comentario inclusive)
  reemplazadas por `{% include "ingenieria/partials/_despiece_resumen_offcanvas.html" %}`.
- Posición preservada: fuera del `<script>`, antes del `{% include "ingenieria/_checkpoint_panel.html" %}`.
- Reducción acumulada en el template monstruo desde Fase 3: **1614 → 1562** (-52).
- **IDs preservados** (críticos para `abrirResumen()` y para `window.toggleFloatingPanel(...)`):
  - `#resumenFab` — botón flotante (onclick="abrirResumen()").
  - `#resumenOffcanvas` — instanciado por `bootstrap.Offcanvas.getOrCreateInstance(...)` en `despiece_maestro.html:1554` y referenciado por `toggleFloatingPanel('resumenOffcanvas')` en línea 1506.
  - `#resumenOffcanvasTitle` — `aria-labelledby` del offcanvas.
  - `#resumenOffcanvasBody` — slot poblado vía `innerHTML` en línea 1507.
- Clases preservadas: `assist-fab`, `assist-fab--resumen`, `assist-fab__icon`,
  `assist-fab__label`, `offcanvas offcanvas-end`, `offcanvas-header`,
  `offcanvas-title`, `offcanvas-body p-0`, `btn-close`, `data-bs-dismiss="offcanvas"`.
- Verificación de no-duplicación (4 IDs en `despiece_maestro.html`): **0/0/0/0** ✅.
- **No depende** de `window.RESUMEN_DATA` (no existe). El JS usa `RESUMEN_META`
  (objeto declarado dentro del `<script>`, **no** dentro del partial), y construye
  el cuerpo del offcanvas vía `innerHTML` en `abrirResumen()`.
- Cero JS movido. Cero CSS movido. Estilos inline conservados tal cual.
- `python manage.py check` → System check identified no issues (0 silenced).

### 13.G Tercer partial extraído — modal "Ver origen de consolidación" (Fase 3G — DONE)
- **Nuevo** `templates/ingenieria/partials/_modal_origen.html` (44 líneas, ~14 LOC sin cabecera).
- **`despiece_maestro.html`**: 15 líneas del bloque modal reemplazadas por
  `{% include "ingenieria/partials/_modal_origen.html" %}`.
- Reducción acumulada en el template monstruo desde Fase 3: **1614 → 1578** (-36).
- **IDs preservados** (críticos para `verOrigen(cid)`):
  - `#modalOrigen` — instanciado por `new bootstrap.Modal(...)` en `despiece_maestro.html:1113`.
  - `#modalOrigenBody` — slot poblado vía `innerHTML` en `despiece_maestro.html:1097`.
- Clases Bootstrap preservadas: `modal fade`, `modal-dialog modal-lg`,
  `modal-content`, `modal-header`, `modal-title`, `modal-body`, `modal-footer`,
  `btn-close`, `data-bs-dismiss="modal"`.
- `grep -c 'id="modalOrigen"' despiece_maestro.html` = **0** (sin duplicado).
- `python manage.py check` → System check identified no issues (0 silenced).

### 13.F Segundo partial extraído — modal "Detalle del cálculo" (Fase 3F — DONE)
- **Nuevo** `templates/ingenieria/partials/_modal_detalle_calculo.html` (42 líneas, ~30 LOC sin cabecera).
- **`despiece_maestro.html`**: 15 líneas del bloque modal reemplazadas por
  `{% include "ingenieria/partials/_modal_detalle_calculo.html" %}`.
- Reducción acumulada en el template monstruo: **1614 → 1592** (-22).
- **IDs preservados** (críticos para `verDetalle(i)` y `verDetalleConsolidada(cid)`):
  - `#modalDetalle` — instanciado por `new bootstrap.Modal(...)` en `despiece_maestro.html:1181, 1258`.
  - `#modalDetalleBody` — slot poblado vía `innerHTML` en `despiece_maestro.html:1158, 1240`.
- Clases Bootstrap preservadas: `modal fade`, `modal-dialog`, `modal-content`,
  `modal-header`, `modal-title`, `modal-body`, `modal-footer`, `btn-close`,
  `data-bs-dismiss="modal"`.
- Cero JS movido. Cero CSS movido.
- `python manage.py check` → System check identified no issues (0 silenced).

---

## §14. Fase 5 — Adopción de cache (DONE 5B–5D)

### 14.A Diagnóstico (5A)
Inventario de call-sites en `ingenieria/views/__init__.py` (lines 157, 266, 332) y `presupuestos/services/apu_service.py` (lines 31, 69). Helpers ya presentes en `apps/common/cache.py`. Sin signals previos para los catálogos.

### 14.B Cache de unidades y categorías en Ingeniería (5B — DONE)
- `_build_unidades_medida_json()` ahora consume `get_cached_unidades()`. Shape JSON al JS preservada (`{abrev, nombre}`).
- Nuevo helper `_categorias_producto_para_template()` envuelve `get_cached_categorias()` y expone `pk` como alias de `id` para no romper `{{ cat.pk }}` en `subsistema_form.html`.
- `SubsistemaCreateView.get_context_data` y `SubsistemaUpdateView.get_context_data` usan el nuevo helper.
- Eliminado import local `from apps.catalogos.models import CategoriaProducto` (ya no requerido).

### 14.C Cache de ConfiguracionAPU (5C — DONE)
- Nuevo helper de módulo `_resolver_config_apu()` en `apps/presupuestos/services/apu_service.py`.
- `APUService.__init__` y `APUService.for_apu` lo usan; fallback a `ConfiguracionAPU.activa_o_default()` si cache vacío o id inválido (preserva auto-creación).
- Sin cambios en lógica de cálculo.

### 14.D Signals de invalidación (5D — DONE)
- `apps/catalogos/signals.py` — `post_save`/`post_delete` sobre `UnidadMedida` y `CategoriaProducto`.
- `apps/presupuestos/signals.py` — `post_save`/`post_delete` sobre `ConfiguracionAPU`.
- `CatalogosConfig.ready()` y `PresupuestosConfig.ready()` importan los signals.

### 14.E Verificación (5E — DONE)
- `python manage.py check` → System check identified no issues (0 silenced).
- Shell test: doble lectura de helpers cacheada; tras `save()` la clave se invalida (`cache.get(KEY_UNIDADES) is None`).

### 14.F No cacheado intencionalmente
- `Producto`, `ProductoProveedor`, precios.
- `ItemCatalogoAPU`.
- `apps/presupuestos/views/__init__.py:1785` (pendiente verificar template).
- Vistas CRUD del propio `apps/catalogos/views.py`.
- Resultados de cálculo, variables de entrada del usuario, snapshots persistidos.

## §15. Fase 6 — Armar mi APU (DONE 6A–6H)

### 15.A — Diagnóstico
Botón actual "Ver APU" en `templates/ingenieria/despiece_maestro.html:417–430` apuntaba a `apu_generar_despiece`, que consolidaba todos los DM del proyecto sin pedir producto principal. Decisión: reemplazar por flujo modal con producto principal + producto-base persistido en `ProyectoSistema.parametros_entrada` (sin migración).

### 15.B — Helper `obtener_lineas_finales_para_apu`
`apps/ingenieria/services/lineas_finales_apu.py`. Mapea consolidaciones + líneas no absorbidas a `LineaFinalAPU` (TypedDict). Sin queries adicionales, Decimal-safe.

### 15.C — Helper `validar_despiece_listo_para_apu`
Mismo módulo. Errores bloqueantes + advertencias separados. Listas detalladas por tipo de problema (pendientes_producto, cantidad_invalida, sin_unidad, sin_precio).

### 15.D — Botón + modal
- `_modal_armar_apu.html` (nuevo). Listado de productos candidatos (deduplicados + sumatoria de cantidad), tabla de líneas finales, botón disabled si validación falla.
- `templates/ingenieria/despiece_maestro.html:417–430`: botón principal cambia de "Ver/Generar APU" a "Armar mi APU"; "Ver APU existente" pasa a `btn-outline-secondary`.
- `apps/ingenieria/views/calculador.py`: inyecta `armar_apu_validacion` y `armar_apu_productos_opciones`.

### 15.E — Endpoint `apu_armar_desde_despiece`
- `apps/presupuestos/urls.py`: `apu/armar-desde-despiece/<int:pk>/`.
- `APUArmarDesdeDespieceView` en `apps/presupuestos/views/__init__.py`. Revalida backend, recalcula cantidad_base sumando líneas finales del producto principal, persiste en `parametros_entrada`, sincroniza `DespieceLinea` y dispara `APUService.generar(ps)`.

### 15.E.A — Fix: filtrado por subsistema
`APUArmarDesdeDespieceView` ahora filtra `todos_dm` también por `subsistema=dm.subsistema`. **Regla**: el APU de un PS solo consolida materiales del mismo proyecto Y mismo subsistema. Otros subsistemas del proyecto no contaminan el APU. Despieces múltiples del mismo subsistema sí se consolidan.

### 15.F — Cálculo de rendimiento
- Helper `calcular_rendimiento_por_producto_principal` en `apu_service.py`. Decimal con `quantize(0.000001)`, valida None/0/negativo.
- `APUService.generar_materiales` switchea por `modo_rendimiento`:
  - `PRODUCTO_PRINCIPAL` → usa el helper con `cantidad_base` del PS.
  - Sin modo o datos corruptos → fallback al cálculo legacy (`_get_total_unidades_componente`).

### 15.G — Materiales en APU detail
- `_build_categorias_context` enriquece líneas MATERIALES con `componente_nombre` (lookup batch a `ComponenteSubsistema`), `producto_nombre`, `cantidad_total`.
- `apu_detail.html` bifurca por `cat.tipo == "MATERIALES"`: tabla nueva con Componente · Producto · Cantidad · Unidad · Rendimiento · Costo unit. · Total. Otras categorías intactas.

### 15.H — Advertencias de unidad
- Helper `advertencias_unidad_linea(linea_final)` en `lineas_finales_apu.py`.
- Casos: mismatch línea↔producto, producto sin unidad, `unidad_apu` ≠ `unidad`.
- Integrado en `validar_despiece_listo_para_apu`: por línea (`advertencias_unidad`) y agregado en `advertencias`.
- Renderizado en el modal: chip ⚠️ junto al nombre + fila amarilla con detalle.
- **No bloquean** la generación.

### 15.I — No cubierto intencionalmente
- Garantías.
- Presentación técnica del producto.
- AIU (sin cambios).
- Migraciones / modelos (producto principal vive en `parametros_entrada`).
- Rediseño completo de `apu_detail`.
- `ItemCatalogoAPU` (Fase 5 no lo cacheó; Fase 6 tampoco lo toca).

### 15.E.B — Fix: APU 1:1 con el modal (sobrescribe 15.E.A)
Cambia la consolidación de "todos los DM del proyecto+subsistema" a
"solo las líneas finales del DM actual". Esto cumple la regla:

> El APU debe generarse únicamente con las líneas finales mostradas en el
> modal "Armar mi APU". No debe usar líneas antiguas ni todas las
> DespieceLinea asociadas al ProyectoSistema.

Diferencias con 15.E.A:
- 15.E.A consolidaba múltiples DM del mismo subsistema.
- 15.E.B usa solo el DM del POST.
- En ambos casos: filtrar el alcance evita contaminación con otros subsistemas
  (regla más estricta gana).

Implementación: `APUArmarDesdeDespieceView.post` reemplaza el loop sobre
`todos_dm` por una iteración directa sobre `validacion["lineas_finales"]`,
mantiene la clave `CONS_{producto_id}` para consolidadas y `componente_codigo`
para normales, hace upsert+delete sobre `DespieceLinea` del PS.

Pre-carga: 1 query a `DespieceMaestroLinea` para resolver `componente_codigo`
por pk en batch.

---

## §16 — Fase 6L: Configuración APU por subsistema

### 16.A — Diagnóstico (causas)
- `APUService._auto_generar_desde_catalogo` y
  `APUProyectoUpdateView.form_valid` traían `ItemCatalogoAPU.objects.filter(
   activo=True, categoria__tipo_apu=tipo)` → toda la biblioteca.
- No existía relación entre Subsistema y los ítems APU concretos. Solo
  `ReglaAPUSubsistema` (fórmula agregada por tipo), insuficiente para
  determinar qué ítems aplican.
- Por eso APUs con catálogo grande mostraban decenas de líneas sin sentido.

### 16.B — Modelo `SubsistemaItemAPU`
- Tabla `subsistema_items_apu`.
- UNIQUE `(subsistema, item_catalogo, tipo)`.
- Migración `0022_subsistema_item_apu` aplicada limpiamente.
- Opción B sobre A (JSONField) por integridad referencial y para evitar
  reincidir en huérfanos SET_NULL como el bug 6E-C.

### 16.C — UI dentro del subsistema_form
- Bloque "5 · Configuración APU del subsistema" en el form existente.
- Sin crear vista nueva ni formulario nuevo.
- `subsistema_service.guardar_items_apu_subsistema(subsistema, post)` —
  reemplazo completo de asociaciones del subsistema en cada submit.
- Reutiliza `SubsistemaCreateView.form_valid` y
  `SubsistemaUpdateView.form_valid`.

### 16.D — APUService usa solo SubsistemaItemAPU
- Nuevo `APUService._items_apu_subsistema(tipo_apu)`.
- `_auto_generar_desde_catalogo`: si la categoría sin asociaciones, log INFO
  y se omite. Nunca rellena con todo el catálogo.
- `APUProyectoUpdateView.form_valid`: misma regla al recalcular por cambio
  de parámetros; categorías sin ítems se limpian (`lineas.filter(...).delete()`).

### 16.E — Tarjetas informativas
- Partial nuevo: `templates/presupuestos/partials/_apu_info_card.html`.
- Datos: `views._build_info_card_data(apu)` (función pura).
- Renderizado al inicio de cada `cat` del bucle `categorias_apu`.
- Materiales: PP + cantidad/unidad + modo + fórmula + mensaje.
- No-Materiales: personas + días + ítems configurados + base + mensaje.
- Dato faltante → "No definido". Cero datos inventados.

### 16.F — Claridad de cálculo
- No se cambia ninguna fórmula.
- Las tarjetas muestran personas/días si existen, "No definido" si no.
- Fórmula visible para Materiales (texto del modo PP).

### 16.G — Búsqueda en modales APU
- Función JS `apuModalFilter(input)` agregada en `apu_detail.html`.
- Inputs `<input type="search">` insertados en los 4 modales.
- Filas con `data-search` y grupos con `apu-modal-cat-group` para
  ocultar/mostrar categorías vacías dinámicamente.
- 100% frontend. Cero queries adicionales.

### 16.H — Validaciones
- Modales (presentación): el `get_context_data` filtra `items_*` por
  `SubsistemaItemAPU`, eliminando la posibilidad de seleccionar no
  asociados.
- Backend (defensa): `_filtrar_items_por_sia(apu, tipo, items_data)` en
  `APUManoObraView` y `APUHerramientasView` descarta ítems no asociados,
  con mensaje de aviso.
- Materiales intacto.

### 16.I — Verificación
- `python manage.py makemigrations` → `0022_subsistema_item_apu` (auto).
- `python manage.py migrate` → OK.
- `python manage.py check` → `System check identified no issues (0 silenced).`

### 16.J — No cubierto intencionalmente
- Materiales (rige Fase 6F/6E-C; este lote no lo toca).
- AIU del proyecto (sin cambios).
- Modelo `ReglaAPUSubsistema` (sigue siendo la fuente de la fórmula
  agregada; ahora se complementa con `SubsistemaItemAPU` para definir qué
  ítems concretos aplican).
- Catálogo de items APU (la biblioteca completa sigue en
  `ItemCatalogoAPU`).
- Rediseño completo de `apu_detail.html` (solo se insertan info-card +
  inputs de búsqueda + estados vacíos mejorados).

---

## 17 — Fase 9 — Garantías del APU

### 17.A — Objetivo
Permitir indicar al armar o revisar un APU si la propuesta incluye
garantía y de qué tipo. La garantía **no afecta** el cálculo de
materiales, el rendimiento por producto principal, la presentación
técnica, las advertencias ni el AIU. Es parte del paquete comercial.

### 17.B — Modelo `TipoGarantia` (apps/comercial)
Catálogo administrable. Campos: `nombre`, `duracion_meses`,
`descripcion`, `condiciones`, `orden`, `activo`. Helper
`duracion_label` ("N años" / "N meses").

Se ubica en `comercial` porque la garantía es metadata comercial junto a
`TipoProyecto`, no parte del cálculo (presupuestos) ni de la ingeniería.

### 17.C — Asociación con `APUProyecto`
Dos campos nuevos opcionales (no rompen APUs legacy):
- `aplica_garantia: BooleanField(default=False)`.
- `tipo_garantia: ForeignKey(comercial.TipoGarantia, on_delete=PROTECT, null=True, blank=True)`.

`PROTECT` impide borrar un tipo en uso; la vista de delete del catálogo
captura `ProtectedError` y sugiere desactivar.

### 17.D — Catálogo `/comercial/garantias/`
Patrón Fase 8.1 (partial fields-only + wrapper):
- `templates/comercial/_garantia_form.html` (partial fields-only).
- `templates/comercial/garantia_form.html` (wrapper editar).
- `templates/comercial/garantia_list.html` (lista + modal create
  reutilizando el partial).
- Vistas: `TipoGarantiaListView/CreateView/UpdateView/DeleteView`.
- `TipoGarantiaForm` único.
- Sidebar: link "Garantías" antes de Catálogos.

### 17.E — Selección al "Armar mi APU"
- `_modal_armar_apu.html`: radio Sí/No + select de tipos activos (oculto
  si "No"), JS limpia el select al cambiar a "No".
- `calculador.py` añade `tipos_garantia_activos` al contexto.
- `APUArmarDesdeDespieceView.post`: tras `APUService.generar(ps)` lee
  `aplica_garantia` y `tipo_garantia_id` **solo si** el POST los envía.
  Re-armar sin pasar la sección no destruye la garantía existente.
- Si "Sí" sin tipo activo → `ValueError` → rollback del POST.

### 17.F — Edición desde el APU
- Tarjeta "Garantía" en `apu_detail.html` después de KPIs, antes de
  búsqueda. Aplica/Tipo/Duración + descripción + condiciones
  colapsables.
- Botón "Editar" abre `#modalEditarGarantia` con radio + select
  prellenados.
- `APUEditarGarantiaView` (POST) replica las validaciones del armar.

### 17.G — Validaciones
1. "Sí" sin tipo activo → rechazo backend.
2. "No" → `tipo_garantia=None`.
3. `activo=False` no aparece en selectores.
4. APU legacy abre sin errores.
5. Re-armar APU preserva garantía si la sección no se envía.
6. `PROTECT` + manejo `ProtectedError` en delete.

### 17.H — Verificación
- `python manage.py makemigrations comercial presupuestos` →
  `0018_tipogarantia`, `0023_apuproyecto_aplica_garantia_and_more`.
- `python manage.py migrate` → OK.
- `python manage.py check` → `System check identified no issues (0 silenced).`

### 17.I — No cubierto intencionalmente
- Cálculo de materiales / rendimiento / presentación técnica /
  advertencias — sin cambios.
- AIU y modalidades — sin cambios (Fase 10).
- `APUService.generar` — sin cambios.
- PDF cliente — pendiente de integrar la tarjeta de garantía cuando se
  ataque el PDF.
- Enforcement por rol (ASESOR_COMERCIAL / PRESUPUESTOS) — sin auth aún.

---

## 18 — Fase 9R — Corrección del concepto de garantía

**Aplicado.** La sección 17 (Fase 9H) documentaba la garantía como un
dato descriptivo (duración en meses) sin impacto comercial. Esa lectura
fue incorrecta. Esta fase la corrige: **la garantía es un recargo
comercial porcentual aplicado únicamente sobre Materiales.**

### 18.A — Decisión sobre `duracion_meses`

- Se agrega `porcentaje_recargo` Decimal al catálogo.
- `duracion_meses` se vuelve `null=True, blank=True` y se **oculta del
  formulario actual**. Permanece como campo legacy.
- **No** se realiza migración de datos: duración ≠ porcentaje, no se
  reutilizan valores existentes.

### 18.B — Modelo `TipoGarantia` (catálogo)

Campos visibles en form: `nombre`, `porcentaje_recargo`, `descripcion`,
`condiciones`, `orden`, `activo`.

`__str__` muestra `Nombre (% recargo)`. `duracion_label` tolerante a
vacío.

### 18.C — Campos nuevos en `APUProyecto`

1. `garantia_porcentaje_aplicado` — snapshot del % al momento de armar/editar.
2. `garantia_modo_aplicacion` — `TOTAL_MATERIALES` / `MATERIAL_ESPECIFICO`.
3. `garantia_material_linea` — FK `APULinea`, `on_delete=SET_NULL`.
4. `garantia_material_nombre_snapshot` — trazabilidad textual.
5. `garantia_base_valor` — base del recargo.
6. `garantia_valor_recargo` — recargo final, sumado a `total_valor_venta`.

Snapshot inmutable: si el catálogo cambia su `porcentaje_recargo`, los
APUs ya armados **no** cambian. Solo se actualizan reeditando la garantía
del APU.

### 18.D — Cálculo del recargo

Centralizado en `APUProyecto._recalcular_garantia_inline()`. Se invoca al
final de `recalcular()`:

- Si no aplica garantía o no hay snapshot → base 0, recargo 0.
- Modo `MATERIAL_ESPECIFICO` con línea válida → base = `valor_total` de
  esa línea.
- Modo `TOTAL_MATERIALES` → base = `subtotal_materiales`.
- `recargo = base * pct / 100` redondeado a 2 decimales.
- `total_valor_venta = total_valor_directo + recargo`.
- `subtotal_materiales`, `costo_total`, `APULinea.valor_total`: **sin
  cambios**.

### 18.E — UI

- **Catálogo** `/comercial/garantias/`: form muestra "Porcentaje de
  recargo (%)". Lista muestra columna `% Recargo`.
- **Modal "Armar mi APU"**: Sí/No → Tipo → muestra `%` → Modo → si modo
  específico, selector con `armar_apu_validacion.lineas_finales`.
- **Modal "Editar garantía"** en `apu_detail.html`: mismo flujo,
  selector de material desde `lineas_materiales_apu` (APULinea reales).
- **Tarjeta Garantía** en `apu_detail.html`: Aplica · Tipo · % · Modo ·
  Material · Base · Recargo. Advertencias para legacy y material
  ausente.
- **KPI "Valor total"**: filas "Recargo garantía" y "Materiales
  ajustado" cuando aplique.
- **Tabla Materiales**: badge "Garantía aplicada" en la línea objetivo.

### 18.F — Vistas

- Helper compartido `_aplicar_garantia_desde_post()` en
  `apps/presupuestos/views/__init__.py`. Se usa tanto en
  `APUArmarDesdeDespieceView` (durante armado) como en
  `APUEditarGarantiaView` (desde apu_detail).
- Validaciones backend (8 reglas — ver ARCHITECTURE 10.8).

### 18.G — Compatibilidad con APUs Fase 9

- APUs con `aplica_garantia=True` pero sin
  `garantia_porcentaje_aplicado` (creados antes de Fase 9R):
  - Abren sin error.
  - Recargo = 0 (no se asume nada).
  - Tarjeta muestra advertencia visual "Esta garantía fue creada antes
    del recargo porcentual. Reedite la garantía para aplicar el
    porcentaje."

### 18.H — Migraciones

1. `comercial/0019_tipogarantia_porcentaje_recargo_and_more.py` —
   agrega `porcentaje_recargo`; `duracion_meses` → null/blank.
2. `presupuestos/0024_apuproyecto_garantia_base_valor_and_more.py` —
   agrega los 6 campos nuevos.

Sin `RunPython` destructivo.

### 18.I — Verificación

```bash
python manage.py makemigrations comercial presupuestos
python manage.py migrate
python manage.py check   # → System check identified no issues (0 silenced).
```

### 18.J — No cubierto intencionalmente

- AIU y modalidades — Fase 10.
- Precios por línea ajustables por revisor — fase posterior.
- Enforcement por rol — sin auth aún.
- Migración de duración → porcentaje — descartada explícitamente.

---

## 19. Fase 10A — AIU final del proyecto (Modalidad 1 y 2)

Cierra el flujo de revisión y aprobación del AIU **final del proyecto**,
introducido al pausar Fase 10 original. Garantía Red Shield queda fuera
de la base AIU (decisión 10A-2 Opción A).

### 19.A — Decisión sobre garantía en base AIU (Opción A)

```
base_aiu_modalidad_1 = mat_tecnico + herr + tran + mano_obra + adm
base_aiu_modalidad_2 =                herr + tran + mano_obra + adm
gran_total_aprobado  = subtotal_directos_tecnico + total_aiu + garantia_valor_recargo
```

Garantía Red Shield:
- ❌ NO entra en `base_aiu`.
- ✅ Sigue afectando `APUProyecto.total_valor_venta`.
- ✅ Se suma al `gran_total` de cada modalidad después del AIU.

Reversible cambiando `calcular_modalidades_aiu()`.

### 19.B — Campos nuevos en `APUProyecto`

| Campo | Tipo | Default | Uso |
|---|---|---|---|
| `aiu_final_admin_pct` | Decimal(8,4) null/blank | NULL | Snapshot Admin% aprobado |
| `aiu_final_imprevistos_pct` | Decimal(8,4) null/blank | NULL | Snapshot Imprev% aprobado |
| `aiu_final_utilidad_pct` | Decimal(8,4) null/blank | NULL | Snapshot Util% aprobado |

Si los 3 están en NULL: se usa `aiu_proyecto_*_pct` base.

### 19.C — Helper `get_aiu_pct_efectivos()`

Devuelve `{admin, imprevistos, utilidad, es_final}`. Resuelve preferencia
final → base. Lo usa `calcular_modalidades_aiu()` y los templates.

### 19.D — Cálculo: `calcular_modalidades_aiu(pct_override=None)`

- Modalidad 1: AIU sobre todos los costos directos técnicos.
- Modalidad 2: AIU sobre costos directos técnicos sin Materiales.
- Modalidades 3 y 4: rechazadas con mensaje claro.
- Gran total incluye `garantia_valor_recargo` después del AIU.
- `pct_override`: usado por la vista de revisión para preview sin persistir.

### 19.E — Vista del revisor (`apu_revisar.html`)

- GET pinta porcentajes efectivos.
- POST a `apu_revisar` con A/I/U → preview recalculado en el mismo render.
- Form de aprobación reenvía A/I/U como hidden y guarda en
  `APUAprobarModalidadView`.
- Botón "Cambiar modalidad" → POST a nuevo endpoint `apu_reset_modalidad`.

### 19.F — `APUAprobarModalidadView` (actualizada)

Persiste: `modalidad_aiu_seleccionada`, `aiu_final_*_pct` (si vienen),
`aprobado_por`, `fecha_aprobacion`.
Avanza proyecto → COTIZADO, solicitud → APROBADA.
Valida: modalidad ∈ {"1","2"}, porcentajes ≥ 0.

### 19.G — `APUResetModalidadView` (nueva)

`POST /presupuestos/apu/<pk>/reset-modalidad/`. Limpia
`modalidad_aiu_seleccionada`, `aprobado_por`, `fecha_aprobacion`.
Conserva `aiu_final_*_pct`.

### 19.H — Vista APU detail

- Tarjeta verde "Modalidad AIU aprobada" con porcentajes efectivos,
  total AIU, garantía Red Shield y gran total.
- Si pendiente: badge "Pendiente de revisión" + modalidades informativas.
- No permite seleccionar modalidad desde aquí.

### 19.I — Limpieza de "cuadrilla" en UI final

Templates ajustados visualmente. IDs de modelos `CuadrillaPreset` y
`CuadrillaPresetItem` se mantienen para no romper formsets ni cálculos.

### 19.J — Migración

`presupuestos/0025_apuproyecto_aiu_final_admin_pct_and_more.py` —
3 AddFields. Sin `RunPython`.

### 19.K — Verificación

```bash
python manage.py makemigrations presupuestos
python manage.py migrate
python manage.py check   # → System check identified no issues (0 silenced).
```

### 19.L — No cubierto intencionalmente

- Modalidades 3 y 4 — pendiente fórmula exacta.
- Ajustes por línea por revisor — Fase 11.
- Enforcement por rol — pendiente.
- Garantía en base AIU — Opción B descartada en 10A; revisable en fase futura.

---

## 20. Fase 11 — Cotización final en pantalla

### 20.A Decisión: vista calculada
No se crea modelo `CotizacionFinal`. La cotización deriva de `APUProyecto` y se
calcula en cada render. Snapshot formal queda para fase posterior.

### 20.B Helper `get_resumen_cotizacion()` en `APUProyecto`
Centraliza la matemática. Devuelve subtotales técnicos, garantía, AIU efectivo,
IVA, total final y bloques relacionales (cliente, proyecto, sistema,
subsistema, contacto).

### 20.C IVA sobre Utilidad
Decisión Fase 11 (Excel técnico): `iva_valor = valor_utilidad * iva_pct / 100`.
Si `aplica_iva=False`, iva_valor=0 y label "Exento / No aplica".

### 20.D Garantía Red Shield
Se mantiene la definición de Fase 9R: recargo sobre Materiales, fuera de la
base AIU y fuera de la base IVA. Se suma al total como concepto separado.

### 20.E Fórmula
```
total_final = subtotal_directos_tecnico
            + total_aiu
            + garantia_valor_recargo
            + iva_sobre_utilidad
```

### 20.F Ruta y vista
- `apu/<int:pk>/cotizacion/` → `APUCotizacionFinalView` → name
  `apu_cotizacion_final`.
- Preliminar si no hay modalidad aprobada; oficial si la hay.

### 20.G Template `templates/presupuestos/apu_cotizacion_final.html`
Estructura comercial; tabla por categoría; sin información técnica interna;
sin "Cuadrilla".

### 20.H Botón en `apu_detail.html`
Condicional según `modalidad_aiu_seleccionada`.

### 20.I Sin migraciones
No se agregan campos ni tablas en esta fase.

### 20.J Pendiente para fases futuras
- PDF de cotización.
- Modelo `CotizacionFinal` + versionamiento.
- Campos comerciales (forma de pago, validez, exclusiones).
- Modalidades 3 y 4, ajustes por línea, permisos por rol.

## 21. Fase 11.1 — PDF descargable y reversión de estados

### 21.A Mover plantillas PDF
- `templates/presupuestos/apu_pdf_interno.html` → `templates/presupuestos/pdf/apu_pdf_interno.html`.
- `templates/presupuestos/apu_pdf_cliente.html` → `templates/presupuestos/pdf/apu_pdf_cliente.html`.
- `apu_cotizacion_final.html` **no** se mueve.

### 21.B Activar WeasyPrint en `APUPDFInternoView` y `APUPDFClienteView`
- Import perezoso de `weasyprint.HTML` dentro de `get`.
- `HTML(string=..., base_url=request.build_absolute_uri("/")).write_pdf()`
- `HttpResponse(pdf_bytes, content_type="application/pdf")` con
  `Content-Disposition: attachment; filename="..."`.
- No se escribe nada a disco.

### 21.C PDF Cliente usa `get_resumen_cotizacion()`
- Variable `resumen` se inyecta en el contexto del template.
- Toda la matemática de garantía, AIU, IVA y total final viene del helper.
- No se duplica lógica en el template.

### 21.D Reset modalidad revierte estados
- `Proyecto → APU_GENERADO`
- `Solicitud → EN_REVISION`
- Conserva `aiu_final_*_pct`.

### 21.E No persistencia
- Verificado: ningún archivo PDF se crea en `static/`, `media/`, raíz ni
  carpetas auxiliares como resultado de la generación.

### 21.F Verificación
- `python manage.py check` sin errores.
- Sin migraciones nuevas.

### 21.G Riesgo conocido
- WeasyPrint requiere `libgobject` / Pango / Cairo. Si no están instaladas
  en el sistema, los botones PDF fallan con `OSError` por diseño (error
  explícito, sin fallback silencioso). Instalación en macOS:
  `brew install pango`.


## 22. Fase 11.3 — Agrupación por APU y unificación de documentos

### 22.A Botones de cotización final fuera de la UI
- Removidos enlaces a `apu_cotizacion_final` de `apu_detail.html`,
  `proyecto_detail.html` y `solicitud_detail.html`.
- Vista `APUCotizacionFinalView` y ruta `apu_cotizacion_final` intactas
  como vista técnica/debug.
- Sin guard `staff_member_required` (decisión explícita).

### 22.B PDF Interno con resumen comercial
- Añadida sección final "Resumen comercial / Cotización interna" usando
  `apu.get_resumen_cotizacion()`.
- Incluye: subtotales por categoría, garantía Red Shield, AIU aprobado
  (A/I/U), IVA sobre Utilidad, total final, modalidad, aprobador, fecha.
- Sin duplicar matemática: solo `currency_nodec` sobre el dict del resumen.
- Detalle técnico previo (tablas por categoría) conservado.

### 22.C PDF Cliente
- Banner "Documento preliminar" si `resumen.es_preliminar`.
- Bloque final con modalidad/aprobador/fecha/garantía.
- Sin costos internos ni rendimientos.

### 22.D Helper `APUProyecto.get_despieces_incluidos()`
- Filtro aproximado: `proyecto + subsistema + estado=GUARDADO`.
- Sin migración. Sin M2M nueva.

### 22.E Agrupación por APU en views
- `ProyectoDetailView` y `SolicitudDetailView` reagrupan en `apus_data`
  + `despieces_sin_apu`.
- Templates renderizan tarjeta única por APU con DMs incluidos como lista,
  botones (`Ver APU`, `PDF Interno`, `PDF Cliente`) y metadatos de
  aprobación.

### 22.F Pendiente para Fase 11.4
- Selección manual de despieces al generar APU:
  `APUGenerarDesdeDespiece` consolida automáticamente todos los DMs
  guardados del proyecto. Hay que intercalar una vista de confirmación
  (`APUGenerarConfirmarView`) que permita al usuario elegir cuáles
  incluir antes de generar/regenerar el APU.

### 22.G Verificación
- `python manage.py check` sin errores.
- Sin migraciones nuevas.


## 23. Fase 11.4 — Selección manual de despieces y APU multi-despiece

### 23.A Objetivo
Sustituir la consolidación automática de despieces por una **selección
manual explícita** con relación de BD dedicada. Trazabilidad real
APU↔DespieceMaestro, agrupación visual por subsistema, soporte para
proyectos grandes multisistema.

### 23.B Cambios de modelo (migración 0026)
- `APUDespieceIncluido` (tabla `apu_despieces_incluidos`): `apu` FK,
  `despiece_maestro` FK PROTECT, snapshots de sistema/subsistema, `orden`,
  `activo`, timestamps; `unique_together = (apu, despiece_maestro)`.
- `APULinea` + `despiece_maestro` (SET_NULL), `sistema_nombre_snapshot`,
  `subsistema_nombre_snapshot`.
- `APUProyecto.proyecto_sistema` permanece `OneToOneField` (PS raíz).

### 23.C Servicios añadidos
- `apps/presupuestos/services/despiece_selection.py`
  → `DespieceSelectionStrategy` (Strategy).
- `apps/presupuestos/services/apu_multi_builder.py`
  → `APUMultiDespieceBuilder` (Builder).
- `APUFacade.generar_desde_seleccion()` (Facade) en `apu_facade.py`.

### 23.D Vista de selección
- `APUSeleccionarDespiecesView` (`presupuestos/apu/seleccionar-despieces/<pk>/`).
- Template `templates/presupuestos/apu_seleccionar_despieces.html`.
- `APUGenerarDesdeDespiece` queda como wrapper de compatibilidad.

### 23.E UI y PDFs
- `apu_detail.html`: banner legacy, tarjeta de despieces incluidos, aviso
  multi-despiece y sub-bloques de materiales por subsistema (cuando el
  APU consolida varios DMs).
- `apu_pdf_interno.html`: tabla de materiales con encabezados por
  subsistema (`regroup`).
- `apu_pdf_cliente.html`: bloque "Alcance por sistema/subsistema" sin
  costos internos.
- `proyecto_detail.html` y `solicitud_detail.html` siguen consumiendo el
  helper `get_despieces_incluidos()`, que ahora lee la relación real con
  fallback legacy.

### 23.F Reglas de cálculo
- Despiece raíz: lógica actual de rendimiento.
- DMs secundarios: `rendimiento = cantidad bruta`, sin forzar contra el
  raíz. Caso degenerado → `rendimiento = 1`.
- No materiales: una sola configuración base; aviso visible cuando hay >1
  despiece incluido. Multi-sistema no-materiales queda diferido.

### 23.G Verificación
- `python manage.py makemigrations presupuestos` → migración 0026 creada.
- `python manage.py migrate` → OK.
- `python manage.py check` → **"System check identified no issues (0 silenced)."**

### 23.H Pruebas manuales recomendadas
1. Proyecto con un solo DM → genera APU directo, sin paso intermedio.
2. Proyecto con varios DMs → muestra `apu_seleccionar_despieces`.
3. Seleccionar solo el origen → APU contiene únicamente materiales del DM
   origen.
4. Seleccionar varios DMs de distintos sistemas → materiales separados
   por sistema/subsistema en `apu_detail`.
5. PDF Interno → sub-encabezados azules por subsistema en la tabla de
   materiales.
6. PDF Cliente → bloque "Alcance por sistema/subsistema" antes del total,
   sin costos.
7. APU sin `APUDespieceIncluido` → banner amarillo "APU legacy" en
   `apu_detail`. Fallback inferido sigue funcionando.
8. APU con un solo despiece → tabla de materiales tradicional sin
   sub-encabezados.
9. Categorías no materiales no se duplican aunque haya múltiples DMs.
10. `python manage.py check` → sin errores.


## 24. Fase 11.5 — Consolidación opcional de APUs

> *La consolidación de APUs es opcional y solo se ejecuta por confirmación
> explícita del usuario. Los APUs individuales conservan su independencia y
> trazabilidad.*

### 24.A Decisiones aprobadas
- Reutilizar `APUProyecto` con campo discriminador `tipo_apu`.
- Persistir consolidado (no vista temporal): permite PDF + trazabilidad.
- `APUConsolidadoOrigen` como tabla intermedia.
- `APULinea.apu_origen` para trazabilidad por línea.
- Materiales: unión acumulativa. No-materiales: dedup por
  `(item_catalogo_id, tipo)` + fallback `(tipo, descripción_norm, unidad)`.
- Conservar la línea de mayor `costo_total` al deduplicar (peor caso).
- Consolidado nace sin garantía y sin modalidad/aprobación.

### 24.B Modelo
- `APUProyecto.tipo_apu`, `APUProyecto.proyecto`, helper `es_consolidado`,
  helper `get_apus_origen`.
- `APULinea.apu_origen` FK SET_NULL.
- `APUConsolidadoOrigen` con `unique_together (apu_consolidado, apu_origen)`
  + `orden` + `incluido_en_pdf_cliente`.
- Migración 0027.

### 24.C Servicios
- `apu_merge_strategies.py`: `LineaPlantilla`, `MaterialesUnionStrategy`,
  `NoMaterialesDedupStrategy`, `construir_resumen_preview`.
- `apu_consolidado_builder.py`: `APUConsolidadoBuilder` transaccional.
- `apu_consolidacion_facade.py`: `APUConsolidacionFacade.validar / preview
  / consolidar`.

### 24.D Vistas y URLs
- `APUConsolidarSeleccionarView` → `proyectos/<pk>/apu/consolidar/`.
- `APUConsolidarPreviewView` → `proyectos/<pk>/apu/consolidar/preview/`.
- `APUConsolidarConfirmarView` → `proyectos/<pk>/apu/consolidar/confirmar/`.

### 24.E Templates
- `apu_consolidar_seleccionar.html`, `apu_consolidar_preview.html`,
  bloques en `apu_detail.html`, `pdf/apu_pdf_interno.html`,
  `pdf/apu_pdf_cliente.html`, `comercial/proyecto_detail.html` y
  `comercial/solicitud_detail.html`.

### 24.F Verificación
- `python manage.py makemigrations presupuestos` → 0027.
- `python manage.py migrate` → OK.
- `python manage.py check` → **"System check identified no issues (0 silenced)."**

### 24.G Pruebas manuales recomendadas
1. Proyecto con 1 APU individual → NO aparece el botón "Unir APUs".
2. Proyecto con 2+ APUs individuales → aparece botón opcional "Unir APUs".
3. Click → `APUConsolidarSeleccionarView` muestra checklist.
4. Selección de 1 solo APU → preview rechaza con mensaje.
5. Selección ≥2 → preview muestra resumen + advertencias.
6. Cancelar en preview → vuelve a `proyecto_detail` sin crear nada.
7. Confirmar → crea APU consolidado y redirige a `apu_detail`.
8. APU consolidado muestra badge **CONSOLIDADO** y lista de APUs origen.
9. APUs origen conservan su estado (no se ocultan ni archivan).
10. PDF Interno del consolidado muestra bloque "APUs origen" tras KPIs.
11. PDF Cliente del consolidado muestra "Alcance consolidado" sin costos.
12. Materiales: aparecen todas las líneas, agrupadas por sistema/subsistema.
13. No-materiales: equivalentes deduplicados a una sola línea.
14. Consolidado nace sin garantía Red Shield aplicada.
15. Consolidado nace sin modalidad AIU aprobada — flujo de revisión propio.
16. `solicitud_detail` muestra banner de estado y resumen de APUs.
17. `python manage.py check` → sin errores.

### 24.H Restricciones cumplidas
Sin tocar garantía Red Shield matemática, AIU matemático, Modalidades 3/4,
descarga de PDFs, permisos, estados/choices, Despiece Maestro ni la
generación de APUs individuales de Fase 11.4. No se usa "Cuadrilla".
No se duplican no-materiales por cada APU. No se consolida sin
confirmación explícita.

### 24.I Fase 11.5.1 — Mejoras de visibilidad
Cambios sin tocar modelo, migración, Builder, Facade ni matemática.

Archivos modificados:
- `apps/presupuestos/services/apu_merge_strategies.py` — `ResumenPreview`
  añade `materiales_por_origen` y `no_materiales_conservados`;
  `construir_resumen_preview()` los rellena.
- `templates/presupuestos/apu_consolidar_preview.html` — bloques
  "Materiales que se consolidarán" y "No-materiales — Se conservan /
  Se deduplicaron".
- `apps/presupuestos/views/__init__.py` — `APUProyectoDetailView`
  expone `materiales_por_origen_consolidado` y `resumen_consolidacion`
  cuando `es_consolidado`.
- `templates/presupuestos/apu_detail.html` — bloque "Resumen de
  consolidación" + materiales agrupados por APU origen con `<details>`.
- `templates/comercial/proyecto_detail.html` — botón
  "Unir APUs y consolidar materiales" + ayuda explícita.
- `templates/presupuestos/apu_consolidar_seleccionar.html` — título y
  copy actualizados.

Pruebas manuales:
1. Selecciona 2 APUs → preview muestra "Materiales que se consolidarán".
2. Cada APU origen tiene su panel con tablas por sistema/subsistema.
3. No-materiales: dos columnas (Se conservan / Se deduplicaron).
4. Confirmar → APU consolidado muestra "Resumen de consolidación".
5. Materiales agrupados por APU origen con `<details>` colapsables.
6. `proyecto_detail.html`: botón con texto y ayuda nuevos.
7. `python manage.py check` → sin errores.

### 24.J Fase 11.5.2 — PDFs del APU consolidado

**Causa raíz.** Las vistas PDF Interno/Cliente no recibían el contexto
consolidado y los templates dependían de `apu.proyecto_sistema`, que en
consolidado es `None`.

**Cambios.**
- `apps/presupuestos/views/__init__.py`:
  - Nuevo helper privado `_build_apu_consolidado_context(apu)`.
  - Refactor de `APUProyectoDetailView.get_context_data` para reutilizar el
    helper.
  - `APUPDFInternoView.get`: agrega `proyecto = apu.get_proyecto()` y, si
    `es_consolidado`, fusiona el helper en el contexto.
  - `APUPDFClienteView.get`: ídem.
- `templates/presupuestos/pdf/apu_pdf_interno.html`:
  - Header y banner usan `proyecto` (independiente de `proyecto_sistema`).
  - Bloque "Resumen de consolidación" con 6 KPIs.
  - Bloque "APUs origen" con tabla (estado + modalidad).
  - Sección Materiales: rama `es_consolidado` agrupa por APU origen →
    sistema/subsistema. Tablas planas, WeasyPrint-safe.
- `templates/presupuestos/pdf/apu_pdf_cliente.html`:
  - Header y banner-obra usan `proyecto`.
  - Banner preliminar diferencia "APU consolidado sin AIU aprobada".
  - "Alcance consolidado" enriquecido con sistemas/subsistemas.
  - Nota usa `proyecto.observaciones`.
- `docs/ARCHITECTURE.md` §16.11.

**No tocado:** modelos, migraciones, Builder, Facade, Strategy, AIU,
garantía Red Shield, aprobación, estados, descarga de PDFs, APUs
individuales, flujo de consolidación.

**Verificación.** `python manage.py check` → "System check identified no
issues (0 silenced)."

**Pruebas manuales recomendadas.**
1. PDF Interno de APU individual → sigue funcionando (regresión).
2. PDF Cliente de APU individual → sigue funcionando (regresión).
3. PDF Interno de APU consolidado → muestra proyecto/cliente en cabecera,
   resumen de consolidación, APUs origen, materiales agrupados por origen,
   no-materiales deduplicados y resumen comercial.
4. PDF Cliente de APU consolidado → muestra proyecto, cliente, alcance
   consolidado, resumen comercial; sin costos internos.
5. APU consolidado sin aprobación → PDF Cliente muestra banner "Documento
   preliminar — APU consolidado sin modalidad AIU aprobada".
6. APU consolidado aprobado → modalidad, aprobador y fecha visibles.
7. Los PDFs no se persisten en disco (siguen siendo `attachment` en memoria).


### 24.K Fase 11.5.3 — Eliminación vs Archivado (2026-06)

**Origen:** `ProtectedError` al intentar eliminar Solicitud/Proyecto/Despiece
con relaciones críticas → pantalla amarilla de Django.

#### Cambios

1. **Manejo de `ProtectedError`** (sin migración):
   - `SolicitudDeleteView` → mensaje amigable + redirect al detalle.
   - `ProyectoDeleteView` → idem.
   - `EliminarDespieceMaestroView` → idem.

2. **Vistas de archivado** (Solicitud/Proyecto sin migración, APU con
   migración 0028):
   - `SolicitudArchivarView` → `EstadoSolicitud.CERRADA`.
   - `ProyectoAnularView` → `EstadoProyecto.ANULADO`.
   - `APUArchivarView` → setea `archivado=True` + metadatos.

3. **Migración 0028** `apuproyecto_archivado_…`:
   - Agrega `archivado`, `fecha_archivado`, `archivado_por`, `motivo_archivado`.
   - No altera FKs ni `on_delete`.

4. **UI**:
   - `solicitud_detail` → botón Archivar cuando hay proyectos.
   - `proyecto_detail` → botón Anular + modal.
   - `apu_detail` → banners contextuales + botón Archivar con motivo.
   - `apu_list` → toggle `?archivados=1`.

5. **No tocado**: PROTECT en `APUConsolidadoOrigen.apu_origen` y
   `APUDespieceIncluido.despiece_maestro`; Builder; Facade; Strategies;
   matemática AIU; garantía Red Shield; modalidad; PDFs; consolidación.

#### Verificación

- `python manage.py makemigrations presupuestos` → 0028 creada
- `python manage.py migrate` → OK
- `python manage.py check` → 0 issues

#### Pruebas manuales recomendadas

1. Eliminar solicitud sin relaciones → eliminada.
2. Eliminar solicitud con proyectos → mensaje amigable, sin pantalla amarilla.
3. Archivar solicitud → estado CERRADA, trazabilidad intacta.
4. Eliminar proyecto con APUs → mensaje amigable.
5. Anular proyecto → estado ANULADO.
6. Eliminar despiece incluido en APU → mensaje amigable.
7. Archivar APU individual origen de consolidado → APU queda archivado,
   relación `APUConsolidadoOrigen` intacta, consolidado sigue funcionando.
8. Archivar APU consolidado → no borra APUs origen.
9. Lista de APUs → archivados ocultos por defecto; `?archivados=1` los muestra.
10. `python manage.py check` → sin errores.


### 24.L Fase 11.5.4 — Devolución vs Rechazo (2026-06)

**Origen:** "Rechazar" era conceptualmente incorrecto — este sistema rastrea
el proceso interno de presupuesto, no la decisión comercial del cliente.

#### Cambios

1. `EstadoSolicitud`: nuevo choice `DEVUELTA`. `RECHAZADA` se mantiene por
   compatibilidad de datos legacy pero la UI lo trata como "Devuelta".
2. `Solicitud.motivo_devolucion` (TextField, blank, default="") — paralelo
   al `Proyecto.motivo_devolucion`.
3. `SolicitudDevolverView` + URL `comercial:solicitud_devolver`.
4. Migración `comercial.0020_solicitud_motivo_devolucion_alter_solicitud_estado`.
5. UI: banner DEVUELTA + CERRADA, botón "Devolver" con modal motivo,
   solicitud_list pinta DEVUELTA/RECHAZADA como "Devuelta" (badge ámbar).
6. Aprobación AIU resuelve la devolución: `APUAprobarModalidadView` ya marca
   `APROBADA` y eso aplica tanto si venía de `EN_REVISION` como de `DEVUELTA`.

#### Verificación

- `python manage.py makemigrations` → 0020 generada.
- `python manage.py migrate` → OK.
- `python manage.py check` → 0 issues.

#### Pruebas manuales recomendadas

1. Solicitud EN_REVISION → "Devolver" con motivo → estado DEVUELTA, motivo visible en banner.
2. Solicitud DEVUELTA → editar → re-enviar a revisión → vuelve a EN_REVISION.
3. Aprobar APU desde solicitud DEVUELTA → solicitud pasa a APROBADA (devolución resuelta).
4. Datos legacy con estado RECHAZADA → UI muestra "Devuelta" (badge ámbar).
5. Solicitud DEVUELTA → "Archivar" → CERRADA.
6. solicitud_list muestra "Devuelta" para DEVUELTA y RECHAZADA.
7. Banner CERRADA visible cuando aplica.

#### No tocado

AIU, garantía Red Shield, PDFs, archivado/anulación de Fase 11.5.3, PROTECT,
consolidación, Fase 12. No se usa "Rechazar/Rechazada" en la UI.

## §24.M — Fase 12 · CotizacionAPU snapshot

### Changelog

- **NUEVO** `apps/presupuestos/models/cotizacion.py`: modelo `CotizacionAPU`
  con FK PROTECT a `APUProyecto`, FK SET_NULL a `Proyecto`/`Solicitud`/`Cliente`,
  snapshots textuales (cliente, proyecto, solicitud, moneda, garantía,
  aprobador), subtotales técnicos, AIU final, garantía Red Shield, IVA,
  `total_final`, `version`, `estado` (APROBADA/REEMPLAZADA), `data_snapshot`
  JSONField con líneas, despieces incluidos y bloque consolidado.
- **NUEVO** `apps/presupuestos/services/cotizacion_snapshot_service.py`:
  `CotizacionSnapshotService` con `crear_snapshot`, `obtener_snapshot_vigente`
  y `construir_contexto_pdf` (rehidrata dict con la forma de
  `get_resumen_cotizacion()` para reutilizar plantillas WeasyPrint).
- **NUEVO** vistas `CotizacionPDFInternoView` y `CotizacionPDFClienteView` en
  `apps/presupuestos/views/__init__.py` + rutas `cotizacion/<pk>/pdf-interno/`
  y `cotizacion/<pk>/pdf-cliente/` en `apps/presupuestos/urls.py`.
- **MOD** `APUAprobarModalidadView`: tras guardar estados, invoca
  `CotizacionSnapshotService.crear_snapshot(apu)` y registra `v{n}` en el
  mensaje de éxito.
- **MOD** `APUProyectoDetailView.get_context_data`: agrega
  `cotizacion_vigente` y `cotizaciones_historico` al contexto.
- **MOD** `APUProyecto.cotizacion_vigente` (property): devuelve la última
  `CotizacionAPU` con `estado=APROBADA`.
- **MOD** `templates/presupuestos/apu_detail.html`: bloque "Cotización
  aprobada" con versión, fecha, aprobador, total, botones PDF aprobados y
  versiones anteriores; mensaje "Sin cotización aprobada" si no hay snapshot.
- **MOD** `templates/comercial/proyecto_detail.html` y
  `templates/comercial/solicitud_detail.html`: badge "Cotización aprobada v{n}"
  + botones PDF aprobados por APU listado. Los PDFs vivos se etiquetan como
  "(vivo)" para distinguirlos.
- **NUEVO** migración `apps/presupuestos/migrations/0029_cotizacionapu.py`.

### Pruebas manuales

1. APU sin aprobar → `apu_detail` muestra "Sin cotización aprobada".
   `apu.cotizacion_vigente == None`.
2. Aprobar modalidad AIU de un APU → mensaje incluye "Cotización aprobada v1".
   El bloque verde aparece con total, fecha, aprobado por.
3. Descargar "PDF Interno aprobado" y "PDF Cliente aprobado" desde
   `apu_detail` → ambos descargan con consecutivo `{proyecto.consecutivo}-COT-v1`.
4. Modificar una línea del APU después de aprobado → recalcular subtotales.
   Descargar otra vez el PDF aprobado → totales NO cambian. Descargar el PDF
   vivo → totales SÍ reflejan el cambio.
5. Resetear modalidad → Proyecto y Solicitud vuelven a revisión. El bloque
   "Cotización aprobada v1" sigue visible en `apu_detail`.
6. Re-aprobar → mensaje "Cotización aprobada v2". v1 queda en
   `cotizaciones_historico` (chip pequeño con links a PDFs históricos). v2 es
   la vigente.
7. APU consolidado: aprobar → snapshot guarda `data_snapshot.consolidado` con
   `apus_origen`. PDF Cliente aprobado de consolidado lista los orígenes.
8. Solicitud DEVUELTA → no borra snapshots históricos. Aprobar APU otra vez →
   nueva versión.
9. `proyecto_detail`: por cada APU con `cotizacion_vigente`, badge verde +
   botones "PDF Interno/Cliente aprobado" visibles.
10. `solicitud_detail`: mismo comportamiento.

### Restricciones honradas

NO se tocó: AIU matemático, garantía Red Shield, Modalidad 3/4,
consolidación, Builder, Facade, Strategies, descarga de PDFs vivos,
archivado/anulación, PROTECT, PDFs físicos, Fase 12 fuera del alcance.
No se usa la palabra "Cuadrilla".

## §25 — Fase 12.2: Seguridad del flujo de aprobación

### Cambios

- Nuevo `apps/common/auth.py` con `get_usuario_actual`, `es_admin`,
  `puede_aprobar_apu`, `puede_enviar_a_revision`, `puede_devolver_solicitud`.
  Python 3.9 safe (sin PEP 604 `X | None`).
- `APUEnviarRevisionView`, `APUAprobarModalidadView`, `APUResetModalidadView`
  añaden gate de permisos + log + redirect con error si el usuario no
  está autorizado.
- `APUAprobarModalidadView`: `apu.aprobado_por = get_usuario_actual(request)`,
  ya no se acepta `aprobado_por_id` del form.
- `APURevisarView`: añade contexto `puede_aprobar`, `es_aprobador_asignado`,
  `es_administrador`, `usuario_actual` (la pantalla sigue siendo accesible
  como vista informativa).
- `SolicitudDevolverView`: gate de permisos + `motivo` obligatorio.
- `_usuario_sistema` en `apps/comercial/views.py`: acepta `session["usuario_id"]`
  como fuente real (antes leía sólo `configuracion_id`, que no se setea).
- `SolicitudDetailView`: añade `puede_devolver` al contexto.
- `APUProyectoDetailView`: añade `puede_aprobar`, `puede_enviar_revision`,
  `es_administrador`, `es_aprobador_asignado`, `usuario_actual`.
- Templates: `apu_detail.html`, `apu_revisar.html`, `solicitud_detail.html`
  condicionan botones/forms; `apu_revisar.html` quita el select
  `aprobado_por_id` y añade modal de devolución con motivo obligatorio.

### Sin migraciones

No se crearon campos nuevos. Se reutiliza `APUProyecto.revisor` como
"aprobador asignado".

### Pruebas manuales

1. Usuario comercial envía APU a revisión asignando revisor → APU queda
   pendiente de aprobación por X.
2. Usuario no aprobador abre el APU → no ve botón aprobar; ve "Pendiente
   de aprobación por: X."
3. Usuario no aprobador POST a `/apu/<pk>/aprobar-modalidad/` por URL
   directa → no aprueba, no crea snapshot, no cambia estados, log
   `APROBACION_DENEGADA`.
4. Revisor asignado entra a revisión → ve banner azul, botones Aprobar /
   Devolver.
5. Revisor aprueba → APU aprobado, Proyecto COTIZADO, Solicitud APROBADA,
   `CotizacionAPU` v+1 creado, log `APROBAR_MODALIDAD`.
6. Revisor devuelve con motivo → Solicitud DEVUELTA, motivo guardado, sin
   snapshot nuevo.
7. Revisor devuelve sin motivo → bloqueado, error y no cambia estado.
8. ADMIN aprueba sin ser revisor → permitido.
9. SOLO_LECTURA intenta enviar o aprobar → bloqueado.
10. Reset modalidad por usuario no autorizado → bloqueado, log.
11. `python manage.py check` → 0 issues, sin migraciones.

### Restricciones honradas

No se tocó AIU matemático, garantía Red Shield, snapshot CotizacionAPU,
Builder, Facade, Strategies, PDFs (sólo enlaces/botones), archivado /
anulación, PROTECT, ni Fase 13. No se usa "Cuadrilla".


## §26 — Fase 12.3: Administrador inicial seguro + tema ADMINISTRADOR

### Cambios

1. **`apps/configuracion/management/commands/ensure_default_admin.py`** —
   nuevo comando idempotente que crea el administrador inicial desde
   variables de entorno (`ANDINACOST_ADMIN_*`). Valida longitud mínima
   y blacklist. Guarda siempre `make_password`. Nunca imprime la
   contraseña.

2. **`apps/configuracion/views.py`** — migración a `check_password`
   con auto-upgrade transparente (`_es_hash_django`,
   `_verificar_password`). `ConfiguracionCreateView.form_valid` y
   `ConfiguracionUpdateView.form_valid` ahora hashean siempre antes
   de guardar.

3. **`apps/common/templatetags/auth_tags.py`** — filtros de plantilla
   `puede_aprobar_apu`, `puede_enviar_a_revision`, `apu_esta_aprobado`.

4. **`templates/base.html`** — `<body>` añade `theme-admin` cuando
   `session.rol == 'ADMINISTRADOR'`. Conserva la clase de unidad.

5. **`static/css/admin-theme.css`** — paleta grises / negros / blancos
   bajo `body.theme-admin`. No afecta otros roles.

6. **`templates/comercial/solicitud_detail.html`** — botón
   **"Ir a la revisión"** condicional (APU `EN_REVISION` + autorizado).

7. **`templates/presupuestos/apu_revisar.html`** — accesos rápidos
   **Ver APU** y **Ver despiece / Ver despieces**.

8. **`templates/presupuestos/apu_detail.html`** — oculta el form
   "Enviar a revisión" si el APU ya fue aprobado.

9. **`apps/presupuestos/views/__init__.py`** —
   `APUEnviarRevisionView.post` bloquea reenvío de APUs aprobados,
   con log `APROBACION_DENEGADA` y mensaje explícito.

10. **`.env.example`** — bloque ANDINACOST_ADMIN_* con valores falsos.

### Sin migraciones

El campo `password_hash` ya es `TextField` y acepta hashes de Django.
`manage.py makemigrations --dry-run → No changes detected`.
`manage.py check → 0 issues`.

### Pruebas manuales

1. `python manage.py ensure_default_admin` sin variables → falla.
2. Con `ANDINACOST_ADMIN_PASSWORD=admin` → falla por blacklist.
3. Con credenciales válidas → crea admin (BD muestra hash, no plano).
4. Re-ejecutar → "Administrador inicial ya existe.", sin sobrescribir.
5. Login con admin recién creado → entra al dashboard.
6. Login con usuario legacy con contraseña plana → entra y su BD se
   migra a hash.
7. Cambiar contraseña desde `/configuracion/` → BD queda hasheada.
8. Login ADMINISTRADOR → UI en grises/negros/blancos.
9. Login con otro rol → UI por unidad, sin `theme-admin`.
10. APU `EN_REVISION` en solicitud → ve "Ir a la revisión" si
    autorizado; "Ver APU" siempre.
11. Pantalla de revisión → accesos "Ver APU" y "Ver despieces".
12. APU aprobado → no aparece "Enviar a revisión".
13. POST manual a `/presupuestos/apu/<pk>/enviar-revision/` sobre APU
    aprobado → bloqueado, mensaje explícito, sin cambios en
    aprobación ni snapshot.
14. `python manage.py check` → 0 issues.

### Restricciones honradas

No se tocó AIU matemático, garantía Red Shield, snapshot CotizacionAPU,
Builder, Facade, Strategies, PDFs (sólo enlaces/botones), archivado /
anulación, PROTECT, ni Fase 13. No se usa "Cuadrilla". No se
introdujeron contraseñas en código ni en el repositorio.


## §27 — Fase 12.3 ext: Rol GERENTE + ADMINISTRADOR global

### Cambios

1. **`apps/common/choices.py`** — `RolSistema.GERENTE = "GERENTE", "Gerente"`.
2. **`apps/configuracion/migrations/0010_alter_configuracionsistema_rol.py`** —
   `AlterField rol` (sólo estado del ORM).
3. **`apps/common/auth.py`** — nuevos helpers: `es_gerente`, `es_global`,
   `puede_ver_todas_las_unidades`, `unidad_efectiva`,
   `puede_gestionar_unidad`. `puede_enviar_a_revision` ampliado a
   `GERENTE` con gate de unidad y `COMPRAS` excluido.
4. **`apps/common/mixins.py`** —
   - `UnidadFilterMixin.get_queryset` con bypass `ADMINISTRADOR`.
   - Nuevo `UnidadObjectAccessMixin` para detail views.
5. **`apps/comercial/views.py`** —
   - Dashboard usa `unidad_efectiva` (ADMIN ve global).
   - `ClienteDetailView`, `SolicitudDetailView`, `ProyectoDetailView`
     heredan `UnidadObjectAccessMixin`.
6. **`apps/presupuestos/views/__init__.py`** —
   - Helper `_apu_unidad(apu)`.
   - `APUProyectoDetailView.dispatch` con gate por unidad.
   - `APURevisarView._render` con gate por unidad.
7. **`templates/base.html`** — `theme-admin-global` excluyente vs
   `theme-{unidad}`.
8. **`static/css/admin-theme.css`** — selector renombrado a
   `body.theme-admin-global`.

### Migración

```bash
python manage.py makemigrations configuracion
python manage.py migrate
python manage.py check
```

Resultado: `0010_alter_configuracionsistema_rol.py` aplicada. Schema
sin cambios. `check → 0 issues`.

### Pruebas manuales

1. Login ADMINISTRADOR → ve todas las unidades, tema gris/negro/blanco.
2. Login GERENTE unidad A → sólo ve unidad A; colores de unidad A.
3. GERENTE unidad A → abrir por URL un proyecto de unidad B → mensaje
   *"No tiene permiso para acceder a información de otra unidad."* +
   redirect a dashboard.
4. PRESUPUESTOS unidad A → ve sólo unidad A.
5. ASESOR_COMERCIAL unidad A → ve sólo unidad A.
6. ADMINISTRADOR → solicitudes/proyectos/APUs muestran datos
   agregados de todas las unidades.
7. (no aplica — sin filtro manual en esta fase).
8. GERENTE no asignado como revisor → no puede aprobar APU.
9. GERENTE asignado como revisor → puede aprobar.
10. ADMINISTRADOR aprueba sin ser revisor → permitido.
11. COMPRAS → no puede "Enviar a revisión".
12. `python manage.py check` → 0 issues.

### Restricciones honradas

No se tocó AIU matemático, garantía Red Shield, snapshot CotizacionAPU,
Builder, Facade, Strategies, PDFs, PROTECT, ni Fase 13. No se usa
"Cuadrilla". GERENTE no accede al CRUD de usuarios en esta fase (queda
para fase posterior). ADMINISTRADOR no recibe selector de unidad
manual en esta fase.


## §28 — Fase 12.3 ext: Unidad corporativa EDILANDINA

### Cambios

1. `apps/common/choices.py` — `UnidadNegocio.EDILANDINA = "EDILANDINA", "Edilandina"`.
2. `apps/configuracion/migrations/0011_alter_configuracionsistema_unidad_negocio_and_more.py`
   (state-only).
3. `apps/configuracion/management/commands/ensure_default_admin.py` —
   default EDILANDINA; reasigna unidad del ADMIN existente sin tocar
   contraseña/rol/nombre.
4. `static/css/admin-theme.css` — selectores compuestos
   `body.theme-admin-global, body.theme-edilandina` (enumerados por
   separado para precedencia correcta).
5. `static/css/sidebar-light.css` — agrega `.theme-edilandina` y
   `.theme-admin-global` con icono activo gris medio (#4b5563).
6. `.env.example` — `ANDINACOST_ADMIN_UNIDAD=EDILANDINA` con
   comentario corporativo.

### Migración

```bash
python manage.py makemigrations configuracion
python manage.py migrate
python manage.py check
```

`0011` aplicada. Schema PG sin cambios. `check → 0 issues`.

### Pruebas manuales

1. `python manage.py ensure_default_admin` sobre admin existente con
   unidad ≠ EDILANDINA → mensaje
   `"Administrador global asociado a EDILANDINA."`, sin tocar contraseña.
2. Re-ejecutar → `"Administrador inicial ya existe."`.
3. Cerrar sesión, hacer Ctrl+Shift+R, login ADMINISTRADOR → UI en
   grises/negros/blancos.
4. ADMINISTRADOR ve solicitudes/proyectos/APUs/clientes de todas las
   unidades.
5. GERENTE Impertienda → conserva su tema verde y sólo ve Impertienda.
6. GERENTE Imperandina → conserva su tema dorado y sólo ve Imperandina.
7. `python manage.py check` → 0 issues.

### Restricciones honradas

No se tocó AIU matemático, garantía Red Shield, snapshot CotizacionAPU,
Builder, Facade, Strategies, PDFs, PROTECT, aprobación, devolución,
archivado, ni Fase 13. No se usa "Cuadrilla". No se introdujeron
credenciales en código.
