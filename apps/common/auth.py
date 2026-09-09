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

Segregación de funciones (quien envía no autoriza):
  • `APUProyecto.enviado_por` guarda quién remitió el APU a revisión.
  • Ese usuario NO puede aprobarlo, sin excepción por rol — tampoco el
    ADMINISTRADOR. La salida es reasignar el autorizador a otra persona
    (`puede_reasignar_revisor`), que es un acto distinto de aprobar.
  • A nivel de proyecto la regla se compone: para autorizar el presupuesto
    consolidado hay que poder autorizar todos sus APUs.
  • APUs anteriores a este control (`enviado_por` vacío) no se bloquean:
    no hay dato para afirmar quién envió.
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

def es_autoaprobacion(usuario, apu) -> bool:
    """
    True si `usuario` es quien remitió este APU a revisión.

    Segregación de funciones: quien envía no autoriza. Aplica a TODOS los
    roles, ADMINISTRADOR incluido — un administrador que envió su propio APU
    debe reasignar el revisor a otra persona para que lo autorice.

    Si `enviado_por` está vacío (APUs anteriores a este control) no se puede
    afirmar quién envió, así que no se bloquea: se conserva el comportamiento
    histórico en lugar de dejar trabajo viejo sin poder aprobarse.
    """
    if usuario is None or apu is None:
        return False
    return bool(apu.enviado_por_id) and apu.enviado_por_id == usuario.pk


def puede_aprobar_apu(request, apu) -> bool:
    """
    Autoriza el APU el revisor asignado en `apu.revisor` o un ADMINISTRADOR,
    salvo que sea quien lo envió (ver `es_autoaprobacion`).

    No basta con tener rol PRESUPUESTOS — debe estar asignado.
    """
    usuario = get_usuario_actual(request)
    if usuario is None:
        return False
    # La regla "quien envía no autoriza" se evalúa primero: gana sobre
    # cualquier rol, incluido ADMINISTRADOR.
    if es_autoaprobacion(usuario, apu):
        return False
    if es_admin(request):
        return True
    return apu.revisor_id is not None and apu.revisor_id == usuario.pk


def motivo_no_puede_aprobar_apu(request, apu) -> str:
    """
    Explica en lenguaje de negocio por qué el usuario no puede aprobar.
    Devuelve "" cuando sí puede. Se usa para el mensaje al usuario y el log.
    """
    usuario = get_usuario_actual(request)
    if usuario is None:
        return "Debe iniciar sesión para autorizar."
    if es_autoaprobacion(usuario, apu):
        return (
            "Usted remitió este presupuesto a revisión, por lo que no puede "
            "autorizarlo. Debe autorizarlo la persona a quien se lo envió, o "
            "reasignar el autorizador a otro usuario."
        )
    if es_admin(request):
        return ""
    if apu.revisor_id is None:
        return (
            "Este presupuesto no tiene autorizador asignado. Solicite que se "
            "asigne uno antes de autorizar."
        )
    if apu.revisor_id != usuario.pk:
        return (
            f"Solo «{aprobador_label(apu)}» puede autorizar este presupuesto. "
            "Si debe autorizarlo otra persona, reasigne el autorizador."
        )
    return ""


def puede_reasignar_revisor(request, apu) -> bool:
    """
    Puede reasignar el autorizador de un APU:
      - ADMINISTRADOR o GERENTE (supervisan el flujo),
      - el revisor actualmente asignado (delega en otro),
      - quien envió el APU (corrige a quién se lo mandó).

    Reasignar NO aprueba: solo cambia a quién le toca autorizar. Por eso sí se
    permite a quien envió — es la vía de salida cuando se equivocó de
    destinatario o el destinatario no está disponible.
    """
    usuario = get_usuario_actual(request)
    if usuario is None:
        return False
    if es_admin(request) or es_gerente(request):
        return True
    if apu.revisor_id and apu.revisor_id == usuario.pk:
        return True
    return bool(apu.enviado_por_id) and apu.enviado_por_id == usuario.pk


# ── Aprobación a nivel de proyecto ────────────────────────────────────────────

def _apus_revisables_del_proyecto(proyecto):
    """APUs vivos del proyecto que participan del flujo de aprobación."""
    from apps.presupuestos.models import APUProyecto
    return APUProyecto.objects.filter(
        proyecto_sistema__proyecto=proyecto,
        archivado=False,
        cantidad_base_apu__isnull=False,
    )


def puede_aprobar_proyecto(request, proyecto) -> bool:
    """
    Autoriza el presupuesto consolidado del proyecto.

    Regla: debe poder aprobar TODOS los APUs que lo componen. Basta con que
    uno solo sea suyo (lo envió él) para que no pueda aprobar el conjunto —
    si no, la segregación de funciones se saltaría aprobando en bloque.

    Sin APUs revisables no hay nada que autorizar → False.
    """
    usuario = get_usuario_actual(request)
    if usuario is None:
        return False
    apus = list(_apus_revisables_del_proyecto(proyecto))
    if not apus:
        return False
    return all(puede_aprobar_apu(request, apu) for apu in apus)


def motivo_no_puede_aprobar_proyecto(request, proyecto) -> str:
    """Primer motivo bloqueante encontrado; "" si puede aprobar."""
    usuario = get_usuario_actual(request)
    if usuario is None:
        return "Debe iniciar sesión para autorizar."
    apus = list(_apus_revisables_del_proyecto(proyecto))
    if not apus:
        return "El proyecto no tiene presupuestos guardados para autorizar."
    for apu in apus:
        motivo = motivo_no_puede_aprobar_apu(request, apu)
        if motivo:
            if len(apus) > 1:
                return f"APU «{apu.nombre}»: {motivo}"
            return motivo
    return ""


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
