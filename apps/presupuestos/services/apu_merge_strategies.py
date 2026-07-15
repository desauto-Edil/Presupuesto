"""
apps/presupuestos/services/apu_merge_strategies.py — Fase 11.5

Estrategias de unión usadas por `APUConsolidadoBuilder`.

- `MaterialesUnionStrategy`: unión acumulativa. No deduplica.
- `NoMaterialesDedupStrategy`: deduplica por (item_catalogo_id, tipo) o
  fallback (tipo, descripcion_norm, unidad). Conserva la línea de mayor
  costo_total (peor caso).

Ambas estrategias devuelven plantillas de líneas — el builder las persiste.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, List, Optional

from apps.common.choices import TipoAPU


CATEGORIAS_NO_MATERIALES = {
    TipoAPU.HERRAMIENTAS_EQUIPOS,
    TipoAPU.TRANSPORTE,
    TipoAPU.MANO_DE_OBRA,
    TipoAPU.ADMINISTRACION,
}


@dataclass
class LineaPlantilla:
    """Snapshot intermedio para crear una APULinea en el consolidado."""

    tipo: str
    descripcion: str
    rendimiento: Decimal
    unidad: str
    precio_referencia: Decimal
    iva_aplicado: bool
    vida_util_dias: Optional[int]
    costo_por_dia: Decimal
    salario_base: Decimal
    prestaciones: Decimal
    costo_unitario: Decimal
    costo_total: Decimal
    valor_unitario: Decimal
    valor_total: Decimal
    tienda_referencia: str
    editable: bool
    item_catalogo_id: Optional[int]
    despiece_linea_id: Optional[int]
    despiece_maestro_id: Optional[int]
    sistema_nombre_snapshot: str
    subsistema_nombre_snapshot: str
    apu_origen_id: Optional[int]
    equivalentes_apus: List[int] = field(default_factory=list)

    @classmethod
    def desde_linea(cls, linea, apu_origen_id: int) -> "LineaPlantilla":
        return cls(
            tipo=linea.tipo,
            descripcion=linea.descripcion or "",
            rendimiento=linea.rendimiento or Decimal("0"),
            unidad=linea.unidad or "und",
            precio_referencia=linea.precio_referencia or Decimal("0"),
            iva_aplicado=bool(linea.iva_aplicado),
            vida_util_dias=linea.vida_util_dias,
            costo_por_dia=linea.costo_por_dia or Decimal("0"),
            salario_base=linea.salario_base or Decimal("0"),
            prestaciones=linea.prestaciones or Decimal("0"),
            costo_unitario=linea.costo_unitario or Decimal("0"),
            costo_total=linea.costo_total or Decimal("0"),
            valor_unitario=linea.valor_unitario or Decimal("0"),
            valor_total=linea.valor_total or Decimal("0"),
            tienda_referencia=linea.tienda_referencia or "",
            editable=bool(linea.editable),
            item_catalogo_id=linea.item_catalogo_id,
            despiece_linea_id=linea.despiece_linea_id,
            despiece_maestro_id=linea.despiece_maestro_id,
            sistema_nombre_snapshot=linea.sistema_nombre_snapshot or "",
            subsistema_nombre_snapshot=linea.subsistema_nombre_snapshot or "",
            apu_origen_id=apu_origen_id,
        )


# ---------------------------------------------------------------------------
# Materiales — unión acumulativa
# ---------------------------------------------------------------------------

class MaterialesUnionStrategy:
    """Concatena todas las líneas de MATERIALES sin deduplicar."""

    def merge(self, apus_origen) -> List[LineaPlantilla]:
        plantillas: List[LineaPlantilla] = []
        for apu in apus_origen:
            for linea in apu.lineas.filter(tipo=TipoAPU.MATERIALES).order_by(
                "subsistema_nombre_snapshot", "despiece_maestro_id", "id"
            ):
                plantillas.append(LineaPlantilla.desde_linea(linea, apu.id))
        return plantillas


# ---------------------------------------------------------------------------
# No-materiales — deduplicación por equivalencia
# ---------------------------------------------------------------------------

def _normalizar_descripcion(texto: str) -> str:
    return " ".join((texto or "").strip().lower().split())


def _clave_equivalencia(linea_o_plantilla) -> tuple:
    """Devuelve la llave de equivalencia para una línea/plantilla no-material.

    Preferencia:
      - (item_catalogo_id, tipo)  cuando item_catalogo_id no es NULL.
    Fallback:
      - (tipo, descripcion_norm, unidad).
    """
    item_id = getattr(linea_o_plantilla, "item_catalogo_id", None)
    tipo = getattr(linea_o_plantilla, "tipo", None)
    if item_id:
        return ("ITEM", item_id, tipo)
    desc = _normalizar_descripcion(getattr(linea_o_plantilla, "descripcion", ""))
    unidad = getattr(linea_o_plantilla, "unidad", "") or ""
    return ("DESC", tipo, desc, unidad)


class NoMaterialesDedupStrategy:
    """Deduplica líneas no-materiales por equivalencia.

    Conserva la línea de mayor `costo_total` (peor caso para presupuesto).
    Registra metadata `equivalentes_apus` con los apus origen donde aparecía.
    """

    def merge(self, apus_origen) -> List[LineaPlantilla]:
        agrupadas: dict[tuple, LineaPlantilla] = {}
        for apu in apus_origen:
            qs = apu.lineas.filter(tipo__in=list(CATEGORIAS_NO_MATERIALES))
            # Saltar líneas de detalle de cuadrilla (las que tienen
            # despiece_linea o item_catalogo NULL pueden ser sumarias) —
            # tomar todas: la dedup las une por equivalencia igual.
            for linea in qs.order_by("tipo", "descripcion", "id"):
                clave = _clave_equivalencia(linea)
                plantilla = LineaPlantilla.desde_linea(linea, apu.id)
                existente = agrupadas.get(clave)
                if existente is None:
                    plantilla.equivalentes_apus = [apu.id]
                    agrupadas[clave] = plantilla
                else:
                    existente.equivalentes_apus.append(apu.id)
                    # Conservar la de mayor costo_total
                    if (plantilla.costo_total or 0) > (existente.costo_total or 0):
                        plantilla.equivalentes_apus = existente.equivalentes_apus
                        agrupadas[clave] = plantilla
        return list(agrupadas.values())


# ---------------------------------------------------------------------------
# Resumen previo (preview) — útil para la vista de confirmación
# ---------------------------------------------------------------------------

@dataclass
class ResumenPreview:
    apus_origen: list
    materiales_total: int
    no_materiales_origen: int
    no_materiales_deduplicados: int
    sistemas: list
    subsistemas: list
    deduplicados_detalle: list  # [{tipo, descripcion, apus:[ids]}]
    # Fase 11.5.1 — detalle visual para el preview
    materiales_por_origen: list  # [{apu, grupos:[{sistema, subsistema, despiece_id, lineas, subtotal_valor}]}]
    no_materiales_conservados: list  # [{tipo, descripcion, unidad, valor_total, apu_origen_id, equivalentes_apus, es_dedup}]


def construir_resumen_preview(apus_origen: Iterable) -> ResumenPreview:
    """Diagnóstico previo a la consolidación, sin persistir nada."""
    apus_origen = list(apus_origen)
    materiales = MaterialesUnionStrategy().merge(apus_origen)
    # No-materiales originales totales:
    no_mat_origen = 0
    for apu in apus_origen:
        no_mat_origen += apu.lineas.filter(
            tipo__in=list(CATEGORIAS_NO_MATERIALES)
        ).count()
    no_mat_dedup = NoMaterialesDedupStrategy().merge(apus_origen)

    sistemas = sorted({p.sistema_nombre_snapshot for p in materiales if p.sistema_nombre_snapshot})
    subsistemas = sorted({p.subsistema_nombre_snapshot for p in materiales if p.subsistema_nombre_snapshot})

    detalle = []
    for p in no_mat_dedup:
        if len(p.equivalentes_apus) > 1:
            detalle.append({
                "tipo": p.tipo,
                "descripcion": p.descripcion,
                "apus_ids": list(p.equivalentes_apus),
                "costo_total": p.costo_total,
            })

    # Fase 11.5.1 — Reagrupar materiales por APU origen → sistema/subsistema/despiece
    apus_por_id = {a.pk: a for a in apus_origen}
    materiales_por_origen: list = []
    for apu in apus_origen:
        lineas_apu = [p for p in materiales if p.apu_origen_id == apu.pk]
        if not lineas_apu:
            continue
        grupos: dict = {}
        for p in lineas_apu:
            key = (p.sistema_nombre_snapshot or "", p.subsistema_nombre_snapshot or "",
                   p.despiece_maestro_id or 0)
            g = grupos.setdefault(key, {
                "sistema": p.sistema_nombre_snapshot or "",
                "subsistema": p.subsistema_nombre_snapshot or "",
                "despiece_id": p.despiece_maestro_id,
                "lineas": [],
                "subtotal_valor": 0,
            })
            g["lineas"].append(p)
            try:
                g["subtotal_valor"] = (g["subtotal_valor"] or 0) + (p.valor_total or 0)
            except Exception:
                pass
        materiales_por_origen.append({
            "apu": apu,
            "grupos": list(grupos.values()),
            "total_lineas": len(lineas_apu),
        })

    # Fase 11.5.1 — No-materiales conservados (todos), con flag de dedup
    no_materiales_conservados = []
    for p in no_mat_dedup:
        no_materiales_conservados.append({
            "tipo": p.tipo,
            "descripcion": p.descripcion,
            "unidad": p.unidad,
            "valor_total": p.valor_total,
            "costo_total": p.costo_total,
            "apu_origen_id": p.apu_origen_id,
            "apu_origen": apus_por_id.get(p.apu_origen_id),
            "equivalentes_apus": list(p.equivalentes_apus),
            "es_dedup": len(p.equivalentes_apus) > 1,
        })

    return ResumenPreview(
        apus_origen=apus_origen,
        materiales_total=len(materiales),
        no_materiales_origen=no_mat_origen,
        no_materiales_deduplicados=len(no_mat_dedup),
        materiales_por_origen=materiales_por_origen,
        no_materiales_conservados=no_materiales_conservados,
        sistemas=sistemas,
        subsistemas=subsistemas,
        deduplicados_detalle=detalle,
    )
