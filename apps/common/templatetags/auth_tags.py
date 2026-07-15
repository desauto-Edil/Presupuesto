"""
auth_tags — Filtros de plantilla para gates de autorización (Fase 12.3).
Permiten condicionar UI por APU sin recalcular en la vista.
"""

from django import template
from apps.common import auth as auth_helpers

register = template.Library()


@register.simple_tag(takes_context=True)
def puede_aprobar_apu(context, apu):
    request = context.get("request")
    if request is None or apu is None:
        return False
    return auth_helpers.puede_aprobar_apu(request, apu)


@register.simple_tag(takes_context=True)
def puede_enviar_a_revision(context, apu):
    request = context.get("request")
    if request is None or apu is None:
        return False
    return auth_helpers.puede_enviar_a_revision(request, apu)


@register.simple_tag(takes_context=True)
def es_admin_actual(context):
    """True si el usuario en sesión tiene rol ADMINISTRADOR (global)."""
    request = context.get("request")
    if request is None:
        return False
    return auth_helpers.es_admin(request)


@register.simple_tag(takes_context=True)
def puede_editar_apu(context, apu):
    """Permiso real de edición del APU para condicionar UI."""
    request = context.get("request")
    if request is None or apu is None:
        return False
    return auth_helpers.puede_editar_apu(request, apu)


@register.simple_tag
def enviado_revision_info(apu):
    """
    Retorna {'usuario': ConfiguracionSistema|None, 'fecha': datetime|None}
    inferido del último LogSistema(accion='ENVIAR_REVISION') para el APU.
    Si no hay log, retorna {'usuario': None, 'fecha': None}.
    """
    if apu is None or not getattr(apu, "pk", None):
        return {"usuario": None, "fecha": None}
    try:
        from apps.comercial.models import LogSistema
        log = (
            LogSistema.objects
            .filter(modelo_afectado="APUProyecto",
                    objeto_id=apu.pk,
                    accion="ENVIAR_REVISION")
            .select_related("configuracion")
            .order_by("-created_at")
            .first()
        )
        if log:
            return {"usuario": log.configuracion, "fecha": log.created_at}
    except Exception:
        pass
    return {"usuario": None, "fecha": None}


@register.simple_tag
def apu_esta_aprobado(apu):
    """Un APU se considera aprobado si tiene modalidad seleccionada o fecha de aprobación."""
    if apu is None:
        return False
    return bool(
        (apu.modalidad_aiu_seleccionada or "").strip()
        or apu.fecha_aprobacion
        or apu.aprobado_por_id
    )
