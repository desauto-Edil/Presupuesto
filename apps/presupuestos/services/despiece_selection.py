"""
apps/presupuestos/services/despiece_selection.py
================================================

Fase 11.4 — Selección manual de despieces para generación de APU.

Patrón: Strategy. Encapsula las reglas de negocio para decidir qué
DespieceMaestro son candidatos a incluirse en un APU y cómo validar la
selección final del usuario.

Reglas (decisión Fase 11.4A aprobada):
  • mismo proyecto que el despiece origen;
  • estado = GUARDADO;
  • con líneas (consolidadas o individuales) válidas;
  • pueden ser de distintos sistemas/subsistemas;
  • marcar (no excluir) los que ya estén incluidos en otro APU aprobado,
    para informar al usuario sin bloquear su decisión.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class CandidatoDespiece:
    """Vista ligera de un DespieceMaestro candidato para la UI de selección."""
    despiece_maestro: object  # apps.ingenieria.models.DespieceMaestro
    sistema_nombre: str
    subsistema_nombre: str
    estado_label: str
    fecha: object
    num_lineas: int
    incluido_en_apu_aprobado: bool
    es_origen: bool


class DespieceSelectionStrategy:
    """
    Estrategia de selección de despieces para construir un APU multi-despiece.
    """

    # ── Listado de candidatos ─────────────────────────────────────────────

    @staticmethod
    def listar_candidatos(despiece_origen) -> List[CandidatoDespiece]:
        """
        Devuelve los DespieceMaestro elegibles del mismo proyecto que
        `despiece_origen`. El despiece origen siempre aparece primero y se
        marca con `es_origen=True` para que la UI lo bloquee.
        """
        from apps.ingenieria.models import DespieceMaestro

        if not despiece_origen or not despiece_origen.proyecto_id:
            return []

        qs = (
            DespieceMaestro.objects
            .filter(
                proyecto=despiece_origen.proyecto,
                estado=DespieceMaestro.GUARDADO,
            )
            .select_related("subsistema", "subsistema__sistema")
            .prefetch_related("lineas", "consolidaciones")
            .order_by(
                # El origen primero, luego por subsistema y fecha
                "subsistema__sistema__nombre",
                "subsistema__nombre",
                "-updated_at",
            )
        )

        # APUs aprobados con sus DM incluidos (para marcar "ya incluido").
        from apps.presupuestos.models import APUDespieceIncluido
        apus_aprobados_dms = set(
            APUDespieceIncluido.objects
            .filter(
                activo=True,
                apu__modalidad_aiu_seleccionada__in=["1", "2"],
                despiece_maestro__proyecto=despiece_origen.proyecto,
            )
            .values_list("despiece_maestro_id", flat=True)
        )

        candidatos: List[CandidatoDespiece] = []
        for dm in qs:
            if not DespieceSelectionStrategy._tiene_lineas_validas(dm):
                # Salta DMs sin líneas válidas excepto si es el origen.
                if dm.pk != despiece_origen.pk:
                    continue
            num_lineas = (
                dm.lineas.exclude(producto__isnull=True).count()
                + dm.consolidaciones.exclude(producto__isnull=True).count()
            )
            candidatos.append(CandidatoDespiece(
                despiece_maestro=dm,
                sistema_nombre=(dm.subsistema.sistema.nombre if dm.subsistema_id else ""),
                subsistema_nombre=(dm.subsistema.nombre if dm.subsistema_id else ""),
                estado_label=dm.get_estado_display() if hasattr(dm, "get_estado_display") else str(dm.estado),
                fecha=getattr(dm, "updated_at", None) or getattr(dm, "created_at", None),
                num_lineas=num_lineas,
                incluido_en_apu_aprobado=(dm.pk in apus_aprobados_dms),
                es_origen=(dm.pk == despiece_origen.pk),
            ))

        # Origen primero
        candidatos.sort(key=lambda c: (0 if c.es_origen else 1, c.sistema_nombre, c.subsistema_nombre))
        return candidatos

    # ── Validación de selección ───────────────────────────────────────────

    @staticmethod
    def validar_seleccion(despiece_origen, dm_ids: Iterable[int]) -> dict:
        """
        Valida y materializa la lista de DespieceMaestro seleccionados.

        Reglas:
          • el origen DEBE estar incluido (se fuerza si el form lo omite);
          • todos deben pertenecer al mismo proyecto que el origen;
          • todos deben estar GUARDADO;
          • todos deben tener líneas válidas.

        Devuelve dict:
            {"ok": bool, "dms": [DespieceMaestro,...], "errores": [str,...]}
        """
        from apps.ingenieria.models import DespieceMaestro

        errores: List[str] = []
        ids = {int(x) for x in dm_ids if str(x).isdigit()}
        ids.add(despiece_origen.pk)  # origen obligatorio

        dms = list(
            DespieceMaestro.objects
            .filter(pk__in=ids)
            .select_related("subsistema", "subsistema__sistema", "proyecto")
            .prefetch_related("lineas", "consolidaciones")
        )

        encontrados = {dm.pk for dm in dms}
        faltantes = ids - encontrados
        if faltantes:
            errores.append(
                f"Algunos despieces seleccionados no existen ({sorted(faltantes)})."
            )

        validos = []
        for dm in dms:
            if dm.proyecto_id != despiece_origen.proyecto_id:
                errores.append(f"Despiece #{dm.pk} no pertenece al proyecto del origen.")
                continue
            if dm.estado != DespieceMaestro.GUARDADO:
                errores.append(f"Despiece #{dm.pk} no está en estado GUARDADO.")
                continue
            if not DespieceSelectionStrategy._tiene_lineas_validas(dm):
                if dm.pk == despiece_origen.pk:
                    errores.append(
                        "El despiece origen no tiene líneas válidas; no se puede generar APU."
                    )
                else:
                    # Despieces secundarios sin líneas se ignoran silenciosamente.
                    continue
            validos.append(dm)

        # Ordenar: origen primero, luego por sistema/subsistema.
        validos.sort(key=lambda dm: (
            0 if dm.pk == despiece_origen.pk else 1,
            (dm.subsistema.sistema.nombre if dm.subsistema_id else ""),
            (dm.subsistema.nombre if dm.subsistema_id else ""),
        ))

        return {
            "ok": not errores,
            "dms": validos,
            "errores": errores,
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _tiene_lineas_validas(despiece_maestro) -> bool:
        if despiece_maestro.lineas.filter(producto__isnull=False).exists():
            return True
        if despiece_maestro.consolidaciones.filter(producto__isnull=False).exists():
            return True
        return False
