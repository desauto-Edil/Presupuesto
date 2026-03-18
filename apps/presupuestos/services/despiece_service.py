"""
apps/presupuestos/services/despiece_service.py — Motor de despiece paramétrico.

Ejecuta las ReglaCalculo activas de un subsistema sobre un ProyectoSistema
y genera/actualiza las DespieceLineas correspondientes.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import List

from django.db import transaction

logger = logging.getLogger(__name__)


class DespieceService:
    """
    Motor de despiece paramétrico.

    Algoritmo:
      1. Obtener ReglaCalculo activas del subsistema (ordenadas por orden_ejecucion).
      2. Construir contexto de variables desde ProyectoSistema.get_contexto().
      3. Evaluar cada regla en orden; actualizar contexto con resultados intermedios.
      4. Crear/actualizar DespieceLinea con la cantidad calculada.
      5. Capturar precio_snapshot desde ProductoProveedor.
    """

    def __init__(self, proyecto_sistema):
        from apps.presupuestos.models import ProyectoSistema
        self.ps: ProyectoSistema = proyecto_sistema

    @transaction.atomic
    def ejecutar(self) -> List[dict]:
        from apps.ingenieria.models import ReglaCalculo
        from apps.presupuestos.models import DespieceLinea

        subsistema = self.ps.subsistema
        if not subsistema:
            raise ValueError("El ProyectoSistema no tiene subsistema asignado.")

        reglas = ReglaCalculo.objects.filter(
            subsistema=subsistema, activa=True
        ).select_related("producto").order_by("orden_ejecucion")

        if not reglas.exists():
            logger.warning("No hay reglas de cálculo para subsistema %s", subsistema.codigo)
            return []

        contexto = self.ps.get_contexto()
        resultados = []

        for regla in reglas:
            try:
                cantidad = regla.evaluar(contexto)
            except ValueError as exc:
                logger.error("Error evaluando regla %s: %s", regla.codigo, exc)
                continue

            # Actualizar contexto con resultado para reglas derivadas
            contexto[regla.codigo] = cantidad
            if regla.variable_salida:
                contexto[regla.variable_salida] = cantidad
            if regla.producto_id:
                contexto[regla.producto.codigo] = cantidad
                contexto[regla.producto.nombre.replace(" ", "_")] = cantidad

            defaults = {
                "regla": regla,
                "cantidad_calculada": Decimal(str(round(cantidad, 6))),
                "es_dependencia_automatica": False,
            }
            if regla.producto_id:
                defaults["producto"] = regla.producto
                defaults["categoria_producto"] = None
            elif regla.categoria_producto_id:
                defaults["categoria_producto"] = regla.categoria_producto

            linea, _ = DespieceLinea.objects.update_or_create(
                proyecto=self.ps.proyecto,
                proyecto_sistema=self.ps,
                regla=regla,
                defaults=defaults,
            )
            linea.capturar_precio()

            resultados.append({
                "producto_codigo": regla.producto.codigo if regla.producto_id else None,
                "producto_nombre": (
                    regla.producto.nombre if regla.producto_id
                    else f"[{regla.categoria_producto}]" if regla.categoria_producto_id
                    else "—"
                ),
                "regla_codigo": regla.codigo,
                "cantidad": round(cantidad, 4),
                "unidad": (
                    regla.producto.unidad.abreviatura if regla.producto_id else "—"
                ),
                "precio_snapshot": float(linea.precio_snapshot or 0),
                "pendiente": linea.pendiente_seleccion,
            })

        return resultados
