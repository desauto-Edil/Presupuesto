"""
apps/common/patterns.py — Bases reutilizables de patrones arquitectónicos.

ESTADO: módulo semilla. Aquí viven sólo las plantillas mínimas que después
los servicios concretos extenderán. No agregar lógica de dominio.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar


T = TypeVar("T")


# ---------------------------------------------------------------------------
# Singleton controlado
# ---------------------------------------------------------------------------
class SingletonMixin:
    """Mixin para clases con instancia única en memoria del proceso.

    Útil para registries / configuradores. NO usar para entidades de dominio
    persistidas (esas siguen siendo Django models, ej. ConfiguracionAPU).
    """
    _instance = None

    def __new__(cls, *args: Any, **kwargs: Any):  # noqa: D401
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------
class Strategy(ABC, Generic[T]):
    """Contrato base para estrategias intercambiables."""
    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> T: ...


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------
class Facade:
    """Marcador semántico para facades de dominio.

    Las facades orquestan varios services/selectors y son el único punto
    de entrada desde las views. Mantenerlas finas: nada de SQL, nada de eval.
    """


# ---------------------------------------------------------------------------
# Memento (snapshot)
# ---------------------------------------------------------------------------
class Memento(ABC):
    """Snapshot inmutable de un agregado.

    El concepto ya está implementado en DB en DespieceMaestroLinea y APULinea;
    esta clase es la plantilla para futuros snapshots en memoria.
    """
    @abstractmethod
    def to_dict(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------
class Adapter(ABC, Generic[T]):
    """Contrato base para adaptar APIs legadas a la API objetivo.

    Caso de uso típico en AndinaCost: envolver CapaConsumo (deprecated)
    para que parezca una ProductoTecnicoAsociado nueva.
    """
    @abstractmethod
    def adapt(self, source: Any) -> T: ...
