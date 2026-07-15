"""
apps/presupuestos/models — Exportaciones públicas del paquete de modelos de presupuestos.
"""

from .despiece import ProyectoSistema, DespieceLinea
from .consumo import CalculoConsumoLinea
from .apu import (
    ConfiguracionAPU,
    APU,
    APULinea,
    APUDespieceIncluido,
    APUConsolidadoOrigen,
    CategoriaItemAPU,
    ItemCatalogoAPU,
    CuadrillaPreset,
    CuadrillaPresetItem,
    ReglaAPUSubsistema,
    SubsistemaItemAPU,
)
from .cotizacion import CotizacionAPU

# Alias de compatibilidad — el modelo se llama APU en el código fuente
APUProyecto = APU

__all__ = [
    "ProyectoSistema",
    "DespieceLinea",
    "CalculoConsumoLinea",
    "ConfiguracionAPU",
    "APU",
    "APUProyecto",   # alias → APU
    "APULinea",
    "APUDespieceIncluido",
    "APUConsolidadoOrigen",
    "CategoriaItemAPU",
    "ItemCatalogoAPU",
    "CuadrillaPreset",
    "CuadrillaPresetItem",
    "ReglaAPUSubsistema",
    "SubsistemaItemAPU",
    "CotizacionAPU",
]
