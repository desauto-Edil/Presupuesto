"""
apps/presupuestos/services/proyecto_service.py — Orquestador del flujo de proyecto.


"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction

from apps.comercial.models import Proyecto
from apps.presupuestos.models.despiece import ProyectoSistema

from .despiece_service import DespieceService
from .apu_service      import APUService

logger = logging.getLogger(__name__)


def clonar_proyecto_como_version(proyecto_base, usuario):
    """
    Clona un Proyecto existente creando una nueva versión dentro de la misma Solicitud.

    · Copia todos los campos editables del proyecto base.
    · La nueva versión queda vinculada a la misma solicitud y hereda el cliente.
    · El auto-versionado (version, es_version_actual) lo gestiona Proyecto.save().
    · No copia APU aprobado ni despieces (cada versión comienza limpia).
    · Registra un LogSistema de la acción.

    Retorna el nuevo Proyecto creado.
    """
    from apps.comercial.models import Proyecto, LogSistema

    nuevo = Proyecto(
        solicitud=proyecto_base.solicitud,
        cliente=proyecto_base.cliente,
        creado_por=usuario,
        tipo_proyecto=proyecto_base.tipo_proyecto,
        nombre=proyecto_base.nombre,
        descripcion=proyecto_base.descripcion,
        dias_duracion=proyecto_base.dias_duracion,
        num_personas=proyecto_base.num_personas,
        trm=proyecto_base.trm,
        margen_comercial_pct=proyecto_base.margen_comercial_pct,
        iva_pct=proyecto_base.iva_pct,
        aiu_pct=proyecto_base.aiu_pct,
        moneda=proyecto_base.moneda,
        aplica_exencion_iva=proyecto_base.aplica_exencion_iva,
        observaciones=proyecto_base.observaciones,
        # estado siempre arranca como SOLICITUD para la nueva versión
    )
    # version y es_version_actual los asigna Proyecto.save()
    nuevo.save()

    try:
        unidad = proyecto_base.solicitud.creado_por.unidad_negocio if (
            proyecto_base.solicitud and proyecto_base.solicitud.creado_por
        ) else ""
        LogSistema.objects.create(
            configuracion=usuario,
            unidad_negocio=unidad,
            accion="CLONAR_PROYECTO",
            descripcion=(
                f"Proyecto {nuevo.consecutivo} v{nuevo.version} creado como clon de "
                f"{proyecto_base.consecutivo} v{proyecto_base.version}"
            ),
            modelo_afectado="Proyecto",
            objeto_id=nuevo.pk,
        )
    except Exception:
        pass

    logger.info(
        "[ProyectoService] Clon: %s v%s → %s v%s.",
        proyecto_base.consecutivo, proyecto_base.version,
        nuevo.consecutivo, nuevo.version,
    )
    return nuevo


_ESTADOS_DESPIECE_PERMITIDOS = frozenset({
    "SOLICITUD",
    "DESPIECE",
    "EN_REVISION_COMPRAS",
})


class ProyectoService:
    """Orquesta la creacion de proyectos y las transiciones de estado."""

    @staticmethod
    @transaction.atomic

    def crear_desde_solicitud(
        solicitud_id: int,
        tipo_proyecto_id: int,
        creado_por,
        area_total_m2: Optional[float] = None,
        perimetro_ml: Optional[float] = None,
        trm: float = 4200,
        margen_comercial_pct: float = 20,
        iva_pct: float = 19,
        aiu_pct: float = 0,
        moneda: str = "COP",
        aplica_exencion_iva: bool = False,
        observaciones: Optional[str] = None,
    ):
        from apps.comercial.models import Solicitud, Proyecto, TipoProyecto

        solicitud = Solicitud.objects.select_related("cliente").get(pk=solicitud_id)
        tipo_pry  = TipoProyecto.objects.get(pk=tipo_proyecto_id)

        proyecto = Proyecto.objects.create(
            consecutivo= Proyecto.siguiente_consecutivo(),
            solicitud= solicitud,
            cliente= solicitud.cliente,
            creado_por= creado_por,
            tipo_proyecto= tipo_pry,
            nombre= solicitud.nombre,
            descripcion= solicitud.descripcion,
            area_total_m2= area_total_m2,
            perimetro_ml= perimetro_ml,
            trm                 = trm,
            margen_comercial_pct= margen_comercial_pct,
            iva_pct             = iva_pct,
            aiu_pct             = aiu_pct,
            moneda              = moneda,
            aplica_exencion_iva = aplica_exencion_iva,
            observaciones       = observaciones,
            estado              = "SOLICITUD",
        )
        logger.info(
            "[ProyectoService] Proyecto %s (%s) creado desde solicitud %s.",
            proyecto.pk, proyecto.consecutivo, solicitud_id,
        )
        return proyecto

    @staticmethod
    @transaction.atomic
    def iniciar_despiece(proyecto_id, sistema_id, subsistema_id, parametros: dict):
        proyecto = Proyecto.objects.select_related("solicitud").get(pk=proyecto_id)

        ps, _ = ProyectoSistema.objects.update_or_create(
            proyecto=proyecto,
            sistema_id=sistema_id,
            defaults={
                "solicitud":         proyecto.solicitud,
                "subsistema_id":     subsistema_id,
                "parametros_entrada": parametros,
            }
        )
        # Si el PS ya existía, asegurar que se actualicen subsistema y parámetros
        if ps.subsistema_id != subsistema_id or ps.parametros_entrada != parametros:
            ps.subsistema_id = subsistema_id
            ps.parametros_entrada = parametros
            ps.save(update_fields=["subsistema_id", "parametros_entrada"])

        DespieceService(ps).ejecutar()
        proyecto.avanzar_a_despiece()
        return ps

    @staticmethod
    @transaction.atomic
    def calcular_powergrip(
        proyecto_id: int,
        subsistema_id: int,
        parametros: dict,
        productos_map: dict,
    ):
        """
        Orquesta el flujo completo PowerGrip en un solo paso transaccional:
          1. Obtiene o crea el ProyectoSistema con el subsistema seleccionado.
          2. Ejecuta el cálculo de despiece (DespieceService).
          3. Asigna los productos a las líneas generadas.
          4. Valida que todos los productos estén resueltos.
          5. Avanza estado del proyecto a DESPIECE.

        productos_map: {categoria_slug: producto_pk}
            Ej: {"PowerGrip": 5, "Fijaciones": 12, "Accesorios": 3, ...}

        Raises:
            ValueError — si faltan productos o el cálculo falla.
        """
        from apps.ingenieria.models import Sistema

        proyecto = Proyecto.objects.select_related("solicitud").get(pk=proyecto_id)
        sistema  = Sistema.objects.get(codigo="POWERGRIP")

        # Validar que productos_map esté completo ANTES de calcular
        if not productos_map:
            raise ValueError(
                "Debe seleccionar todos los productos antes de calcular el despiece."
            )

        ps, _ = ProyectoSistema.objects.update_or_create(
            proyecto=proyecto,
            sistema=sistema,
            defaults={
                "solicitud":         proyecto.solicitud,
                "subsistema_id":     subsistema_id,
                "parametros_entrada": parametros,
            }
        )
        # Actualizar si ya existía con otro subsistema
        if str(ps.subsistema_id) != str(subsistema_id) or ps.parametros_entrada != parametros:
            ps.subsistema_id = subsistema_id
            ps.parametros_entrada = parametros
            ps.save(update_fields=["subsistema_id", "parametros_entrada"])

        svc = DespieceService(ps)

        # Paso 1: calcular cantidades
        lineas_resultado = svc.ejecutar()
        if not lineas_resultado:
            raise ValueError(
                "El cálculo de despiece no produjo líneas. "
                "Verifica que el sistema/subsistema esté correctamente configurado."
            )

        # Paso 2: asignar productos a las líneas pendientes
        errores = svc.asignar_productos(productos_map)
        if errores:
            raise ValueError(f"Errores al asignar productos: {'; '.join(errores)}")

        # Paso 3: validar que todo quedó resuelto
        pendientes = svc.validar_productos_completos()
        if pendientes:
            raise ValueError(
                f"Faltan productos para las categorías: {', '.join(pendientes)}. "
                "Seleccione un producto por cada categoría antes de calcular."
            )

        proyecto.avanzar_a_despiece()
        logger.info(
            "[ProyectoService] PowerGrip PS %s calculado OK — %d líneas | proyecto=%s.",
            ps.pk, len(lineas_resultado), proyecto.consecutivo,
        )
        return ps
    

    @staticmethod
    @transaction.atomic
    def iniciar_apu(proyecto_sistema_id: int, **kwargs_apu):
        """
        Genera el APU completo para un ProyectoSistema.
        Solo se puede iniciar si el proyecto esta en DESPIECE_VALIDADO, APU
        o APU_GENERADO (permite regenerar).
        """
        from apps.presupuestos.models import ProyectoSistema
        from apps.common.choices import EstadoProyecto

        ps      = ProyectoSistema.objects.select_related("proyecto").get(pk=proyecto_sistema_id)
        proyecto = ps.proyecto

        estados_validos = (
            EstadoProyecto.DESPIECE_VALIDADO,
            EstadoProyecto.APU,
            EstadoProyecto.APU_GENERADO,
        )
        if proyecto.estado not in estados_validos:
            raise ValueError(
                f"Proyecto '{proyecto.consecutivo}' en estado "
                f"'{proyecto.get_estado_display()}'. "
                "Valide el despiece antes de generar el APU."
            )

        logger.info(
            "[ProyectoService] Iniciando APU para PS %s (proyecto=%s, estado=%s).",
            ps.pk, proyecto.consecutivo, proyecto.estado,
        )

        service      = APUService(ps)
        materiales   = service.generar_materiales()
        mo_result    = service.generar_mano_obra(
            hya_dia        = kwargs_apu.get("hya_dia", 0),
            cuadrilla_dia  = kwargs_apu.get("cuadrilla_dia", 0),
            dotacion_dia   = kwargs_apu.get("dotacion_dia", 0),
            proteccion_dia = kwargs_apu.get("proteccion_dia", 0),
        )
        herramientas = service.generar_herramientas(kwargs_apu.get("herramientas_items", []))
        transporte   = service.generar_transporte(kwargs_apu.get("costo_transporte", 0))
        admin        = service.generar_administracion(kwargs_apu.get("costo_admin", 0))
        totales      = service.finalizar()

        logger.info(
            "[ProyectoService] APU PS %s — costo=%.2f | venta=%.2f.",
            ps.pk,
            totales.get("total_costo", 0),
            totales.get("total_valor_venta", 0),
        )

        return {
            "materiales":    materiales,
            "mano_obra":     mo_result,
            "herramientas":  herramientas,
            "transporte":    transporte,
            "administracion": admin,
            "totales":       totales,
        }
