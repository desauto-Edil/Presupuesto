"""
apps/ingenieria/services/admin_eliminacion.py
==============================================

Servicio explícito para que el ADMINISTRADOR global elimine DespieceMaestro.

Regla principal:
    Si el despiece está incluido en uno o más APUs (vía `APUDespieceIncluido`),
    se **bloquea** la eliminación. La trazabilidad APU↔Despiece tiene valor
    operativo y no debe romperse silenciosamente, ni siquiera para el admin.
    El admin debe primero eliminar los APUs que lo incluyen.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction

from apps.common.eliminacion_errors import EliminacionBloqueadaError


logger = logging.getLogger(__name__)


def _registrar_log(usuario, accion: str, descripcion: str,
                   modelo_afectado: str, objeto_id: Optional[int]) -> None:
    try:
        from apps.comercial.models import LogSistema
        LogSistema.objects.create(
            configuracion=usuario,
            accion=accion[:50],
            descripcion=descripcion[:500],
            modelo_afectado=modelo_afectado[:50],
            objeto_id=objeto_id,
        )
    except Exception:
        logger.exception(
            "[admin_eliminacion] No se pudo registrar log de %s pk=%s",
            modelo_afectado, objeto_id,
        )


def eliminar_despiece_admin(despiece, usuario=None) -> dict:
    """
    Elimina definitivamente un DespieceMaestro.

    Si el despiece está incluido en uno o más APUs, levanta
    `EliminacionBloqueadaError` con un detalle legible para la UI.

    Devuelve un dict con resumen de impacto cuando la eliminación es viable.
    """
    from apps.ingenieria.models import DespieceMaestro, DespieceMaestroLinea
    from apps.presupuestos.models import APUDespieceIncluido

    apus_que_lo_incluyen = list(
        APUDespieceIncluido.objects
        .filter(despiece_maestro=despiece)
        .select_related("apu")
    )
    if apus_que_lo_incluyen:
        ref = []
        for r in apus_que_lo_incluyen[:5]:
            try:
                ref.append(f"#{r.apu.pk} «{r.apu.nombre}»")
            except Exception:
                ref.append(f"#{r.apu_id}")
        mas = "" if len(apus_que_lo_incluyen) <= 5 else (
            f" y {len(apus_que_lo_incluyen) - 5} más"
        )
        detalle = (
            f"Este despiece está incluido en {len(apus_que_lo_incluyen)} APU(s): "
            + ", ".join(ref) + mas + ". Elimine primero los APUs relacionados "
            "antes de eliminar el despiece."
        )
        raise EliminacionBloqueadaError(detalle)

    with transaction.atomic():
        resumen = {
            "despiece_pk": despiece.pk,
            "lineas": DespieceMaestroLinea.objects.filter(
                despiece=despiece).count(),
        }
        _registrar_log(
            usuario,
            "ELIMINAR_DESPIECE_ADMIN",
            (f"DespieceMaestro #{despiece.pk} — "
             f"lineas={resumen['lineas']}"),
            "DespieceMaestro",
            despiece.pk,
        )
        # DespieceMaestroLinea y ConsolidacionDespieceMaestro son CASCADE.
        despiece.delete()

    return resumen
