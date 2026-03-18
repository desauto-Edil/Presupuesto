from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import List, TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from apps.presupuestos.models import ProyectoSistema

logger = logging.getLogger(__name__)


class DespieceService:
    def __init__(self, proyecto_sistema: ProyectoSistema):
        self.ps = proyecto_sistema

    @transaction.atomic
    def ejecutar(self) -> List[dict]:
        from apps.ingenieria.models import ReglaCalculo
        from apps.presupuestos.models import DespieceLinea

        subsistema = self.ps.subsistema
        if not subsistema:
            raise ValueError("El ProyectoSistema no tiene subsistema asignado.")

        reglas = ReglaCalculo.objects.filter(
            subsistema=subsistema, activa=True
        ).order_by("orden_ejecucion")

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
