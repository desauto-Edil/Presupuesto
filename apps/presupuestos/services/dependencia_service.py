"""
apps/presupuestos/services/dependencia_service.py — Inyección de dependencias técnicas.

DependenciaService inyecta automáticamente las dependencias obligatorias de
un subsistema al momento de seleccionarlo en el despiece de un proyecto.
"""

from __future__ import annotations
from typing import List
from django.db import transaction


class DependenciaService:
    """
    Inyecta automáticamente las dependencias obligatorias de un subsistema
    al momento de seleccionarlo en el despiece.
    """

    def __init__(self, proyecto_sistema):
        self.ps = proyecto_sistema

    @transaction.atomic
    def inyectar(self) -> List[dict]:
        """
        Llama a ProyectoSistema.inyectar_dependencias() y retorna
        una lista descriptiva de lo que se creó.
        """
        lineas = self.ps.inyectar_dependencias()
        resultado = []
        for l in lineas:
            if l.producto_id:
                resultado.append({
                    "producto_codigo": l.producto.codigo,
                    "producto_nombre": l.producto.nombre,
                    "unidad":          l.producto.unidad.abreviatura,
                    "automatica":      True,
                    "pendiente":       False,
                })
            else:
                resultado.append({
                    "producto_codigo": None,
                    "producto_nombre": f"[{l.categoria_producto}]" if l.categoria_producto_id else "—",
                    "unidad":          "—",
                    "automatica":      True,
                    "pendiente":       l.pendiente_seleccion,
                })
        return resultado

    def dependencias_del_subsistema(self) -> List[dict]:
        """
        Retorna lista de dependencias obligatorias del subsistema
        sin necesariamente crearlas (para preview en UI).
        """
        from apps.ingenieria.models import DependenciaTecnica

        if not self.ps.subsistema:
            return []

        deps = DependenciaTecnica.objects.filter(
            subsistema=self.ps.subsistema, obligatoria=True
        ).select_related("producto_dependiente__unidad", "categoria_producto")

        resultado = []
        for d in deps:
            if d.producto_dependiente_id:
                resultado.append({
                    "producto_codigo": d.producto_dependiente.codigo,
                    "producto_nombre": d.producto_dependiente.nombre,
                    "unidad": d.producto_dependiente.unidad.abreviatura,
                    "tipo_regla": d.tipo_regla,
                    "obligatoria": d.obligatoria,
                    "pendiente": False,
                })
            else:
                resultado.append({
                    "producto_codigo": None,
                    "producto_nombre": d.nombre or f"[{d.categoria_producto}]",
                    "unidad": "—",
                    "tipo_regla": d.tipo_regla,
                    "obligatoria": d.obligatoria,
                    "pendiente": True,
                })
        return resultado
