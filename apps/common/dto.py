"""
apps/common/dto.py — Data Transfer Objects (dataclasses).

Objetivo:
    Reemplazar gradualmente los `dict` que devuelven los servicios
    (DespieceMaestroService.calcular, DespieceService.calcular, APUService...)
    por estructuras tipadas que documenten el contrato.

ESTADO: módulo base. NO está cableado a los servicios actuales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Resultado de evaluación de una fórmula
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FormulaResult:
    """Resultado de evaluar una sola fórmula con su contexto."""
    formula: str
    valor: float
    valores_usados: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Línea calculada de despiece (maestro o por proyecto)
# ---------------------------------------------------------------------------
@dataclass
class CalculationLineDTO:
    """Snapshot de una línea calculada antes de persistirse.

    Es el contrato común que deberían producir tanto DespieceService como
    DespieceMaestroService. Hoy ambos devuelven dicts con shape divergente.
    """
    subconjunto_nombre: str
    componente_codigo: str
    componente_nombre: str
    formula_texto: str
    valores_usados: dict[str, Any]
    cantidad_calculada: Decimal
    cantidad_redondeada: Decimal
    unidad: str

    # Producto resuelto (opcional — puede no haber match)
    producto_id: Optional[int] = None
    producto_codigo: Optional[str] = None
    producto_nombre: Optional[str] = None
    categoria_codigo: Optional[str] = None

    # Precio capturado al momento del cálculo
    precio_unitario: Optional[Decimal] = None
    moneda: Optional[str] = None
    fecha_precio: Optional[str] = None


# ---------------------------------------------------------------------------
# Snapshot de variables de entrada
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VariablesSnapshotDTO:
    """Estado validado de las variables de entrada de un despiece."""
    valores: dict[str, Any]
    faltantes: list[str] = field(default_factory=list)
    invalidas: list[str] = field(default_factory=list)

    @property
    def es_completo(self) -> bool:
        return not self.faltantes and not self.invalidas
