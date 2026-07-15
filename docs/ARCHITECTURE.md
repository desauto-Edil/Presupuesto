# AndinaCost — Arquitectura objetivo

Documento vivo. Estado: **Fase 0–1 implementadas (settings + base de `common/`)**.
El resto se irá implementando por fases verificables.

---

## 1. Principios

- **Apps por dominio**, sin app `core` monolítica.
- **Capas finas y unidireccionales**: la View nunca llama al ORM directo si hay un Service/Selector que cubra el caso.
- **Snapshots inmutables** para todo lo que cotiza precios o resultados de cálculo.
- **Cache-Aside** centralizado en `apps/common/cache.py`. Nunca se cachean precios ni resultados de cálculo de un proyecto.
- **Una sola implementación** de:
  - evaluación de fórmulas (`apps/common/formula_evaluator.py`),
  - conversión de moneda / TRM (futuro `apps/catalogos/services/precio_service.py`),
  - construcción de contexto de variables de subsistema.

---

## 2. Capas

```
┌───────────────────────────────────────────────────────────┐
│                       Templates / JS                      │  presentación
├───────────────────────────────────────────────────────────┤
│                          Views                            │  HTTP, forms, permisos
├───────────────────────────────────────────────────────────┤
│                         Facades                           │  orquestación de dominio
├───────────────────────────────────────────────────────────┤
│   Services        Selectors        Calculators            │  lógica pura / consultas / cálculos
├───────────────────────────────────────────────────────────┤
│                         Models                            │  ORM, invariantes simples
├───────────────────────────────────────────────────────────┤
│       Cache  ·  Formula Evaluator  ·  DTOs                │  apps/common
└───────────────────────────────────────────────────────────┘
```

Reglas:
- **View** → llama Facade o Service. No llama Selector directo si una Facade ya lo expone.
- **Facade** → orquesta Services + Selectors. No habla SQL.
- **Service** → muta estado de un agregado. Una sola transacción por método.
- **Selector** → consulta read-only, retorna QuerySet o DTOs.
- **Calculator** → función pura `(input) → output`. Cero ORM.
- **Model** → invariantes locales y representación (`__str__`). No `save()` con efectos colaterales sobre otras filas.

---

## 3. Patrones y dónde aplican

| Patrón | Aplicación en AndinaCost |
|---|---|
| **Service Layer** | Existe parcialmente en `ingenieria/services/` y `presupuestos/services/`. Falta para `comercial` y `catalogos`. |
| **Facade** | `DespieceFacade`, `APUFacade`, `ProyectoFacade`, `ProductoFacade` (ver §4). |
| **Selector** | Mover `ProyectoSistema.get_contexto/get_variables_requeridas` a `ingenieria/selectors/receta.py`. |
| **Calculator** | Mover `APU.recalcular`, `APU.calcular_modalidades_aiu` a `presupuestos/calculators/`. |
| **Snapshot / Memento** | Ya implementado en `DespieceMaestroLinea` y `APULinea`. Mantener; no cachear ni mutar. |
| **Strategy** | Selección DB vs `system_defs` en `DespieceService` → formalizar como `RecetaStrategy`. Modalidades de AIU → `AIUModalidadStrategy`. |
| **Registry** | `apps/ingenieria/system_defs/registry.py` — patrón ya correcto. |
| **Factory** | `APUFactory.from_despiece(proyecto_sistema)` para reemplazar la construcción ad-hoc actual. |
| **Singleton (controlado)** | `ConfiguracionAPU.activa_o_default()` es de facto un singleton de DB. No introducir singletons en memoria salvo registries. |
| **Cache-Aside** | `apps/common/cache.py`. TTL definidos por dominio. |
| **Adapter** | Envolver `CapaConsumo` (deprecated) tras una interfaz moderna durante la transición. |
| **DTO** | `apps/common/dto.py`. Reemplazar dicts en la frontera service↔view. |

---

## 4. Facades propuestas (NO implementadas todavía)

### 4.1 DespieceFacade
**Responsabilidad**: orquesta despiece maestro y despiece por proyecto bajo una sola API.
```
calcular(subsistema_id, variables, subconjuntos=None) -> list[CalculationLineDTO]
guardar(despiece_id, lineas) -> DespieceMaestro
calcular_para_proyecto(proyecto_sistema_id) -> list[CalculationLineDTO]
```
Sustituye llamadas dispersas a `DespieceService` y `DespieceMaestroService`.

### 4.2 APUFacade
**Responsabilidad**: generación, recálculo y modalidades AIU.
```
generar_desde_despiece(proyecto_sistema_id) -> APU
recalcular(apu_id) -> APU
calcular_modalidades_aiu(apu_id) -> dict
enviar_a_revision(apu_id, usuario_id) -> APU
aprobar(apu_id, usuario_id) -> APU
```

### 4.3 ProyectoFacade
**Responsabilidad**: ciclo de vida del proyecto, incluyendo versionado.
Mueve fuera de `Proyecto.save()` la lógica de:
- asignación de consecutivo,
- creación de nueva versión,
- marcado de `es_version_actual=False` en versiones anteriores.

```
crear_desde_solicitud(solicitud_id, datos) -> Proyecto
clonar_como_version(proyecto_id) -> Proyecto
avanzar_estado(proyecto_id, nuevo_estado) -> Proyecto
```

### 4.4 ProductoFacade
**Responsabilidad**: precios y conversión.
Elimina los literales `4200` (TRM) dispersos.
```
precio_actual(producto_id, moneda='COP') -> Decimal
precio_para_display(producto_id) -> str
buscar_por_categoria(categoria_id, query='') -> QuerySet
```

---

## 5. apps/common — base ya instalada

| Archivo | Rol |
|---|---|
| `cache.py` | Helpers cache-aside + TTLs centralizados |
| `formula_evaluator.py` | `evaluate_formula`, `extract_tokens`, `SAFE_NAMES` |
| `dto.py` | `FormulaResult`, `CalculationLineDTO`, `VariablesSnapshotDTO` |
| `patterns.py` | `SingletonMixin`, `Strategy`, `Facade`, `Memento`, `Adapter` |
| `choices.py` | Enums centralizados (ya existía) |
| `constants.py` | Constantes (ya existía) |
| `mixins.py` | Form/view mixins (ya existía) |

---

## 6. Cache: política

- **Sí cachear**: catálogos (unidades, categorías, funciones de consumo, problemas resueltos, superficies), `ConfiguracionAPU.activa`, receta técnica de un subsistema, listados de selectores.
- **No cachear**: precios de productos, resultados de cálculo de un proyecto, variables de entrada, snapshots de líneas (ya están persistidos).
- **Backend**: `LocMemCache` en dev, `RedisCache` en prod (controlado por `CACHE_BACKEND` y `REDIS_URL` en `.env`).

### 6.1 Estado de adopción (Fase 5B–5D — DONE)

| Recurso | Clave | TTL | Loader | Invalidación |
|---|---|---|---|---|
| `UnidadMedida` (listado) | `catalogos:unidades` | 24 h | `get_cached_unidades()` | signal `post_save`/`post_delete` sobre `UnidadMedida` |
| `CategoriaProducto` (activas) | `catalogos:categorias` | 1 h | `get_cached_categorias()` | signal `post_save`/`post_delete` sobre `CategoriaProducto` |
| `ConfiguracionAPU.activa` (id) | `presupuestos:config_apu:activa` | 1 h | `get_cached_config_apu_id()` | signal `post_save`/`post_delete` sobre `ConfiguracionAPU` |

**Estrategia cache-aside** (lectura): cache → si miss, DB + set. **Escritura**: invalidar la clave (signals). El helper genérico vive en `apps/common/cache.py::cache_aside()`.

**Call-sites adoptados**:
- `apps/ingenieria/views/__init__.py::_build_unidades_medida_json` (consumido por `SubsistemaCreateView` y `SubsistemaUpdateView`).
- `apps/ingenieria/views/__init__.py::_categorias_producto_para_template` (idem).
- `apps/presupuestos/services/apu_service.py::_resolver_config_apu` (usado por `APUService.__init__` y `APUService.for_apu`).

**Signals registrados** (Fase 5D):
- `apps/catalogos/signals.py` — registrados vía `CatalogosConfig.ready()`.
- `apps/presupuestos/signals.py` — registrados vía `PresupuestosConfig.ready()`.

**Fallback de robustez**: `_resolver_config_apu()` recurre a `ConfiguracionAPU.activa_o_default()` si el cache devuelve `None` o el id no existe — preserva el efecto colateral de auto-creación.

**No cacheado intencionalmente**: `Producto`, `ProductoProveedor`, precios, `ItemCatalogoAPU`, resultados de cálculo, variables del usuario, y las vistas CRUD propias del catálogo (`apps/catalogos/views.py`).

---

## 7. Fase 2 aplicada — progresivo

### 7.A Confirmación de eliminación centralizada (Lote A — DONE)

- **Partial**: `templates/partials/_confirm_delete_modal.html`.
- **Contrato** (todos los parámetros opcionales):

  | Param | Default | Descripción |
  |---|---|---|
  | `titulo` | `"Confirmar eliminación"` | Encabezado rojo. |
  | `nombre_objeto` | `{{ object }}` | Nombre del registro. |
  | `mensaje` | `"¿Está seguro…?"` | Línea principal. |
  | `submensaje` | `"Esta acción no se puede deshacer."` | Línea secundaria. |
  | `cancel_url` | `javascript:history.back()` | Botón Cancelar. |
  | `texto_cancelar` | `"Cancelar"` | — |
  | `texto_boton` | `"Eliminar"` | Botón POST. |
  | `clase_boton` | `"btn-danger"` | Clase CSS del botón POST. |
  | `action_url` | `""` (URL actual) | POST destino. |

- **Template default `confirm_delete.html`** ahora es un wrapper de 12 líneas
  que `{% include %}` el partial sin parámetros (= conserva el render
  exacto que ya consumen todas las `DeleteView` existentes en
  `configuracion`, `ingenieria` y `catalogos`).
- **Cómo replicar** desde una vista que necesite confirmación custom
  (p. ej. eliminar un componente desde un modal):

  ```django
  {% include "partials/_confirm_delete_modal.html" with
       titulo="Eliminar componente"
       nombre_objeto=componente.nombre
       mensaje="Quita este componente del subsistema."
       cancel_url=request.META.HTTP_REFERER %}
  ```

### 7.B Partial de formulario reutilizable — piloto Unidad (Lote B — DONE)

- **Patrón**: por cada entidad, un partial `_xxx_form.html` con el `<form>` (campos + errores + botones). El template `xxx_form.html` queda como wrapper (`extends base` + `panel` + `include partial`).
- **Piloto**: `templates/catalogos/_unidad_form.html`. El wrapper `catalogos/unidad_form.html` quedó en 21 líneas (antes 58).
- **Contrato del partial** (todos los parámetros opcionales):

  | Param | Default | Descripción |
  |---|---|---|
  | `form` | variable del contexto | ModelForm. |
  | `action_url` | `""` (URL actual) | POST destino. |
  | `cancel_url` | `{% url 'catalogos:catalogo' %}` | Botón Cancelar. |
  | `submit_label` | `"Guardar cambios"` / `"Crear unidad"` según `object` | Texto submit. |

- **Cero cambio** en `UnidadCreateView` / `UnidadUpdateView` ni en URLs.
- **Cuándo crear partial**: cuando crear/editar comparten template **y** se prevé reutilizar el form desde otro contexto (modal, página combinada). Si no se prevé reuso, dejar el form inline para no añadir indirección.

### 7.C Replicación del patrón partial form (Lote C — DONE)

Aplicado a tres entidades más, siempre con cero cambio visible:

| Entidad | Wrapper | Partial nuevo | Líneas wrapper antes/después |
|---|---|---|---|
| Categoría | `catalogos/categoria_form.html` | `catalogos/_categoria_form.html` | 67 → 22 |
| Tipo de proyecto | `comercial/tipoproyecto_form.html` | `comercial/_tipoproyecto_form.html` | 49 → 22 |
| Producto | `catalogos/producto_form.html` | `catalogos/_producto_form.html` | 206 → 65 |

Notas:
- En `producto_form.html` la cabecera con código/registrado/último precio se queda en el wrapper porque es metadata, no parte del form.
- En `tipoproyecto_form.html` se descartó el comentario suelto `# Revisar si es necesaria` que estaba fuera de cualquier `{% block %}` (Django lo ignoraba al extender `base.html`, no afectaba el render).

### 7.D Service Layer — primera extracción (Lote D — DONE)

**`apps/ingenieria/services/subsistema_service.py`** (nuevo)
- Funciones movidas **tal cual** desde `apps/ingenieria/views/__init__.py`:
  - `guardar_variables`
  - `guardar_subconjuntos_componentes`
  - `guardar_reglas_apu`
  - `guardar_m2m_consumo`
  - `guardar_productos_tecnicos_componentes_quimicos`
  - `parsear_opciones` (helper)
  - `proximo_codigo_numerico` (helper)
- Las vistas `SubsistemaCreateView.form_valid` y `SubsistemaUpdateView.form_valid` ahora importan y llaman estos nombres públicos. Cero cambio de comportamiento, cero cambio de POST shape.

**`apps/comercial/services/proyecto_service.py`** (nuevo, capa preparada — NO migra `save()`)
- `generar_consecutivo()` — delega en `Proyecto.siguiente_consecutivo()`.
- `crear_proyecto_desde_solicitud(...)` — constructor estable que las vistas pueden adoptar progresivamente; hoy el versionado lo sigue haciendo `Proyecto.save()`.
- `crear_version_desde_proyecto(...)` — delega en `apps.presupuestos.services.proyecto_service.clonar_proyecto_como_version`.
- `marcar_versiones_anteriores(...)` — helper expuesto para reuso futuro; hoy no se llama desde el flujo activo.

**Plan de migración futura** (cuando haya tests de regresión):
1. Mover el bloque de auto-versionado de `Proyecto.save()` a `crear_proyecto_desde_solicitud`.
2. Reducir `Proyecto.save()` a un `save()` clásico sin efectos.
3. Actualizar las vistas a construir el proyecto vía service en lugar de `Proyecto(...).save()`.

### 7.E Facades semilla (Lote E — DONE)

**`apps/ingenieria/services/despiece_facade.py`** — clase `DespieceFacade`.
Métodos estáticos thin que delegan en los services existentes:

| Método | Delega en |
|---|---|
| `calcular_maestro(despiece)` | `DespieceMaestroService.calcular` |
| `guardar_maestro(despiece, …)` | `DespieceMaestroService.guardar` |
| `obtener_variables_requeridas(despiece)` | `DespieceMaestroService.get_variables_requeridas` |
| `validar_variables_entrada(despiece, vars)` | `DespieceMaestroService.validar_variables_entrada` |
| `calcular_para_proyecto(ps)` | `DespieceService.ejecutar` |
| `validar_productos_completos(ps)` | `DespieceService.validar_productos_completos` |
| `asignar_productos(ps, map)` | `DespieceService.asignar_productos` |

**`apps/presupuestos/services/apu_facade.py`** — clase `APUFacade`.
Métodos estáticos thin que delegan en `APUService`:

| Método | Delega en |
|---|---|
| `generar_desde_despiece(ps)` | `APUService.generar` |
| `for_apu(apu)` | `APUService.for_apu` |
| `generar_materiales(ps)` | `APUService.generar_materiales` |
| `generar_mano_obra_desde_catalogo(ps, items)` | `APUService.generar_mano_obra_desde_catalogo` |
| `generar_herramientas_desde_catalogo(...)` | idem |
| `generar_transporte_desde_catalogo(...)` | idem |
| `generar_administracion_desde_catalogo(...)` | idem |
| `finalizar(ps)` | `APUService.finalizar` |

**Las vistas no las consumen todavía.** El propósito en esta fase es solo
dejar el punto de entrada estable. La migración progresiva ocurre cuando
existan tests de regresión.

---

## 8. Qué NO hacer

- No introducir un ORM extra ni un message bus.
- No reemplazar Django Templates por un SPA hasta que las facades estén estables.
- No mover modelos entre apps en esta fase (el refactor 2026-03 ya estabilizó la estructura).
- No tocar `signals` de `APULinea` hasta tener un context manager `recalculo_diferido()`.
- No borrar `CapaConsumo`, `ReglaCalculo`, `DependenciaTecnica` sin auditoría de uso en datos reales.

## §7. Flujo "Armar mi APU" (Fase 6 — DONE 6A–6H)

### Concepto: línea final
Una **línea final** es la unidad que efectivamente entra al APU de Materiales.
Se deriva de un `DespieceMaestro` con esta regla:

- Cada `ConsolidacionDespieceMaestro` activa → 1 línea final tipo `consolidada`.
- Cada `DespieceMaestroLinea` cuyo `pk` **NO** está en `lineas_ids` de ninguna
  consolidación → 1 línea final tipo `normal`.
- Las líneas absorbidas por una consolidación (`lineas_ids`) NO se emiten como
  individuales (no hay duplicación origen-vs-consolidado).

Helper: `apps.ingenieria.services.lineas_finales_apu.obtener_lineas_finales_para_apu(despiece)`.

### Validación "listo para APU"
Helper: `validar_despiece_listo_para_apu(despiece)`.

Errores bloqueantes:
1. Despiece sin proyecto.
2. Despiece no guardado.
3. Sin líneas finales.
4. Líneas finales sin producto seleccionado.
5. Líneas finales con cantidad ≤ 0.
6. Líneas finales sin unidad.

Advertencias no bloqueantes (Fase 6H):
- Líneas sin precio snapshot.
- Mismatch unidad línea ↔ unidad producto.
- Producto sin unidad configurada.
- `unidad_apu` ≠ `unidad` de la línea.

### Producto principal
Persistido en `ProyectoSistema.parametros_entrada` (JSONField, sin migración):
- `producto_principal_id`
- `cantidad_base` (sumatoria si el producto aparece en varias líneas finales)
- `unidad_base`
- `modo_rendimiento = "PRODUCTO_PRINCIPAL"`

### Fórmula de rendimiento
Helper: `apps.presupuestos.services.apu_service.calcular_rendimiento_por_producto_principal(cantidad_linea, cantidad_base)`.

    rendimiento = cantidad_linea / cantidad_base   (Decimal, 6 decimales)

La línea del producto principal sale automáticamente con rendimiento = 1
(porque `cantidad_linea == cantidad_base`).

`APUService.generar_materiales` detecta el modo en `parametros_entrada`:
- Modo `PRODUCTO_PRINCIPAL` → usa el helper.
- Sin modo / corrupto → fallback al cálculo legacy (compatibilidad con APUs anteriores).

### Alcance del APU (Fix 6E-A)
**Regla obligatoria**: el APU de un `ProyectoSistema(proyecto, sistema, subsistema)`
solo consolida despieces guardados del **mismo proyecto Y mismo subsistema**.

Despieces de **otros subsistemas** del mismo proyecto NO mezclan sus materiales
en este APU. Esto respeta el modelo `APUProyecto = OneToOne(ProyectoSistema)`.

Despieces múltiples del **mismo subsistema** sí se consolidan (suma de cantidades
por componente).

Implementado en `APUArmarDesdeDespieceView.post` (filtro
`subsistema=dm.subsistema` en `todos_dm`).

### Transición visible
- Botón principal del Despiece Maestro: **"Armar mi APU"** (antes "Ver APU" /
  "Generar APU"). Abre `#modalArmarApu`.
- "Ver APU existente" queda como link secundario (`btn-outline-secondary`).
- El usuario nunca llega al APU sin pasar por el modal: el modal exige
  seleccionar producto principal y revalida en backend antes de generar.

### Render APU detail
La sección **Materiales** muestra: Componente · Producto · Cantidad · Unidad ·
Rendimiento · Costo unit. · Total. Las demás categorías (Herramientas, MO,
Transporte, Administración) conservan su tabla original.

### Alcance del APU (refinamiento Fix 6E-B)
**Regla obligatoria, sobrescribe parcialmente 6E-A**: el APU se genera
**únicamente con las líneas finales mostradas en el modal "Armar mi APU"**.
Eso es exactamente `obtener_lineas_finales_para_apu(dm)` del despiece que
disparó el POST.

Implicaciones:
- No se consolidan otros despieces del mismo subsistema. Si en el subsistema
  hay varios DM guardados, cada armado de APU reemplaza al anterior (el último
  "Armar mi APU" gana).
- Las `DespieceLinea` antiguas del PS que no estén en las líneas finales del
  modal actual se **eliminan** antes de regenerar el APU.
- El APU refleja 1:1 lo que el usuario vio en el modal. No hay líneas
  "fantasma" provenientes de despieces previos.

Implementación: `APUArmarDesdeDespieceView.post` itera
`validacion["lineas_finales"]` (del dm actual) en lugar de los DM hermanos del
proyecto, hace `update_or_create` por línea y `delete` de obsoletas en el PS.

---

## §8 — Fase 6L: Configuración APU por subsistema (2026-06)

### 8.1 Regla funcional
- **Materiales** sigue viniendo del despiece (Fase 6F/6E-C). No se toca.
- **Herramientas, Transporte, Mano de obra y Administración** ya no se
  rellenan con todo el catálogo APU. El subsistema decide qué ítems del
  catálogo APU aplican por defecto.
- Si el subsistema no tiene ítems configurados para una categoría, esa
  categoría queda **vacía** con mensaje claro. No se rellena
  automáticamente con todo el catálogo.

### 8.2 Modelo nuevo: `SubsistemaItemAPU`
Tabla `subsistema_items_apu` (migración `0022_subsistema_item_apu`).

Campos:
- `subsistema` → FK `ingenieria.Subsistema` (CASCADE)
- `item_catalogo` → FK `ItemCatalogoAPU` (CASCADE)
- `tipo` → choices = TipoAPU sin MATERIALES
- `cantidad` (PositiveIntegerField, default 1)
- `orden` (PositiveIntegerField, default 0)
- `activo` (BooleanField, default True)
- `rendimiento_override` (Decimal nullable) — para sobrescribir rendimiento
- `observaciones` (TextField blank)
- `created_at`, `updated_at`

UNIQUE `(subsistema, item_catalogo, tipo)`.

### 8.3 Flujo de configuración (subsistema_form.html)
Bloque nuevo **"5 · Configuración APU del subsistema"** dentro del form actual.
- Acordeón por cada categoría no-Materiales (Herramientas, Transporte,
  Mano de obra, Administración).
- Cada acordeón muestra el catálogo agrupado por `CategoriaItemAPU`, con
  checkbox + cantidad + barra de búsqueda frontend (`siaFilter`).
- Search filtra por nombre, código, categoría, unidad usando `data-search`.
- Persistencia: `subsistema_service.guardar_items_apu_subsistema(subsistema, post)`.
- Vista intacta: `SubsistemaCreateView` / `SubsistemaUpdateView` reutilizadas.

### 8.4 Generación APU (APUService)
`APUService._items_apu_subsistema(tipo_apu)` consulta `SubsistemaItemAPU`
filtrado por `subsistema_id`, `tipo`, `activo=True`. Devuelve `items_data`
compatible con `_generar_categoria_desde_catalogo`.

`_auto_generar_desde_catalogo` ahora usa este helper. Si la categoría no
tiene ítems configurados, log INFO y se omite (no fallback al catálogo
completo).

`APUProyectoUpdateView.form_valid` (cambio de AIU/margen/días/factor_venta)
también pasa por el mismo filtro y limpia líneas previas de categorías sin
configuración.

### 8.5 Tarjetas informativas (`_apu_info_card.html`)
Partial único reutilizado en las 5 secciones del APU detail.
- Materiales: producto principal, cantidad base, unidad base, modo de
  rendimiento, fórmula, mensaje explicativo.
- No-Materiales: número de personas, número de días, ítems configurados,
  base de cálculo, mensaje explicativo.
- Datos ausentes → "No definido" (regla: no inventar datos).

Datos construidos por `views._build_info_card_data(apu)`:
- Personas → `proyecto.num_personas`.
- Días → `apu.dias_duracion`.
- Items configurados → `SubsistemaItemAPU.objects.filter(...).count()` por tipo.
- Producto principal → `ps.parametros_entrada.producto_principal_id` →
  `Producto.objects.get(...)`.

### 8.6 Búsqueda en modales de configuración APU
- Inputs `<input type="search">` agregados a los 4 modales de
  `apu_detail.html`.
- Función `apuModalFilter(input)` filtra `.apu-modal-item-row` por
  `data-search` y oculta `.apu-modal-cat-group` vacíos.
- Sin tocar backend. Sin paginación.

### 8.7 Validaciones (6L-H)
1. Materiales siempre desde despiece. No se afecta por 6L.
2. APUService genera no-Materiales SOLO desde `SubsistemaItemAPU`.
3. `apu_detail.html` modales de configuración muestran SOLO ítems
   asociados al subsistema (queryset filtrado en `get_context_data`).
4. `_filtrar_items_por_sia(apu, tipo, items_data)` actúa como defensa de
   servidor en `APUManoObraView` y `APUHerramientasView`: ítems no
   asociados se descartan.
5. Si categoría sin ítems configurados → mensaje claro, no se bloquea.
6. Cambiar configuración del subsistema y "Actualizar APU" refleja la nueva
   selección automáticamente (vía `APUProyectoUpdateView`).

### 8.8 Reutilización y archivos nuevos
- 1 partial nuevo: `templates/presupuestos/partials/_apu_info_card.html`.
- 1 migración nueva: `presupuestos/migrations/0022_subsistema_item_apu.py`.
- 0 vistas nuevas. 0 forms nuevos.
- Reutilizado: `SubsistemaCreateView`, `SubsistemaUpdateView`,
  `SubsistemaService`, `subsistema_form.html`, `APUService`,
  `_build_categorias_context`, `_apu_info_card.html` (en las 5 categorías).

---

## 9. Garantías del APU (Fase 9)

### 9.1 Objetivo
Permitir indicar al armar o revisar un APU si la propuesta incluye
garantía y de qué tipo. La garantía es **información comercial**: forma
parte de la propuesta final pero **no afecta** el cálculo de materiales,
el rendimiento por producto principal, la presentación técnica, las
advertencias ni el AIU.

### 9.2 Modelo `TipoGarantia` (apps/comercial/models.py)
Catálogo administrable de tipos de garantía. Se ubica en `apps/comercial/`
porque la garantía es metadata comercial junto a `TipoProyecto`.

Campos:
- `nombre` — etiqueta corta.
- `duracion_meses` — entero positivo; helper `duracion_label` devuelve
  "N años" si es múltiplo de 12, "N meses" en caso contrario.
- `descripcion` — frase corta visible en propuesta y APU.
- `condiciones` — texto largo (alcance / exclusiones).
- `orden` — orden de presentación.
- `activo` — solo los activos aparecen en selectores.
- `created_at`, `updated_at`.

Meta: `db_table="tipos_garantia"`, `ordering=["orden", "nombre"]`.

### 9.3 Asociación con APU
La garantía se asocia a `APUProyecto`, no al producto individual ni al
proyecto, porque la decisión comercial vive en el APU que se entrega al
cliente.

Campos nuevos en `APUProyecto` (ambos opcionales, no rompen APUs legacy):
- `aplica_garantia: BooleanField(default=False)`.
- `tipo_garantia: ForeignKey("comercial.TipoGarantia", on_delete=PROTECT, null=True, blank=True, related_name="apus")`.

`on_delete=PROTECT` impide borrar un tipo de garantía usado en un APU.
La `TipoGarantiaDeleteView` captura `ProtectedError` y muestra un mensaje
sugiriendo desactivar en vez de eliminar.

### 9.4 Catálogo `/comercial/garantias/`
Patrón Fase 8.1 (reutilizar, no duplicar):
- Partial fields-only: `templates/comercial/_garantia_form.html`.
- Wrapper edición: `templates/comercial/garantia_form.html` (aporta
  `<form>` + csrf + footer).
- Lista: `templates/comercial/garantia_list.html` con modal
  `#modalGarantia` que hace `{% include "_garantia_form.html" %}`
  contra `TipoGarantiaCreateView`.
- Form `TipoGarantiaForm` único.
- Vistas: `TipoGarantiaListView` / `CreateView` / `UpdateView` /
  `DeleteView` en `apps/comercial/views.py`.
- Sidebar: link "Garantías" antes de Catálogos.

### 9.5 Selección al "Armar mi APU"
En `_modal_armar_apu.html`, dentro del bloque `if validacion.ok`, se
muestra:
- Radio "¿Aplica garantía?" Sí / No (`name="aplica_garantia"`).
- `<select name="tipo_garantia_id">` con `tipos_garantia_activos`,
  oculto si "No".
- JS `armarApuOnAplicaGarantia(aplica)` limpia el select al pasar a "No".

`tipos_garantia_activos` lo añade el calculador
(`apps/ingenieria/views/calculador.py`) al contexto.

`APUArmarDesdeDespieceView.post`, tras `APUService.generar(ps)`:
1. Si el POST trae `aplica_garantia` lo persiste; si trae "1" sin
   `tipo_garantia_id` activo → `ValueError` → rollback de la transacción.
2. Si el POST **no** trae `aplica_garantia` (re-armar sin tocar la
   sección), la garantía existente no se pierde.
3. Persiste con `update_fields=["aplica_garantia", "tipo_garantia", "updated_at"]`.

`APUService.generar` no toca esos campos: la garantía es ortogonal al
cálculo.

### 9.6 Edición desde el APU (apu_detail)
Bloque "Garantía" en `templates/presupuestos/apu_detail.html`, ubicado
después de la fila de KPIs y antes de la búsqueda:
- 3 columnas: Aplica / Tipo / Duración.
- Descripción corta inline.
- `<details>` colapsable con `condiciones`.
- Si `aplica_garantia=False`: mensaje "Esta propuesta no incluye
  garantía.".
- Botón "Editar" abre `#modalEditarGarantia` con radio + select
  prellenados. Submit a `apu_editar_garantia`.

Vista: `APUEditarGarantiaView` (POST). Misma validación que armar:
"Sí" sin tipo activo → mensaje de error, no se persiste.

### 9.7 Validaciones (Fase 9F)
1. "Sí aplica" sin tipo válido → rechazo backend.
2. "No aplica" → `tipo_garantia=None`.
3. `TipoGarantia.activo=False` no aparece en selectores
   (`filter(activo=True)`).
4. APU legacy: `aplica_garantia=False` por default, todo opcional.
5. Re-armar APU sin tocar la sección: garantía preservada.
6. JS limpia tipo al cambiar a "No".
7. `PROTECT` impide borrar tipo en uso. La vista de delete lo captura.

### 9.8 Reutilización y archivos nuevos
- 1 modelo nuevo: `comercial.TipoGarantia`.
- 2 campos nuevos opcionales en `APUProyecto`.
- 2 migraciones: `comercial/0018_tipogarantia.py`,
  `presupuestos/0023_apuproyecto_aplica_garantia_and_more.py`.
- 1 form nuevo: `TipoGarantiaForm`.
- 1 partial nuevo + 2 wrappers/templates de catálogo.
- 1 vista nueva en presupuestos: `APUEditarGarantiaView`.
- Sin tocar: cálculo de materiales, rendimiento, presentación técnica,
  advertencias, AIU, modalidades, `APUService.generar`, signals,
  `apu_facade`.

---

## 10. Garantía como recargo comercial (Fase 9R) — corrección de Fase 9

> **Importante:** La sección 9 documentó la primera implementación de la
> garantía como dato descriptivo con duración en meses. La sección 10
> corrige ese concepto. **La garantía ahora es un recargo comercial
> porcentual aplicado únicamente sobre Materiales.** El catálogo conserva
> `duracion_meses` como campo legacy nullable.

### 10.1 Concepto

- La garantía es un **recargo comercial** que se suma a `total_valor_venta`.
- Solo afecta el **valor comercial** del APU. **No afecta** cantidades,
  rendimientos, costo unitario, costo total técnico, despiece, herramientas,
  transporte, mano de obra, administración, ni AIU.
- La base del recargo es **siempre Materiales** (total o un material
  específico).

### 10.2 Catálogo — `TipoGarantia`

Campos funcionales:
- `nombre`
- `porcentaje_recargo` (Decimal, `default=0`). Ej.: `5.00` = 5 %.
- `descripcion`, `condiciones`, `orden`, `activo`.

Campos legacy (Fase 9):
- `duracion_meses` (PositiveInteger, `null=True, blank=True`). **Oculto en
  el formulario actual.** `duracion_label` y `__str__` son tolerantes a
  vacío. Se conserva por compatibilidad histórica.

Form `TipoGarantiaForm` expone `porcentaje_recargo` con label
"Porcentaje de recargo (%)".

### 10.3 Campos nuevos en `APUProyecto`

| Campo | Tipo | Propósito |
|---|---|---|
| `garantia_porcentaje_aplicado` | Decimal null | **Snapshot** del % tomado del catálogo al armar/editar. |
| `garantia_modo_aplicacion` | CharField choices | `TOTAL_MATERIALES` o `MATERIAL_ESPECIFICO`. |
| `garantia_material_linea` | FK `APULinea` (`on_delete=SET_NULL`) | Línea Materiales objetivo cuando aplica modo específico. |
| `garantia_material_nombre_snapshot` | CharField | Trazabilidad textual si la línea es regenerada/eliminada. |
| `garantia_base_valor` | Decimal | Base sobre la que se calculó el recargo. |
| `garantia_valor_recargo` | Decimal | Recargo sumado a `total_valor_venta`. |

Snapshot inmutable: cambiar `TipoGarantia.porcentaje_recargo` en el
catálogo **no** muta APUs existentes. Solo se actualiza si el usuario
reedita la garantía del APU.

### 10.4 Cálculo

```
if not aplica_garantia or not tipo_garantia or porcentaje_aplicado is None:
    base = 0
    recargo = 0
elif modo == MATERIAL_ESPECIFICO and material_linea:
    base = material_linea.valor_total
    recargo = base * pct / 100
else:  # TOTAL_MATERIALES
    base = subtotal_materiales
    recargo = base * pct / 100

total_valor_venta = total_valor_directo + recargo
```

`APUProyecto._recalcular_garantia_inline()` se llama al final de
`recalcular()`. No modifica `subtotal_materiales` técnico ni
`APULinea.valor_total`.

### 10.5 AIU

- La base AIU sigue usando los subtotales técnicos.
- El recargo de garantía **no entra** en la base AIU.
- Si en el futuro se decide incluirlo, será una fase posterior.

### 10.6 Flujo de selección

**Modal "Armar mi APU"** (`templates/ingenieria/partials/_modal_armar_apu.html`):
1. ¿Aplica garantía? Sí/No
2. Tipo de garantía (muestra `%` en el option).
3. Modo: Total materiales / Material específico.
4. Si "Material específico": selector construido desde
   `armar_apu_validacion.lineas_finales` (envía `DespieceLinea.id` y
   snapshot textual). El backend resuelve a `APULinea` por
   `despiece_linea_id` después de que `APUService.generar()` cree las
   líneas.

**Modal "Editar garantía"** en `apu_detail.html`:
- Mismo flujo, pero el selector de material sale de
  `lineas_materiales_apu` (APULinea ya existentes).

### 10.7 Visualización en `apu_detail.html`

Tarjeta Garantía:
- Aplica · Tipo · % aplicado · Modo · Material objetivo · Base · Recargo.
- Advertencia visual para legacy: "Esta garantía fue creada antes del
  recargo porcentual. Reedite la garantía para aplicar el porcentaje."
- Si `garantia_material_linea` fue eliminada pero existe
  `garantia_material_nombre_snapshot`: "Material objetivo no disponible.
  Reedite la garantía para recalcular el recargo." (Recargo queda en 0
  hasta reedición.)

KPI "Valor total":
- Subtotales por categoría (sin cambios).
- Si `aplica_garantia` y recargo > 0:
  - Línea "Recargo garantía" — `garantia_valor_recargo`.
  - Línea "Materiales ajustado" — `subtotal_materiales + recargo`.

Tabla Materiales: badge "Garantía aplicada" en la línea cuyo `pk` coincide
con `apu.garantia_material_linea_id`.

### 10.8 Validaciones (backend)

Centralizadas en `_aplicar_garantia_desde_post()`
(`apps/presupuestos/views/__init__.py`):

1. Si `aplica_garantia=True` → `tipo_garantia` obligatorio y activo.
2. Si `aplica_garantia=True` → porcentaje válido (≥ 0).
3. Modo debe ser `TOTAL_MATERIALES` o `MATERIAL_ESPECIFICO`.
4. Modo `MATERIAL_ESPECIFICO` → material objetivo obligatorio.
5. El material objetivo debe pertenecer al APU actual y ser tipo
   MATERIALES.
6. Garantías inactivas excluidas de selectores
   (`tipos_garantia_activos = activo=True`).
7. Si `aplica_garantia=False` → todos los campos derivados se limpian.
8. APUs legacy Fase 9 (con `aplica_garantia=True` pero sin
   `garantia_porcentaje_aplicado`) abren sin error; recargo = 0 y se
   muestra advertencia para reeditar.

### 10.9 Migraciones

- `comercial/0019_tipogarantia_porcentaje_recargo_and_more.py` — agrega
  `porcentaje_recargo`; `duracion_meses` → null/blank.
- `presupuestos/0024_apuproyecto_garantia_base_valor_and_more.py` — añade
  los 6 campos nuevos.
- **Sin `RunPython` destructivo.** No se convierte duración a porcentaje.

### 10.10 Lo que NO se tocó en 9R

- `costo_total`, `costo_unitario`, `cantidad_base`, `rendimiento`,
  `valor_total` de `APULinea`.
- Despiece Maestro, dependencias técnicas, producto principal.
- Reglas de cálculo, `APUService.generar`.
- AIU y modalidades (Fase 10 sigue en pausa).
- Presentación técnica, advertencias de unidad.

---

## 11. Fase 10A — AIU final del proyecto (Modalidad 1 y 2)

Consolidación del AIU **final del proyecto** revisado/aprobado por el revisor.
Reemplaza el flujo previo en el que el revisor solo elegía modalidad sin
poder ajustar A/I/U efectivos del proyecto.

### 11.1 AIU contratista vs AIU final del proyecto

| Concepto | Ámbito | Campo(s) |
|---|---|---|
| **AIU contratista** | Costo unitario de cada `APULinea`. Afecta `valor_unitario` y por tanto el costo comercial técnico. | `aiu_contratista_pct`, `margen_ganancia_pct`, `factor_venta_pct` en `APUProyecto` |
| **AIU final del proyecto** | Cálculo agregado sobre subtotales técnicos del APU para llegar al gran total comercial aprobado. | `aiu_proyecto_admin_pct`, `aiu_proyecto_imprevistos_pct`, `aiu_proyecto_utilidad_pct` (base) y `aiu_final_admin_pct`, `aiu_final_imprevistos_pct`, `aiu_final_utilidad_pct` (snapshot del revisor) |

No mezclar: el contratista se aplica **dentro** del cálculo por línea; el
final del proyecto se aplica **fuera**, sobre los subtotales agregados.

### 11.2 Porcentajes base vs porcentajes finales

- **Porcentajes base** (`aiu_proyecto_*_pct`): valores por defecto del
  proyecto/APU. Editables en parámetros del APU. Defaults 10/5/8.
- **Porcentajes finales** (`aiu_final_*_pct`): snapshot ajustado por el
  revisor al aprobar la modalidad. `NULL` por defecto.

Helper: `APUProyecto.get_aiu_pct_efectivos()` devuelve
`{admin, imprevistos, utilidad, es_final}`. Si `aiu_final_*` son `NULL`,
cae a los porcentajes base (retro-compatibilidad con APUs anteriores).

### 11.3 Modalidades soportadas

| # | Base AIU | Estado |
|---|---|---|
| 1 | Materiales + Herramientas + Transporte + Mano de obra + Administración (todos los costos directos técnicos) | ✅ Confirmada por el Excel técnico |
| 2 | Herramientas + Transporte + Mano de obra + Administración (sin Materiales) | ✅ Alternativa existente |
| 3, 4 | — | ❌ Pendientes; rechazadas si se envían manualmente |

`calcular_modalidades_aiu(pct_override=None)`:
- Si `pct_override` se pasa (usado por el revisor para preview), usa esos.
- Si no, usa `get_aiu_pct_efectivos()`.
- Garantía: el recargo `garantia_valor_recargo` se suma **al gran_total**
  de cada modalidad pero **NO entra en la base AIU** (decisión 10A-2,
  Opción A — ver §11.4).

### 11.4 Garantía Red Shield y base AIU — Decisión 10A-2

**Opción aprobada: Opción A.** La garantía Red Shield NO entra en la
base de cálculo del AIU del proyecto.

```
base_aiu_modalidad_1 = materiales_tecnico + herramientas + transporte + mano_obra + administracion
base_aiu_modalidad_2 = herramientas + transporte + mano_obra + administracion
total_aiu            = base_aiu * (A% + I% + U%) / 100
gran_total_aprobado  = subtotal_directos_tecnico + total_aiu + garantia_valor_recargo
```

**Razones:**
1. Coherencia con Fase 9R (garantía solo afecta `total_valor_venta`).
2. AIU = administración + imprevistos + utilidad sobre costos técnicos;
   incluir un recargo comercial sería "ganancia sobre ganancia".
3. El Excel técnico ubica la garantía como línea agregada, no dentro de
   la base AIU.

**Reversible:** si en una fase futura se decide lo contrario, basta cambiar
`calcular_modalidades_aiu()` para usar `subtotal_materiales_ajustado` en
Modalidad 1. Sin migraciones.

### 11.5 Flujo de revisión y aprobación

```
APU armado
  → Enviar a revisión (APUEnviarRevisionView)
    → proyecto → APU_GENERADO, solicitud → EN_REVISION
  → Revisor abre /apu/<pk>/revisar/
    → ve resumen técnico + garantía Red Shield si aplica
    → ajusta A/I/U → POST preview (recalcula sin persistir)
    → elige Modalidad 1 o 2
    → POST /apu/<pk>/aprobar-modalidad/
      → guarda modalidad_aiu_seleccionada, aiu_final_*_pct, aprobado_por, fecha_aprobacion
      → proyecto → COTIZADO, solicitud → APROBADA
  → Cambiar modalidad (opcional):
    → POST /apu/<pk>/reset-modalidad/
      → limpia modalidad_aiu_seleccionada, aprobado_por, fecha_aprobacion
      → CONSERVA aiu_final_*_pct
```

### 11.6 Vista del revisor (`apu_revisar.html`)

- Header con badge Pendiente / Aprobado.
- Resumen técnico (subtotales por categoría + total directos).
- Bloque Garantía Red Shield si aplica (informativo).
- Form de A/I/U editables + botón "Recalcular preview"
  (POST a la misma vista, sin persistir).
- Tabla comparativa Modalidad 1 vs Modalidad 2.
- Form de aprobación (radios M1/M2 + aprobador) que persiste los
  porcentajes A/I/U vía hidden inputs.
- Si ya aprobado: botón "Cambiar modalidad" → `apu_reset_modalidad`.

### 11.7 Vista APU detail (`apu_detail.html`)

- Si NO aprobado: badge "Pendiente de revisión" + modalidades
  informativas.
- Si aprobado: tarjeta verde "Modalidad AIU aprobada" con modalidad,
  porcentajes efectivos, total AIU, garantía y gran total aprobado.
- No permite seleccionar modalidad desde aquí.

### 11.8 Validaciones backend (`APUAprobarModalidadView`)

1. `modalidad_aiu` ∈ {"1", "2"}; cualquier otro valor (incluida "3"/"4")
   se rechaza con mensaje.
2. `aiu_final_*_pct` opcionales; si vienen, deben ser numéricos y ≥ 0.
3. Si NO vienen, el snapshot existente se conserva.

### 11.9 Reset de aprobación (`APUResetModalidadView`)

Limpia:
- `modalidad_aiu_seleccionada`
- `aprobado_por`
- `fecha_aprobacion`

Conserva:
- `aiu_final_admin_pct`, `aiu_final_imprevistos_pct`, `aiu_final_utilidad_pct`

Razón: el revisor puede querer corregir la modalidad usando los últimos
porcentajes ya ajustados, sin reescribirlos.

### 11.10 Migración

- `presupuestos/0025_apuproyecto_aiu_final_admin_pct_and_more.py` —
  agrega los 3 campos `aiu_final_*_pct` Decimal(8,4) null/blank.
- Sin `RunPython`; APUs anteriores siguen funcionando con fallback a
  porcentajes base.

### 11.11 Lenguaje visual

A partir de Fase 10A se evita la palabra "cuadrilla" en la UI final.
Sustituciones aplicadas: "Cuadrillas preset" → "Personal preset",
"Datos de la cuadrilla" → "Datos del grupo de personal",
"cuadrilla especializada" → "personal especializado". Los IDs internos
del modelo `CuadrillaPreset` se mantienen para no romper cálculos.

### 11.12 Lo que NO se tocó en Fase 10A

- `APULinea.valor_total`, `costo_total`, `factor_venta_pct`.
- `APUService.generar`, signals.
- Despiece Maestro, dependencias técnicas, producto principal.
- Garantía Red Shield (solo se lee `garantia_valor_recargo` para gran total).
- Modalidades 3 y 4 — pendientes para futura fase.
- Ajustes por línea (Fase 11).
- Enforcement por rol (pendiente).

---

## 12. Fase 11 — Cotización final en pantalla

### 12.1 Alcance y motivación
La cotización final consolida la información técnica y comercial del APU en un
formato entendible para el cliente. En esta fase es **una vista calculada en
pantalla** desde `APUProyecto`, no un modelo persistido ni un PDF.

### 12.2 Decisión: vista calculada, no modelo
No se crea modelo `CotizacionFinal` ni migración nueva. Toda la información se
deriva de `APUProyecto` y sus relaciones. El snapshot formal con trazabilidad
quedará para una fase posterior (PDF firmado, envío al cliente, versionado de
cotizaciones).

### 12.3 Helper `APUProyecto.get_resumen_cotizacion()`
Centraliza toda la matemática para que el template no calcule totales. Devuelve
un diccionario con subtotales técnicos, garantía, AIU efectivo, IVA, total
final y bloques relacionales (cliente, proyecto, sistema, subsistema).

Reglas implementadas:
- Si `modalidad_aiu_seleccionada` ∈ {"1","2"}: usa esa modalidad como bloque
  oficial. `es_preliminar=False`.
- Si no hay modalidad aprobada: `es_preliminar=True`, se exponen ambas
  modalidades como referencia.
- Porcentajes A/I/U: provienen de `get_aiu_pct_efectivos()` (finales del
  revisor o base del proyecto).

### 12.4 IVA sobre Utilidad (decisión Fase 11)
Por el Excel técnico, el IVA de la cotización se calcula **sobre la Utilidad**,
no sobre el subtotal completo:

```
iva_valor = valor_utilidad * iva_pct / 100   (si aplica_iva y no exención)
iva_valor = 0                                (si aplica_iva=False o exento)
```

La garantía Red Shield **no entra** en la base IVA en esta fase.

### 12.5 Fórmula del total final
```
total_final = subtotal_directos_tecnico
            + total_aiu
            + garantia_valor_recargo
            + iva_sobre_utilidad
```
Coincidente con la decisión 10A-2 (garantía fuera de base AIU) y con la
decisión 11 (IVA sobre Utilidad).

### 12.6 Vista y ruta
- `APUCotizacionFinalView` (`apps/presupuestos/views/__init__.py`).
- Ruta: `apu/<int:pk>/cotizacion/` → name `apu_cotizacion_final`.
- No bloquea acceso si el APU no está aprobado: muestra modo preliminar con
  banner de advertencia.

### 12.7 Template `apu_cotizacion_final.html`
Estructura comercial limpia:
1. Encabezado con badge Preliminar/Aprobado.
2. Datos de cliente y proyecto.
3. Alcance (sistema/subsistema).
4. Tabla de resumen comercial por categoría (no por línea técnica).
5. Comparativo M1 vs M2 (solo en preliminar).
6. Garantía Red Shield (si aplica) o aviso de no inclusión.
7. Condiciones comerciales (placeholders "Por definir" para forma de pago,
   validez y exclusiones; valores reales solo si existen en el modelo).

### 12.8 Lo que NO se muestra al cliente
- Costos internos por línea, costo unitario técnico.
- Rendimientos, fórmulas, variables del despiece.
- Detalles de `APULinea` o configuración interna.
- Palabra "Cuadrilla" (sustituida por Personal / Mano de obra).

### 12.9 Botón desde `apu_detail.html`
- Si `modalidad_aiu_seleccionada` está vacío → "Vista preliminar de cotización"
  (outline warning).
- Si está aprobada → "Ver cotización final" (success).

### 12.10 No cubierto en esta fase
- PDF de cotización (fase posterior).
- Modelo `CotizacionFinal` y versionamiento formal.
- Campos comerciales nuevos (forma de pago, validez, exclusiones) — se muestran
  como placeholders.
- Modalidades 3 y 4, ajustes por línea, permisos por rol.

## 13. Fase 11.1 — Organización de PDF y descarga real

### 13.1 Alcance
- Activar la descarga real de PDF en los botones existentes `PDF Interno` y
  `PDF Cliente` del detalle del APU.
- Reorganizar las plantillas PDF en `templates/presupuestos/pdf/`.
- Alinear la matemática del PDF Cliente con `get_resumen_cotizacion()`
  (helper de Fase 11) para garantizar coherencia entre cotización en pantalla
  y cotización enviada al cliente.
- Revertir estados del Proyecto y la Solicitud cuando se resetea la modalidad
  AIU aprobada.

### 13.2 Estructura de plantillas
```
templates/presupuestos/
├── apu_cotizacion_final.html      # vista web — Fase 11
└── pdf/
    ├── apu_pdf_interno.html       # PDF técnico interno
    └── apu_pdf_cliente.html       # PDF comercial para cliente
```

`apu_cotizacion_final.html` **no** se mueve: es vista HTML de pantalla, no PDF.

### 13.3 Generación de PDF en memoria (sin persistencia)
- WeasyPrint (`weasyprint.HTML(...).write_pdf()`) renderiza bytes en memoria.
- La respuesta HTTP usa `Content-Disposition: attachment` con nombre
  `APU_Interno_<consecutivo>.pdf` o `Cotizacion_Cliente_<consecutivo>.pdf`.
- **No se escribe ningún archivo a disco**: ni en `static/`, ni en `media/`,
  ni en raíz, ni en carpetas auxiliares. El navegador del usuario es el único
  destino del PDF.
- Si las dependencias del sistema de WeasyPrint (libgobject/Pango/Cairo)
  no están instaladas, el `OSError` se propaga al usuario sin enmascararse.

### 13.4 Diferencia funcional entre las tres salidas
| Salida | Propósito | Costos internos | Salida real | Persistencia |
|---|---|---|---|---|
| PDF Interno | Revisión técnica interna | Permitido | `application/pdf` attachment | Ninguna |
| PDF Cliente | Documento comercial al cliente | Prohibido | `application/pdf` attachment | Ninguna |
| Cotización final | Vista en pantalla para validar | Prohibido | `text/html` render | Ninguna |

### 13.5 Fuente única de verdad en PDF Cliente
- `APUPDFClienteView` invoca `apu.get_resumen_cotizacion()` y pasa el dict
  `resumen` al template. Garantía Red Shield, AIU aprobado, IVA sobre Utilidad
  y total final salen de la misma matemática que la vista de cotización final.

### 13.6 Reset de modalidad — reversión de estados
`APUResetModalidadView` ahora:
1. Limpia `modalidad_aiu_seleccionada`, `aprobado_por`, `fecha_aprobacion`.
2. Conserva `aiu_final_admin_pct`, `aiu_final_imprevistos_pct`, `aiu_final_utilidad_pct`.
3. Devuelve `Proyecto.estado` → `EstadoProyecto.APU_GENERADO`.
4. Devuelve `Solicitud.estado` → `EstadoSolicitud.EN_REVISION`.
5. Mensaje al usuario: *"La modalidad AIU fue reiniciada. El proyecto y la
   solicitud vuelven a revisión."*

`APUAprobarModalidadView` se mantiene sin cambios: `Proyecto → COTIZADO`,
`Solicitud → APROBADA`.

### 13.7 Lo que no se cubre en Fase 11.1
- Modelo `CotizacionFinal` (sigue postergado).
- Versionamiento de cotizaciones.
- Modalidades 3 y 4, ajustes por línea, permisos por rol.
- Mejoras de CSS específicas para WeasyPrint (puede requerir ajustes si el
  render PDF no replica fielmente el Bootstrap del navegador).


## 14. Fase 11.3 — Agrupación por APU y unificación de documentos

### 14.1 Botón "Cotización final" fuera de la UI
Los botones que enlazaban a `apu_cotizacion_final` se removieron de:

- `templates/presupuestos/apu_detail.html`
- `templates/comercial/proyecto_detail.html`
- `templates/comercial/solicitud_detail.html`

La vista `APUCotizacionFinalView` y la ruta `apu_cotizacion_final` quedan
intactas como vista técnica/debug accesible por URL directa, sin enlaces
desde la UI principal y sin guards de auth nuevos. El usuario solo ve dos
salidas oficiales: **PDF Interno** y **PDF Cliente**.

### 14.2 PDF Interno absorbe el resumen comercial
`apu_pdf_interno.html` añade una sección final **"Resumen comercial /
Cotización interna"** con la misma matemática de `get_resumen_cotizacion()`:

- Subtotales por categoría (materiales, herramientas, transporte, mano de
  obra, administración).
- Recargo Garantía Red Shield (si aplica).
- Subtotal directos técnicos.
- AIU aprobado (A, I, U) con sus porcentajes y valores.
- IVA sobre Utilidad.
- Total final.
- Modalidad AIU aprobada, aprobador y fecha.

El detalle técnico previo (tablas por categoría) se preserva. El template
usa `currency_nodec` — no duplica matemática.

### 14.3 PDF Cliente — banner preliminar y aprobación
`apu_pdf_cliente.html` añade:

- Banner **"Documento preliminar — APU sin modalidad AIU aprobada"** al
  inicio cuando `resumen.es_preliminar`.
- Bloque al final con modalidad AIU aprobada, aprobador, fecha y tipo de
  garantía. No expone costos internos, rendimientos ni fórmulas.

### 14.4 Detección de despieces incluidos en un APU
Helper aproximado en `APUProyecto.get_despieces_incluidos()`:

```python
DespieceMaestro.objects.filter(
    proyecto=ps.proyecto,
    subsistema=ps.subsistema,
    estado=DespieceMaestro.GUARDADO,
)
```

**No existe** una relación explícita APU ↔ DespieceMaestro en BD. La
consolidación real ocurre en `APUGenerarDesdeDespiece` y se pierde el
linaje al volcarse en `DespieceLinea`. El helper devuelve los despieces
del mismo proyecto y subsistema en estado GUARDADO, que es una
aproximación razonable para la presentación de UI.

### 14.5 Agrupación por APU en Proyecto y Solicitud
`ProyectoDetailView` y `SolicitudDetailView` construyen:

- `apus_data = [{"apu": APU, "despieces": [DM, ...]}, ...]`
- `despieces_sin_apu = [DM, ...]`

Los templates renderizan **una tarjeta por APU** con la lista de DMs
incluidos, los botones únicos (`Ver APU`, `PDF Interno`, `PDF Cliente`) y
metadatos de aprobación (modalidad, aprobador, fecha, garantía). Los DMs
sin APU se listan aparte con etiqueta "Sin APU". Ya no se muestra cada
DespieceMaestro como si fuera aprobado individualmente.

### 14.6 Lo que NO se hizo en Fase 11.3 (queda para 11.4)
- **Selección manual de despieces al generar APU.** `APUGenerarDesdeDespiece`
  sigue consolidando automáticamente todos los DMs guardados del proyecto.
  En Fase 11.4 se introducirá una vista de confirmación que permita al
  usuario elegir qué DMs incluir.
- Relación explícita M2M `APUProyecto.despieces` (sin migración en esta
  fase).
- Modalidades 3/4, ajustes por línea, persistencia de PDFs.

### 14.7 Restricciones cumplidas
Sin migraciones. Sin tocar cálculo de Garantía Red Shield, AIU matemático,
DespieceMaestro, modalidades 3/4, modelo de datos ni `EstadoProyecto`/
`EstadoSolicitud`. Sin usar "Cuadrilla". Sin permisos/auth nuevos.


## 15. Fase 11.4 — Selección manual de despieces y APU multi-despiece

### 15.1 Motivación
En proyectos grandes (cubierta, fachada, canales, domos, etc.) un mismo APU
debe consolidar varios `DespieceMaestro` de distintos subsistemas. Hasta
Fase 11.3 la consolidación era automática y opaca: cualquier DM guardado
del proyecto se mezclaba en el `ProyectoSistema` del DM disparador,
ensuciando líneas y rompiendo trazabilidad. Fase 11.4 sustituye esa
inferencia por una **selección manual explícita** con una relación de BD
dedicada.

### 15.2 Modelo de datos
- Nuevo modelo `APUDespieceIncluido` (tabla `apu_despieces_incluidos`):
  `apu` FK→`APUProyecto`, `despiece_maestro` FK→`DespieceMaestro`
  (`PROTECT`), `sistema_nombre_snapshot`, `subsistema_nombre_snapshot`,
  `orden`, `activo`, `created_at`/`updated_at`,
  `unique_together = (apu, despiece_maestro)`.
- `APULinea` recibe tres campos nuevos:
  `despiece_maestro` (FK `SET_NULL`), `sistema_nombre_snapshot`,
  `subsistema_nombre_snapshot`. Solo aplican a líneas `MATERIALES`.
- `APUProyecto.proyecto_sistema` permanece `OneToOneField` como **PS raíz**
  (configuración base del APU: AIU, garantía, no-materiales). La
  multi-pertenencia se expresa a través de `APUDespieceIncluido`.
- Migración: `presupuestos/migrations/0026_apulinea_despiece_maestro_and_more.py`.

### 15.3 Patrones de diseño
- **Strategy** → `apps/presupuestos/services/despiece_selection.py`
  (`DespieceSelectionStrategy`): lista candidatos del proyecto, valida la
  selección y marca los DMs ya incluidos en algún APU aprobado.
- **Builder** → `apps/presupuestos/services/apu_multi_builder.py`
  (`APUMultiDespieceBuilder`): reconstruye `APULinea(MATERIALES)` para el
  APU, sincroniza `DespieceLinea` del PS raíz con el DM origen,
  agrega materiales de DMs secundarios con `rendimiento` = cantidad bruta
  y snapshots de sistema/subsistema/despiece. Crea o desactiva los
  registros `APUDespieceIncluido`.
- **Facade** → `APUFacade.generar_desde_seleccion(despiece_origen, ids)`
  coordina Strategy → PS raíz → APU base (`APUService.generar`) → Builder
  dentro de `transaction.atomic`. La vista solo orquesta mensajes/redirect.

### 15.4 Flujo de generación
1. El usuario pulsa **Generar APU** desde un `DespieceMaestro`.
2. `APUSeleccionarDespiecesView` (`/presupuestos/apu/seleccionar-despieces/<pk>/`)
   lista candidatos. El origen se marca y bloquea; los demás son
   opcionales. Si no hay otros candidatos válidos, genera directo sin paso
   intermedio.
3. El POST envía la lista de IDs seleccionados (origen forzado).
4. `APUFacade.generar_desde_seleccion` ejecuta validación + builder.
5. Redirige a `apu_detail` con mensaje informativo.

`APUGenerarDesdeDespiece` se conserva como wrapper de compatibilidad y
redirige al flujo de selección (los formularios `POST` existentes siguen
funcionando).

### 15.5 Reglas de cálculo
- **Despiece raíz**: usa `ProyectoSistema` raíz, conserva la lógica de
  rendimiento (producto principal o componente legacy).
- **Despieces secundarios**: sus materiales se agregan como bloques
  independientes. `rendimiento` = cantidad bruta del producto en el DM;
  `precio_referencia` = snapshot del producto; **no se fuerzan contra la
  base del raíz**. Si la cantidad no es positiva, se persiste con
  `rendimiento = 1` (caso degenerado, no inventa rendimiento).
- **Categorías no materiales** (`MO`, `Herramientas`, `Transporte`,
  `Administración`): se generan **una sola vez** a partir de
  `SubsistemaItemAPU` del subsistema raíz. No se duplican por DM. Cuando
  el APU contiene varios DMs, `apu_detail` y los PDFs muestran un aviso:
  *"Este APU incluye varios despieces. Las categorías no materiales se
  calculan con la configuración base del APU y pueden ajustarse
  manualmente."*

### 15.6 Vistas y PDFs
- `APUProyectoDetailView` añade al contexto:
  `es_legacy_sin_seleccion`, `despieces_incluidos_lista`,
  `materiales_por_subsistema`, `materiales_multi_despiece`.
- `apu_detail.html` renderiza banner legacy, tarjeta de despieces
  incluidos, aviso multi-despiece y, cuando aplica, sub-bloques de
  materiales por subsistema.
- `apu_pdf_interno.html` agrupa la tabla de materiales por
  `subsistema_nombre_snapshot` (encabezados azules).
- `apu_pdf_cliente.html` añade un bloque **"Alcance por sistema/subsistema"**
  sobre el total final, sin costos internos.

### 15.7 APUs legacy
APUs creados antes de Fase 11.4 no tienen registros `APUDespieceIncluido`.
`APUProyecto.es_legacy_sin_seleccion()` lo detecta y muestra el banner
informativo en `apu_detail.html`. `get_despieces_incluidos()` cae al
filtro inferido por proyecto+subsistema **solo para lectura**. No se
migran datos automáticamente; no se rompen PDFs existentes.

### 15.8 Restricciones cumplidas
Sin tocar garantía Red Shield, AIU matemático, modalidades 3/4, persistencia
física de PDFs, permisos por rol, estados/choices ni la palabra "Cuadrilla".
Sin duplicar no-materiales por cada despiece. Sin marcar despieces como
incluidos si no fueron seleccionados explícitamente.

### 15.9 Pendientes diferidos
- Multi-sistema real para categorías no materiales (`MO`, `Herramientas`,
  `Transporte`, `Administración`).
- Rendimiento por producto principal independiente para cada DM secundario.
- UI de des-inclusión retroactiva (editar APU para quitar/cambiar despieces).


## 16. Fase 11.5 — Consolidación opcional de APUs

> **La consolidación de APUs es opcional y solo se ejecuta por confirmación
> explícita del usuario. Los APUs individuales conservan su independencia y
> trazabilidad.**

### 16.1 Motivación
Un proyecto puede tener varios APUs individuales (uno por subsistema, p. ej.
Cubierta + PowerGrip). El usuario puede necesitar una propuesta consolidada
sin perder los APUs individuales. La consolidación es siempre **opt-in**.

### 16.2 Modelo de datos
- `APUProyecto.tipo_apu`: `INDIVIDUAL` (default) o `CONSOLIDADO`.
- `APUProyecto.proyecto`: FK opcional a `comercial.Proyecto`. Sólo los
  consolidados la usan; los individuales siguen con `proyecto_sistema` como
  llave natural (OneToOne).
- `APULinea.apu_origen`: FK SET_NULL al APU individual de origen. NULL en
  APUs individuales.
- `APUConsolidadoOrigen` (tabla `apu_consolidado_origenes`): M2M-through
  entre el APU consolidado y los APUs de origen.

### 16.3 Reglas de unión
- **Materiales — `MaterialesUnionStrategy`**: unión acumulativa. Cada línea
  conserva `apu_origen`, `despiece_maestro`, snapshots de sistema/subsistema.
  No se deduplica.
- **No-materiales — `NoMaterialesDedupStrategy`**: deduplica por equivalencia.
  Llave preferida `(item_catalogo_id, tipo)`; fallback `(tipo, descripción
  normalizada, unidad)`. Conserva la línea de mayor `costo_total` (peor caso
  para presupuesto).
- **Garantía Red Shield**: el consolidado nace sin garantía aplicada.
- **AIU y aprobación**: el consolidado nace sin modalidad ni aprobador;
  pasa por su propio flujo de revisión.
- **APUs origen**: quedan intactos. No se archivan, no se ocultan, no
  cambian de estado.

### 16.4 Patrones de diseño
- **Facade**: `APUConsolidacionFacade.validar / preview / consolidar`.
- **Builder**: `APUConsolidadoBuilder` orquesta cabecera, replicación de
  inclusiones, materiales, no-materiales y `recalcular()`.
- **Strategy**: `MaterialesUnionStrategy` y `NoMaterialesDedupStrategy`
  implementan las reglas por categoría.

### 16.5 Flujo de usuario
1. `proyecto_detail.html` muestra el botón opcional **"Unir APUs"** cuando
   hay ≥2 APUs individuales.
2. Vista `APUConsolidarSeleccionarView` lista los APUs disponibles con
   checkboxes y separa visualmente individuales de consolidados.
3. POST → `APUConsolidarPreviewView` muestra resumen (APUs origen,
   sistemas/subsistemas, # materiales, # no-materiales antes/después de
   deduplicar, ítems deduplicados) + advertencias.
4. Confirmar → `APUConsolidarConfirmarView` ejecuta `consolidar()` y
   redirige a `apu_detail` del consolidado.
5. Sin confirmación explícita, no se crea ningún consolidado.

### 16.6 Vistas y plantillas
- `presupuestos/apu_consolidar_seleccionar.html` — checklist de APUs.
- `presupuestos/apu_consolidar_preview.html` — preview + advertencias.
- `presupuestos/apu_detail.html` — bloque "APUs origen" cuando el APU es
  consolidado (badge **CONSOLIDADO**).
- `presupuestos/pdf/apu_pdf_interno.html` — bloque "APUs origen" tras KPIs.
- `presupuestos/pdf/apu_pdf_cliente.html` — "Alcance consolidado" sin costos.
- `comercial/proyecto_detail.html` — separación visual de individuales vs.
  consolidados, badge "Individual"/"Consolidado", botón opcional "Unir APUs".
- `comercial/solicitud_detail.html` — banner visual de estado
  (EN_REVISION / APROBADA / RECHAZADA) y resumen de APUs (total /
  individuales / consolidados / en revisión / aprobados).

### 16.7 Migración
`presupuestos/migrations/0027_apulinea_apu_origen_apuproyecto_proyecto_and_more.py`
añade `tipo_apu`, `proyecto`, `APULinea.apu_origen` y crea
`APUConsolidadoOrigen`.

### 16.8 Restricciones cumplidas
Sin tocar garantía Red Shield matemática, AIU matemático, Modalidades 3/4,
descarga de PDFs, permisos, estados/choices ni Despiece Maestro. No se usa
"Cuadrilla". No se duplican no-materiales. No se consolida sin confirmación.

### 16.9 Pendientes diferidos
- Botón para des-consolidar / desactivar `APUConsolidadoOrigen`.
- Editar ítems deduplicados antes de confirmar (override manual).
- Heredar garantía/modalidad sugerida desde el APU origen elegido.

### 16.10 Fase 11.5.1 — Visibilidad de la consolidación
- `construir_resumen_preview()` ahora devuelve `materiales_por_origen`
  (jerarquía APU → sistema/subsistema/despiece → líneas) y
  `no_materiales_conservados` (lista completa con flag `es_dedup`).
- `apu_consolidar_preview.html` muestra:
  - "Materiales que se consolidarán": panel por APU origen con tablas
    Material/Unidad/Cantidad/Valor por subsistema y subtotal.
  - "No-materiales que se reutilizarán / deduplicarán" en dos columnas
    (Se conservan / Se deduplicaron) con explicación textual por ítem.
- `APUProyectoDetailView` agrega `materiales_por_origen_consolidado` y
  `resumen_consolidacion` (conteos) cuando `apu.es_consolidado`.
- `apu_detail.html` muestra "Resumen de consolidación" arriba (KPIs:
  APUs origen, sistemas, subsistemas, materiales, no-materiales antes/
  después). Materiales: bloques `<details>` colapsables por APU origen,
  cada uno con sus grupos sistema/subsistema/despiece.
- `proyecto_detail.html`: botón "⊕ Unir APUs y consolidar materiales"
  con ayuda explícita.

Esta fase es solo de visibilidad: no toca modelos, migraciones, Builder,
Facade, AIU, garantía Red Shield, aprobación, PDFs ni permisos.

### 16.11 Fase 11.5.2 — PDFs del APU consolidado

**Problema corregido.** Los PDFs Interno y Cliente de un APU consolidado se
renderizaban incompletos porque:
- `APUPDFInternoView` y `APUPDFClienteView` no recibían el contexto
  consolidado que sí construía `APUProyectoDetailView`.
- Los templates PDF asumían siempre `apu.proyecto_sistema` no nulo, pero el
  consolidado tiene `proyecto_sistema=None` y referencia su proyecto vía
  `APUProyecto.proyecto` (FK directo).

**Solución — helper compartido.**
`apps/presupuestos/views/__init__.py::_build_apu_consolidado_context(apu)`
centraliza la construcción de:
- `apus_origen`
- `resumen_consolidacion`
- `materiales_por_origen_consolidado`
- `lineas_no_materiales`

Los tres puntos de consumo lo usan: `APUProyectoDetailView`,
`APUPDFInternoView`, `APUPDFClienteView`. Cero duplicación.

**Vistas.** Ambas vistas PDF ahora calculan `proyecto = apu.get_proyecto()` y,
si `apu.es_consolidado`, fusionan el helper en el contexto.

**Templates.**
- `apu_pdf_interno.html`: header/banner usan `proyecto`; nuevo bloque
  "Resumen de consolidación" (6 KPIs), nuevo bloque "APUs origen" con estado
  y modalidad. La sección Materiales abre rama cuando `es_consolidado` y
  agrupa por APU origen → sistema/subsistema en tablas planas (no `<details>`,
  WeasyPrint-safe).
- `apu_pdf_cliente.html`: header y banner-obra usan `proyecto`; banner
  preliminar diferencia el copy si es consolidado; bloque "Alcance
  consolidado" se enriquece con lista de sistemas/subsistemas; sin costos
  internos, sin rendimientos.

**No se tocó:** modelos, migraciones, Builder, Facade, Strategy, matemática
AIU, garantía Red Shield, aprobación, estados, descarga de PDFs ni el flujo
de consolidación.


### 16.12 Fase 11.5.3 — Eliminación vs Archivado (2026-06)

**Causa que se corrigió:** intentar eliminar una `Solicitud`, `Proyecto` o
`DespieceMaestro` con relaciones críticas producía un `ProtectedError` que
escalaba a la pantalla amarilla de Django (HTTP 500).

#### Política funcional

| Operación  | Significado | Cuándo aplica |
|------------|-------------|---------------|
| Eliminar   | Borrado físico irreversible | Solo si NO hay relaciones críticas |
| Archivar   | Solicitud pasa a `EstadoSolicitud.CERRADA` | Solicitud con proyectos/APUs |
| Anular     | Proyecto pasa a `EstadoProyecto.ANULADO` | Proyecto con APUs/despieces |
| Archivar APU | `APUProyecto.archivado=True` | APUs origen de consolidado, APUs consolidados, o cualquier APU que se quiera ocultar preservando trazabilidad |

#### Trazabilidad protegida (no se relaja)

Se mantienen los `on_delete=PROTECT` existentes:

- `APUConsolidadoOrigen.apu_origen` → APU individual no se borra si es origen
  de un consolidado.
- `APUDespieceIncluido.despiece_maestro` → DespieceMaestro no se borra si está
  incluido en un APU.

La solución no es relajar la integridad referencial sino capturar el error y
ofrecer archivado.

#### Manejo de `ProtectedError`

Las 3 vistas que pueden disparar el error ahora lo capturan y muestran un
mensaje amigable + redirect al detalle:

- `SolicitudDeleteView` (`apps/comercial/views.py`)
- `ProyectoDeleteView` (`apps/comercial/views.py`)
- `EliminarDespieceMaestroView` (`apps/ingenieria/views/calculador.py`)

Nunca aparece la pantalla amarilla de Django.

#### Nuevas vistas de archivado

- `SolicitudArchivarView` (POST `/comercial/solicitudes/<pk>/archivar/`)
  → `estado = CERRADA`.
- `ProyectoAnularView` (POST `/comercial/proyectos/<pk>/anular/`)
  → `estado = ANULADO`.
- `APUArchivarView` (POST `/presupuestos/apu/<pk>/archivar/`)
  → marca `archivado=True`, fija `fecha_archivado`, `archivado_por` y
  `motivo_archivado`. No toca líneas, líneas consolidadas, APUs origen,
  aprobación AIU, garantía Red Shield ni PDFs.

#### Campos nuevos en `APUProyecto` (migración 0028)

```
archivado          BooleanField(default=False, db_index=True)
fecha_archivado    DateTimeField(null=True, blank=True)
archivado_por      FK ConfiguracionSistema SET_NULL null=True blank=True
motivo_archivado   TextField(blank=True, default="")
```

Justificación: `APUProyecto` no tiene un estado propio de anulado/archivado
(su "estado" surge de modalidad AIU + aprobación + fechas), por eso no
conviene mezclar archivado con la máquina de aprobación.

#### Comportamiento con APU consolidado

- Archivar un APU **individual** que es origen de un consolidado: el flag se
  pone en True; la relación `APUConsolidadoOrigen` se conserva intacta; el
  consolidado sigue existiendo y mostrando sus materiales.
- Archivar un APU **consolidado**: no se tocan los APUs origen ni las
  relaciones `APUConsolidadoOrigen`.

#### Filtros de listas

- `APUListView` oculta archivados por defecto. `?archivados=1` los muestra.
- `Solicitud`/`Proyecto`: el visual ya distingue `CERRADA` y `ANULADO`.

#### UI

- `solicitud_detail`: si hay proyectos, el botón "Eliminar" se reemplaza por
  "Archivar"; el modal explica que por trazabilidad solo se archivará.
- `proyecto_detail`: botón "Anular" abre modal de confirmación.
- `apu_detail`:
  - banner "APU archivado" con fecha/usuario/motivo;
  - banner "Este APU hace parte de consolidado #X" cuando aplica;
  - botón "Archivar" con modal y campo motivo.

#### No se tocó

Builder, Facade, Strategies, matemática AIU, garantía Red Shield, aprobación,
modalidad, descarga de PDFs, APUs individuales matemáticamente, flujo de
consolidación, ni los `on_delete=PROTECT` existentes.


### 16.13 Fase 11.5.4 — Devolución vs Rechazo (2026-06)

**Decisión conceptual:** este sistema gestiona el **proceso interno** de
presupuestos, no el seguimiento comercial del cliente. Por lo tanto, cuando
el aprobador no aprueba una solicitud, la acción correcta es **devolver**,
no rechazar.

#### Semántica de estados de `Solicitud`

| Estado | Significado | UI |
|--------|-------------|----|
| EN_GESTION / EN_PRESUPUESTO | Trabajo en curso | — |
| EN_REVISION | Pendiente de aprobación | "Solicitud en revisión — pendiente de aprobación." |
| APROBADA | Presupuesto aprobado y finalizado | "Solicitud aprobada y finalizada." |
| **DEVUELTA** | Devuelta por el aprobador para ajustes | "Solicitud devuelta para ajustes." |
| CERRADA | Cierre administrativo / archivado (Fase 11.5.3) | "Solicitud cerrada / archivada." |
| RECHAZADA | **Legacy.** Se mantiene en choices por compatibilidad, pero en la UI se trata visualmente como "Devuelta". No se usa para nuevas devoluciones. | "Devuelta" |

**"Devuelta" NO significa:** rechazo comercial · cierre negativo · que el
cliente rechazó · pérdida de la oportunidad. Es un estado intermedio del
flujo interno de presupuesto.

#### Migración 0020 de `comercial`

- Choices de `Solicitud.estado`: agrega `DEVUELTA = "DEVUELTA", "Devuelta"`.
- Nuevo campo `Solicitud.motivo_devolucion = TextField(blank=True, default="")`
  — paralelo al `Proyecto.motivo_devolucion` ya existente. Se guarda separado
  de `observaciones` para no contaminar el campo libre del asesor.

#### Vista y URL

`SolicitudDevolverView` (POST `/comercial/solicitudes/<pk>/devolver/`):
- escribe `estado = DEVUELTA`;
- guarda el motivo del POST en `motivo_devolucion`;
- registra log `DEVOLVER_SOLICITUD`.

No borra proyectos, APUs ni cotizaciones. Trazabilidad intacta.

#### Resolución de la devolución

Cuando el revisor aprueba la modalidad AIU del APU vía
`APUAprobarModalidadView`, la solicitud pasa a `APROBADA` aunque viniera de
`DEVUELTA`. Es decir, aprobar el APU corregido **resuelve la devolución
automáticamente** — no se requiere acción manual extra.

#### UI

- `solicitud_detail`: banner ámbar "Solicitud devuelta para ajustes" con
  motivo; botón "Devolver" solo si `EN_REVISION`; modal con campo motivo.
- `solicitud_list`: badge ámbar (no rojo) para `DEVUELTA` y `RECHAZADA`,
  ambas etiquetadas "Devuelta".

#### No se tocó

AIU matemático, garantía Red Shield, PDFs, archivado/anulación de
Fase 11.5.3, PROTECT, consolidación de APUs, Fase 12.

## §16.14 — Fase 12 · Snapshot inmutable de cotización aprobada

### Decisión

Cuando el revisor aprueba la modalidad AIU de un APU se crea un **snapshot
inmutable** del documento aprobado. El snapshot vive en el modelo
`CotizacionAPU` y conserva todos los datos finales (subtotales, AIU, garantía,
IVA, total, líneas, despieces incluidos, APUs origen del consolidado) de modo
que los PDFs Interno y Cliente puedan regenerarse después en memoria SIN
depender de los datos vivos del APU.

**No se persiste archivo PDF físico** ni en `static`, ni en `media`. Solo se
persiste el dato congelado en BD.

### Distinción APU vivo ↔ Cotización aprobada

| | APU vivo (`APUProyecto`) | Cotización aprobada (`CotizacionAPU`) |
|---|---|---|
| Editable | Sí | No |
| Cambia con modificaciones posteriores | Sí | No (congelada) |
| PDFs generados | Preliminares (vivos) | Aprobados (snapshot) |
| Rutas | `apu/<pk>/pdf-interno`, `apu/<pk>/pdf-cliente` | `cotizacion/<pk>/pdf-interno`, `cotizacion/<pk>/pdf-cliente` |
| Total mostrado | Puede cambiar | Inmutable |

### Versionamiento

- Cada llamada a `CotizacionSnapshotService.crear_snapshot(apu)` calcula
  `version = max(version anterior) + 1` para ese APU.
- La versión anterior con `estado=APROBADA` se marca `REEMPLAZADA`. El
  histórico NUNCA se elimina.
- El último snapshot con `estado=APROBADA` es el **vigente**, accesible por
  `apu.cotizacion_vigente` o `CotizacionSnapshotService.obtener_snapshot_vigente(apu)`.

### Creación del snapshot

`APUAprobarModalidadView` lo invoca **después** de:

1. Guardar `modalidad_aiu_seleccionada`, `aprobado_por`, `fecha_aprobacion`,
   `aiu_final_*_pct` en el APU vivo.
2. Marcar `Proyecto.estado = COTIZADO`.
3. Marcar `Solicitud.estado = APROBADA`.

Es decir, el snapshot refleja exactamente el estado oficial aprobado.

### Comportamiento con Reset de modalidad

`APUResetModalidadView` revierte el APU vivo y los estados de
Proyecto/Solicitud, pero **NO toca los snapshots**. La cotización aprobada
anterior se conserva como histórico (`APROBADA` → quedará como `REEMPLAZADA`
cuando se cree el siguiente snapshot al re-aprobar).

### Comportamiento con Solicitud DEVUELTA

`SolicitudDevolverView` (Fase 11.5.4) NO toca snapshots, NO borra APUs y NO
borra trazabilidad. Si después la solicitud se aprueba de nuevo, se crea una
nueva versión del snapshot que reemplaza a la anterior.

### APU consolidado

El snapshot de un APU consolidado guarda en `data_snapshot.consolidado`:

- Lista de APUs origen (`apus_origen`) con `id + nombre_snapshot + tipo`.
- Materiales congelados con su `apu_origen_id`, `despiece_maestro_id`,
  `sistema_nombre_snapshot`, `subsistema_nombre_snapshot`.
- Despieces incluidos.

Esto permite regenerar el PDF Cliente con los bloques de orígenes incluso si
un APU origen se modifica o archiva después.

### Garantía Red Shield, Modalidad 3/4, AIU matemático

NO se tocaron. La garantía queda congelada con sus snapshots dedicados
(`garantia_porcentaje_snapshot`, `garantia_modo_snapshot`,
`garantia_material_snapshot`, `garantia_base_valor`, `garantia_valor_recargo`).

## §17 — Seguridad del flujo de aprobación (Fase 12.2)

### Identidad

El proyecto NO usa `django.contrib.auth` para autorización: opera con su
propia `ConfiguracionSistema` y `AuthCustomMiddleware`. La sesión guarda
`session["usuario_id"]` y `session["rol"]`. El helper central
`apps.common.auth.get_usuario_actual(request)` resuelve el
`ConfiguracionSistema` correspondiente (activo).

### Gates centralizados (`apps/common/auth.py`)

| Función                              | Regla |
|--------------------------------------|-------|
| `puede_aprobar_apu(request, apu)`    | revisor asignado en `apu.revisor` **o** rol `ADMINISTRADOR` |
| `puede_enviar_a_revision(request,apu)` | creador del proyecto **o** rol `ASESOR_COMERCIAL` / `PRESUPUESTOS` / `ADMINISTRADOR` |
| `puede_devolver_solicitud(request,s)` | revisor de algún APU vivo de la solicitud **o** `ADMINISTRADOR` |
| `es_admin(request)`                  | rol == `ADMINISTRADOR` |
| `get_usuario_actual(request)`        | `ConfiguracionSistema` activo según sesión |

### Vistas protegidas

- `APUEnviarRevisionView.post` — `puede_enviar_a_revision`.
- `APUAprobarModalidadView.post` — `puede_aprobar_apu`; `apu.aprobado_por`
  se asigna **automáticamente** desde `get_usuario_actual(request)` y se
  ignora cualquier `aprobado_por_id` enviado en el form.
- `APUResetModalidadView.post` — `puede_aprobar_apu`.
- `SolicitudDevolverView.post` — `puede_devolver_solicitud` + `motivo`
  obligatorio (sin motivo, no devuelve y muestra error).
- `APURevisarView` — el GET sigue abierto a usuarios autenticados como
  vista informativa, pero el contexto incluye `puede_aprobar`,
  `es_aprobador_asignado`, `es_administrador`, `usuario_actual` para que
  el template oculte el form de aprobación / devolución y muestre solo
  lectura cuando no se cumple.

### Comportamiento ante intento no autorizado

`redirect` con `messages.error("No tiene permiso para aprobar este APU.
Solo el aprobador asignado puede realizar esta acción.")` + log
`APROBACION_DENEGADA` en `LogSistema`. **Nunca** se crea snapshot, nunca
cambia el estado del Proyecto a `COTIZADO` ni el de la Solicitud a
`APROBADA`, nunca se persiste modalidad.

### Auditoría

Acciones registradas vía `registrar_log`:

- `ENVIAR_REVISION`
- `APROBAR_MODALIDAD`
- `RESET_MODALIDAD`
- `DEVOLVER_SOLICITUD`
- `APROBACION_DENEGADA` (intentos rechazados por gate)

### UI condicional

- `apu_detail.html`: botón "Enviar a revisión" sólo si `puede_enviar_revision`.
  "Ir a revisión" sólo si `puede_aprobar`. Si no: chip "Pendiente de
  aprobación por: X."
- `apu_revisar.html`: banner azul para el aprobador asignado, banner naranja
  para administrador no asignado, banner gris solo-lectura para el resto.
  El form de aprobación y el modal "Devolver" sólo se renderizan si
  `puede_aprobar`. Se eliminó el select `aprobado_por_id` — el aprobador
  se toma del usuario en sesión y se muestra como referencia.
- `solicitud_detail.html`: botón "Devolver" sólo si `puede_devolver`.
  Modal exige textarea de motivo `required`.

### Restricciones honradas

NO se tocó AIU matemático, garantía Red Shield, snapshot `CotizacionAPU`,
Builder, Facade, Strategies, PDFs (sólo enlaces/botones de navegación),
archivado/anulación, ni se introdujeron migraciones nuevas.


## §18 — Administrador inicial seguro y tema visual ADMINISTRADOR (Fase 12.3)

### Identidad y contraseñas

A partir de Fase 12.3 las contraseñas de `ConfiguracionSistema` se almacenan
**hasheadas con los hashers de Django** (`make_password` / `check_password`).
El campo `password_hash` siempre contiene un hash, nunca texto plano.

#### Auto-upgrade transparente

Para usuarios creados antes de Fase 12.3 cuyo `password_hash` quedó como
texto plano, el login (`apps/configuracion/views.py:LoginConfiguracionView`)
sigue este flujo:

1. Identifica si el valor en BD es un hash Django (`identify_hasher`).
2. Si lo es → `check_password` normal.
3. Si es texto plano legacy → compara con el POST y, si coincide, lo
   reemplaza inmediatamente por `make_password(password)` y autentica.
4. Cualquier guardado posterior (`ConfiguracionCreateView`,
   `ConfiguracionUpdateView`) usa `make_password`.

Resultado: la migración a hashing es transparente para los usuarios
existentes y no requiere migración de BD.

### Comando `ensure_default_admin`

Ubicación: `apps/configuracion/management/commands/ensure_default_admin.py`.

Crea (o detecta) el administrador inicial leyendo:

| Variable | Obligatoria | Default |
|---|---|---|
| `ANDINACOST_ADMIN_EMAIL` | sí | — |
| `ANDINACOST_ADMIN_PASSWORD` | sí | — |
| `ANDINACOST_ADMIN_NAME` | no | "Administrador del sistema" |
| `ANDINACOST_ADMIN_UNIDAD` | no | `IMPERANDINA` |

Reglas:

- Idempotente conservador: si el usuario ya existe **no** sobrescribe
  contraseña ni rol.
- Valida longitud mínima (10 chars) y blacklist (`admin`, `admin123`,
  `password`, `123456`, …).
- Nunca imprime la contraseña.
- Guarda siempre `make_password(...)`.

Uso recomendado:

```bash
export ANDINACOST_ADMIN_EMAIL=admin@empresa.com
export ANDINACOST_ADMIN_PASSWORD='clave-fuerte-no-trivial'
python manage.py ensure_default_admin
```

Tras el primer ingreso, el administrador puede cambiar su contraseña
desde la pantalla de Configuración. El cambio queda hasheado por
`ConfiguracionUpdateView.form_valid`.

### Tema visual `ADMINISTRADOR`

El template base aplica:

```html
<body class="theme-{{ unidad_slug }}{% if request.session.rol == 'ADMINISTRADOR' %} theme-admin{% endif %}">
```

El nuevo `static/css/admin-theme.css` redefine, sólo cuando coexiste
`theme-admin`, las variables `--theme-accent`, `--surface`, `--card`,
`--ink`, `--ink-soft` y `--border` hacia una paleta de grises, negros
y blancos. No afecta a otros roles ni al theme por unidad de negocio
(la unidad permanece como clase base).

### Flujo de revisión — Accesos del aprobador

- `solicitud_detail.html`: en cada APU listado, si el APU está en revisión
  (`fecha_envio_revision`) y el usuario actual está autorizado para aprobarlo
  (helper `puede_aprobar_apu`), aparece un botón **"Ir a la revisión"**
  que lleva a `apu_revisar`. El botón **"Ver APU"** permanece como acceso
  alterno al detalle. Filtros condicionales viven en
  `apps/common/templatetags/auth_tags.py`.

- `apu_revisar.html`: cabecera con accesos rápidos del aprobador:
  **Ver APU** y **Ver despiece** (o un dropdown **Ver despieces (N)**
  si el APU incluye varios). Usa `apu.get_despieces_incluidos()`.

### Bloqueo de reenvío a revisión tras aprobación

`APUEnviarRevisionView.post` bloquea cualquier intento de reenvío si el
APU ya fue aprobado (tiene `modalidad_aiu_seleccionada` **o**
`fecha_aprobacion` **o** `aprobado_por`). El bloqueo:

- Registra `APROBACION_DENEGADA` en `LogSistema`.
- Muestra el mensaje exacto:
  *"Este APU ya fue aprobado y no puede reenviarse a revisión. Si
  requiere cambios, primero debe resetear la modalidad según el flujo
  autorizado."*
- No modifica `revisor`, `fecha_envio_revision`, ni la aprobación.
- No crea/borra snapshot `CotizacionAPU`.

La UI complementa: el form de "Enviar a revisión" en
`apu_detail.html` queda oculto cuando el APU está aprobado.

### Restricciones honradas

No se tocó AIU matemático, garantía Red Shield, snapshot `CotizacionAPU`,
Builder, Facade, Strategies, PDFs (sólo enlaces/botones), archivado /
anulación, ni se introdujeron migraciones nuevas.


## §19 — Rol GERENTE y ADMINISTRADOR global (Fase 12.3 ext)

### Jerarquía funcional

1. **ADMINISTRADOR** — global, atraviesa todas las unidades de negocio.
   Tema visual: `theme-admin-global` (grises / negros / blancos).
2. **GERENTE** — acceso total, **únicamente a su unidad**.
   Tema visual: `theme-{unidad}` (colores de su unidad).
3. **PRESUPUESTOS** — operación de presupuestos en su unidad.
4. **ASESOR_COMERCIAL** — operación comercial en su unidad.
5. **COMPRAS** — operación de compras en su unidad.
6. **SOLO_LECTURA** — consulta en su unidad.

### Helpers (apps/common/auth.py)

- `es_admin(request)` — rol ADMINISTRADOR.
- `es_gerente(request)` — rol GERENTE.
- `es_global(request)` — atraviesa unidades. Hoy ≡ `es_admin`.
- `puede_ver_todas_las_unidades(request)` — sólo ADMINISTRADOR.
- `unidad_efectiva(request)` — `""` para ADMINISTRADOR (global), o
  `session["unidad_negocio"]` para el resto. Se usa en filtros de
  queryset (`UnidadFilterMixin`) y en el dashboard.
- `puede_gestionar_unidad(request, unidad)` — True si ADMINISTRADOR o
  si `unidad == session["unidad_negocio"]`.

### Matriz de permisos

| Acción | ADMIN | GERENTE | PRESUPUESTOS | ASESOR | COMPRAS | SOLO_LECTURA |
|---|---|---|---|---|---|---|
| Ver datos otras unidades | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Ver datos su unidad | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Enviar a revisión (su unidad) | ✓ (global) | ✓ | ✓ | ✓ | ✗ | ✗ |
| Aprobar APU | ✓ (siempre) | sólo si revisor | sólo si revisor | sólo si revisor | ✗ | ✗ |
| Devolver solicitud | ✓ (siempre) | sólo si revisor | sólo si revisor | sólo si revisor | ✗ | ✗ |
| Reset modalidad | ✓ | sólo si revisor | sólo si revisor | sólo si revisor | ✗ | ✗ |
| CRUD usuarios | ✓ | ✗ (fase posterior) | ✗ | ✗ | ✗ | ✗ |

GERENTE **no aprueba** ni devuelve solicitudes automáticamente por ser
gerente. Aplica la misma regla de Fase 12.2: sólo el revisor asignado
o ADMINISTRADOR.

### Filtros por unidad

- `UnidadFilterMixin.get_queryset` ahora hace bypass para
  ADMINISTRADOR. El resto de roles ve únicamente su unidad.
- `DashboardView` usa `unidad_efectiva(request)` para que el ADMIN vea
  totales globales sin selector adicional.

### Acceso por URL directa — gates de detalle

Para evitar que un usuario no-ADMIN abra por URL un objeto de otra
unidad, se aplica el nuevo `UnidadObjectAccessMixin` (en
`apps/common/mixins.py`) a:

- `ClienteDetailView`
- `SolicitudDetailView`
- `ProyectoDetailView`
- `APUProyectoDetailView` (via `dispatch` directo)
- `APURevisarView` (validación al inicio de `_render`)

Si la unidad del objeto no coincide → log, mensaje
*"No tiene permiso para acceder a información de otra unidad."* y
redirect al dashboard.

### Tema visual

`templates/base.html` aplica clases mutuamente excluyentes:

```html
{% if request.session.rol == 'ADMINISTRADOR' %}
  <body class="theme-admin-global">
{% else %}
  <body class="theme-{{ unidad_slug }}">
{% endif %}
```

`static/css/admin-theme.css` define la paleta gris/negro/blanco bajo
`body.theme-admin-global`. GERENTE conserva los colores de su unidad
porque no entra a la rama admin.

### Migración

Sólo cambio de `choices` en `RolSistema` (agregar GERENTE). Migración
generada `apps/configuracion/migrations/0010_alter_configuracionsistema_rol.py`.
No altera el schema PostgreSQL — sólo el `state_operations` del ORM.

### Compatibilidad técnica del ADMINISTRADOR

`ConfiguracionSistema.unidad_negocio` sigue siendo obligatorio. Para
los usuarios `ADMINISTRADOR` la unidad almacenada **no limita** datos
ni define el tema — sólo conserva integridad técnica del modelo.


## §20 — Unidad corporativa EDILANDINA (Fase 12.3 ext)

### Concepto

`EDILANDINA` es una unidad de negocio **corporativa/técnica** reservada
al ADMINISTRADOR global. No representa una unidad operativa como
Imperandina, Solarandina o Impertienda. Su única función es darle
identidad visual al alcance global del administrador (paleta
gris/negro/blanco) sin romper la integridad del modelo, que exige
`ConfiguracionSistema.unidad_negocio` obligatorio.

**Regla funcional:** un usuario con `rol = ADMINISTRADOR` y
`unidad_negocio = EDILANDINA` sigue siendo global: ve solicitudes,
proyectos, APUs, clientes y opciones de todas las unidades. La unidad
EDILANDINA **no filtra** sus datos.

### Choices

`UnidadNegocio.EDILANDINA = "EDILANDINA", "Edilandina"` en
`apps/common/choices.py`. La migración generada
(`apps/configuracion/migrations/0011_*.py`) es state-only —
`AlterField unidad_negocio` y `AlterField codigo` de `UnidadNegocioInfo`,
sin cambios de schema en PostgreSQL.

### Tema visual

`static/css/admin-theme.css` aplica la misma paleta a:

- `body.theme-admin-global` — activo cuando `rol == ADMINISTRADOR`.
- `body.theme-edilandina` — activo cuando un usuario no admin tenga
  `unidad_negocio == EDILANDINA` (caso atípico).

Ambos selectores enumeran cada combinación por separado para evitar
problemas de precedencia. `static/css/sidebar-light.css` agrega
`--sidebar-light-icon-active: #4b5563` para ambos.

`templates/base.html` no requiere cambios: la lógica excluyente sigue
siendo `rol == ADMINISTRADOR → theme-admin-global`, en otro caso
`theme-{unidad_slug}`. Si esa unidad es EDILANDINA, la clase queda
`theme-edilandina` y comparte estilos con `theme-admin-global`.

### Comando `ensure_default_admin` ampliado

- Default de `ANDINACOST_ADMIN_UNIDAD` cambia de `IMPERANDINA` a
  `EDILANDINA`.
- Si el administrador ya existe y tiene rol `ADMINISTRADOR` con una
  unidad distinta a la pedida, el comando **reasigna solamente la
  unidad** (no toca contraseña, rol, ni nombre) y emite:
  `"Administrador global asociado a {unidad}."`.
- Si el administrador ya existe y su unidad coincide → mensaje
  conservador `"Administrador inicial ya existe."`.
- Si existe un usuario con ese email pero **no** es ADMINISTRADOR → no
  se toca, mensaje explícito.
- Idempotente. Nunca imprime contraseña.

### Compatibilidad

Las tres unidades operativas (Imperandina, Solarandina, Impertienda)
conservan sus colores y comportamiento. Ningún usuario existente con
esas unidades se ve afectado por agregar EDILANDINA.

### Restricciones honradas

No se tocó AIU matemático, garantía Red Shield, snapshot CotizacionAPU,
Builder, Facade, Strategies, PDFs, aprobación, devolución, archivado,
PROTECT ni Fase 13. No se usa "Cuadrilla".
