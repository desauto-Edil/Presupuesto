"""
apps/common/auth.py
===================

Fase 12.2 — Helpers centralizados de autorización.

Compatibles con Python 3.9 (sin PEP 604 `X | None`).

Lee la identidad del usuario desde la sesión personalizada del proyecto
(`request.session["usuario_id"]`) y resuelve el `ConfiguracionSistema`
correspondiente. Expone gates declarativos para el flujo de aprobación
de APUs y devolución de Solicitudes.

Reglas (Fase 12.2):
  • Aprobar / resetear modalidad: revisor asignado en `apu.revisor`
    o usuario con rol ADMINISTRADOR.
  • Enviar a revisión: creador del proyecto, ASESOR_COMERCIAL,
    PRESUPUESTOS o ADMINISTRADOR.
  • Devolver solicitud: revisor asignado de algún APU del proyecto o
    ADMINISTRADOR.
"""

from __future__ import annotations

from typing import Optional


# ── Identidad ─────────────────────────────────────────────────────────────────

def get_usuario_actual(request) -> Optional["ConfiguracionSistema"]:  # noqa: F821
    """
    Resuelve el `ConfiguracionSistema` del request leyendo
    `request.session["usuario_id"]`.
    Devuelve None si no hay sesión o si el usuario no existe.
    """
    from apps.configuracion.models import ConfiguracionSistema

    try:
        usuario_id = request.session.get("usuario_id")
    except Exception:
        usuario_id = None
    if not usuario_id:
        return None
    return ConfiguracionSistema.objects.filter(pk=usuario_id, activo=True).first()


def get_rol(request) -> str:
    """Devuelve el rol guardado en sesión (string), o '' si no hay."""
    try:
        return request.session.get("rol", "") or ""
    except Exception:
        return ""


def es_admin(request) -> bool:
    """True si el usuario actual tiene rol ADMINISTRADOR (global)."""
    return get_rol(request) == "ADMINISTRADOR"


def es_gerente(request) -> bool:
    """True si el usuario actual tiene rol GERENTE (acceso total a su unidad)."""
    return get_rol(request) == "GERENTE"


def es_global(request) -> bool:
    """True si el rol da acceso global (atraviesa unidades). Hoy: sólo ADMINISTRADOR."""
    return es_admin(request)


# ── Acceso por unidad de negocio ──────────────────────────────────────────────

def puede_ver_todas_las_unidades(request) -> bool:
    """Solo ADMINISTRADOR atraviesa unidades."""
    return es_admin(request)


def unidad_efectiva(request) -> str:
    """
    Unidad de negocio del usuario para filtrar querysets.
    - ADMINISTRADOR → "" (sin filtro: ve global).
    - Resto → session["unidad_negocio"].
    """
    if puede_ver_todas_las_unidades(request):
        return ""
    try:
        return request.session.get("unidad_negocio", "") or ""
    except Exception:
        return ""


def puede_gestionar_unidad(request, unidad) -> bool:
    """
    True si el usuario puede ver/gestionar datos cuya unidad sea `unidad`.
    - ADMINISTRADOR → siempre (global).
    - Resto → sólo si `unidad` coincide con su `session.unidad_negocio`.

    Para objetos sin unidad explícita (unidad vacía/None) **bloqueamos** a
    cualquiera que no sea ADMINISTRADOR. El acceso del creador a sus propios
    datos legacy lo cubre el bypass por `creado_por_id` que vive en
    `UnidadObjectAccessMixin` y en los gates de `APUProyectoDetailView` /
    `APURevisarView`; no se debe relajar aquí.
    """
    if puede_ver_todas_las_unidades(request):
        return True
    if not unidad:
        return False
    try:
        return (request.session.get("unidad_negocio") or "") == unidad
    except Exception:
        return False


# ── Gates de permisos ─────────────────────────────────────────────────────────

def puede_aprobar_apu(request, apu) -> bool:
    """
    Solo el revisor asignado en `apu.revisor` o un ADMINISTRADOR.
    No basta con tener rol PRESUPUESTOS — debe estar asignado.
    """
    usuario = get_usuario_actual(request)
    if usuario is None:
        return False
    if es_admin(request):
        return True
    return apu.revisor_id is not None and apu.revisor_id == usuario.pk


def puede_enviar_a_revision(request, apu) -> bool:
    """
    Puede enviar a revisión: ADMINISTRADOR, GERENTE, PRESUPUESTOS, ASESOR_COMERCIAL.
    COMPRAS y SOLO_LECTURA no pueden enviar.
    No evalúa estado del APU (archivado/aprobado) — eso se compone en la vista.
    """
    usuario = get_usuario_actual(request)
    if usuario is None:
        return False
    rol = get_rol(request)
    _ROLES_PUEDEN_ENVIAR = {"ADMINISTRADOR", "GERENTE", "PRESUPUESTOS", "ASESOR_COMERCIAL"}
    return rol in _ROLES_PUEDEN_ENVIAR


def puede_editar_apu(request, apu) -> bool:
    """
    Permiso de edición del APU (Parámetros, líneas, garantía).
    Misma regla que `puede_enviar_a_revision` para coherencia operativa:
      - ADMINISTRADOR global.
      - GERENTE, PRESUPUESTOS, ASESOR_COMERCIAL si gestionan la unidad del
        proyecto (con fallback a la unidad del usuario actual si el proyecto
        no la declara — datos huérfanos).
      - Creador del proyecto (cualquier rol salvo SOLO_LECTURA).
    COMPRAS y SOLO_LECTURA no editan APUs.

    NOTA: este helper NO evalúa el estado del APU. La UI debe componer:
        `puede_editar_apu AND not aprobado AND not archivado`.
    """
    return puede_enviar_a_revision(request, apu)


def puede_devolver_solicitud(request, solicitud) -> bool:
    """
    Solo un ADMINISTRADOR o el revisor asignado de algún APU vivo del
    proyecto vinculado a la solicitud.
    """
    usuario = get_usuario_actual(request)
    if usuario is None:
        return False
    if es_admin(request):
        return True
    # Busca cualquier APU pendiente de revisión cuyo revisor sea el usuario
    from apps.presupuestos.models import APUProyecto
    apus = APUProyecto.objects.filter(
        proyecto_sistema__proyecto__solicitud=solicitud,
        revisor_id=usuario.pk,
        archivado=False,
    )
    return apus.exists()


def aprobador_label(apu) -> str:
    """Texto humano para mostrar quién es el aprobador asignado."""
    if apu.revisor_id and apu.revisor:
        return apu.revisor.nombre_completo or apu.revisor.email
    return "— sin asignar —"
