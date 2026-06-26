"""
apps/ingenieria/services/lineas_finales_apu.py — Fase 6B/6C/6H.

Helpers para resolver el conjunto de líneas "finales" de un DespieceMaestro
que deben entrar al APU, validar que el despiece está listo y emitir
advertencias no bloqueantes de unidad.

Concepto: línea final
---------------------
Una "línea final" es la que efectivamente representa un material en el APU.
La regla de derivación es:

    Si existe una ConsolidacionDespieceMaestro activa, ESA es la línea final
    y las DespieceMaestroLinea origen incluidas en `lineas_ids` quedan
    "absorbidas" — no entran como individuales.

    Las DespieceMaestroLinea que NO están en ninguna consolidación entran
    como líneas finales individuales.

Esto evita duplicar materiales entre la consolidación y sus orígenes.

Persistencia / efectos colaterales
----------------------------------
Estos helpers son SOLO de lectura. No tocan la base de datos, no crean
modelos ni guardan cache. La auto-creación o invalidación de cache de
ConfiguracionAPU/unidades/categorías (Fase 5) no es competencia de este
módulo.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, List, Optional, TypedDict


# ────────────────────────────────────────────────────────────────────────────
# Tipos
# ────────────────────────────────────────────────────────────────────────────


class LineaFinalAPU(TypedDict, total=False):
    """Shape estable que retornan las funciones de este módulo.

    Las claves marcadas como obligatorias siempre vienen pobladas; las
    opcionales pueden faltar o ser None cuando el origen no las tiene.
    """

    # Identidad de la línea final
    tipo: str            # "normal" | "consolidada"
    id: int              # pk de DespieceMaestroLinea o de ConsolidacionDespieceMaestro
    nombre: str          # componente_nombre / componente_codigo (normal) o label (consolidada)

    # Producto seleccionado (puede no estar resuelto)
    producto: Optional[object]      # instancia catalogos.Producto o None
    producto_id: Optional[int]
    producto_nombre: str            # snapshot o nombre actual; "" si sin producto

    # Cantidad y unidad
    cantidad_total: Decimal
    unidad: str

    # Snapshot de precio (Decimal o None)
    precio_unitario: Optional[Decimal]
    fecha_precio: Optional[object]   # datetime o None

    # Trazabilidad inversa
    origen_lineas_ids: List[int]     # pks origen para consolidadas; [pk_propio] para normales


# ────────────────────────────────────────────────────────────────────────────
# 6B — obtener_lineas_finales_para_apu
# ────────────────────────────────────────────────────────────────────────────


def _pks_absorbidos_por_consolidaciones(consolidaciones: Iterable) -> set:
    """Set de pks de DespieceMaestroLinea que están dentro de algún
    `lineas_ids` de consolidación. Esas líneas NO entran como individuales."""
    absorbidos: set = set()
    for c in consolidaciones:
        # `lineas_ids` es JSONField con lista de pks; tolerante a None.
        for pk in (c.lineas_ids or []):
            try:
                absorbidos.add(int(pk))
            except (TypeError, ValueError):
                continue
    return absorbidos


def _normalizar_linea_normal(dml) -> LineaFinalAPU:
    """Mapea una DespieceMaestroLinea individual a la shape de línea final."""
    nombre = (dml.componente_nombre or "").strip() or dml.componente_codigo or f"Línea #{dml.pk}"
    producto_nombre = (
        (dml.producto_nombre or "").strip()
        or (dml.producto.nombre if dml.producto_id and dml.producto else "")
    )
    return {
        "tipo": "normal",
        "id": dml.pk,
        "nombre": nombre,
        "producto": dml.producto if dml.producto_id else None,
        "producto_id": dml.producto_id,
        "producto_nombre": producto_nombre,
        "cantidad_total": Decimal(str(dml.cantidad_calculada or 0)),
        "unidad": dml.unidad or "",
        "unidad_apu": dml.unidad_apu or "",  # Fase 6H: para detectar mismatch
        "precio_unitario": dml.precio_unitario,
        "fecha_precio": dml.fecha_precio,
        "origen_lineas_ids": [dml.pk],
    }


def _normalizar_linea_consolidada(c) -> LineaFinalAPU:
    """Mapea una ConsolidacionDespieceMaestro a la shape de línea final."""
    nombre = (c.label or "").strip() or f"Consolidado #{c.pk}"
    producto_nombre = (
        (c.producto_nombre or "").strip()
        or (c.producto.nombre if c.producto_id and c.producto else "")
    )
    return {
        "tipo": "consolidada",
        "id": c.pk,
        "nombre": nombre,
        "producto": c.producto if c.producto_id else None,
        "producto_id": c.producto_id,
        "producto_nombre": producto_nombre,
        "cantidad_total": Decimal(str(c.cantidad_total or 0)),
        "unidad": c.unidad or "",
        "unidad_apu": "",  # consolidaciones no manejan unidad_apu separada
        "precio_unitario": c.precio_unitario,
        "fecha_precio": c.fecha_precio,
        "origen_lineas_ids": [int(x) for x in (c.lineas_ids or []) if str(x).isdigit() or isinstance(x, int)],
    }


def obtener_lineas_finales_para_apu(despiece) -> List[LineaFinalAPU]:
    """
    Devuelve las líneas finales del despiece — las que entran al APU.

    Reglas (Fase 6B):
      1. Cada consolidación activa entra como una línea final tipo="consolidada".
      2. Las líneas individuales cuyo pk está dentro de ALGÚN `lineas_ids`
         de consolidación NO entran (quedan absorbidas).
      3. Las líneas individuales restantes entran como tipo="normal".
      4. No hay duplicados: una línea individual nunca aparece en dos
         lugares; una consolidación tampoco se reemite por sus orígenes.

    Orden: primero consolidaciones (por `orden`, luego pk), luego normales
    (por `orden`, luego pk). El consumidor puede re-ordenar si lo necesita.

    Sin queries adicionales: usa los managers tal cual; se recomienda al
    caller usar `prefetch_related("lineas__producto__unidad",
    "consolidaciones__producto__unidad")` cuando vaya a iterar.

    Args:
        despiece: instancia de `apps.ingenieria.models.DespieceMaestro`.

    Returns:
        list[LineaFinalAPU] — puede ser vacía si el despiece no tiene líneas.
    """
    consolidaciones = list(despiece.consolidaciones.all().order_by("orden", "id"))
    absorbidos = _pks_absorbidos_por_consolidaciones(consolidaciones)

    lineas_individuales = [
        dml
        for dml in despiece.lineas.all().order_by("orden", "id")
        if dml.pk not in absorbidos
    ]

    finales: List[LineaFinalAPU] = []
    finales.extend(_normalizar_linea_consolidada(c) for c in consolidaciones)
    finales.extend(_normalizar_linea_normal(dml) for dml in lineas_individuales)
    return finales


# ────────────────────────────────────────────────────────────────────────────
# 6C — validar_despiece_listo_para_apu
# ────────────────────────────────────────────────────────────────────────────


# Mensajes oficiales (mantener literal; se exponen al usuario en el modal).
MSG_SIN_PROYECTO = "Solo los despieces asociados a un proyecto pueden generar APU."
MSG_NO_GUARDADO = "El despiece debe estar guardado antes de armar el APU."
MSG_SIN_LINEAS = "El despiece no tiene líneas para armar el APU. Calcula y guarda primero."
MSG_FALTAN_PRODUCTOS = (
    "No puede armar el APU porque hay materiales sin producto seleccionado."
)
MSG_CANTIDAD_INVALIDA = (
    "Hay líneas finales con cantidad cero o vacía. No se puede armar el APU."
)
MSG_SIN_UNIDAD = (
    "Hay líneas finales sin unidad de medida. Revise el despiece antes de armar el APU."
)


def _unidad_producto(producto) -> str:
    """Devuelve el código (o abreviatura) de la unidad del producto, o "" si no tiene."""
    if producto is None:
        return ""
    unidad = getattr(producto, "unidad", None)
    if unidad is None:
        return ""
    # Prioridad: codigo (estable) → abreviatura → nombre
    return (
        getattr(unidad, "codigo", "")
        or getattr(unidad, "abreviatura", "")
        or getattr(unidad, "nombre", "")
        or ""
    )


def _norm_unidad(u: str) -> str:
    """Normaliza una unidad para comparación: trim + lower."""
    return (u or "").strip().lower()


def advertencias_unidad_linea(linea_final: dict) -> List[str]:
    """Fase 6H — Devuelve advertencias no bloqueantes sobre la unidad de una
    línea final.

    Casos cubiertos (todos informativos, nunca bloquean armar el APU):
      1. La unidad de la línea no coincide con la unidad del producto.
      2. El producto no tiene unidad configurada.
      3. La línea tiene `unidad_apu` distinta de `unidad` (caso DM cuando
         el subsistema definió variable_referencia_apu con otra unidad).

    Sin producto seleccionado → sin advertencias de unidad (ya hay error
    bloqueante en otra parte de la validación).
    """
    msgs: List[str] = []
    producto = linea_final.get("producto")
    if producto is None:
        return msgs

    unidad_linea = (linea_final.get("unidad") or "").strip()
    unidad_prod = _unidad_producto(producto)

    if not unidad_prod:
        msgs.append(
            f"El producto «{linea_final.get('producto_nombre', '')}» no tiene "
            f"unidad configurada."
        )
    elif unidad_linea and _norm_unidad(unidad_linea) != _norm_unidad(unidad_prod):
        msgs.append(
            f"La unidad de la línea es «{unidad_linea}», pero el producto está "
            f"configurado en «{unidad_prod}». Revise si corresponde."
        )

    unidad_apu = (linea_final.get("unidad_apu") or "").strip()
    if unidad_apu and unidad_linea and _norm_unidad(unidad_apu) != _norm_unidad(unidad_linea):
        msgs.append(
            f"La unidad APU declarada es «{unidad_apu}» pero la línea está en "
            f"«{unidad_linea}»."
        )

    return msgs


def _es_cantidad_invalida(cantidad) -> bool:
    """True si la cantidad es None o no positiva. Tolerante a Decimal/float/str."""
    if cantidad is None:
        return True
    try:
        return Decimal(str(cantidad)) <= Decimal("0")
    except Exception:
        return True


def validar_despiece_listo_para_apu(despiece) -> dict:
    """
    Valida si un DespieceMaestro está listo para armar un APU.

    Reglas (Fase 6C, todas bloqueantes en `errores`):
      1. Pertenece a un proyecto (`despiece.proyecto_id is not None`).
      2. Está guardado (`despiece.esta_guardado`).
      3. Existen líneas finales (obtener_lineas_finales_para_apu(d) no vacío).
      4. Todas las líneas finales tienen producto seleccionado.
      5. Todas las líneas finales tienen cantidad_total > 0.
      6. Todas las líneas finales tienen unidad no vacía.

    Advertencias no bloqueantes (en `advertencias`):
      - Línea final sin precio_unitario snapshot (el APU resolverá desde
        el producto activo; informativo para el usuario).

    Returns:
        dict con shape:
            {
                "ok": bool,                # True si no hay errores
                "errores": [str, ...],     # mensajes generales
                "advertencias": [str, ...],
                "lineas_finales": [LineaFinalAPU, ...],
                "lineas_pendientes_producto": [LineaFinalAPU, ...],
                "lineas_cantidad_invalida":   [LineaFinalAPU, ...],
                "lineas_sin_unidad":          [LineaFinalAPU, ...],
            }

    Diseño:
        Los detalles por línea quedan en listas separadas para que el
        modal/template pueda renderizarlas formateadas sin tener que
        re-derivarlas. El mensaje agregado en `errores` resume el motivo.
    """
    errores: List[str] = []
    advertencias: List[str] = []

    # 1. Proyecto
    if not getattr(despiece, "proyecto_id", None):
        errores.append(MSG_SIN_PROYECTO)

    # 2. Guardado
    if not getattr(despiece, "esta_guardado", False):
        errores.append(MSG_NO_GUARDADO)

    # 3. Líneas finales
    lineas_finales = obtener_lineas_finales_para_apu(despiece)
    if not lineas_finales:
        errores.append(MSG_SIN_LINEAS)

    # 4–6. Chequeos por línea (solo si hay líneas; si no, ya hubo error global)
    pendientes_producto: List[LineaFinalAPU] = []
    cantidad_invalida: List[LineaFinalAPU] = []
    sin_unidad: List[LineaFinalAPU] = []
    sin_precio: List[LineaFinalAPU] = []
    # Fase 6H: advertencias por línea (no bloqueantes).
    advertencias_unidad_por_linea: dict = {}

    for f in lineas_finales:
        if not f.get("producto_id"):
            pendientes_producto.append(f)
        if _es_cantidad_invalida(f.get("cantidad_total")):
            cantidad_invalida.append(f)
        if not (f.get("unidad") or "").strip():
            sin_unidad.append(f)
        if f.get("precio_unitario") in (None, "", 0, Decimal("0")):
            sin_precio.append(f)
        # Advertencias de unidad: solo si la línea tiene producto seleccionado.
        # No deben bloquear; solo informar.
        avisos = advertencias_unidad_linea(f)
        if avisos:
            advertencias_unidad_por_linea[(f["tipo"], f["id"])] = avisos
            # También se inyectan en la propia línea para facilitar el render
            # inline en el modal sin tener que cruzar referencias.
            f["advertencias_unidad"] = avisos
        else:
            f["advertencias_unidad"] = []

    if pendientes_producto:
        errores.append(MSG_FALTAN_PRODUCTOS)
    if cantidad_invalida:
        errores.append(MSG_CANTIDAD_INVALIDA)
    if sin_unidad:
        errores.append(MSG_SIN_UNIDAD)
    if sin_precio:
        advertencias.append(
            "Algunas líneas no tienen precio snapshot guardado; el APU "
            "tomará el precio activo del producto al generarse."
        )
    if advertencias_unidad_por_linea:
        # Resumen agregado para el bloque de advertencias generales.
        n = len(advertencias_unidad_por_linea)
        advertencias.append(
            f"{n} línea{'s' if n != 1 else ''} con posible desajuste de unidad. "
            f"Revisa el detalle más abajo. No bloquea armar el APU."
        )

    return {
        "ok": not errores,
        "errores": errores,
        "advertencias": advertencias,
        "lineas_finales": lineas_finales,
        "lineas_pendientes_producto": pendientes_producto,
        "lineas_cantidad_invalida": cantidad_invalida,
        "lineas_sin_unidad": sin_unidad,
        "lineas_sin_precio": sin_precio,
        "advertencias_unidad_por_linea": advertencias_unidad_por_linea,
    }


# ────────────────────────────────────────────────────────────────────────────
# Productos candidatos a producto principal (Fase 6E preview)
# ────────────────────────────────────────────────────────────────────────────


def productos_principal_opciones(lineas_finales: List[LineaFinalAPU]) -> List[dict]:
    """
    Construye opciones únicas de "producto principal" agrupando por producto_id.

    Si un mismo producto aparece en varias líneas finales, la `cantidad_base`
    es la sumatoria de cantidades finales con ese producto (regla 5 del
    usuario para Fase 6).

    Returns:
        list[dict] con:
            producto_id, producto_nombre, unidad, cantidad_base (Decimal),
            origen_lineas: [{tipo, id, nombre, cantidad_total}, ...]
    """
    por_producto: dict = {}
    for f in lineas_finales:
        pid = f.get("producto_id")
        if not pid:
            continue
        slot = por_producto.setdefault(pid, {
            "producto_id": pid,
            "producto_nombre": f.get("producto_nombre", ""),
            "unidad": f.get("unidad", ""),
            "cantidad_base": Decimal("0"),
            "origen_lineas": [],
        })
        slot["cantidad_base"] += Decimal(str(f.get("cantidad_total") or 0))
        slot["origen_lineas"].append({
            "tipo": f["tipo"],
            "id": f["id"],
            "nombre": f["nombre"],
            "cantidad_total": f["cantidad_total"],
        })
        # Si el nombre snapshot estaba vacío, intenta llenarlo con el más reciente.
        if not slot["producto_nombre"] and f.get("producto_nombre"):
            slot["producto_nombre"] = f["producto_nombre"]
    return list(por_producto.values())


def calcular_base_apu_backend(despiece) -> dict:
    """
    Calcula la Base APU desde el backend, sin confiar en el POST.

    1. Obtiene las variables del subsistema marcadas con `participa_en_base_apu=True`.
    2. Lee sus valores desde `despiece.variables_entrada`.
    3. Suma los valores numéricos.

    Retorna un dict con:
        {
            "valida": bool,
            "total": Decimal,
            "unidad": str,
            "resumen": list[dict]
        }
    """
    from apps.ingenieria.models import VariableSubsistema

    resumen = []
    total = Decimal("0")
    unidad = ""
    valida = False

    try:
        vars_base_qs = VariableSubsistema.objects.filter(
            subsistema=despiece.subsistema, participa_en_base_apu=True,
        ).order_by("orden")
        vars_base = list(vars_base_qs)
        valores_usuario = despiece.variables_entrada or {}

        if vars_base:
            for v in vars_base:
                raw = valores_usuario.get(v.variable, v.valor_default)
                if raw not in (None, ""):
                    valor_num = Decimal(str(raw))
                    resumen.append({"label": v.label, "valor": valor_num, "unidad": v.unidad})
                    total += valor_num
            if resumen:
                unidad = resumen[0]["unidad"]
            valida = total > Decimal("0")
    except (TypeError, ValueError, Exception):
        valida = False

    return {"valida": valida, "total": total, "unidad": unidad, "resumen": resumen}
