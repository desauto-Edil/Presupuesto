"""
apps/presupuestos/services/apu_consolidado_builder.py — Fase 11.5

`APUConsolidadoBuilder` orquesta la construcción de un APU consolidado a
partir de varios APUs individuales seleccionados por el usuario.

Reglas:
  • Materiales: unión acumulativa (MaterialesUnionStrategy).
  • No-materiales: deduplicación por equivalencia (NoMaterialesDedupStrategy).
  • Garantía Red Shield NO se suma — el consolidado nace sin garantía.
  • AIU y aprobación NO se copian — el consolidado nace SIN modalidad ni
    aprobador y pasa su propio flujo.
  • Los APUDespieceIncluido de los APUs origen se replican apuntando al
    consolidado para reutilizar las plantillas de agrupación.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.db import transaction

from apps.presupuestos.models import (
    APUProyecto, APULinea, APUDespieceIncluido, APUConsolidadoOrigen,
)

from .apu_merge_strategies import (
    MaterialesUnionStrategy, NoMaterialesDedupStrategy, LineaPlantilla,
)


class APUConsolidadoBuilder:
    """
    Builder transaccional del APU consolidado.

    Uso típico::

        builder = APUConsolidadoBuilder(proyecto, apus_origen, nombre="…")
        apu_consolidado = builder.build()
    """

    def __init__(self, proyecto, apus_origen: Iterable, nombre: str = ""):
        self.proyecto = proyecto
        self.apus_origen = list(apus_origen)
        self.nombre = nombre or self._nombre_default()
        self.apu_consolidado = None

    # ------------------------------------------------------------------
    def _nombre_default(self) -> str:
        codigo = getattr(self.proyecto, "codigo", None) or f"P{self.proyecto.pk}"
        return f"APU Consolidado — {codigo}"

    # ------------------------------------------------------------------
    @transaction.atomic
    def build(self) -> APUProyecto:
        self._build_cabecera()
        self._registrar_origenes()
        self._replicar_despieces_incluidos()
        self._materiales()
        self._no_materiales()
        self.apu_consolidado.recalcular()
        return self.apu_consolidado

    # ------------------------------------------------------------------
    def _build_cabecera(self) -> None:
        # Tomamos como semilla los parámetros base del primer APU origen,
        # pero sin copiar aprobación, modalidad, garantía ni snapshots AIU.
        semilla = self.apus_origen[0]
        self.apu_consolidado = APUProyecto.objects.create(
            nombre=self.nombre,
            descripcion=(
                f"APU consolidado generado el "
                f"{semilla.updated_at:%Y-%m-%d %H:%M} a partir de "
                f"{len(self.apus_origen)} APUs individuales."
            ),
            tipo_apu=APUProyecto.TipoAPUConsolidacion.CONSOLIDADO,
            proyecto=self.proyecto,
            proyecto_sistema=None,
            # Parámetros de cálculo (semilla, configurables después):
            factor_venta_pct=semilla.factor_venta_pct,
            iva_pct=semilla.iva_pct,
            aplica_iva=semilla.aplica_iva,
            aiu_contratista_pct=semilla.aiu_contratista_pct,
            margen_ganancia_pct=semilla.margen_ganancia_pct,
            dias_duracion=semilla.dias_duracion,
            aiu_proyecto_admin_pct=semilla.aiu_proyecto_admin_pct,
            aiu_proyecto_imprevistos_pct=semilla.aiu_proyecto_imprevistos_pct,
            aiu_proyecto_utilidad_pct=semilla.aiu_proyecto_utilidad_pct,
            # AIU final, modalidad y aprobación: vacíos en el consolidado.
            aiu_final_admin_pct=None,
            aiu_final_imprevistos_pct=None,
            aiu_final_utilidad_pct=None,
            modalidad_aiu_seleccionada=None,
            aprobado_por=None,
            fecha_aprobacion=None,
            revisor=None,
            fecha_envio_revision=None,
        )

    # ------------------------------------------------------------------
    def _registrar_origenes(self) -> None:
        for idx, apu in enumerate(self.apus_origen):
            APUConsolidadoOrigen.objects.create(
                apu_consolidado=self.apu_consolidado,
                apu_origen=apu,
                orden=idx,
                incluido_en_pdf_cliente=True,
            )

    # ------------------------------------------------------------------
    def _replicar_despieces_incluidos(self) -> None:
        """Copia los APUDespieceIncluido de los orígenes hacia el consolidado.

        Si dos orígenes traen el mismo DespieceMaestro, se respeta el unique
        (apu, despiece_maestro) — la primera ocurrencia gana.
        """
        vistos: set = set()
        orden = 0
        for apu in self.apus_origen:
            for inc in apu.despieces_incluidos.filter(activo=True).order_by("orden", "id"):
                if inc.despiece_maestro_id in vistos:
                    continue
                vistos.add(inc.despiece_maestro_id)
                APUDespieceIncluido.objects.create(
                    apu=self.apu_consolidado,
                    despiece_maestro=inc.despiece_maestro,
                    sistema_nombre_snapshot=inc.sistema_nombre_snapshot,
                    subsistema_nombre_snapshot=inc.subsistema_nombre_snapshot,
                    orden=orden,
                    activo=True,
                )
                orden += 1

    # ------------------------------------------------------------------
    def _materiales(self) -> None:
        plantillas = MaterialesUnionStrategy().merge(self.apus_origen)
        self._persistir_lineas(plantillas)

    def _no_materiales(self) -> None:
        plantillas = NoMaterialesDedupStrategy().merge(self.apus_origen)
        self._persistir_lineas(plantillas)

    # ------------------------------------------------------------------
    def _persistir_lineas(self, plantillas: list[LineaPlantilla]) -> None:
        for p in plantillas:
            APULinea.objects.create(
                apu=self.apu_consolidado,
                tipo=p.tipo,
                descripcion=p.descripcion,
                rendimiento=p.rendimiento,
                unidad=p.unidad,
                precio_referencia=p.precio_referencia,
                iva_aplicado=p.iva_aplicado,
                vida_util_dias=p.vida_util_dias,
                costo_por_dia=p.costo_por_dia,
                salario_base=p.salario_base,
                prestaciones=p.prestaciones,
                costo_unitario=p.costo_unitario,
                costo_total=p.costo_total,
                valor_unitario=p.valor_unitario,
                valor_total=p.valor_total,
                tienda_referencia=p.tienda_referencia,
                editable=p.editable,
                item_catalogo_id=p.item_catalogo_id,
                despiece_linea_id=p.despiece_linea_id,
                despiece_maestro_id=p.despiece_maestro_id,
                sistema_nombre_snapshot=p.sistema_nombre_snapshot,
                subsistema_nombre_snapshot=p.subsistema_nombre_snapshot,
                apu_origen_id=p.apu_origen_id,
            )
