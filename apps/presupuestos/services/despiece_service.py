"""
apps/presupuestos/services/despiece_service.py — Motor de cálculo de despiece.

Prioridad de receta técnica:
  1. Componentes definidos en DB (ComponenteSubsistema) — preferidos, editables desde UI.
  2. Registro Python en system_defs/registry.py — fallback para sistemas hardcodeados.

Flujo:
  1. Verificar si el subsistema tiene ComponenteSubsistema en DB.
     · Si sí → usar componentes DB.
     · Si no → leer SubsistemaDef del registro Python.
  2. Construir contexto: datos del proyecto + parametros_entrada del PS.
     · Si DB: inyectar también los defaults de VariableSubsistema para variables no provistas.
  3. Ejecutar componentes en orden ascendente.
  4. Para cada componente:
     a. Evaluar la fórmula con el contexto acumulado.
     b. Si tiene variable_salida, inyectarla al contexto (cascada).
     c. Obtener CategoriaProducto (desde FK en DB o por nombre en registry).
     d. Crear/actualizar DespieceLinea identificada por componente_codigo.
     e. Capturar precio snapshot si el producto ya está resuelto.
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from apps.presupuestos.models import ProyectoSistema

logger = logging.getLogger(__name__)


class DespieceService:
    def __init__(self, proyecto_sistema: "ProyectoSistema"):
        self.ps = proyecto_sistema

    @transaction.atomic
    def ejecutar(self) -> list[dict]:
        """
        Calcula todas las líneas de despiece para el ProyectoSistema.

        Prioridad: componentes en DB (ComponenteSubsistema) > registry Python.
        Devuelve lista de dicts con el resumen de líneas procesadas.
        """
        from apps.catalogos.models import CategoriaProducto
        from apps.presupuestos.models import DespieceLinea
        from apps.ingenieria.models import ComponenteSubsistema, VariableSubsistema

        ps = self.ps

        if not ps.sistema_id or not ps.subsistema_id:
            logger.warning("[DespieceService] PS %s sin sistema/subsistema definido.", ps.pk)
            return []

        # ── Elegir fuente de componentes ──────────────────────────────────────
        componentes_db = list(
            ComponenteSubsistema.objects.filter(subsistema=ps.subsistema)
            .select_related("categoria")
            .order_by("orden")
        )

        if componentes_db:
            return self._ejecutar_desde_db(ps, componentes_db, DespieceLinea)
        else:
            return self._ejecutar_desde_registry(ps, CategoriaProducto, DespieceLinea)

    def _ejecutar_desde_db(self, ps, componentes_db, DespieceLinea) -> list[dict]:
        """Ejecuta el despiece usando componentes definidos en ComponenteSubsistema."""
        from apps.ingenieria.models import VariableSubsistema

        contexto = ps.get_contexto()

        # Inyectar defaults de variables DB para las que el usuario no proporcionó valor
        for var in VariableSubsistema.objects.filter(subsistema=ps.subsistema).order_by("orden"):
            if var.variable not in contexto:
                contexto[var.variable] = float(var.valor_default)

        logger.debug("[DespieceService][DB] Contexto PS %s: %s", ps.pk, contexto)
        resultados = []

        for comp in componentes_db:
            try:
                cantidad_float = comp.evaluar(contexto)
            except (KeyError, ValueError) as exc:
                logger.error(
                    "[DespieceService][DB] Error en componente '%s' (PS %s): %s",
                    comp.codigo, ps.pk, exc,
                )
                continue

            if comp.variable_salida:
                contexto[comp.variable_salida] = cantidad_float

            cantidad_decimal = Decimal(str(cantidad_float)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )

            categoria = comp.categoria  # ya FK directo

            linea, created = DespieceLinea.objects.update_or_create(
                proyecto_sistema=ps,
                componente_codigo=comp.codigo,
                defaults={
                    "proyecto": ps.proyecto,
                    "cantidad_calculada": cantidad_decimal,
                    "categoria_producto": categoria,
                    "es_dependencia_automatica": False,
                },
            )

            # No auto-asignar producto: el usuario elige manualmente desde el despiece.
            # Solo capturar precio si ya tiene producto asignado previamente.
            linea.capturar_precio()

            resultados.append({
                "componente_codigo": comp.codigo,
                "nombre": comp.nombre,
                "cantidad": float(cantidad_decimal),
                "unidad": comp.unidad,
                "categoria": categoria.nombre if categoria else "",
                "pendiente": linea.pendiente_seleccion,
                "estado": linea.estado_tecnico,
            })

        logger.info(
            "[DespieceService][DB] PS %s → %d líneas procesadas.", ps.pk, len(resultados)
        )
        return resultados

    def _ejecutar_desde_registry(self, ps, CategoriaProducto, DespieceLinea) -> list[dict]:
        """Fallback: ejecuta el despiece usando system_defs Python registry."""
        from apps.ingenieria.system_defs.registry import get_subsistema_def

        sub_def = get_subsistema_def(ps.sistema.codigo, ps.subsistema.codigo)
        if not sub_def:
            logger.warning(
                "[DespieceService] Sin definición para %s/%s (PS %s). "
                "Define los componentes en DB o en system_defs/.",
                ps.sistema.codigo, ps.subsistema.codigo, ps.pk,
            )
            return []

        contexto = ps.get_contexto()
        logger.debug("[DespieceService][Registry] Contexto PS %s: %s", ps.pk, contexto)

        _cat_cache: dict[str, object] = {}

        def _get_categoria(slug: str):
            if slug not in _cat_cache:
                cat = CategoriaProducto.objects.filter(nombre__iexact=slug).first()
                if not cat:
                    logger.warning(
                        "[DespieceService] CategoriaProducto '%s' no encontrada (PS %s).",
                        slug, ps.pk,
                    )
                _cat_cache[slug] = cat
            return _cat_cache[slug]

        componentes_ordenados = sorted(sub_def.componentes, key=lambda c: c.orden)
        resultados = []

        for comp in componentes_ordenados:
            try:
                cantidad_float = float(comp.formula(contexto))
            except KeyError as exc:
                logger.error(
                    "[DespieceService] Variable %s no en contexto al evaluar '%s' (PS %s).",
                    exc, comp.codigo, ps.pk,
                )
                continue
            except Exception as exc:
                logger.error(
                    "[DespieceService] Error evaluando '%s' (PS %s): %s",
                    comp.codigo, ps.pk, exc,
                )
                continue

            if comp.variable_salida:
                contexto[comp.variable_salida] = cantidad_float

            cantidad_decimal = Decimal(str(cantidad_float)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )

            categoria = _get_categoria(comp.categoria_slug) if comp.categoria_slug else None

            linea, created = DespieceLinea.objects.update_or_create(
                proyecto_sistema=ps,
                componente_codigo=comp.codigo,
                defaults={
                    "proyecto": ps.proyecto,
                    "cantidad_calculada": cantidad_decimal,
                    "categoria_producto": categoria,
                    "es_dependencia_automatica": False,
                },
            )
            linea.capturar_precio()

            resultados.append({
                "componente_codigo": comp.codigo,
                "nombre": comp.nombre,
                "cantidad": float(cantidad_decimal),
                "unidad": comp.unidad,
                "categoria": comp.categoria_slug,
                "pendiente": linea.pendiente_seleccion,
                "estado": linea.estado_tecnico,
            })

        logger.info(
            "[DespieceService] PS %s → %d líneas procesadas (%s/%s).",
            ps.pk, len(resultados), ps.sistema.codigo, ps.subsistema.codigo,
        )
        return resultados

    def validar_productos_completos(self) -> list[str]:
        """
        Devuelve la lista de categorías que aún no tienen producto asignado.
        Lista vacía = todos los productos resueltos = listo para APU.

        Uso:
            pendientes = DespieceService(ps).validar_productos_completos()
            if pendientes:
                raise ValueError(f"Faltan productos: {pendientes}")
        """
        from apps.presupuestos.models import DespieceLinea

        pendientes = list(
            DespieceLinea.objects.filter(
                proyecto_sistema=self.ps,
                producto__isnull=True,
                categoria_producto__isnull=False,
            ).values_list("categoria_producto__nombre", flat=True)
        )

        if pendientes:
            logger.warning(
                "[DespieceService] PS %s — %d categorías sin producto: %s",
                self.ps.pk, len(pendientes), pendientes,
            )
        else:
            logger.debug(
                "[DespieceService] PS %s — todos los productos resueltos.", self.ps.pk
            )

        return pendientes

    def asignar_productos(self, productos_map: dict[str, int]) -> list[str]:
        """
        Asigna productos a las líneas pendientes de selección.

        productos_map: {categoria_slug: producto_pk}
        Devuelve lista de errores (vacía si todo OK).

        Flujo:
          1. Para cada línea pendiente de selección.
          2. Busca el producto_pk en productos_map usando el nombre de la categoría.
          3. Llama a linea.resolver_producto(producto) que valida la categoría.
          4. Si hay error, lo registra y continúa (no aborta el loop).
        """
        from apps.catalogos.models import Producto
        from apps.presupuestos.models import DespieceLinea
        from django.core.exceptions import ValidationError

        errores = []
        lineas_pendientes = DespieceLinea.objects.filter(
            proyecto_sistema=self.ps,
            producto__isnull=True,
            categoria_producto__isnull=False,
        ).select_related("categoria_producto")

        for linea in lineas_pendientes:
            slug = linea.categoria_producto.nombre
            producto_pk = productos_map.get(slug)
            if not producto_pk:
                errores.append(f"Sin producto para categoría '{slug}'.")
                continue
            try:
                producto = Producto.objects.get(pk=producto_pk, activo=True)
                linea.resolver_producto(producto)
                logger.debug(
                    "[DespieceService] Línea %s → producto '%s' asignado.",
                    linea.pk, producto.nombre,
                )
            except Producto.DoesNotExist:
                errores.append(f"Producto pk={producto_pk} no encontrado o inactivo.")
            except ValidationError as exc:
                errores.append(f"Producto inválido para '{slug}': {exc.message}")
            except Exception as exc:
                errores.append(f"Error asignando '{slug}': {exc}")

        return errores
