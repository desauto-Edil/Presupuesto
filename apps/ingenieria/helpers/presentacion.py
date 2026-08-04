"""
apps/ingenieria/helpers/presentacion.py

Helper centralizado para resolver el valor de presentación de un producto.

Responsabilidad única: dado un ComponenteSubsistema y un Producto, devuelve
el valor numérico (float) que debe inyectarse en la fórmula, o un mensaje
de error específico por campo si el valor no es válido.

Todos los servicios de cálculo diferido deben llamar a esta función en lugar
de acceder directamente a producto.cantidad_presentacion.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.catalogos.models import Producto
    from apps.ingenieria.models import ComponenteSubsistema

_CAMPO_A_ATRIBUTO: dict[str, tuple[str, str]] = {
    "CANTIDAD": ("cantidad_presentacion", "una cantidad por presentación"),
    "ANCHO":    ("ancho_presentacion",    "un ancho"),
    "LARGO":    ("largo_presentacion",    "un largo"),
}

_MENSAJES_ERROR: dict[str, str] = {
    "CANTIDAD": 'El producto "{nombre}" no tiene configurada una cantidad por presentación válida.',
    "ANCHO":    'El producto "{nombre}" no tiene configurado un ancho válido.',
    "LARGO":    'El producto "{nombre}" no tiene configurado un largo válido.',
}


def obtener_valor_presentacion(
    componente: "ComponenteSubsistema",
    producto: "Producto",
) -> tuple[float | None, str | None]:
    """
    Retorna ``(valor_float, None)`` si el campo de presentación del producto
    es válido (existe, es numérico y > 0).

    Retorna ``(None, mensaje_error)`` si el valor no está disponible.

    El campo se determina por ``componente.campo_presentacion_producto``.
    Valores aceptados: ``'CANTIDAD'``, ``'ANCHO'``, ``'LARGO'``.
    Cualquier valor desconocido recae en ``'CANTIDAD'``.
    """
    campo = (getattr(componente, "campo_presentacion_producto", None) or "CANTIDAD").upper()

    if campo not in _CAMPO_A_ATRIBUTO:
        campo = "CANTIDAD"

    atributo, _ = _CAMPO_A_ATRIBUTO[campo]
    valor = getattr(producto, atributo, None)

    if not valor or valor <= 0:
        mensaje = _MENSAJES_ERROR[campo].format(nombre=producto.nombre)
        return None, mensaje

    return float(valor), None
