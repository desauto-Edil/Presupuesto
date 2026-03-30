"""
apps/presupuestos/services/apu_service.py — Motor de APU automático.

Genera APU + APULineas a partir de:
  - DespieceLineas del ProyectoSistema  (materiales)
  - Catálogo de ítems                   (mano de obra, herramientas)
  - Entradas manuales                   (transporte, administración)
  - ConfiguracionAPU activa             (valores predeterminados)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, List

from django.db import transaction

logger = logging.getLogger(__name__)

# Claves buscadas en parametros_entrada para la cantidad de referencia del sistema.
_CLAVES_UNIDAD_REFERENCIA = (
    "total_powergrip",
    "total_unidades",
    "cantidad",
    "n_apoyos",
    "ml_fachada",
    "m2",
    "area_m2",
)


class APUService:
    """Motor de APU automático."""

    # ── Constructor ───────────────────────────────────────────────────────────

    def __init__(self, proyecto_sistema):
        from apps.presupuestos.models import APU, ConfiguracionAPU

        self.ps  = proyecto_sistema
        self.cfg = ConfiguracionAPU.activa_o_default()

        # Nombre y descripción predeterminados derivados del proyecto sistema
        nombre_default = (
            f"APU {proyecto_sistema.sistema} — "
            f"{proyecto_sistema.proyecto}"
        )

        self.apu, created = APU.objects.get_or_create(
            proyecto_sistema=proyecto_sistema,
            defaults={
                "nombre": nombre_default,
                "descripcion": "",
                "factor_venta_pct": self.cfg.factor_venta_pct,
                "iva_pct": getattr(proyecto_sistema.proyecto, "iva_pct", self.cfg.iva_pct),
                "aplica_iva": not getattr(proyecto_sistema.proyecto, "aplica_exencion_iva", False),
            },
        )
        logger.info(
            "[APUService] APU %s (%s) para PS %s | config='%s'.",
            self.apu.pk, "nuevo" if created else "existente",
            proyecto_sistema.pk, self.cfg.nombre,
        )

    # ── Classmethod de entrada ────────────────────────────────────────────────

    @classmethod
    def generar(cls, proyecto_sistema) -> "APU":
        """
        Punto de entrada principal.
        Genera líneas de materiales, finaliza y devuelve el APU.
        """
        svc = cls(proyecto_sistema)
        svc.generar_materiales()
        svc.finalizar()
        return svc.apu

    # ── Helper: cantidad de referencia ────────────────────────────────────────

    def _get_total_unidades(self) -> float:
        """
        Determina la cantidad de referencia del sistema.
        Busca en parametros_entrada con prioridad definida en _CLAVES_UNIDAD_REFERENCIA.
        Fallback: area_total_m2 del proyecto. Mínimo devuelto: 1.0.
        """
        params = self.ps.parametros_entrada or {}
        for clave in _CLAVES_UNIDAD_REFERENCIA:
            val = params.get(clave)
            if val:
                try:
                    total = float(val)
                    if total > 0:
                        logger.debug(
                            "[APUService] _get_total_unidades: clave='%s' valor=%.4f (PS %s)",
                            clave, total, self.ps.pk,
                        )
                        return total
                except (ValueError, TypeError):
                    pass
        fallback = float(self.ps.proyecto.area_total_m2 or 1) or 1.0
        logger.debug(
            "[APUService] _get_total_unidades: fallback area_m2=%.4f (PS %s)",
            fallback, self.ps.pk,
        )
        return fallback

    # ── Generadores de líneas ─────────────────────────────────────────────────

    @transaction.atomic
    def generar_materiales(self) -> List[dict]:
        """
        Genera APULineas tipo MATERIALES desde las DespieceLineas resueltas.
        rendimiento = total_unidades / cantidad_final
        Omite líneas pendientes_seleccion o sin producto.
        """
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        lineas_despiece = self.ps.despiece_lineas.select_related(
            "producto", "producto__unidad", "categoria_producto",
        )
        tp      = self._get_total_unidades()
        creadas = []

        for dl in lineas_despiece:
            if dl.pendiente_seleccion:
                logger.warning(
                    "[APUService] Línea %s omitida: pendiente de selección (PS=%s).",
                    dl.pk, self.ps.pk,
                )
                continue
            if not dl.producto_id:
                logger.warning(
                    "[APUService] Línea %s omitida: sin producto (PS=%s).",
                    dl.pk, self.ps.pk,
                )
                continue

            nombre      = dl.producto.nombre
            precio      = float(dl.precio_snapshot or 0)
            cantidad    = float(dl.cantidad_final)
            rendimiento = (tp / cantidad) if cantidad > 0 else 1.0

            linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.MATERIALES,
                despiece_linea=dl,
                defaults={
                    "descripcion": nombre,
                    "rendimiento": Decimal(str(round(rendimiento, 6))),
                    "unidad": getattr(dl.producto.unidad, "codigo", "und"),
                    "precio_referencia": Decimal(str(precio)),
                    "iva_aplicado": self.apu.aplica_iva,
                    "editable": False,
                },
            )
            linea.calcular()
            creadas.append({
                "descripcion": nombre,
                "rendimiento": round(rendimiento, 4),
                "precio": precio,
                "costo_unitario": float(linea.costo_unitario),
                "valor_unitario": float(linea.valor_unitario),
                "costo_total": float(linea.costo_total),
                "valor_total": float(linea.valor_total),
            })
            logger.debug(
                "[APUService] Material '%s' | cantidad=%.4f | rend=%.6f | cu=%.4f",
                nombre, cantidad, rendimiento, float(linea.costo_unitario),
            )

        logger.info(
            "[APUService] %d líneas de materiales generadas para APU %s.",
            len(creadas), self.apu.pk,
        )
        return creadas

    @transaction.atomic
    def generar_mano_obra_desde_catalogo(self, items_data: List[Dict]) -> List[dict]:
        """
        Genera APULineas MANO_DE_OBRA desde ítems del catálogo.
        items_data: [{"item_id": int, "cantidad": int}]

        Fórmula:
          días_trabajo = total_unidades / (total_personas × 40)
          CU_persona   = (precio_día × cantidad × días × AIU × margen) / total_unidades

        Conversión de unidad:
          mes  → precio_día = precio_base / 22 días hábiles
          hora → precio_día = precio_base × 8
          día  → precio_día = precio_base
        """
        from apps.presupuestos.models import APULinea, ItemCatalogoAPU
        from apps.common.choices import TipoAPU

        tp = self._get_total_unidades()
        total_pers = max(sum(int(d.get("cantidad", 1)) for d in items_data), 1)
        aiu = 1 + float(self.cfg.aiu_contratista_pct) / 100
        mg = 1 + float(self.cfg.margen_ganancia_pct) / 100
        dias = tp / (total_pers * 40) if total_pers > 0 else 1.0

        creadas = []
        for d in items_data:
            item     = ItemCatalogoAPU.objects.get(pk=d["item_id"])
            cantidad = max(int(d.get("cantidad", 1)), 1)

            # Usar total_mes_personal si está definido, si no precio_base
            if item.salario_base or item.prestaciones:
                precio_mes = float(item.total_mes_personal)
            else:
                precio_mes = float(item.precio_base)

            if item.unidad == "mes":
                precio_dia = precio_mes / 22
            elif item.unidad == "hora":
                precio_dia = float(item.precio_base) * 8
            else:
                precio_dia = float(item.precio_base)

            cu = (precio_dia * cantidad * dias * aiu * mg) / tp if tp else 0

            linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.MANO_DE_OBRA,
                descripcion=f"{item.nombre} ×{cantidad}",
                defaults={
                    "item_catalogo": item,
                    "rendimiento": Decimal("1"),
                    "unidad": item.unidad,
                    "precio_referencia": Decimal(str(round(cu, 6))),
                    "salario_base": item.salario_base,
                    "prestaciones": item.prestaciones,
                    "iva_aplicado": False,
                    "editable": True,
                },
            )
            linea.calcular()
            creadas.append({
                "descripcion": linea.descripcion,
                "costo_unitario": float(linea.costo_unitario),
            })
            logger.debug(
                "[APUService] MO catálogo '%s' ×%d | días=%.2f | cu=%.6f",
                item.nombre, cantidad, dias, cu,
            )

        logger.info(
            "[APUService] %d líneas MO (catálogo) para APU %s.", len(creadas), self.apu.pk,
        )
        return creadas

    @transaction.atomic
    def generar_herramientas_desde_catalogo(self, items_data: List[Dict]) -> List[dict]:
        """
        Genera APULineas HERRAMIENTAS_EQUIPOS desde ítems del catálogo.
        items_data: [{"item_id": int, "cantidad": int}]

        Con vida útil (herramientas):
          costo_total = (precio_base × cantidad / vida_util_dias) × días_trabajo
        Sin vida útil (fungibles: cables, consumibles):
          costo_total = precio_base × cantidad
        CU = costo_total / total_unidades
        """
        from apps.presupuestos.models import APULinea, ItemCatalogoAPU
        from apps.common.choices import TipoAPU

        tp   = self._get_total_unidades()
        # Estimar días de trabajo desde mano de obra ya registrada, o fallback
        dias = self._estimar_dias()

        creadas = []
        for d in items_data:
            item     = ItemCatalogoAPU.objects.get(pk=d["item_id"])
            cantidad = max(int(d.get("cantidad", 1)), 1)
            precio   = float(item.precio_base)

            if item.vida_util_dias and item.vida_util_dias > 0:
                costo_total_item = (precio * cantidad / item.vida_util_dias) * dias
            else:
                costo_total_item = precio * cantidad

            cu = costo_total_item / tp if tp else 0

            linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.HERRAMIENTAS_EQUIPOS,
                descripcion=f"{item.nombre} ×{cantidad}",
                defaults={
                    "item_catalogo": item,
                    "rendimiento": Decimal("1"),
                    "unidad": item.unidad,
                    "precio_referencia": Decimal(str(round(cu, 6))),
                    "vida_util_dias": item.vida_util_dias,
                    "iva_aplicado": False,
                    "editable": True,
                },
            )
            linea.calcular()
            creadas.append({
                "descripcion": linea.descripcion,
                "costo_unitario": float(linea.costo_unitario),
            })
            logger.debug(
                "[APUService] Herr '%s' ×%d | dias=%.2f | cu=%.6f",
                item.nombre, cantidad, dias, cu,
            )

        logger.info(
            "[APUService] %d herramientas (catálogo) para APU %s.", len(creadas), self.apu.pk,
        )
        return creadas

    @transaction.atomic
    def generar_transporte_items(self, items: List[Dict]) -> List[dict]:
        """
        Genera APULineas TRANSPORTE a partir de una lista de ítems libres.
        items: [{"descripcion": str, "precio_total": float}]

        CU = precio_total / total_unidades
        """
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        tp      = self._get_total_unidades()
        creadas = []

        for item in items:
            desc = item["descripcion"].strip()
            precio_total = float(item["precio_total"])
            cu = precio_total / tp if tp else 0

            linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.TRANSPORTE,
                descripcion=desc,
                defaults={
                    "rendimiento": Decimal("1"),
                    "unidad": "global",
                    "precio_referencia": Decimal(str(round(cu, 6))),
                    "iva_aplicado": False,
                    "editable": True,
                },
            )
            linea.calcular()
            creadas.append({
                "descripcion": linea.descripcion,
                "costo_unitario": float(linea.costo_unitario),
            })
            logger.debug(
                "[APUService] Transporte '%s' | total=%.2f | cu=%.6f", desc, precio_total, cu,
            )

        logger.info(
            "[APUService] %d líneas transporte para APU %s.", len(creadas), self.apu.pk,
        )
        return creadas

    @transaction.atomic
    def generar_administracion(self, costo_total_admin: float) -> dict:
        """
        Genera una APULinea ADMINISTRACION.
        CU = costo_total_admin / total_unidades
        """
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        tp = self._get_total_unidades()
        cu = costo_total_admin / tp if tp else 0

        linea, _ = APULinea.objects.update_or_create(
            apu=self.apu,
            tipo=TipoAPU.ADMINISTRACION,
            descripcion="Administración",
            defaults={
                "rendimiento": Decimal("1"),
                "unidad": "global",
                "precio_referencia": Decimal(str(round(cu, 6))),
                "iva_aplicado": False,
                "editable": True,
            },
        )
        linea.calcular()
        logger.debug(
            "[APUService] Admin APU %s | costo_total=%.2f | cu=%.6f",
            self.apu.pk, costo_total_admin, cu,
        )
        return {"descripcion": "Administración", "costo_unitario": float(linea.costo_unitario)}

    # ── Helper: estimar días de trabajo ───────────────────────────────────────

    def _estimar_dias(self) -> float:
        """
        Estima los días de trabajo necesarios.
        Si ya hay líneas MO registradas, infiere personas desde su cantidad.
        Fallback: total_unidades / (7 personas estándar × 40).
        """
        from apps.common.choices import TipoAPU

        total_personas = (
            self.apu.lineas
            .filter(tipo=TipoAPU.MANO_DE_OBRA)
            .count()
        ) or 7  # cuadrilla estándar

        tp   = self._get_total_unidades()
        dias = tp / (total_personas * 40)
        return max(dias, 1.0)

    # ── Cierre ────────────────────────────────────────────────────────────────

    def finalizar(self) -> dict:
        """
        Recalcula totales del APU y avanza el estado del proyecto a APU en proceso.
        Devuelve un resumen de totales.
        """
        from apps.common.choices import EstadoProyecto

        self.apu.recalcular()
        proyecto = self.ps.proyecto

        if proyecto.estado not in (EstadoProyecto.APU, EstadoProyecto.APU_GENERADO):
            proyecto.avanzar_a_apu()

        logger.info(
            "[APUService] APU %s finalizado | costo=%.2f | venta=%.2f | estado='%s'.",
            self.apu.pk,
            float(self.apu.total_costo),
            float(self.apu.total_valor_venta),
            proyecto.estado,
        )

        return {
            "total_costo": float(self.apu.total_costo),
            "total_valor_venta": float(self.apu.total_valor_venta),
            "subtotales": {
                "materiales": float(self.apu.subtotal_materiales),
                "herramientas": float(self.apu.subtotal_herramientas),
                "transporte": float(self.apu.subtotal_transporte),
                "mano_obra": float(self.apu.subtotal_mano_obra),
                "administracion": float(self.apu.subtotal_administracion),
            },
        }
    