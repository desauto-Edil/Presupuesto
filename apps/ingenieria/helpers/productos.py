"""
apps/ingenieria/helpers/productos.py

Serialización de productos para el despiece (búsqueda del selector y
producto predeterminado de la receta técnica).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.catalogos.models import Producto


def producto_a_dict(p: "Producto") -> dict:
    """Serializa un Producto con los datos que usa la tabla del despiece
    (precio, unidad y presentación). Compartido por la búsqueda y la receta."""
    return {
        "id":                        p.pk,
        "codigo":                    p.codigo,
        "nombre":                    p.nombre,
        "unidad":                    p.unidad.abreviatura if p.unidad else "",
        # precio_unitario = precio real por unidad (precio_actual / unidades_por_presentacion)
        "precio_unitario":           float(p.precio_unitario_real),
        "precio_presentacion":       float(p.precio_actual),
        "unidades_por_presentacion": p.unidades_por_presentacion or 1,
        "moneda":                    p.moneda,
        "fecha_actualizacion_precio": (
            p.fecha_actualizacion_precio.strftime("%Y-%m-%dT%H:%M:%S")
            if p.fecha_actualizacion_precio else None
        ),
        # ── Presentación técnica (opcional, para advertencias futuras) ──
        "presentacion_nombre":   p.presentacion_nombre or "",
        "ancho_presentacion":    float(p.ancho_presentacion) if p.ancho_presentacion is not None else None,
        "largo_presentacion":    float(p.largo_presentacion) if p.largo_presentacion is not None else None,
        "unidad_dimension":      p.unidad_dimension or "",
        "cantidad_presentacion": float(p.cantidad_presentacion) if p.cantidad_presentacion is not None else None,
        "unidad_presentacion":   p.unidad_presentacion.abreviatura if p.unidad_presentacion else "",
    }
