"""
apps/presupuestos/models — Exportaciones públicas del paquete de modelos de presupuestos.
"""

from .despiece import ProyectoSistema, DespieceLinea
from .cotizacion import CotizacionAPU
from .consumo import CalculoConsumoLinea
from .apu import (
    ConfiguracionAPU,
    APU,
    APULinea,
    CategoriaItemAPU,
    ItemCatalogoAPU,
    CuadrillaPreset,
    CuadrillaPresetItem,
    ReglaAPUSubsistema,
    SubsistemaItemAPU,
    APUDespieceIncluido,
    APUConsolidadoOrigen,
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
    "CuadrillaPreset",
    "CuadrillaPresetItem",
    "ReglaAPUSubsistema",
    "CotizacionAPU",
    "CalculoConsumoLinea",
    "SubsistemaItemAPU",
    "APUDespieceIncluido",
    "APUConsolidadoOrigen",
]
