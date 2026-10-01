"""
apps/presupuestos/services/presupuesto_resumen_service.py — Fase 3.D.

Resumen económico de los APU que forman el presupuesto del proyecto, tal cual
se ve en el detalle de cada APU: valores UNITARIOS (por la unidad del APU), sin
multiplicar por la cantidad del presupuesto — eso ya lo hace el ítem. Es
informativo y de SOLO LECTURA: no recalcula ni guarda nada en los APU.

Por cada APU:
    costo_tipo  = subtotal_<tipo>
    valor_tipo  = Σ valor_total de las líneas que APUProyecto.recalcular()
                  cuenta para ese tipo (materiales: todas; demás tipos: las
                  líneas resumen si existen, si no todas)
    costo_total = total_costo
    valor_total = total_valor_venta

`valor_materiales` no se usa: está desactualizado en algunos APU históricos.
"""

from decimal import Decimal

from django.db.models import Sum

from apps.common.choices import TipoAPU

# Orden y campos de costo, igual que APUProyecto.recalcular()
TIPOS_RESUMEN = (
    (TipoAPU.MATERIALES, "subtotal_materiales", "Materiales"),
    (TipoAPU.HERRAMIENTAS_EQUIPOS, "subtotal_herramientas", "Herramientas"),
    (TipoAPU.TRANSPORTE, "subtotal_transporte", "Transporte"),
    (TipoAPU.MANO_DE_OBRA, "subtotal_mano_obra", "Mano de obra"),
    (TipoAPU.ADMINISTRACION, "subtotal_administracion", "Administración"),
)

# Iconos Bootstrap por tipo: los mismos del resumen del detalle del APU.
ICONO_TIPO = {
    TipoAPU.MATERIALES: "box-seam",
    TipoAPU.HERRAMIENTAS_EQUIPOS: "tools",
    TipoAPU.TRANSPORTE: "truck",
    TipoAPU.MANO_DE_OBRA: "people",
    TipoAPU.ADMINISTRACION: "briefcase",
}

# Tolerancia por APU (valores unitarios con 4–6 decimales en BD)
_TOLERANCIA_UNITARIA = Decimal("0.01")


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def valores_por_tipo(apu) -> dict:
    """
    Σ valor_total por TipoAPU con la MISMA selección de líneas que
    APUProyecto.recalcular(). Solo lectura. Devuelve {tipo: Decimal} (unitario).
    """
    valores = {}
    for tipo, _campo, _label in TIPOS_RESUMEN:
        if tipo == TipoAPU.MATERIALES:
            qs = apu.lineas.filter(tipo=tipo)
        else:
            qs_resumen = apu.lineas.filter(
                tipo=tipo, item_catalogo__isnull=True, despiece_linea__isnull=True,
            )
            qs = qs_resumen if qs_resumen.exists() else apu.lineas.filter(tipo=tipo)
        valores[tipo] = _d(qs.aggregate(v=Sum("valor_total"))["v"])
    return valores


def _nombre_item(apu) -> str:
    """Mismo nombre que el ítem del presupuesto (subsistema → sistema → APU)."""
    ps = apu.proyecto_sistema
    if ps and ps.subsistema_id:
        return ps.subsistema.nombre
    if ps and ps.sistema_id:
        return ps.sistema.nombre
    return apu.nombre


def resumen_apu(apu) -> dict:
    """Resumen unitario de UN APU (lo mismo que muestran sus tarjetas)."""
    v_unit = valores_por_tipo(apu)
    tipos = [
        {
            "tipo": tipo,
            "label": label,
            "icono": ICONO_TIPO[tipo],
            "costo": _d(getattr(apu, campo)),
            "valor": v_unit[tipo],
        }
        for tipo, campo, label in TIPOS_RESUMEN
    ]
    costo_total = _d(apu.total_costo)
    valor_total = _d(apu.total_valor_venta)

    # Totales guardados que no cuadran con sus tipos (datos históricos):
    # se reportan, no se corrigen.
    inconsistencias = []
    for campo, suma, total in (
        ("total_costo", sum((t["costo"] for t in tipos), Decimal("0")), costo_total),
        ("total_valor_venta", sum((t["valor"] for t in tipos), Decimal("0")), valor_total),
    ):
        if abs(suma - total) > _TOLERANCIA_UNITARIA:
            inconsistencias.append({
                "apu_id": apu.pk, "campo": campo,
                "tipos": suma, "total": total, "diferencia": total - suma,
            })

    return {
        "apu": apu,
        "nombre": _nombre_item(apu),
        "unidad": apu.unidad_base_apu or "",
        "tipos": tipos,
        "costo_total": costo_total,
        "valor_total": valor_total,
        "inconsistencias": inconsistencias,
    }


def resumen_apus_presupuesto(apus) -> dict:
    """
    Resumen por APU de los APU del presupuesto (mismo queryset/lista que la
    tabla de ítems). Valores unitarios en Decimal; el redondeo es solo de
    presentación.

    Retorna: {"apus": [resumen_apu(...)], "n_apus", "inconsistencias"}.
    """
    por_apu = [resumen_apu(apu) for apu in apus]
    return {
        "apus": por_apu,
        "n_apus": len(por_apu),
        "inconsistencias": [i for r in por_apu for i in r["inconsistencias"]],
    }
