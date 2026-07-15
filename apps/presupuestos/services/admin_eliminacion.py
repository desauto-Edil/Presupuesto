"""
apps/presupuestos/services/admin_eliminacion.py
================================================

Servicio explícito para eliminar APUs como ADMINISTRADOR global.

Reglas:
    - Listado explícito de relaciones a borrar.
    - Sin uso de `_meta.related_objects` para tomar decisiones genéricas.
    - Cotizaciones / snapshots se borran junto con el APU (decisión aprobada).
    - Si el APU es origen de un consolidado, también se elimina el consolidado.
    - Todo dentro de `transaction.atomic`.
    - Resumen de impacto registrado en LogSistema.

La autorización (rol ADMINISTRADOR) se valida en la vista llamadora, no aquí.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction


logger = logging.getLogger(__name__)


def _calcular_resumen_apu(apu) -> dict:
    """
    Cuenta lo que se eliminará al borrar este APU. Sin efectos secundarios.
    """
    from apps.presupuestos.models import (
        APULinea, APUDespieceIncluido, APUConsolidadoOrigen, CotizacionAPU,
    )
    resumen = {
        "apu_pk": apu.pk,
        "apu_nombre": apu.nombre,
        "lineas": APULinea.objects.filter(apu=apu).count(),
        "despieces_incluidos": APUDespieceIncluido.objects.filter(apu=apu).count(),
        "cotizaciones": CotizacionAPU.objects.filter(apu=apu).count(),
        "consolidaciones_como_destino": APUConsolidadoOrigen.objects.filter(
            apu_consolidado=apu).count(),
        "consolidaciones_como_origen": APUConsolidadoOrigen.objects.filter(
            apu_origen=apu).count(),
        "consolidados_dependientes": list(
            APUConsolidadoOrigen.objects
            .filter(apu_origen=apu)
            .values_list("apu_consolidado_id", flat=True)
            .distinct()
        ),
    }
    return resumen


def _registrar_log(usuario, accion: str, descripcion: str,
                   modelo_afectado: str, objeto_id: Optional[int]) -> None:
    """
    Log opcional — no interrumpe el borrado si falla.
    """
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
        logger.exception("[admin_eliminacion] No se pudo registrar log de %s pk=%s",
                         modelo_afectado, objeto_id)


def eliminar_apu_admin(apu, usuario=None) -> dict:
    """
    Elimina definitivamente un APU.

    Orden:
        1. Resumen y log.
        2. Eliminar APUs consolidados que tienen este APU como origen
           (llamada recursiva al mismo servicio).
        3. Borrar CotizacionAPU del APU (snapshot).
        4. Borrar APUConsolidadoOrigen donde el APU es consolidado.
        5. Borrar APUDespieceIncluido del APU (CASCADE igual, explícito).
        6. apu.delete() — CASCADE a APULinea.

    Devuelve el `resumen` calculado al inicio. La vista lo puede mostrar al
    usuario para auditoría.
    """
    from apps.presupuestos.models import (
        APUProyecto, APUDespieceIncluido, APUConsolidadoOrigen, CotizacionAPU,
    )

    with transaction.atomic():
        resumen = _calcular_resumen_apu(apu)
        _registrar_log(
            usuario,
            "ELIMINAR_APU_ADMIN",
            (f"APU #{apu.pk} '{apu.nombre}' — "
             f"lineas={resumen['lineas']} "
             f"cotizaciones={resumen['cotizaciones']} "
             f"consolidados_origen={resumen['consolidaciones_como_origen']}"),
            "APUProyecto",
            apu.pk,
        )

        # 2. APUs consolidados que tienen este APU como origen.
        consolidados_pks = list(set(resumen["consolidados_dependientes"]))
        for cons_pk in consolidados_pks:
            try:
                cons = APUProyecto.objects.get(pk=cons_pk)
            except APUProyecto.DoesNotExist:
                continue
            # Recursión: el consolidado se elimina con la misma política.
            eliminar_apu_admin(cons, usuario=usuario)

        # Tras eliminar consolidados dependientes, ya no quedan relaciones
        # APUConsolidadoOrigen(apu_origen=apu). Defensa: limpiar las que pudieran
        # quedar (no debería).
        APUConsolidadoOrigen.objects.filter(apu_origen=apu).delete()

        # 3. Cotizaciones (snapshot) — borrado explícito, decisión aprobada.
        CotizacionAPU.objects.filter(apu=apu).delete()

        # 4. APUConsolidadoOrigen donde el APU es el consolidado (CASCADE,
        #    explícito para legibilidad).
        APUConsolidadoOrigen.objects.filter(apu_consolidado=apu).delete()

        # 5. APUDespieceIncluido del APU (CASCADE igual, explícito).
        APUDespieceIncluido.objects.filter(apu=apu).delete()

        # 6. Borrado del APU. Django propaga CASCADE a APULinea.
        apu.delete()

    return resumen
