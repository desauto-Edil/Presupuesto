"""
apps/presupuestos/services/consumo_service.py — Motor de cálculo para sistemas de CONSUMO.

Flujo:
    1. Verifica que el sistema sea de tipo CONSUMO (lanza ValueError si es CONSTRUCTIVO).
    2. Lee las CapaConsumo del subsistema ordenadas por `orden`.
    3. Para cada capa calcula:
           cantidad = area_m2 × consumo_m2 × num_capas × (1 + desperdicio_pct/100)
    4. Crea / reemplaza los registros CalculoConsumoLinea.
    5. Si el subsistema es BICOMPONENTE:
       - Lee ComponenteQuimico ordenados.
       - Valida que los porcentajes sumen 100.
       - Crea una sub-línea hija por componente:
             cantidad_comp = cantidad_capa × porcentaje/100

Restricción crítica:
    DespieceService NO debe ejecutarse en sistemas CONSUMO.
    Este servicio NO debe ejecutarse en sistemas CONSTRUCTIVO.
    La separación es explícita y forzada en ambos servicios.
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from apps.presupuestos.models import ProyectoSistema

logger = logging.getLogger(__name__)


class ConsumoService:
    """
    Calcula el consumo de productos para un ProyectoSistema de tipo CONSUMO.

    Uso:
        servicio = ConsumoService(proyecto_sistema)
        resultados = servicio.ejecutar()
    """

    def __init__(self, proyecto_sistema: "ProyectoSistema"):
        self.ps = proyecto_sistema

    # ── Punto de entrada principal ────────────────────────────────────────────

    @transaction.atomic
    def ejecutar(self) -> list[dict]:
        """
        Calcula el consumo para todas las capas del subsistema.

        Retorna lista de dicts con resumen de líneas procesadas.
        Borra y recrea los CalculoConsumoLinea existentes en cada ejecución.
        """
        from apps.ingenieria.models import CapaConsumo, ComponenteQuimico
        from apps.presupuestos.models import CalculoConsumoLinea
        from apps.common.choices import TipoSistema, TipoProductoConsumo

        ps = self.ps

        # ── Guardia: solo sistemas CONSUMO ─────────────────────────────────────
        if ps.sistema.tipo_sistema != TipoSistema.CONSUMO:
            raise ValueError(
                f"ConsumoService solo opera en sistemas CONSUMO. "
                f"'{ps.sistema.codigo}' es de tipo {ps.sistema.tipo_sistema}. "
                f"Use DespieceService para sistemas constructivos."
            )

        if not ps.subsistema_id:
            logger.warning("[ConsumoService] PS %s sin subsistema definido.", ps.pk)
            return []

        # ── Área base ──────────────────────────────────────────────────────────
        contexto = ps.get_contexto()
        area_m2 = Decimal(str(contexto.get("area_m2", 0)))
        if area_m2 <= 0:
            logger.warning(
                "[ConsumoService] PS %s — área_m2 = %s. Verifique el proyecto.",
                ps.pk, area_m2,
            )

        # ── Cargar definición del subsistema ───────────────────────────────────
        capas = list(
            CapaConsumo.objects.filter(subsistema=ps.subsistema)
            .select_related("categoria")
            .order_by("orden")
        )

        if not capas:
            logger.warning(
                "[ConsumoService] Subsistema '%s' sin CapaConsumo definidas (PS %s).",
                ps.subsistema.codigo, ps.pk,
            )
            return []

        es_bicomponente = ps.subsistema.tipo_producto == TipoProductoConsumo.BICOMPONENTE
        componentes_quimicos = []
        if es_bicomponente:
            componentes_quimicos = list(
                ComponenteQuimico.objects.filter(subsistema=ps.subsistema).order_by("orden")
            )
            self._validar_porcentajes(componentes_quimicos, ps.pk)

        # ── Borrar cálculo anterior ────────────────────────────────────────────
        CalculoConsumoLinea.objects.filter(proyecto_sistema=ps).delete()

        # ── Calcular y crear líneas ────────────────────────────────────────────
        resultados = []

        for orden, capa in enumerate(capas, start=1):
            cantidad = capa.calcular_cantidad(area_m2)

            linea = CalculoConsumoLinea.objects.create(
                proyecto_sistema=ps,
                capa_nombre=capa.nombre,
                categoria_producto=capa.categoria,
                area_m2=area_m2,
                consumo_m2=capa.consumo_m2,
                num_capas=capa.num_capas,
                desperdicio_pct=capa.desperdicio_pct or Decimal("0"),
                cantidad_calculada=cantidad,
                unidad=capa.unidad,
                es_componente_quimico=False,
                orden=orden,
            )
            linea.capturar_precio()

            resultado: dict = {
                "capa_nombre": capa.nombre,
                "cantidad": float(cantidad),
                "unidad": capa.unidad,
                "categoria": capa.categoria.nombre if capa.categoria else "",
                "pendiente": linea.pendiente_seleccion,
                "estado": linea.estado_tecnico,
            }

            # ── Sub-líneas para bicomponente ───────────────────────────────────
            if es_bicomponente and componentes_quimicos:
                sub_resultados = self._crear_sublineas_quimicas(
                    linea, cantidad, capa, componentes_quimicos, ps,
                )
                resultado["componentes"] = sub_resultados

            resultados.append(resultado)

        logger.info(
            "[ConsumoService] PS %s → %d capas calculadas (área: %s m²).",
            ps.pk, len(resultados), area_m2,
        )
        return resultados

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _crear_sublineas_quimicas(
        self, linea_padre, cantidad_total: Decimal, capa, componentes, ps
    ) -> list[dict]:
        """Crea líneas hijas (ComponenteQuimico) de una línea de capa."""
        from apps.presupuestos.models import CalculoConsumoLinea

        sub_resultados = []
        for cq in componentes:
            porcentaje = Decimal(str(cq.porcentaje)) / Decimal("100")
            cantidad_comp = (cantidad_total * porcentaje).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
            linea_comp = CalculoConsumoLinea.objects.create(
                proyecto_sistema=ps,
                capa_nombre=f"{capa.nombre} — {cq.nombre}",
                categoria_producto=cq.categoria,
                area_m2=linea_padre.area_m2,
                consumo_m2=capa.consumo_m2,
                num_capas=capa.num_capas,
                desperdicio_pct=capa.desperdicio_pct or Decimal("0"),
                cantidad_calculada=cantidad_comp,
                unidad=capa.unidad,
                linea_padre=linea_padre,
                es_componente_quimico=True,
                porcentaje_componente=cq.porcentaje,
                orden=cq.orden,
            )
            linea_comp.capturar_precio()
            sub_resultados.append({
                "nombre": cq.nombre,
                "porcentaje": float(cq.porcentaje),
                "cantidad": float(cantidad_comp),
                "unidad": capa.unidad,
                "categoria": cq.categoria.nombre if cq.categoria else "",
                "pendiente": linea_comp.pendiente_seleccion,
                "estado": linea_comp.estado_tecnico,
            })
        return sub_resultados

    @staticmethod
    def _validar_porcentajes(componentes, ps_pk: int) -> None:
        """
        Verifica que los porcentajes de los ComponenteQuimico sumen 100.
        Lanza ValueError si hay desviación > 0.01%.
        """
        if not componentes:
            return
        total = sum(Decimal(str(c.porcentaje)) for c in componentes)
        if abs(total - Decimal("100")) > Decimal("0.01"):
            raise ValueError(
                f"[ConsumoService] PS {ps_pk}: los porcentajes de componentes químicos "
                f"suman {total}% (deben ser exactamente 100%). "
                f"Corrija la definición del subsistema."
            )

    # ── Consultas de estado ───────────────────────────────────────────────────

    def validar_productos_completos(self) -> list[str]:
        """
        Retorna categorías sin producto asignado.
        Lista vacía = todos resueltos.
        """
        from apps.presupuestos.models import CalculoConsumoLinea

        pendientes = list(
            CalculoConsumoLinea.objects.filter(
                proyecto_sistema=self.ps,
                producto__isnull=True,
                categoria_producto__isnull=False,
            ).values_list("categoria_producto__nombre", flat=True)
        )
        return pendientes

    def asignar_producto(self, linea_pk: int, producto_pk: int) -> list[str]:
        """
        Asigna un producto a una CalculoConsumoLinea específica.
        Retorna lista de errores (vacía si OK).
        """
        from apps.catalogos.models import Producto
        from apps.presupuestos.models import CalculoConsumoLinea
        from django.core.exceptions import ValidationError

        errores = []
        try:
            linea = CalculoConsumoLinea.objects.get(
                pk=linea_pk, proyecto_sistema=self.ps
            )
            producto = Producto.objects.get(pk=producto_pk, activo=True)
            linea.resolver_producto(producto)
        except CalculoConsumoLinea.DoesNotExist:
            errores.append(f"Línea pk={linea_pk} no encontrada.")
        except Producto.DoesNotExist:
            errores.append(f"Producto pk={producto_pk} no encontrado o inactivo.")
        except ValidationError as exc:
            errores.append(str(exc.message))
        except Exception as exc:
            errores.append(str(exc))
        return errores
