"""
apps/comercial/services/proyecto_service.py
===========================================

Capa de servicio del Proyecto (lado comercial). Esta es la **capa nueva**
que se introduce en Fase 2 — Lote D. NO mueve lógica fuera de
`apps.comercial.models.Proyecto.save()` todavía: solo expone una API
estable a las vistas para que cuando una fase posterior decida sacar el
versionamiento del modelo, las vistas no requieran cambios.

Estado de cada función:
    - ``crear_proyecto_desde_solicitud``  : envuelve el constructor normal y
      delega el versionamiento al ``save()`` actual del modelo.
    - ``generar_consecutivo``             : delega en ``Proyecto.siguiente_consecutivo()``.
    - ``marcar_versiones_anteriores``     : helper expuesto para reuso futuro;
      hoy el ``save()`` ya hace este update inline, así que esta función NO
      se llama desde el flujo normal.
    - ``crear_version_desde_proyecto``    : delega en
      ``apps.presupuestos.services.proyecto_service.clonar_proyecto_como_version``.

Plan de migración (fase posterior, cuando haya tests de regresión):
    1. Mover el bloque de auto-versionamiento de ``Proyecto.save()`` aquí,
       dentro de ``crear_proyecto_desde_solicitud``.
    2. Convertir ``Proyecto.save()`` en un ``save()`` clásico sin efectos.
    3. Actualizar las vistas para construir el proyecto vía service en lugar
       de instanciar ``Proyecto(...)`` directamente.

Reglas para esta fase:
    - Cero cambio funcional.
    - Cero migraciones.
    - Cero cambio en ``Proyecto.save()``.
    - Las vistas pueden adoptar este service progresivamente; mientras no lo
      hagan, el comportamiento sigue siendo idéntico.
"""

from __future__ import annotations

from typing import Optional, Any, Dict

from django.db import transaction


# ── API pública ──────────────────────────────────────────────────────────────

def generar_consecutivo() -> str:
    """Genera el próximo consecutivo ``PRY-YYYY-NNNN``.

    Delega en ``Proyecto.siguiente_consecutivo()`` para no duplicar la regla.
    """
    from apps.comercial.models import Proyecto
    return Proyecto.siguiente_consecutivo()


@transaction.atomic
def crear_proyecto_desde_solicitud(
    *,
    solicitud,
    creado_por,
    nombre: str,
    tipo_proyecto=None,
    descripcion: str = "",
    extra: Optional[Dict[str, Any]] = None,
):
    """Crea un Proyecto vinculado a una Solicitud.

    Por ahora el versionamiento (``version``, ``es_version_actual``) y la
    asignación de consecutivo siguen ocurriendo en ``Proyecto.save()``.
    Esta función es el **punto de entrada estable** que las vistas pueden
    adoptar hoy y que mañana absorberá la lógica de save() sin cambiar la
    firma.

    Parámetros mínimos: ``solicitud``, ``creado_por``, ``nombre``.
    El resto se acepta vía ``extra`` para no acoplarse al shape exacto del
    modelo (que aún tiene varios campos opcionales).
    """
    from apps.comercial.models import Proyecto

    proyecto = Proyecto(
        solicitud=solicitud,
        cliente=getattr(solicitud, "cliente", None),
        creado_por=creado_por,
        nombre=nombre,
        descripcion=descripcion,
        tipo_proyecto=tipo_proyecto,
    )
    if extra:
        for k, v in extra.items():
            setattr(proyecto, k, v)
    proyecto.save()
    return proyecto


@transaction.atomic
def crear_version_desde_proyecto(proyecto_base, usuario):
    """Clona un Proyecto como nueva versión dentro de la misma Solicitud.

    Delega en ``apps.presupuestos.services.proyecto_service.clonar_proyecto_como_version``
    (la rutina ya existente que copia campos editables y registra LogSistema).
    """
    from apps.presupuestos.services.proyecto_service import clonar_proyecto_como_version
    return clonar_proyecto_como_version(proyecto_base, usuario)


def marcar_versiones_anteriores(solicitud_id, excluir_pk: Optional[int] = None) -> int:
    """Marca como `es_version_actual=False` todas las versiones de un proyecto
    bajo una solicitud, opcionalmente excluyendo un PK.

    Helper expuesto para reuso futuro. Hoy el ``Proyecto.save()`` ya ejecuta
    este update inline al crear una versión nueva, así que esta función NO
    se invoca desde el flujo activo. Retorna el número de filas afectadas.
    """
    from apps.comercial.models import Proyecto
    qs = Proyecto.objects.filter(solicitud_id=solicitud_id)
    if excluir_pk is not None:
        qs = qs.exclude(pk=excluir_pk)
    return qs.update(es_version_actual=False)


# ── Transiciones de estado (capa futura) ─────────────────────────────────────
# Avanzar de estado y aprobar APU siguen viviendo en métodos del modelo
# (``Proyecto.avanzar_a_despiece``, etc.). Cuando se extraigan, se exponen aquí
# como ``avanzar_estado(proyecto, nuevo_estado)``.
