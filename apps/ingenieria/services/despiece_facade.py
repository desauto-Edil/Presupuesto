"""
apps/ingenieria/services/despiece_facade.py
===========================================

Facade del dominio de despiece. **Punto de entrada único** previsto para
que las vistas no construyan `DespieceMaestroService` ni `DespieceService`
directamente.

ESTADO: **semilla (Fase 2 — Lote E)**.
    - Las vistas **no** la adoptan todavía. Se mantiene compatibilidad con
      los servicios existentes.
    - Cada método es un wrapper delgado sobre un service existente.
    - Cero cambio funcional respecto al uso directo de los services.

Plan de migración (fase posterior):
    1. Sustituir progresivamente en las vistas:
         DespieceMaestroService(despiece).calcular()
       por:
         DespieceFacade.calcular_maestro(despiece)
    2. Cuando todas las vistas usen la facade, los services internos pueden
       refactorizarse sin tocar capas superiores.
"""

from __future__ import annotations

from typing import Optional

from apps.common.patterns import Facade


class DespieceFacade(Facade):
    """API estable para despiece maestro y despiece por proyecto.

    Diseñada como conjunto de métodos estáticos para que los call-sites
    de las vistas no necesiten pasar el service como dependencia.
    """

    # ── Despiece maestro ─────────────────────────────────────────────────

    @staticmethod
    def calcular_maestro(despiece) -> list[dict]:
        """Calcula las líneas del despiece maestro a partir de su receta y
        variables actuales.

        Wrapper sobre `DespieceMaestroService(despiece).calcular()`.
        """
        from apps.ingenieria.services.despiece_maestro_service import DespieceMaestroService
        return DespieceMaestroService(despiece).calcular()

    @staticmethod
    def guardar_maestro(despiece, resultados: list[dict], variables_entrada: dict, **kwargs):
        """Persiste los resultados como snapshot inmutable.

        Wrapper sobre `DespieceMaestroService.guardar`. Acepta kwargs extra
        (subconjuntos, usuario, etc.) sin acoplar la facade al shape exacto;
        se reenvían tal cual al service.
        """
        from apps.ingenieria.services.despiece_maestro_service import DespieceMaestroService
        return DespieceMaestroService(despiece).guardar(
            resultados, variables_entrada, **kwargs
        )

    @staticmethod
    def obtener_variables_requeridas(despiece) -> list[dict]:
        """Variables que el despiece maestro necesita para calcularse.

        Wrapper sobre `DespieceMaestroService.get_variables_requeridas`.
        """
        from apps.ingenieria.services.despiece_maestro_service import DespieceMaestroService
        return DespieceMaestroService(despiece).get_variables_requeridas()

    @staticmethod
    def validar_variables_entrada(despiece, variables: dict) -> list[str]:
        """Devuelve la lista de errores (vacía si todo OK)."""
        from apps.ingenieria.services.despiece_maestro_service import DespieceMaestroService
        return DespieceMaestroService(despiece).validar_variables_entrada(variables)

    # ── Despiece por proyecto ────────────────────────────────────────────

    @staticmethod
    def calcular_para_proyecto(proyecto_sistema) -> list[dict]:
        """Calcula el despiece de un ProyectoSistema (despiece por proyecto).

        Wrapper sobre `DespieceService(proyecto_sistema).ejecutar()`.
        """
        from apps.presupuestos.services.despiece_service import DespieceService
        return DespieceService(proyecto_sistema).ejecutar()

    @staticmethod
    def validar_productos_completos(proyecto_sistema) -> list[str]:
        """Wrapper sobre `DespieceService.validar_productos_completos`."""
        from apps.presupuestos.services.despiece_service import DespieceService
        return DespieceService(proyecto_sistema).validar_productos_completos()

    @staticmethod
    def asignar_productos(proyecto_sistema, productos_map: dict[str, int]) -> list[str]:
        """Wrapper sobre `DespieceService.asignar_productos`."""
        from apps.presupuestos.services.despiece_service import DespieceService
        return DespieceService(proyecto_sistema).asignar_productos(productos_map)
