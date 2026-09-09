# CONTEXT — Despiece & APU
> Scope: presupuestos (Despiece + APU). Excluye: comercial, clientes, usuarios, logs.

---

## 1. MODELOS

### Proyecto (`comercial.Proyecto` · db: `proyectos`)
- Propósito: cabecera del presupuesto
- Campos clave: `consecutivo`, `estado` (EstadoProyecto), `area_total_m2`, `perimetro_ml`, `iva_pct`, `aplica_exencion_iva`, `trm`, `margen_material_pct`, `margen_mano_obra_pct`, `aiu_contratista_pct`
- Relaciones: → ProyectoSistema (1:N), → DespieceLinea (1:N)
- Métodos: `avanzar_a_despiece()`, `avanzar_a_apu()`

### ProyectoSistema (`presupuestos` · db: `proyecto_sistemas`)
- Propósito: instancia de un sistema/subsistema ejecutado para un proyecto
- Campos clave: `parametros_entrada` (JSONField), FK→`proyecto`, FK→`sistema`, FK→`subsistema` (nullable)
- Relaciones: → DespieceLinea (1:N), ↔ APU (1:1)
- Métodos: `get_contexto()` → dict con area_m2 + params, `get_variables_requeridas()` → lee system_defs
- Unique: `(proyecto, sistema, subsistema)`

### DespieceLinea (`presupuestos` · db: `despiece_lineas`)
- Propósito: componente calculado del despiece con precio snapshot
- Campos clave: `componente_codigo`, `cantidad_calculada`, `cantidad_ajustada` (nullable), `precio_snapshot`, `motivo_ajuste`, FK→`producto` (nullable), FK→`categoria_producto` (nullable), FK→`proyecto_sistema`
- Propiedades: `cantidad_final` = ajustada ?? calculada; `pendiente_seleccion` = producto NULL & categoria NOT NULL; `estado_tecnico` = RESUELTO | PENDIENTE_SELECCION | ERROR_CONFIGURACION
- Métodos: `capturar_precio()` (mejor precio activo del proveedor), `resolver_producto(p)`

### Producto (`catalogos.Producto`)
- Propósito: material/insumo del catálogo
- Campos clave: `nombre`, `codigo`, FK→`categoria` (CategoriaProducto), FK→`unidad`
- **NO tiene precio propio** — precio viene de `ProveedorProducto.precio_unitario`
- Relación: → DespieceLinea via `despiece_lineas`

### CategoriaProducto (`catalogos.CategoriaProducto`)
- Propósito: agrupador de productos, placeholder en DespieceLinea sin producto
- Campos: `nombre`, `slug`

### ConfiguracionAPU (`presupuestos` · db: `configuracion_apu`)
- Propósito: parámetros globales para el cálculo APU (singleton activo)
- Campos: `margen_material_pct` (def 20%), `iva_pct` (def 19%), `aiu_contratista_pct` (def 30%), `margen_mano_obra_pct` (def 20%), `desperdicio_pct` (def 3%)
- Classmethod: `activa_o_default()` → crea si no existe

### APU (`presupuestos` · db: `apus`)
- Propósito: cabecera del Análisis de Precios Unitarios
- Campos clave: `nombre`, FK→`proyecto_sistema` (OneToOne nullable), `margen_material_pct`, `margen_mano_obra_pct`, `aiu_contratista_pct`, `iva_pct`, `aplica_iva`
- Los márgenes y el AIU se siembran desde el `Proyecto` al crear el APU; `ConfiguracionAPU` es el respaldo
- Subtotales (calculados): `subtotal_materiales`, `subtotal_herramientas`, `subtotal_transporte`, `subtotal_mano_obra`, `subtotal_administracion`
- Totales (calculados): `total_costo`, `total_valor_venta`
- Método: `recalcular()` → llama `linea.calcular()` por cada línea, agrega por tipo, guarda

### APULinea (`presupuestos` · db: `apu_lineas`)
- Propósito: recurso individual del APU con su costo
- Campos entrada: `tipo` (TipoAPU), `descripcion`, `rendimiento`, `unidad`, `precio_referencia`, `iva_aplicado`, `editable`
- Campos por tipo:
  - Personal: `salario_base`, `prestaciones`
  - Herramienta: `vida_util_dias`, `costo_por_dia`
- Campos calculados: `costo_unitario`, `costo_total`, `valor_unitario`, `valor_total`
- FKs origen: FK→`item_catalogo` (ItemCatalogoAPU nullable), FK→`despiece_linea` (DespieceLinea nullable)
- Señales: `post_save` (si update_fields incluye costo_total) + `post_delete` → disparan `apu.recalcular()`

### CategoriaItemAPU (`presupuestos` · db: `catalogo_apu_categorias`)
- Propósito: agrupa ítems del catálogo APU por TipoAPU
- Campos: `tipo_apu` (TipoAPU), `nombre`, `activa`, `orden`

### ItemCatalogoAPU (`presupuestos` · db: `catalogo_apu_items`)
- Propósito: recurso reutilizable (personal, herramienta, equipo, transporte)
- Campos: `categoria` (FK), `codigo` (unique nullable), `nombre`, `precio_base`, `unidad` (dia/mes/hora/und/mts/global)
- Personal: `salario_base`, `prestaciones` → property `total_mes_personal`
- Herramienta: `vida_util_dias` → property `costo_por_dia_herramienta` = precio_base / vida_util_dias

### CuadrillaPreset (`presupuestos` · db: `cuadrilla_presets`)
- Propósito: plantilla de cuadrilla nombrada (básica, completa, etc.)
- Campos: `nombre`, `activo`
- Properties: `total_personas`, `costo_mes_total`
- Composición: → CuadrillaPresetItem (1:N)

### CuadrillaPresetItem (`presupuestos` · db: `cuadrilla_preset_items`)
- Propósito: cargo × cantidad dentro de un preset
- Campos: FK→`preset`, FK→`item` (ItemCatalogoAPU), `cantidad`
- Unique: `(preset, item)`

---

## 2. ENUMS

```
TipoAPU:       MATERIALES | HERRAMIENTAS_EQUIPOS | TRANSPORTE | MANO_DE_OBRA | ADMINISTRACION
EstadoProyecto: BORRADOR → SOLICITUD → DESPIECE → EN_REVISION_COMPRAS → DESPIECE_VALIDADO
                → APU → APU_GENERADO → COTIZADO → APROBADO → CERRADO | ANULADO
```

---

## 3. FLUJO

```
Proyecto
  → ProyectoSistema (parametros_entrada JSON)
    → DespieceService.calcular()
      → DespieceLinea[] (componente_codigo, cantidad_calculada, precio_snapshot)
    → APUService.generar(ps)           ← solo genera MATERIALES automáticamente
      → APU (get_or_create por proyecto_sistema)
        → APULinea[] tipo=MATERIALES   ← desde DespieceLineas resueltas
      → proyecto.avanzar_a_apu()
    → APUService(ps).generar_mano_obra_desde_catalogo(items_data)   ← manual
    → APUService(ps).generar_herramientas_desde_catalogo(items_data) ← manual
    → APUService(ps).generar_transporte_items(items)                 ← manual
    → APUService(ps).generar_administracion(costo_total)             ← manual
```

---

## 4. LÓGICA DE CÁLCULO APU

### Referencia de unidades del sistema
```python
_CLAVES_UNIDAD_REFERENCIA = (
    "total_powergrip", "total_unidades", "cantidad",
    "n_apoyos", "ml_fachada", "m2", "area_m2"
)
tp = first_match(parametros_entrada, claves) or proyecto.area_total_m2
```

### Materiales (auto desde despiece)
```
rendimiento = tp / cantidad_final
CU = precio_snapshot × IVA_factor
CT = rendimiento × CU
VU = CU × (1 + margen_material_pct/100)     # sólo MATERIALES
VT = rendimiento × VU
```

### Mano de obra (catálogo, manual)
```
dias_trabajo = tp / (total_personas × 40)
precio_dia:
  unidad=mes  → precio_dia = total_mes_personal / 22
  unidad=hora → precio_dia = precio_base × 8
  unidad=dia  → precio_dia = precio_base
CU = (precio_dia × cantidad × dias × AIU × margen) / tp
IVA no aplicado a MO
```

### Herramientas / equipos (catálogo, manual)
```
dias = _estimar_dias()  # desde líneas MO existentes, fallback tp/(7×40)
Con vida_util_dias:  costo_item = (precio_base × cantidad / vida_util_dias) × dias
Sin vida_util_dias:  costo_item = precio_base × cantidad
CU = costo_item / tp
```

### Transporte (libre, manual)
```
CU = precio_total_item / tp
```

### Administración (manual)
```
CU = costo_total_admin / tp
```

### Fórmula general (APULinea.calcular)
```python
iva_factor = 1 + iva_pct/100  if iva_aplicado and aplica_iva  else 1
CU = precio_referencia × iva_factor
CT = rendimiento × CU
VU = CU × (1 + margen_material_pct/100)  si tipo == MATERIALES,  si no  VU = CU
VT = rendimiento × VU

# El resto de categorías obtiene su margen de la fórmula del subsistema
# (variables `margen_mano_obra`, `margen_material`, `aiu`), no de aquí.
```

---

## 5. REGLAS DE NEGOCIO

- `DespieceLinea` con `producto=NULL` → omitida en generar_materiales
- `precio_snapshot` capturado desde `ProveedorProducto` (menor precio activo)
- APU se genera una sola vez (get_or_create); re-ejecutar sobreescribe líneas vía update_or_create
- Sólo MATERIALES se generan automáticamente; MO / Herr / Transporte / Admin requieren acción manual
- `APULinea.editable=True` → usuario puede ajustar `precio_referencia` y `rendimiento` vía UI
- `APULinea.editable=False` → materiales generados automáticamente (protegidos)
- `recalcular()` del APU se dispara automáticamente por señal post_save/post_delete de APULinea
- `ConfiguracionAPU.activa_o_default()` siempre devuelve un registro (lo crea si no hay)
- `CuadrillaPreset` es solo plantilla de selección; al usar, se expande en APULineas individuales por cargo

---

## 6. RELACIONES CRÍTICAS

```
APULinea.tipo = MATERIALES       → despiece_linea FK activo, item_catalogo NULL
APULinea.tipo = MANO_DE_OBRA     → item_catalogo FK (ItemCatalogoAPU), salario_base/prestaciones copiados
APULinea.tipo = HERRAMIENTAS_*   → item_catalogo FK, vida_util_dias copiado
APULinea.tipo = TRANSPORTE       → item_catalogo NULL, descripcion libre
APULinea.tipo = ADMINISTRACION   → item_catalogo NULL, descripcion="Administración"

DespieceLinea.estado_tecnico:
  RESUELTO            → producto_id NOT NULL
  PENDIENTE_SELECCION → producto_id NULL & categoria_producto_id NOT NULL
  ERROR_CONFIGURACION → ambos NULL

ItemCatalogoAPU.unidad:
  "dia"  → precio_base = $/día
  "mes"  → precio_base = $/mes (÷22 para convertir a día)
  "hora" → precio_base = $/hora (×8 para convertir a día)
```

---

## 7. URLS APU (app_name=presupuestos)

```
apu/                              → apu_list
apu/<pk>/                         → apu_detail
apu/<pk>/editar/                  → apu_update
apu/generar/<pk>/                 → apu_generar         (POST → APUService.generar)
apu/<pk>/mano-obra/               → apu_mano_obra       (POST → generar_mano_obra_desde_catalogo)
apu/<pk>/herramientas/            → apu_herramientas    (POST → generar_herramientas_desde_catalogo)
apu/<pk>/transporte/              → apu_transporte      (POST → generar_transporte_items)
apu/<pk>/administrativo/          → apu_admin           (POST → generar_administracion)
apu/linea/<pk>/editar/            → apu_linea_update    (POST → APULinea update + recalcular)
despiece/proyecto/<pk>/           → despiece_proyecto
despiece/calcular/<pk>/           → despiece_calcular
despiece/ejecutar/<pk>/           → despiece_ejecutar
despiece/ajuste/<pk>/             → despiece_ajuste
despiece/api/ajuste/<pk>/         → despiece_api_ajuste
```

---

## 8. TABLAS DB

```
proyectos                  → comercial.Proyecto
proyecto_sistemas          → ProyectoSistema
despiece_lineas            → DespieceLinea
apus                       → APU
apu_lineas                 → APULinea
configuracion_apu          → ConfiguracionAPU
catalogo_apu_categorias    → CategoriaItemAPU
catalogo_apu_items         → ItemCatalogoAPU
cuadrilla_presets          → CuadrillaPreset
cuadrilla_preset_items     → CuadrillaPresetItem
```

---

## 9. PENDIENTES

- `apps/presupuestos/forms.py` — FALTA crear: `CategoriaItemAPUForm`, `ItemCatalogoAPUForm`, `CuadrillaPresetForm`, `CuadrillaPresetItemFormSet`
- `views/__init__.py` importa esos forms → **ImportError si no existen** (Django no arranca)
- Vistas catálogo CRUD pendientes: `CatalogoAPUView`, `ItemCatalogoAPUCreateView/UpdateView`, `CuadrillaPresetCreateView/UpdateView`
- URLs catálogo no registradas aún en `urls.py`
- Template `catalogo_apu.html` — pendiente crear
- `apu_detail.html` modales MO / Herramientas — pendiente migrar a selección por catálogo
- `base.html` nav APU → apunta a `apu_list`; cambiar a `catalogo_apu` cuando exista
