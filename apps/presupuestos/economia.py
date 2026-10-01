"""
apps/presupuestos/economia.py — Regla económica universal del catálogo APU.

Fuente ÚNICA de verdad para el valor diario de un ItemCatalogoAPU de los tipos
HERRAMIENTAS_EQUIPOS, MANO_DE_OBRA, TRANSPORTE y ADMINISTRACION:

    valor_diario = valor_base / vida_util_dias

La cantidad NO forma parte del valor diario; el aporte de un ítem a la variable
`suma` de ReglaAPUSubsistema es:

    aporte = valor_diario × cantidad

MATERIALES no usa esta regla: se valoriza desde el despiece
(DespieceLinea.precio_snapshot × cantidad_final_apu).

Contrato numérico:
    - Todo en Decimal (nunca float).
    - valor_diario se cuantiza a 6 decimales con ROUND_HALF_UP, la misma
      precisión que APULinea.precio_referencia.
    - valor_base = 0      → valor_diario = 0 (válido).
    - valor_base < 0      → ValorDiarioError.
    - vida_util_dias NULL → ValorDiarioError (dato pendiente de configuración;
                            nunca se asume 1).
    - vida_util_dias <= 0 → ValorDiarioError (nunca hay división por cero).

Este módulo es puro (no importa modelos) para que modelo, servicios, vistas y
admin lo reutilicen sin ciclos de importación.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

PRECISION_VALOR_DIARIO = Decimal("0.000001")


class ValorDiarioError(ValueError):
    """El ítem no tiene los datos necesarios para calcular su valor diario."""


def _a_decimal(valor, campo: str) -> Decimal:
    if valor is None:
        raise ValorDiarioError(f"{campo} no está definido.")
    try:
        return valor if isinstance(valor, Decimal) else Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ValorDiarioError(f"{campo} no es numérico: {valor!r}.")


def calcular_valor_diario(valor_base, vida_util_dias) -> Decimal:
    """valor_base / vida_util_dias, cuantizado a 6 decimales (ROUND_HALF_UP)."""
    base = _a_decimal(valor_base, "valor_base")
    if base < 0:
        raise ValorDiarioError(f"valor_base no puede ser negativo (recibido: {base}).")
    if vida_util_dias is None:
        raise ValorDiarioError(
            "vida_util_dias no está definida: el ítem está pendiente de configuración."
        )
    vida = _a_decimal(vida_util_dias, "vida_util_dias")
    if vida <= 0:
        raise ValorDiarioError(
            f"vida_util_dias debe ser mayor que cero (recibido: {vida_util_dias})."
        )
    return (base / vida).quantize(PRECISION_VALOR_DIARIO, rounding=ROUND_HALF_UP)


def calcular_aporte(valor_diario, cantidad) -> Decimal:
    """Aporte de un ítem a `suma`: valor_diario × cantidad (sin redondeo extra)."""
    return _a_decimal(valor_diario, "valor_diario") * _a_decimal(cantidad, "cantidad")
