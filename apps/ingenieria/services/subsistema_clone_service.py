"""
apps/ingenieria/services/subsistema_clone_service.py
====================================================

Clonado de plantillas técnicas (Subsistema) hacia el Sistema que elija el
usuario.

Motivación
----------
Muchos subsistemas comparten materiales y fórmulas casi idénticos. Rehacer la
receta completa desde cero es costoso y propenso a error. Este servicio copia
un `Subsistema` con TODA su configuración dependiente y lo deja colgando del
`Sistema` destino que se indique.

Qué se copia
------------
    Subsistema                         (campos escalares + M2M de catálogos)
      ├── VariableSubsistema           variables_subsistema
      ├── SubconjuntoRecetaTecnica     subconjuntos_receta_tecnica
      ├── ComponenteSubsistema         componentes_subsistema   (remapea subconjunto)
      ├── VariableDependenciaSubsistema variable_dependencia_subsistema (remapea variables)
      ├── ProductoTecnicoAsociado      productos_tecnicos_asociados
      ├── ComponenteQuimico            componentes_quimicos
      ├── ReglaAPUSubsistema           reglas_apu_subsistema    (app presupuestos)
      └── SubsistemaItemAPU            subsistema_items_apu     (app presupuestos)

Qué NO se copia
---------------
    - DespieceMaestro / DespieceMaestroLinea: son cálculos históricos, no
      parte de la plantilla.
    - ProyectoSistema y su despiece: pertenecen a proyectos comerciales.
    - CapaConsumo: modelo deprecado (reemplazado por ProductoTecnicoAsociado).

Puntos delicados resueltos aquí
-------------------------------
    1. `Subsistema.codigo` es `unique=True` GLOBAL (además del
       `unique_together ['sistema', 'codigo']`). No basta con cambiar de
       sistema: hay que generar un código libre a nivel de toda la tabla.
    2. `VariableDependenciaSubsistema` referencia variables por PK, no por
       nombre. Se construye un mapa `pk_origen → pk_nuevo` y se remapea.
    3. `ComponenteSubsistema.subconjunto` es FK: mismo tratamiento con su
       propio mapa.
    4. `Subsistema.imagen_tecnica` se copia como referencia al mismo archivo
       (no se duplica el binario en disco). Editar la imagen del clon exige
       subir una nueva, que Django guardará con nombre propio.
"""

from __future__ import annotations

import re

from django.db import transaction

from apps.ingenieria.models import (
    Sistema,
    Subsistema,
    VariableSubsistema,
    SubconjuntoRecetaTecnica,
    ComponenteSubsistema,
    VariableDependenciaSubsistema,
    ProductoTecnicoAsociado,
    ComponenteQuimico,
)


class SubsistemaCloneError(Exception):
    """Error de negocio al clonar una plantilla. El mensaje es apto para UI."""


# ── Generación de código libre ───────────────────────────────────────────────

_SUFIJO_COPIA = re.compile(r"^(?P<base>.+?)[-_]COPIA(?:[-_](?P<n>\d+))?$", re.IGNORECASE)


def sugerir_codigo_clon(codigo_origen: str) -> str:
    """
    Propone un código libre derivado del original.

    "PG_PLUS"          → "PG_PLUS-COPIA"
    "PG_PLUS-COPIA"    → "PG_PLUS-COPIA-2"
    "PG_PLUS-COPIA-2"  → "PG_PLUS-COPIA-3"

    Respeta el `max_length=50` de `Subsistema.codigo` recortando la base
    cuando el sufijo no cabe.
    """
    codigo_origen = (codigo_origen or "SUB").strip()
    m = _SUFIJO_COPIA.match(codigo_origen)
    base = m.group("base") if m else codigo_origen

    ocupados = set(
        Subsistema.objects.values_list("codigo", flat=True)
    )

    n = 1
    while True:
        sufijo = "-COPIA" if n == 1 else f"-COPIA-{n}"
        margen = 50 - len(sufijo)
        candidato = f"{base[:margen]}{sufijo}"
        if candidato not in ocupados:
            return candidato
        n += 1


def sugerir_nombre_clon(nombre_origen: str) -> str:
    """Propone un nombre legible para el clon, respetando max_length=200."""
    nombre_origen = (nombre_origen or "Subsistema").strip()
    sufijo = " (copia)"
    return f"{nombre_origen[:200 - len(sufijo)]}{sufijo}"


# ── Clonado ──────────────────────────────────────────────────────────────────

# Campos escalares del Subsistema que se copian tal cual. Se excluyen
# explícitamente: pk, sistema, codigo, nombre (los define el usuario) y las
# marcas de tiempo (auto_now / auto_now_add).
_CAMPOS_COPIABLES = (
    "descripcion",
    "notas_tecnicas",
    "activo",
    "imagen_tecnica",
    "variable_referencia_apu",
    "unidad_apu",
    "tipo_producto",
    "resistencia_quimica",
    "temperatura_min",
    "temperatura_max",
    "interior_exterior",
    "consumo_min_g_m2",
    "consumo_max_g_m2",
)


@transaction.atomic
def clonar_subsistema(
    origen: Subsistema,
    sistema_destino: Sistema,
    codigo_nuevo: str = "",
    nombre_nuevo: str = "",
) -> Subsistema:
    """
    Clona `origen` dentro de `sistema_destino` y devuelve el nuevo Subsistema.

    Args:
        origen:           Subsistema plantilla a copiar.
        sistema_destino:  Sistema (la "categoría") donde queda el clon.
        codigo_nuevo:     Código del clon. Si viene vacío se autogenera.
        nombre_nuevo:     Nombre del clon. Si viene vacío se autogenera.

    Raises:
        SubsistemaCloneError: si el código ya existe o falta el sistema destino.
    """
    if sistema_destino is None:
        raise SubsistemaCloneError("Debe indicar el sistema destino de la copia.")

    codigo_nuevo = (codigo_nuevo or "").strip() or sugerir_codigo_clon(origen.codigo)
    nombre_nuevo = (nombre_nuevo or "").strip() or sugerir_nombre_clon(origen.nombre)

    # `codigo` es unique global, no solo dentro del sistema: validamos así.
    if Subsistema.objects.filter(codigo=codigo_nuevo).exists():
        raise SubsistemaCloneError(
            f"Ya existe un subsistema con el código «{codigo_nuevo}». "
            "Elija otro código para la copia."
        )

    # ── 1. Cabecera ──────────────────────────────────────────────────────────
    clon = Subsistema(
        sistema=sistema_destino,
        codigo=codigo_nuevo,
        nombre=nombre_nuevo,
    )
    for campo in _CAMPOS_COPIABLES:
        setattr(clon, campo, getattr(origen, campo))
    clon.save()

    # ── 2. M2M de catálogos de consumo ───────────────────────────────────────
    clon.funciones.set(origen.funciones.all())
    clon.problemas_resuelve.set(origen.problemas_resuelve.all())
    clon.superficies_compatibles.set(origen.superficies_compatibles.all())

    # ── 3. Variables de entrada (mapa pk_origen → pk_clon) ───────────────────
    mapa_variables: dict = {}
    for v in VariableSubsistema.objects.filter(subsistema=origen).order_by("orden", "pk"):
        nueva = VariableSubsistema.objects.create(
            subsistema=clon,
            variable=v.variable,
            label=v.label,
            unidad=v.unidad,
            valor_default=v.valor_default,
            tipo_entrada=v.tipo_entrada,
            opciones=list(v.opciones or []),
            participa_en_base_apu=v.participa_en_base_apu,
            orden=v.orden,
        )
        mapa_variables[v.pk] = nueva

    # ── 4. Subconjuntos de receta (mapa pk_origen → pk_clon) ─────────────────
    mapa_subconjuntos: dict = {}
    for s in SubconjuntoRecetaTecnica.objects.filter(subsistema=origen).order_by("orden", "pk"):
        nuevo = SubconjuntoRecetaTecnica.objects.create(
            subsistema=clon,
            nombre=s.nombre,
            descripcion=s.descripcion,
            orden=s.orden,
            activo=s.activo,
        )
        mapa_subconjuntos[s.pk] = nuevo

    # ── 5. Componentes (remapean su subconjunto) ─────────────────────────────
    for c in ComponenteSubsistema.objects.filter(subsistema=origen).order_by("orden", "pk"):
        ComponenteSubsistema.objects.create(
            subsistema=clon,
            subconjunto=mapa_subconjuntos.get(c.subconjunto_id),
            codigo=c.codigo,
            nombre=c.nombre,
            categoria_id=c.categoria_id,
            formula_texto=c.formula_texto,
            variable_salida=c.variable_salida,
            unidad=c.unidad,
            orden=c.orden,
            requiere_presentacion_producto=c.requiere_presentacion_producto,
            variable_presentacion_producto=c.variable_presentacion_producto,
            campo_presentacion_producto=c.campo_presentacion_producto,
            variable_referencia_apu=c.variable_referencia_apu,
            unidad_apu=c.unidad_apu,
        )

    # ── 6. Dependencias entre variables (remapean origen y destino) ──────────
    # Se omiten en silencio las reglas cuyas variables no se pudieron mapear
    # (datos inconsistentes en el origen); el resto se copia intacto.
    for d in VariableDependenciaSubsistema.objects.filter(subsistema=origen).order_by("orden", "pk"):
        var_origen = mapa_variables.get(d.variable_origen_id)
        var_destino = mapa_variables.get(d.variable_destino_id)
        if var_origen is None or var_destino is None:
            continue
        VariableDependenciaSubsistema.objects.create(
            subsistema=clon,
            variable_origen=var_origen,
            valor_origen=d.valor_origen,
            variable_destino=var_destino,
            valor_destino=d.valor_destino,
            activa=d.activa,
            orden=d.orden,
            notas=d.notas,
        )

    # ── 7. Productos técnicos asociados ──────────────────────────────────────
    for p in ProductoTecnicoAsociado.objects.filter(subsistema=origen).order_by("orden", "pk"):
        ProductoTecnicoAsociado.objects.create(
            subsistema=clon,
            nombre=p.nombre,
            descripcion=p.descripcion,
            estado_fisico=p.estado_fisico,
            consumo_min_g_m2=p.consumo_min_g_m2,
            consumo_max_g_m2=p.consumo_max_g_m2,
            unidad=p.unidad,
            orden=p.orden,
        )

    # ── 8. Componentes químicos ──────────────────────────────────────────────
    for q in ComponenteQuimico.objects.filter(subsistema=origen).order_by("orden", "pk"):
        ComponenteQuimico.objects.create(
            subsistema=clon,
            nombre=q.nombre,
            porcentaje=q.porcentaje,
            estado_fisico=q.estado_fisico,
            categoria_id=q.categoria_id,
            orden=q.orden,
        )

    # ── 9. Configuración APU (vive en la app presupuestos) ───────────────────
    # Import diferido: ingenieria no debe depender de presupuestos en tiempo
    # de import (evita ciclos en el arranque de Django).
    from apps.presupuestos.models import ReglaAPUSubsistema, SubsistemaItemAPU

    for r in ReglaAPUSubsistema.objects.filter(subsistema=origen).order_by("orden", "pk"):
        ReglaAPUSubsistema.objects.create(
            subsistema=clon,
            tipo_apu=r.tipo_apu,
            formula_costo_unitario=r.formula_costo_unitario,
            orden=r.orden,
        )

    for i in SubsistemaItemAPU.objects.filter(subsistema=origen).order_by("orden", "pk"):
        SubsistemaItemAPU.objects.create(
            subsistema=clon,
            item_catalogo_id=i.item_catalogo_id,
            tipo=i.tipo,
            cantidad=i.cantidad,
            orden=i.orden,
            activo=i.activo,
            rendimiento_override=i.rendimiento_override,
            observaciones=i.observaciones,
        )

    return clon


def resumen_clonado(origen: Subsistema) -> dict:
    """
    Cuenta qué se va a copiar. Se usa para el mensaje de confirmación en la UI
    y para el registro en LogSistema.
    """
    from apps.presupuestos.models import ReglaAPUSubsistema, SubsistemaItemAPU

    return {
        "variables":       VariableSubsistema.objects.filter(subsistema=origen).count(),
        "subconjuntos":    SubconjuntoRecetaTecnica.objects.filter(subsistema=origen).count(),
        "componentes":     ComponenteSubsistema.objects.filter(subsistema=origen).count(),
        "dependencias":    VariableDependenciaSubsistema.objects.filter(subsistema=origen).count(),
        "productos_tec":   ProductoTecnicoAsociado.objects.filter(subsistema=origen).count(),
        "comp_quimicos":   ComponenteQuimico.objects.filter(subsistema=origen).count(),
        "reglas_apu":      ReglaAPUSubsistema.objects.filter(subsistema=origen).count(),
        "items_apu":       SubsistemaItemAPU.objects.filter(subsistema=origen).count(),
    }
