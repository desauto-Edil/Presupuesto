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
