"""
apps/presupuestos/services/despiece_service.py — Motor de despiece paramétrico.

Ejecuta las ReglaCalculo activas de un subsistema sobre un ProyectoSistema
y genera/actualiza las DespieceLineas correspondientes.

CORRECCIONES vs versión original:
  1. select_related añade producto__unidad y categoria_producto (evita N+1 y AttributeError).
  2. update_or_create limpia explícitamente producto/categoria opuestos en cada rama.
  3. Validación temprana de total_powergip con advertencia.
  4. Logging detallado: contexto, resultado por regla, resumen final.
  5. El resultado de cada regla incluye linea_id, nueva (created flag) y unidad segura.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from apps.presupuestos.models import ProyectoSistema

logger = logging.getLogger(__name__)


class DespieceService:
    """Motor de despiece paramétrico."""

    def __init__(self, proyecto_sistema):
        self.ps = proyecto_sistema

    @transaction.atomic
    def ejecutar(self) -> List[dict]:
        from apps.ingenieria.models import ReglaCalculo
        from apps.presupuestos.models import DespieceLinea

        subsistema = self.ps.subsistema
        if not subsistema:
            raise ValueError(
                f"ProyectoSistema {self.ps.pk} no tiene subsistema asignado."
            )

        # Validacion de variable de entrada principal
        total_pg = float(self.ps.total_powergip or 0)
        if total_pg <= 0:
            logger.warning(
                "[DespieceService] PS %s: total_powergip=%s — formulas con "
                "Total_PowerGrip produciran 0.",
                self.ps.pk, total_pg,
            )

        # BUG CORREGIDO: producto__unidad agregado a select_related
        # para evitar N+1 queries y AttributeError cuando se accede a unidad.
        reglas = (
            ReglaCalculo.objects
            .filter(subsistema=subsistema, activa=True)
            .select_related("producto", "producto__unidad", "categoria_producto")
            .order_by("orden_ejecucion")
        )

        if not reglas.exists():
            logger.warning(
                "[DespieceService] Sin reglas activas para subsistema %s (%s).",
                subsistema.codigo, subsistema.nombre,
            )
            return []

        contexto = self.ps.get_contexto()
        logger.info(
            "[DespieceService] PS %s | subsistema=%s | %d reglas | contexto=%s",
            self.ps.pk, subsistema.codigo, reglas.count(), contexto,
        )

        resultados: List[dict] = []

        for regla in reglas:
            # Evaluacion de la formula
            try:
                cantidad = regla.evaluar(contexto)
            except ValueError as exc:
                logger.error(
                    "[DespieceService] Regla %s (%s) — error evaluacion: %s",
                    regla.codigo, regla.nombre, exc,
                )
                continue

            logger.debug(
                "[DespieceService] Regla %s => cantidad=%.6f", regla.codigo, cantidad
            )

            # Propagar resultado al contexto para reglas derivadas
            if regla.variable_salida:
                contexto[regla.variable_salida] = cantidad
            contexto[regla.codigo] = cantidad
            if regla.producto_id:
                contexto[regla.producto.codigo] = cantidad
                contexto[regla.producto.nombre.replace(" ", "_")] = cantidad

            # BUG CORREGIDO: cuando la regla es de categoria, se limpia producto=None
            # (y viceversa) para que update_or_create no deje campos contradictorios
            # si la linea ya existia con un estado diferente.
            defaults: dict = {
                "regla": regla,
                "cantidad_calculada": Decimal(str(round(cantidad, 6))),
                "es_dependencia_automatica": False,
            }

            if regla.producto_id:
                defaults["producto"]           = regla.producto
                defaults["categoria_producto"] = None
            elif regla.categoria_producto_id:
                defaults["producto"]           = None
                defaults["categoria_producto"] = regla.categoria_producto
            else:
                defaults["producto"]           = None
                defaults["categoria_producto"] = None

            linea, created = DespieceLinea.objects.update_or_create(
                proyecto=self.ps.proyecto,
                proyecto_sistema=self.ps,
                regla=regla,
                defaults=defaults,
            )
            linea.capturar_precio()

            # Acceso seguro a unidad: solo si producto y unidad existen
            unidad_abrev = "—"
            if regla.producto_id and regla.producto.unidad_id:
                unidad_abrev = regla.producto.unidad.abreviatura

            resultados.append({
                "linea_id":        linea.pk,
                "producto_codigo": regla.producto.codigo if regla.producto_id else None,
                "producto_nombre": (
                    regla.producto.nombre               if regla.producto_id
                    else f"[{regla.categoria_producto}]" if regla.categoria_producto_id
                    else "—"
                ),
                "regla_codigo":    regla.codigo,
                "cantidad":        round(cantidad, 4),
                "unidad":          unidad_abrev,
                "precio_snapshot": float(linea.precio_snapshot or 0),
                "pendiente":       linea.pendiente_seleccion,
                "nueva":           created,
            })

        n_pendientes = sum(1 for r in resultados if r["pendiente"])
        logger.info(
            "[DespieceService] PS %s — %d lineas generadas (%d pendientes de seleccion).",
            self.ps.pk, len(resultados), n_pendientes,
        )
        return resultados
