"""
apps/ingenieria/system_defs/registry.py — Registro central de definiciones de sistemas.

Todos los sistemas definidos en este paquete se registran aquí.
DespieceService y ProyectoSistema consultan este registro en lugar de la DB
para obtener las recetas técnicas.

Para agregar un nuevo sistema:
  1. Crea apps/ingenieria/system_defs/mi_sistema.py con SistemaDef completo
  2. Importa y registra aquí: _register(MI_SISTEMA)
"""

from __future__ import annotations

from typing import Optional

from apps.ingenieria.system_defs.base import SistemaDef, SubsistemaDef, ComponenteDef, VariableRequerida
from apps.ingenieria.system_defs.powergrip import POWERGRIP


# ── Registro interno ──────────────────────────────────────────────────────────
# Estructura: {sistema_codigo: {subsistema_codigo: SubsistemaDef}}

_REGISTRY: dict[str, dict[str, SubsistemaDef]] = {}


def _register(sistema_def: SistemaDef) -> None:
    _REGISTRY[sistema_def.codigo] = {
        sub.codigo: sub
        for sub in sistema_def.subsistemas
    }


# ── Registro de sistemas disponibles ─────────────────────────────────────────

_register(POWERGRIP)
# _register(FACHADA)   ← agregar cuando esté disponible
# _register(IMPERMAX)  ← agregar cuando esté disponible


# ── API pública ───────────────────────────────────────────────────────────────

def get_subsistema_def(
    sistema_codigo: str,
    subsistema_codigo: str,
) -> Optional[SubsistemaDef]:
    """
    Devuelve la definición backend de un subsistema por código.
    Retorna None si el sistema o subsistema no está registrado.
    """
    return _REGISTRY.get(sistema_codigo, {}).get(subsistema_codigo)


def get_sistema_def(sistema_codigo: str) -> list[SubsistemaDef]:
    """Devuelve todos los subsistemas de un sistema registrado."""
    return list(_REGISTRY.get(sistema_codigo, {}).values())


def get_todos_los_sistemas() -> dict[str, dict[str, SubsistemaDef]]:
    """Devuelve el registro completo (para inspección o admin)."""
    return dict(_REGISTRY)


def sistema_tiene_def(sistema_codigo: str) -> bool:
    """True si el sistema tiene al menos un subsistema registrado."""
    return sistema_codigo in _REGISTRY


__all__ = [
    "get_subsistema_def",
    "get_sistema_def",
    "get_todos_los_sistemas",
    "sistema_tiene_def",
    "SistemaDef",
    "SubsistemaDef",
    "ComponenteDef",
    "VariableRequerida",
]
