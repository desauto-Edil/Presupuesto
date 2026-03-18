"""
apps/presupuestos/services/dependencia_service.py — Inyeccion de dependencias tecnicas.

DependenciaService inyecta automaticamente las dependencias obligatorias de
un subsistema al momento de seleccionarlo en el despiece de un proyecto.

CORRECCIONES vs version original:
  1. inyectar(): protege acceso a l.categoria_producto con guard (era AttributeError
     si la linea tenia dependencia_tecnica pero sin categoria asignada).
  2. Logging mejorado: cuantas se inyectaron vs ya existentes, y las pendientes.
  3. dependencias_del_subsistema(): acceso a unidad.abreviatura protegido con guard.
"""

from __future__ import annotations

import logging
from typing import List, TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from apps.presupuestos.models import ProyectoSistema

logger = logging.getLogger(__name__)


class DependenciaService:
    """
    Inyecta automaticamente las dependencias obligatorias de un subsistema
    al momento de seleccionarlo en el despiece.
    """

    def __init__(self, proyecto_sistema: "ProyectoSistema"):
        self.ps = proyecto_sistema

    @transaction.atomic
    def inyectar(self) -> List[dict]:
        """
        Delega en ProyectoSistema.inyectar_dependencias() y construye
        el resultado serializable para la capa superior.

        Retorna lista de dicts con info de cada linea creada.
        """
        if not self.ps.subsistema:
            logger.info(
                "[DependenciaService] PS %s sin subsistema — sin dependencias a inyectar.",
                self.ps.pk,
            )
            return []

        logger.info(
            "[DependenciaService] Inyectando dependencias para PS %s (subsistema=%s).",
            self.ps.pk, self.ps.subsistema.codigo,
        )

        lineas = self.ps.inyectar_dependencias()

        resultado = []
        for linea in lineas:
            # BUG CORREGIDO: categoria_producto puede ser None si la dependencia
            # fue creada con dependencia_tecnica pero sin categoria_producto explicita.
            if linea.producto_id:
                nombre = linea.producto.nombre
                pendiente = False
            elif linea.categoria_producto_id:
                # Acceso seguro: categoria_producto puede ser lazy
                nombre = f"[{linea.categoria_producto.nombre}]"
                pendiente = True
            else:
                nombre = "(sin producto ni categoria)"
                pendiente = True

            resultado.append({
                "id":              linea.pk,
                "producto_nombre": nombre,
                "automatica":      True,
                "pendiente":       pendiente,
            })

        n_pendientes = sum(1 for r in resultado if r["pendiente"])
        logger.info(
            "[DependenciaService] PS %s — %d dependencias inyectadas (%d pendientes).",
            self.ps.pk, len(resultado), n_pendientes,
        )
        return resultado

    def dependencias_del_subsistema(self) -> List[dict]:
        """
        Retorna lista de dependencias obligatorias del subsistema
        sin crearlas (preview en UI antes de confirmar el despiece).
        """
        from apps.ingenieria.models import DependenciaTecnica

        if not self.ps.subsistema:
            return []

        deps = DependenciaTecnica.objects.filter(
            subsistema=self.ps.subsistema, obligatoria=True
        ).select_related(
            "producto_dependiente",
            "producto_dependiente__unidad",
            "categoria_producto",
        ).order_by("orden")

        resultado = []
        for d in deps:
            if d.producto_dependiente_id:
                # BUG CORREGIDO: acceso a unidad protegido
                unidad = (
                    d.producto_dependiente.unidad.abreviatura
                    if d.producto_dependiente.unidad_id
                    else "—"
                )
                resultado.append({
                    "producto_codigo": d.producto_dependiente.codigo,
                    "producto_nombre": d.producto_dependiente.nombre,
                    "unidad":          unidad,
                    "tipo_regla":      d.tipo_regla,
                    "obligatoria":     d.obligatoria,
                    "pendiente":       False,
                })
            else:
                nombre = d.nombre or (
                    f"[{d.categoria_producto}]" if d.categoria_producto_id else "—"
                )
                resultado.append({
                    "producto_codigo": None,
                    "producto_nombre": nombre,
                    "unidad":          "—",
                    "tipo_regla":      d.tipo_regla,
                    "obligatoria":     d.obligatoria,
                    "pendiente":       True,
                })

        return resultado
