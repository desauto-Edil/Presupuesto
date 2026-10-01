"""
apps/presupuestos/models — Exportaciones públicas del paquete de modelos de presupuestos.
"""

from .despiece import ProyectoSistema, DespieceLinea
from .cotizacion import CotizacionAPU
from .consumo import CalculoConsumoLinea
from .presentacion_comercial import PresentacionItemPresupuesto, LineaPresentacionPresupuesto
from .apu import (
    ConfiguracionAPU,
    APU,
    APULinea,
    APUPoliza,
    CategoriaItemAPU,
    ItemCatalogoAPU,
    ReglaAPUSubsistema,
    SubsistemaItemAPU,
    APUDespieceIncluido,
    APUConsolidadoOrigen,
    PaqueteAPU,
    PaqueteAPUItem,
    SubsistemaPaqueteAPU,
    APUPaquete,
)

# Alias de compatibilidad — el modelo se llama APU en el código fuente
APUProyecto = APU

__all__ = [
    "ProyectoSistema",
    "DespieceLinea",
    "ConfiguracionAPU",
    "APU",
    "APUProyecto",          # alias → APU
    "APULinea",
    "CategoriaItemAPU",
    "ItemCatalogoAPU",
    "ReglaAPUSubsistema",
    "CotizacionAPU",
    "CalculoConsumoLinea",
    "SubsistemaItemAPU",
    "APUDespieceIncluido",
    "APUConsolidadoOrigen",
    "APUPoliza",
    "PaqueteAPU",
    "PaqueteAPUItem",
    "SubsistemaPaqueteAPU",
    "APUPaquete",
    "PresentacionItemPresupuesto",
    "LineaPresentacionPresupuesto",
]
