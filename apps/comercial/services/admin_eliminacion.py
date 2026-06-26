"""
apps/comercial/services/admin_eliminacion.py
=============================================

Servicios explícitos para que el ADMINISTRADOR global elimine Solicitudes y
Proyectos. Cada servicio delega en `eliminar_apu_admin` (presupuestos) para
los APUs y cotizaciones asociados.

Reglas:
    - Sin uso de `_meta.related_objects`.
    - Solo se borra lo declarado.
    - Los catálogos (Cliente, Contacto, TipoProyecto, Sistema, Subsistema,
      TipoGarantia) NO se tocan.
    - `transaction.atomic` en todos los servicios.
    - La autorización (rol ADMINISTRADOR) la valida la vista llamadora.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction


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


def _calcular_resumen_proyecto(proyecto) -> dict:
    from apps.presupuestos.models import (
        APUProyecto, ProyectoSistema, CotizacionAPU,
    )
    from apps.ingenieria.models import DespieceMaestro

    apus_qs = APUProyecto.objects.filter(
        proyecto_sistema__proyecto_id=proyecto.pk
    ) | APUProyecto.objects.filter(proyecto_id=proyecto.pk)
    apus_qs = apus_qs.distinct()

    return {
        "proyecto_pk": proyecto.pk,
        "proyecto_consecutivo": proyecto.consecutivo,
        "proyecto_sistemas": ProyectoSistema.objects.filter(
            proyecto=proyecto).count(),
        "despieces_maestros": DespieceMaestro.objects.filter(
            proyecto=proyecto).count(),
        "apus": apus_qs.count(),
        "cotizaciones": CotizacionAPU.objects.filter(
            apu__in=apus_qs).count(),
    }


def _calcular_resumen_solicitud(solicitud) -> dict:
    resumen = {
        "solicitud_pk": solicitud.pk,
        "solicitud_consecutivo": solicitud.consecutivo,
        "proyectos": solicitud.proyectos.count(),
        "archivos": solicitud.archivos.count(),
    }
    return resumen


def eliminar_proyecto_admin(proyecto, usuario=None) -> dict:
    """
    Elimina definitivamente un Proyecto.

    Orden:
        1. Resumen y log.
        2. Por cada APU asociado (vía proyecto_sistema o proyecto): invocar
           `eliminar_apu_admin` (gestiona cotizaciones y consolidados).
        3. Borrar DespieceMaestro del proyecto que ya no estén incluidos en
           ningún APU (los APUs ya fueron eliminados en el paso 2).
        4. `proyecto.delete()` — Django CASCADE a ProyectoSistema y a
           DespieceLinea (legacy).

    NO toca: Cliente, TipoProyecto, configuraciones de catálogo.
    """
    from apps.presupuestos.models import APUProyecto
    from apps.presupuestos.services.admin_eliminacion import eliminar_apu_admin
    from apps.ingenieria.models import DespieceMaestro, DespieceMaestroLinea

    with transaction.atomic():
        resumen = _calcular_resumen_proyecto(proyecto)
        _registrar_log(
            usuario,
            "ELIMINAR_PROYECTO_ADMIN",
            (f"Proyecto {proyecto.consecutivo} — "
             f"apus={resumen['apus']} cotiz={resumen['cotizaciones']} "
             f"despieces={resumen['despieces_maestros']}"),
            "Proyecto",
            proyecto.pk,
        )

        # 2. Eliminar APUs del proyecto (via proyecto_sistema.proyecto o
        #    proyecto directo).
        apus = list(
            (APUProyecto.objects.filter(proyecto_sistema__proyecto_id=proyecto.pk)
             | APUProyecto.objects.filter(proyecto_id=proyecto.pk))
            .distinct()
        )
        for apu in apus:
            eliminar_apu_admin(apu, usuario=usuario)

        # 3. DespieceMaestro asociados al proyecto. Como ya eliminamos los
        #    APUs (paso 2), no debe quedar APUDespieceIncluido apuntando a
        #    estos despieces. Si por alguna razón quedara una relación
        #    huérfana, no la borramos: el delete fallará con ProtectedError y
        #    se reportará vía mensaje (defensa explícita).
        for dm in DespieceMaestro.objects.filter(proyecto=proyecto):
            # Confirmar que no quedan relaciones APUDespieceIncluido vivas.
            from apps.presupuestos.models import APUDespieceIncluido
            if APUDespieceIncluido.objects.filter(despiece_maestro=dm).exists():
                # En lugar de borrar la relación silenciosamente, dejamos el
                # despiece huérfano (proyecto=NULL vía SET_NULL al borrar el
                # proyecto). Esto preserva la trazabilidad.
                dm.proyecto = None
                dm.save(update_fields=["proyecto"])
                continue
            # Sin trazabilidad APU. DespieceMaestroLinea es CASCADE.
            dm.delete()

        # 4. Borrar el proyecto. Django CASCADE a ProyectoSistema (cuyos
        #    APUProyecto ya fueron borrados arriba) y a DespieceLinea legacy.
        proyecto.delete()

    return resumen


def eliminar_solicitud_admin(solicitud, usuario=None) -> dict:
    """
    Elimina definitivamente una Solicitud.

    Orden:
        1. Resumen y log.
        2. Por cada proyecto: invocar `eliminar_proyecto_admin`.
        3. `solicitud.delete()` — CASCADE a SolicitudArchivo y a
           ProyectoSistema (denormalizado). CotizacionAPU.solicitud queda
           SET_NULL automáticamente (las cotizaciones reales ya se
           eliminaron en los APUs del paso 2).

    NO toca: Cliente, Contacto, ConfiguracionSistema (catálogos/usuarios).
    """
    with transaction.atomic():
        resumen = _calcular_resumen_solicitud(solicitud)
        _registrar_log(
            usuario,
            "ELIMINAR_SOLICITUD_ADMIN",
            (f"Solicitud {solicitud.consecutivo} — "
             f"proyectos={resumen['proyectos']} "
             f"archivos={resumen['archivos']}"),
            "Solicitud",
            solicitud.pk,
        )
        # 2. Eliminar proyectos vía servicio dedicado.
        for proyecto in list(solicitud.proyectos.all()):
            eliminar_proyecto_admin(proyecto, usuario=usuario)
        # 3. Borrar solicitud.
        solicitud.delete()

    return resumen
