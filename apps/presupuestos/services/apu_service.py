"""
apps/presupuestos/services/apu_service.py — Motor de APU automatico (Nivel 4).

Genera APUProyecto + APULineas a partir de:
  - DespieceLineas del ProyectoSistema (materiales)
  - Variables de entrada del proyecto (mano de obra, equipos, transporte)
  - ConfiguracionAPU activa como valores predeterminados

CORRECCIONES vs version original:
  1. generar_materiales(): logging con ID de linea y motivo de omision detallado.
  2. generar_mano_obra(): calcular_tiempo() se llama y documenta antes de leer
     dias_trabajo, previniendo uso de valor None en la formula.
  3. Todos los metodos loggean PS id y APU id para trazabilidad.
  4. finalizar(): logging de totales calculados.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, List

from django.db import transaction

logger = logging.getLogger(__name__)


class APUService:
    """Motor de APU automatico (Nivel 4)."""

    def __init__(self, proyecto_sistema):
        from apps.presupuestos.models import APUProyecto, ConfiguracionAPU

        self.ps  = proyecto_sistema
        self.cfg = ConfiguracionAPU.activa_o_default()

        self.apu, created = APUProyecto.objects.get_or_create(
            proyecto_sistema=proyecto_sistema,
            defaults={
                "factor_venta_pct":       self.cfg.porcentaje_ganancia,
                "aiu_contratista_pct":    self.cfg.aiu_contratista,
                "margen_contratista_pct": self.cfg.margen_ganancia_contratista,
                "iva_pct":                proyecto_sistema.proyecto.iva_pct,
                "aplica_iva":             not proyecto_sistema.proyecto.aplica_exencion_iva,
            },
        )
        logger.info(
            "[APUService] APU %s (%s) para PS %s | config='%s'.",
            self.apu.pk, "nuevo" if created else "existente", proyecto_sistema.pk,
            self.cfg.nombre,
        )

    @transaction.atomic
    def generar_materiales(self) -> List[dict]:
        """
        Genera APULineas tipo MATERIALES desde las DespieceLineas resueltas.
        Omite lineas pendientes_seleccion con advertencia.
        rendimiento = Total_PowerGrip / cantidad_final
        costo_unitario = precio_snapshot * IVA_factor
        """
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        lineas_despiece = self.ps.despiece_lineas.select_related(
            "producto", "producto__unidad", "categoria_producto",
        )
        tp      = float(self.ps.total_powergip or 1) or 1
        creadas = []

        for dl in lineas_despiece:
            if dl.pendiente_seleccion:
                logger.warning(
                    "[APUService] Linea %s omitida: pendiente de seleccion "
                    "(categoria=%s, PS=%s).",
                    dl.pk, dl.categoria_producto, self.ps.pk,
                )
                continue

            if not dl.producto_id:
                logger.warning(
                    "[APUService] Linea %s omitida: sin producto ni categoria (PS=%s).",
                    dl.pk, self.ps.pk,
                )
                continue

            nombre   = dl.producto.nombre
            precio   = float(dl.precio_snapshot or 0)
            cantidad = float(dl.cantidad_final)
            rendimiento = (tp / cantidad) if cantidad > 0 else 1.0

            logger.debug(
                "[APUService] Material '%s' | cantidad=%.4f | precio=%.4f | rend=%.6f",
                nombre, cantidad, precio, rendimiento,
            )

            apu_linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.MATERIALES,
                despiece_linea=dl,
                defaults={
                    "descripcion":      nombre,
                    "rendimiento":      Decimal(str(round(rendimiento, 6))),
                    "precio_referencia": Decimal(str(precio)),
                    "iva_aplicado":     self.apu.aplica_iva,
                    "editable":         False,
                },
            )
            apu_linea.calcular()
            creadas.append({
                "descripcion":   nombre,
                "rendimiento":   round(rendimiento, 4),
                "precio":        precio,
                "costo_unitario": float(apu_linea.costo_unitario),
                "valor_unitario": float(apu_linea.valor_unitario),
                "costo_total":   float(apu_linea.costo_total),
                "valor_total":   float(apu_linea.valor_total),
            })

        logger.info(
            "[APUService] %d lineas de materiales generadas para APU %s.",
            len(creadas), self.apu.pk,
        )
        return creadas

    @transaction.atomic
    def generar_mano_obra(
        self,
        hya_dia: float = 0,
        cuadrilla_dia: float = 0,
        dotacion_dia: float = 0,
        proteccion_dia: float = 0,
    ) -> dict:
        """
        Genera APULineas de tipo MANO_DE_OBRA.
        dias_trabajo = Total_PowerGrip / (personas * 40) — calculado y persistido
        por calcular_tiempo() antes de usarse.
        """
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        # CORRECCION: calcular_tiempo() se llama primero y guarda dias_trabajo en DB.
        # Luego self.apu.dias_trabajo tiene el valor correcto (no None).
        self.apu.calcular_tiempo()
        self.apu.refresh_from_db(fields=["dias_trabajo", "tiempo_estimado_meses", "rendimiento_und_dia"])

        tp      = float(self.ps.total_powergip or 1) or 1
        personas = float(self.ps.cuadrilla_personas or 1) or 1
        dias    = float(self.apu.dias_trabajo or (tp / (personas * 40)))
        rend    = float(self.apu.rendimiento_und_dia or 0)
        aiu     = 1 + float(self.apu.aiu_contratista_pct) / 100
        mg      = 1 + float(self.apu.margen_contratista_pct) / 100

        logger.info(
            "[APUService] MO APU %s | dias=%.2f | rend=%.4f | personas=%.0f | "
            "aiu=%.3f | mg=%.3f",
            self.apu.pk, dias, rend, personas, aiu, mg,
        )

        items_mo = [
            ("HYA — Herramientas y andamios", hya_dia,
             (hya_dia * (rend + personas) * dias * aiu * mg) / tp),
            ("Cuadrilla de instalacion",      cuadrilla_dia,
             (cuadrilla_dia * personas * aiu * mg) / tp),
            ("Dotacion",                      dotacion_dia,
             (dotacion_dia * (rend + personas) * dias * aiu * mg) / tp),
            ("Proteccion",                    proteccion_dia,
             (proteccion_dia * (rend + personas) * dias * aiu * mg) / tp),
        ]

        creadas = []
        for desc, precio_base, cu in items_mo:
            if precio_base <= 0:
                continue
            apu_linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.MANO_DE_OBRA,
                descripcion=desc,
                defaults={
                    "rendimiento":      Decimal("1"),
                    "precio_referencia": Decimal(str(round(cu, 6))),
                    "iva_aplicado":     False,
                    "editable":         True,
                },
            )
            apu_linea.calcular()
            creadas.append({
                "descripcion":   desc,
                "costo_unitario": float(apu_linea.costo_unitario),
            })
            logger.debug("[APUService] MO '%s' | cu=%.6f", desc, cu)

        return {
            "mano_obra":    creadas,
            "dias":          dias,
            "tiempo_meses":  float(self.apu.tiempo_estimado_meses or 0),
        }

    @transaction.atomic
    def generar_herramientas(self, items: List[Dict]) -> List[dict]:
        """items: [{"descripcion": str, "precio_total": float}]"""
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        tp      = float(self.ps.total_powergip or 1) or 1
        creadas = []
        for item in items:
            precio = float(item.get("precio_total", 0))
            cu     = precio / tp
            apu_linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.HERRAMIENTAS_EQUIPOS,
                descripcion=item["descripcion"],
                defaults={
                    "rendimiento":      Decimal("1"),
                    "precio_referencia": Decimal(str(round(cu, 6))),
                    "iva_aplicado":     False,
                    "editable":         True,
                },
            )
            apu_linea.calcular()
            creadas.append({
                "descripcion":   item["descripcion"],
                "costo_unitario": float(apu_linea.costo_unitario),
            })
        logger.info(
            "[APUService] %d lineas de herramientas generadas para APU %s.",
            len(creadas), self.apu.pk,
        )
        return creadas

    @transaction.atomic
    def generar_transporte(self, costo_total_transporte: float) -> dict:
        """CU_transporte = costo_total / Total_PowerGrip"""
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        tp  = float(self.ps.total_powergip or 1) or 1
        cu  = costo_total_transporte / tp
        apu_linea, _ = APULinea.objects.update_or_create(
            apu=self.apu,
            tipo=TipoAPU.TRANSPORTE,
            descripcion="Transporte",
            defaults={
                "rendimiento":      Decimal("1"),
                "precio_referencia": Decimal(str(round(cu, 6))),
                "iva_aplicado":     False,
                "editable":         True,
            },
        )
        apu_linea.calcular()
        logger.debug(
            "[APUService] Transporte APU %s | costo_total=%.2f | cu=%.6f",
            self.apu.pk, costo_total_transporte, cu,
        )
        return {"descripcion": "Transporte", "costo_unitario": float(apu_linea.costo_unitario)}

    @transaction.atomic
    def generar_administracion(self, costo_total_admin: float) -> dict:
        """CU_admin = costo_total / Total_PowerGrip"""
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        tp  = float(self.ps.total_powergip or 1) or 1
        cu  = costo_total_admin / tp
        apu_linea, _ = APULinea.objects.update_or_create(
            apu=self.apu,
            tipo=TipoAPU.ADMINISTRACION,
            descripcion="Administracion",
            defaults={
                "rendimiento":      Decimal("1"),
                "precio_referencia": Decimal(str(round(cu, 6))),
                "iva_aplicado":     False,
                "editable":         True,
            },
        )
        apu_linea.calcular()
        logger.debug(
            "[APUService] Admin APU %s | costo_total=%.2f | cu=%.6f",
            self.apu.pk, costo_total_admin, cu,
        )
        return {"descripcion": "Administracion", "costo_unitario": float(apu_linea.costo_unitario)}

    def finalizar(self) -> dict:
        """Recalcula totales del APU y avanza estado del proyecto a APU en proceso."""
        from apps.common.choices import EstadoProyecto

        self.apu.recalcular()
        proyecto = self.ps.proyecto

        if proyecto.estado not in (EstadoProyecto.APU, EstadoProyecto.APU_GENERADO):
            proyecto.avanzar_a_apu()

        logger.info(
            "[APUService] APU %s finalizado | costo=%.2f | venta=%.2f | "
            "estado_proyecto='%s'.",
            self.apu.pk,
            float(self.apu.total_costo),
            float(self.apu.total_valor_venta),
            proyecto.estado,
        )

        return {
            "total_costo":       float(self.apu.total_costo),
            "total_valor_venta": float(self.apu.total_valor_venta),
            "subtotales": {
                "materiales":   float(self.apu.subtotal_materiales),
                "herramientas": float(self.apu.subtotal_herramientas),
                "transporte":   float(self.apu.subtotal_transporte),
                "mano_obra":    float(self.apu.subtotal_mano_obra),
                "administracion": float(self.apu.subtotal_administracion),
            },
        }
