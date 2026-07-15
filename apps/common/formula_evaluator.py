"""
apps/common/formula_evaluator.py — Evaluador seguro de fórmulas.

Objetivo:
    Centralizar el uso de eval() restringido que hoy aparece duplicado en:
      - apps.ingenieria.models.sistemas.ComponenteSubsistema.evaluar()
      - apps.presupuestos.models.apu.ReglaAPUSubsistema.evaluar()
      - apps.presupuestos.services.apu_service (internamente)

Política:
    - Sólo se permiten nombres de variables presentes en `context`.
    - Sólo se permiten funciones de `SAFE_MATH` (subset de `math`).
    - No se permiten builtins, no se permiten dunders, no se permiten imports.

ESTADO: módulo base. NO está cableado todavía a los servicios existentes.
La migración a este evaluador se hará en una fase posterior — primero
queremos que el evaluador exista, esté testeado y sea estable.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Nombres seguros disponibles dentro de las fórmulas
# ---------------------------------------------------------------------------
SAFE_MATH: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "sqrt": math.sqrt,
    "ceil": math.ceil,
    "floor": math.floor,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "pow": math.pow,
    "fabs": math.fabs,
}

SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "int": int,
    "float": float,
}

# Conjunto base de nombres permitidos (sin variables del contexto).
SAFE_NAMES: dict[str, Any] = {**SAFE_MATH, **SAFE_BUILTINS}


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------
class FormulaError(Exception):
    """Error genérico al evaluar una fórmula."""


class FormulaSyntaxError(FormulaError):
    """Error de sintaxis o nombre no permitido."""


class FormulaRuntimeError(FormulaError):
    """Error en tiempo de ejecución (división por cero, etc.)."""


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def extract_tokens(formula: str) -> set[str]:
    """Devuelve los identificadores presentes en la fórmula.

    Incluye nombres del catálogo SAFE_NAMES. Para obtener sólo variables del
    contexto, hacer `extract_tokens(f) - SAFE_NAMES.keys()`.
    """
    if not formula:
        return set()
    return set(_IDENT_RE.findall(formula))


def extract_variable_tokens(formula: str) -> set[str]:
    """Sólo los tokens que NO pertenecen al catálogo de nombres seguros."""
    return extract_tokens(formula) - set(SAFE_NAMES.keys())


# ---------------------------------------------------------------------------
# Evaluación
# ---------------------------------------------------------------------------
def evaluate_formula(formula: str, context: Mapping[str, Any]) -> float:
    """Evalúa `formula` con `context` como espacio de variables.

    Raises:
        FormulaSyntaxError: si hay tokens fuera del whitelist.
        FormulaRuntimeError: si la evaluación lanza una excepción.
    """
    if not formula or not formula.strip():
        raise FormulaSyntaxError("Fórmula vacía")

    allowed = {**SAFE_NAMES, **dict(context)}
    tokens = extract_tokens(formula)
    unknown = tokens - set(allowed.keys())
    if unknown:
        raise FormulaSyntaxError(
            f"Tokens no permitidos en la fórmula: {sorted(unknown)}"
        )

    try:
        # __builtins__ vacío evita acceso a builtins peligrosos
        return float(eval(formula, {"__builtins__": {}}, allowed))  # noqa: S307
    except FormulaSyntaxError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FormulaRuntimeError(f"Error evaluando '{formula}': {exc}") from exc
