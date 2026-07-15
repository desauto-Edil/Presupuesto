"""
apps/presupuestos/services/apu_consolidacion_facade.py — Fase 11.5

Facade público para la consolidación opcional de APUs.

La consolidación es **opcional y siempre por confirmación explícita** del
usuario. Esta fachada centraliza:

  • validación de la selección (mismo proyecto, ≥2 APUs, individuales);
  • generación del preview (sin persistir);
  • creación del APU consolidado (transaccional).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from django.db import transaction

from apps.presupuestos.models import APUProyecto
from .apu_consolidado_builder import APUConsolidadoBuilder
from .apu_merge_strategies import construir_resumen_preview, ResumenPreview


@dataclass
class ValidacionConsolidacion:
    ok: bool
    apus: List[APUProyecto]
    errores: List[str]


class APUConsolidacionFacade:
    """Punto de entrada de Fase 11.5 — Consolidación opcional de APUs."""

    # ------------------------------------------------------------------
    @staticmethod
    def validar(proyecto, apu_ids: Iterable[int]) -> ValidacionConsolidacion:
        ids = [int(x) for x in apu_ids if str(x).strip().isdigit()]
        errores: List[str] = []
        apus: List[APUProyecto] = []

        if len(ids) < 2:
            errores.append("Selecciona al menos dos APUs para consolidar.")
            return ValidacionConsolidacion(False, [], errores)

        qs = (
            APUProyecto.objects
            .filter(pk__in=ids)
            .select_related("proyecto_sistema__subsistema__sistema",
                            "proyecto_sistema__proyecto",
                            "proyecto")
        )
        apus_dict = {a.pk: a for a in qs}
        for pk in ids:
            apu = apus_dict.get(pk)
            if apu is None:
                errores.append(f"APU #{pk} no existe.")
                continue
            if apu.tipo_apu != APUProyecto.TipoAPUConsolidacion.INDIVIDUAL:
                errores.append(
                    f"APU #{apu.pk} no es individual y no se puede consolidar."
                )
                continue
            apu_proyecto = apu.get_proyecto()
            if apu_proyecto is None or apu_proyecto.pk != proyecto.pk:
                errores.append(
                    f"APU #{apu.pk} no pertenece al proyecto seleccionado."
                )
                continue
            apus.append(apu)

        if not errores and len(apus) < 2:
            errores.append("Se requieren al menos dos APUs válidos del mismo proyecto.")

        # Orden estable por pk
        apus.sort(key=lambda a: ids.index(a.pk))
        return ValidacionConsolidacion(ok=not errores, apus=apus, errores=errores)

    # ------------------------------------------------------------------
    @staticmethod
    def preview(proyecto, apu_ids: Iterable[int]) -> tuple[ValidacionConsolidacion, Optional[ResumenPreview]]:
        v = APUConsolidacionFacade.validar(proyecto, apu_ids)
        if not v.ok:
            return v, None
        return v, construir_resumen_preview(v.apus)

    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def consolidar(proyecto, apu_ids: Iterable[int], nombre: str = "") -> tuple[ValidacionConsolidacion, Optional[APUProyecto]]:
        v = APUConsolidacionFacade.validar(proyecto, apu_ids)
        if not v.ok:
            return v, None
        builder = APUConsolidadoBuilder(proyecto=proyecto, apus_origen=v.apus, nombre=nombre)
        apu_consolidado = builder.build()
        return v, apu_consolidado
