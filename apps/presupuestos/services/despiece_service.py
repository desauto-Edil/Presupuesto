"""
apps/presupuestos/services/despiece_service.py — Motor de cálculo de despiece.

Lee la receta técnica del sistema desde apps/ingenieria/system_defs/registry.py
(NO desde ReglaCalculo en DB). El presupuestador solo ingresa variables de entrada;
las fórmulas y componentes están definidos en Python por el backend.

Flujo:
  1. Obtener SubsistemaDef del registro backend.
  2. Construir contexto: datos del proyecto + parametros_entrada del PS.
  3. Ejecutar componentes en orden ascendente.
  4. Para cada componente:
     a. Evaluar la fórmula con el contexto acumulado.
     b. Si tiene variable_salida, inyectarla al contexto (cascada).
     c. Buscar CategoriaProducto en DB por categoria_slug.
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

        Devuelve lista de dicts con el resumen de líneas procesadas.
        Las líneas existentes identificadas por componente_codigo se actualizan;
        las nuevas se crean. Los ajustes manuales (cantidad_ajustada) se conservan.
        """
        from apps.ingenieria.system_defs.registry import get_subsistema_def
        from apps.catalogos.models import CategoriaProducto
        from apps.presupuestos.models import DespieceLinea

        ps = self.ps

        if not ps.sistema_id or not ps.subsistema_id:
            logger.warning(
                "[DespieceService] PS %s sin sistema/subsistema definido.", ps.pk
            )
            return []

        sub_def = get_subsistema_def(ps.sistema.codigo, ps.subsistema.codigo)
        if not sub_def:
            logger.warning(
                "[DespieceService] Sin definición backend para %s/%s (PS %s). "
                "Verifica que el código del sistema/subsistema coincida con system_defs.",
                ps.sistema.codigo, ps.subsistema.codigo, ps.pk,
            )
            return []

        contexto = ps.get_contexto()
        logger.debug("[DespieceService] Contexto inicial PS %s: %s", ps.pk, contexto)

        # Cache de categorías para no consultar la DB en cada iteración
        _cat_cache: dict[str, object] = {}

        def _get_categoria(slug: str):
            if slug not in _cat_cache:
                cat = CategoriaProducto.objects.filter(nombre__iexact=slug).first()
                if not cat:
                    logger.warning(
                        "[DespieceService] CategoriaProducto '%s' no encontrada en DB (PS %s).",
                        slug, ps.pk,
                    )
                _cat_cache[slug] = cat
            return _cat_cache[slug]

        componentes_ordenados = sorted(sub_def.componentes, key=lambda c: c.orden)
        resultados = []

        for comp in componentes_ordenados:
            # 1. Evaluar fórmula
            try:
                cantidad_float = float(comp.formula(contexto))
            except KeyError as exc:
                logger.error(
                    "[DespieceService] Variable %s no encontrada en contexto "
                    "al evaluar '%s' (PS %s). Verifica los parametros_entrada.",
                    exc, comp.codigo, ps.pk,
                )
                continue
            except Exception as exc:
                logger.error(
                    "[DespieceService] Error evaluando componente '%s' (PS %s): %s",
                    comp.codigo, ps.pk, exc,
                )
                continue

            # 2. Cascada: inyectar resultado al contexto si tiene variable_salida
            if comp.variable_salida:
                contexto[comp.variable_salida] = cantidad_float
                logger.debug(
                    "[DespieceService] Contexto actualizado: %s = %.6f",
                    comp.variable_salida, cantidad_float,
                )

            cantidad_decimal = Decimal(str(cantidad_float)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )

            # 3. Buscar categoría en DB
            categoria = _get_categoria(comp.categoria_slug) if comp.categoria_slug else None

            # 4. Crear/actualizar DespieceLinea (clave: proyecto_sistema + componente_codigo)
            linea, created = DespieceLinea.objects.update_or_create(
                proyecto_sistema=ps,
                componente_codigo=comp.codigo,
                defaults={
                    "proyecto":               ps.proyecto,
                    "cantidad_calculada":     cantidad_decimal,
                    "categoria_producto":     categoria,
                    "es_dependencia_automatica": False,
                    # producto se conserva si ya fue resuelto (update_or_create no lo toca)
                },
            )

            # Si ya tenía producto resuelto, conservarlo (no sobreescribir con None)
            # update_or_create solo pisa los campos en defaults, así que producto queda intacto

            # 5. Capturar precio snapshot si el producto ya está asignado
            linea.capturar_precio()

            logger.debug(
                "[DespieceService] %s componente '%s' | cantidad=%.4f | cat='%s'",
                "Creada" if created else "Actualizada", comp.codigo,
                float(cantidad_decimal), comp.categoria_slug,
            )

            resultados.append({
                "componente_codigo": comp.codigo,
                "nombre":            comp.nombre,
                "cantidad":          float(cantidad_decimal),
                "unidad":            comp.unidad,
                "categoria":         comp.categoria_slug,
                "pendiente":         linea.pendiente_seleccion,
                "estado":            linea.estado_tecnico,
            })

        logger.info(
            "[DespieceService] PS %s → %d líneas procesadas (%s/%s).",
            ps.pk, len(resultados), ps.sistema.codigo, ps.subsistema.codigo,
        )
        return resultados
