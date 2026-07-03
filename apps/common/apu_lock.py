"""
apps/common/apu_lock.py — Bloqueo de solo lectura por APU aprobado.

Fuente ÚNICA de la regla: una vez un APU está aprobado (APUProyecto.fecha_aprobacion
no nula), toda la cadena asociada —solicitud, proyecto, despiece, líneas del APU y
selección de productos— queda en solo lectura. La aprobación se representa con la
propiedad `esta_aprobado` en APUProyecto y `tiene_apu_aprobado` en
ProyectoSistema / Proyecto / Solicitud.

Este módulo NO define nuevos estados; solo centraliza la comprobación para que las
vistas POST y los templates la reutilicen sin duplicar lógica.
"""

from django.contrib import messages
from django.shortcuts import redirect

MENSAJE_BLOQUEO = (
    "El APU ya fue aprobado: la información quedó en solo lectura y no puede modificarse. "
    "Si necesita editarla, primero debe restablecer la modalidad del APU."
)


def objeto_bloqueado_por_apu(obj) -> bool:
    """
    Devuelve True si `obj` está bloqueado porque un APU relacionado ya fue aprobado.

    Resuelve el tipo del objeto de dominio y delega en las propiedades canónicas de
    los modelos. Import diferido para evitar ciclos de importación entre apps.
    """
    if obj is None:
        return False

    from apps.presupuestos.models import APUProyecto, APULinea, ProyectoSistema, DespieceLinea
    from apps.comercial.models import Proyecto, Solicitud

    if isinstance(obj, APUProyecto):
        return obj.esta_aprobado
    if isinstance(obj, APULinea):
        return bool(obj.apu_id) and obj.apu.esta_aprobado
    if isinstance(obj, ProyectoSistema):
        return obj.tiene_apu_aprobado
    if isinstance(obj, DespieceLinea):
        if obj.proyecto_sistema_id:
            return obj.proyecto_sistema.tiene_apu_aprobado
        return bool(obj.proyecto_id) and obj.proyecto.tiene_apu_aprobado
    if isinstance(obj, Proyecto):
        return obj.tiene_apu_aprobado
    if isinstance(obj, Solicitud):
        return obj.tiene_apu_aprobado
    return False


def redirect_si_bloqueado(request, obj, destino, *destino_args, mensaje=None):
    """
    Guard para usar al inicio de un `post()` de escritura.

    Si `obj` está bloqueado por un APU aprobado, agrega un mensaje de error y
    devuelve un HttpResponseRedirect a `destino`. Si no está bloqueado, devuelve
    None (la vista continúa normalmente).

        blk = redirect_si_bloqueado(request, apu, "presupuestos:apu_detail", apu.pk)
        if blk:
            return blk
    """
    if objeto_bloqueado_por_apu(obj):
        messages.error(request, mensaje or MENSAJE_BLOQUEO)
        if destino_args:
            return redirect(destino, *destino_args)
        return redirect(destino)
    return None
