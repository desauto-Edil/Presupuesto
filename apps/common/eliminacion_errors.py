"""
apps/common/eliminacion_errors.py
=================================

Excepciones tipadas para los servicios de eliminación administrativa
(ADMINISTRADOR global). Las vistas las capturan y producen mensajes
amigables al usuario; no se propagan a pantalla amarilla.
"""

from __future__ import annotations


class EliminacionBloqueadaError(Exception):
    """
    Se lanza cuando una eliminación administrativa NO debe propagarse porque
    rompería trazabilidad declarada como crítica (ej. un despiece incluido
    en uno o más APUs).

    El atributo `detalle` es una cadena legible que la vista puede pasar
    directamente a `messages.error`.
    """

    def __init__(self, detalle: str):
        super().__init__(detalle)
        self.detalle = detalle
