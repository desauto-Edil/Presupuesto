"""
apps/presupuestos/services/presentacion_service.py

PresentacionProductoService — cálculo diferido por presentación de producto.

Responsabilidades:
  1. recalcular_tras_asignacion: evalúa la fórmula de un componente marcado con
     'requiere_presentacion_producto', guarda el resultado y propaga la cascade.
  2. limpiar_tras_eliminacion: revierte la resolución cuando se quita el producto
     y propaga la invalidación cascade.

No evalúa fórmulas de componentes normales; delega siempre en comp.evaluar().
No llama a DespieceService para evitar recalcular líneas con cantidad_ajustada.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from apps.catalogos.models import Producto
    from apps.ingenieria.models import ComponenteSubsistema
    from apps.presupuestos.models import DespieceLinea, ProyectoSistema

logger = logging.getLogger(__name__)

_Q6 = Decimal("0.000001")


class PresentacionProductoService:

    # ── Interfaz pública ──────────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def recalcular_tras_asignacion(
        cls,
        linea: "DespieceLinea",
        producto: "Producto",
    ) -> list["DespieceLinea"]:
        """
        Calcula la cantidad de 'linea' usando producto.cantidad_presentacion
        y propaga la cascade a componentes subsiguientes que dependan de
        comp.variable_salida.

        Lanza ValueError si:
          - El componente no existe o no tiene requiere_presentacion_producto=True.
          - producto.cantidad_presentacion es None o <= 0.
        """
        ps = linea.proyecto_sistema
        comp = cls._get_componente(linea)

        if comp is None:
            raise ValueError(
                f"ComponenteSubsistema '{linea.componente_codigo}' "
                f"no encontrado en subsistema del PS {ps.pk}."
            )

        if not comp.requiere_presentacion_producto:
            raise ValueError(
                f"El componente '{comp.codigo}' no tiene "
                "'requiere_presentacion_producto' activo."
            )

        pres = producto.cantidad_presentacion
        if not pres or pres <= 0:
            raise ValueError(
                f"El producto '{producto.nombre}' no tiene 'cantidad_presentacion' "
                "válida (debe ser > 0). Actualiza el catálogo antes de asignarlo."
            )

        ctx = cls._build_context_before(ps, comp)
        ctx[comp.variable_presentacion_producto] = float(pres)

        try:
            cantidad_float = comp.evaluar(ctx)
        except ValueError as exc:
            raise ValueError(
                f"Error evaluando fórmula del componente '{comp.codigo}': {exc}"
            ) from exc

        cantidad_decimal = Decimal(str(cantidad_float)).quantize(_Q6, rounding=ROUND_HALF_UP)

        linea.cantidad_calculada = cantidad_decimal
        linea.pendiente_producto = False
        linea.presentacion_snapshot = Decimal(str(pres))
        linea.save(update_fields=[
            "cantidad_calculada", "pendiente_producto",
            "presentacion_snapshot", "updated_at",
        ])

        logger.info(
            "[PresentacionService] PS %s / '%s' → cantidad=%s (pres=%s)",
            ps.pk, comp.codigo, cantidad_decimal, pres,
        )

        actualizadas: list["DespieceLinea"] = [linea]

        if comp.variable_salida:
            ctx[comp.variable_salida] = cantidad_float
            actualizadas += cls._propagar_cascade(ps, comp, ctx)

        return actualizadas

    @classmethod
    @transaction.atomic
    def limpiar_tras_eliminacion(cls, linea: "DespieceLinea") -> list["DespieceLinea"]:
        """
        Revierte la resolución de 'linea' cuando se retira su producto.
        Invalida en cascade los componentes subsiguientes que dependían de
        la variable_salida de este componente.
        """
        comp = cls._get_componente(linea)

        linea.cantidad_calculada = None
        linea.pendiente_producto = True
        linea.presentacion_snapshot = None
        linea.save(update_fields=[
            "cantidad_calculada", "pendiente_producto",
            "presentacion_snapshot", "updated_at",
        ])

        logger.info(
            "[PresentacionService] PS %s / '%s' → pendiente (producto retirado).",
            linea.proyecto_sistema_id,
            comp.codigo if comp else linea.componente_codigo,
        )

        actualizadas: list["DespieceLinea"] = [linea]

        if comp and comp.variable_salida:
            actualizadas += cls._invalidar_cascade(linea.proyecto_sistema, comp)

        return actualizadas

    # ── Helpers privados ──────────────────────────────────────────────────────

    @classmethod
    def _get_componente(cls, linea: "DespieceLinea") -> "ComponenteSubsistema | None":
        from apps.ingenieria.models import ComponenteSubsistema

        ps = linea.proyecto_sistema
        if not ps or not ps.subsistema_id:
            return None
        return (
            ComponenteSubsistema.objects
            .filter(subsistema_id=ps.subsistema_id, codigo=linea.componente_codigo)
            .first()
        )

    @classmethod
    def _build_context_before(
        cls,
        ps: "ProyectoSistema",
        comp: "ComponenteSubsistema",
    ) -> dict:
        """
        Devuelve el contexto de evaluación con:
          - Variables del proyecto (area_m2, perimetro_ml) + parametros_entrada.
          - Defaults de VariableSubsistema.
          - variable_salida de cada componente precedente ya resuelto.
        """
        from apps.ingenieria.models import ComponenteSubsistema, VariableSubsistema
        from apps.presupuestos.models import DespieceLinea

        ctx = ps.get_contexto()

        for var in VariableSubsistema.objects.filter(subsistema_id=ps.subsistema_id):
            if var.variable not in ctx:
                ctx[var.variable] = float(var.valor_default)

        precedentes = list(
            ComponenteSubsistema.objects
            .filter(subsistema_id=ps.subsistema_id, orden__lt=comp.orden)
            .exclude(variable_salida="")
            .values("codigo", "variable_salida")
        )

        if precedentes:
            codigos = [p["codigo"] for p in precedentes]
            lineas_map = {
                l.componente_codigo: l
                for l in DespieceLinea.objects.filter(
                    proyecto_sistema=ps,
                    componente_codigo__in=codigos,
                )
            }
            for entrada in precedentes:
                linea = lineas_map.get(entrada["codigo"])
                if linea and linea.cantidad_calculada is not None:
                    ctx[entrada["variable_salida"]] = float(linea.cantidad_calculada)

        return ctx

    @classmethod
    def _propagar_cascade(
        cls,
        ps: "ProyectoSistema",
        fuente_comp: "ComponenteSubsistema",
        contexto: dict,
    ) -> list["DespieceLinea"]:
        """
        Tras resolver fuente_comp, intenta recalcular en orden los componentes
        subsiguientes que estaban en pendiente_producto=True.
        Actualiza 'contexto' en-place con cada variable_salida resuelta,
        lo que permite una cadena de cascades.
        """
        from apps.ingenieria.models import ComponenteSubsistema
        from apps.presupuestos.models import DespieceLinea

        subsiguientes = list(
            ComponenteSubsistema.objects
            .filter(subsistema_id=fuente_comp.subsistema_id, orden__gt=fuente_comp.orden)
            .select_related("categoria")
            .order_by("orden")
        )
        if not subsiguientes:
            return []

        codigos = [c.codigo for c in subsiguientes]
        lineas_map = {
            l.componente_codigo: l
            for l in DespieceLinea.objects.filter(
                proyecto_sistema=ps,
                componente_codigo__in=codigos,
                pendiente_producto=True,
            ).select_related("producto")
        }

        actualizadas: list["DespieceLinea"] = []

        for comp in subsiguientes:
            linea = lineas_map.get(comp.codigo)
            if not linea:
                continue

            ctx_eval = {**contexto}

            if comp.requiere_presentacion_producto:
                if not linea.producto_id:
                    continue
                pres = linea.producto.cantidad_presentacion
                if not pres or pres <= 0:
                    continue
                ctx_eval[comp.variable_presentacion_producto] = float(pres)

            try:
                cantidad_float = comp.evaluar(ctx_eval)
            except Exception:
                continue  # sigue sin poderse resolver

            cantidad_decimal = Decimal(str(cantidad_float)).quantize(_Q6, rounding=ROUND_HALF_UP)

            update_vals: dict = {
                "cantidad_calculada": cantidad_decimal,
                "pendiente_producto": False,
            }
            if comp.requiere_presentacion_producto:
                update_vals["presentacion_snapshot"] = linea.producto.cantidad_presentacion

            for field, val in update_vals.items():
                setattr(linea, field, val)
            linea.save(update_fields=list(update_vals.keys()) + ["updated_at"])

            if comp.variable_salida:
                contexto[comp.variable_salida] = cantidad_float

            actualizadas.append(linea)
            logger.debug(
                "[PresentacionService] cascade → PS %s / '%s' → %s",
                ps.pk, comp.codigo, cantidad_decimal,
            )

        return actualizadas

    @classmethod
    def _invalidar_cascade(
        cls,
        ps: "ProyectoSistema",
        fuente_comp: "ComponenteSubsistema",
    ) -> list["DespieceLinea"]:
        """
        Cuando fuente_comp pierde su valor (producto retirado), invalida todos
        los componentes subsiguientes cuyas fórmulas referencian su variable_salida
        (o variables_salida derivadas de componentes ya invalidados).
        """
        from apps.ingenieria.models import ComponenteSubsistema
        from apps.presupuestos.models import DespieceLinea

        if not fuente_comp.variable_salida:
            return []

        subsiguientes = list(
            ComponenteSubsistema.objects
            .filter(subsistema_id=fuente_comp.subsistema_id, orden__gt=fuente_comp.orden)
            .order_by("orden")
        )

        vars_invalidas: set[str] = {fuente_comp.variable_salida}
        actualizadas: list["DespieceLinea"] = []

        for comp in subsiguientes:
            formula_vars = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', comp.formula_texto or ""))
            if not (formula_vars & vars_invalidas):
                continue

            qs = DespieceLinea.objects.filter(
                proyecto_sistema=ps,
                componente_codigo=comp.codigo,
                pendiente_producto=False,
            )
            for linea in qs:
                linea.cantidad_calculada = None
                linea.pendiente_producto = True
                if comp.requiere_presentacion_producto:
                    linea.presentacion_snapshot = None
                linea.save(update_fields=[
                    "cantidad_calculada", "pendiente_producto",
                    "presentacion_snapshot", "updated_at",
                ])
                actualizadas.append(linea)
                logger.debug(
                    "[PresentacionService] invalidación → PS %s / '%s'",
                    ps.pk, comp.codigo,
                )

            if comp.variable_salida:
                vars_invalidas.add(comp.variable_salida)

        return actualizadas
