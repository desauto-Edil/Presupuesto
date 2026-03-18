"""
apps/presupuestos/services/proyecto_service.py — Orquestador del flujo de proyecto.

ProyectoService coordina la creacion de proyectos y las transiciones de estado,
delegando la logica de calculo a DespieceService, DependenciaService y APUService.

CORRECCIONES vs version original:
  1. iniciar_despiece(): valida estado del proyecto antes de continuar
     (evita ejecutar despiece sobre proyectos ya en APU o COTIZADO).
  2. ps.save() usa update_fields para no sobrescribir campos no relacionados.
  3. Logging mejorado con contexto de IDs y estados.
  4. iniciar_apu(): logging mejorado, states check sin cambio de logica.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction

from .despiece_service    import DespieceService
from .dependencia_service import DependenciaService
from .apu_service         import APUService

logger = logging.getLogger(__name__)

# Estados desde los que se puede (re)ejecutar el despiece
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
            consecutivo         = Proyecto.siguiente_consecutivo(),
            solicitud           = solicitud,
            cliente             = solicitud.cliente,
            creado_por          = creado_por,
            tipo_proyecto       = tipo_pry,
            nombre              = solicitud.nombre,
            descripcion         = solicitud.descripcion,
            area_total_m2       = area_total_m2,
            perimetro_ml        = perimetro_ml,
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
    def iniciar_despiece(
        proyecto_id: int,
        sistema_id: int,
        subsistema_id: int,
        total_powergip: float,
        cuadrilla: int = 1,
    ):
        """
        Crea o actualiza ProyectoSistema, inyecta dependencias, ejecuta despiece
        parametrico y avanza el proyecto a estado DESPIECE.

        Permitido solo cuando el proyecto esta en: SOLICITUD, DESPIECE o
        EN_REVISION_COMPRAS (permite recalcular sin perder el avance).
        """
        from apps.comercial.models import Proyecto
        from apps.ingenieria.models import Sistema, Subsistema
        from apps.presupuestos.models import ProyectoSistema

        proyecto   = Proyecto.objects.get(pk=proyecto_id)
        sistema    = Sistema.objects.get(pk=sistema_id)
        subsistema = Subsistema.objects.get(pk=subsistema_id)

        # BUG CORREGIDO: validacion de estado antes de cualquier operacion
        if proyecto.estado not in _ESTADOS_DESPIECE_PERMITIDOS:
            raise ValueError(
                f"No se puede iniciar despiece: el proyecto '{proyecto.consecutivo}' "
                f"esta en estado '{proyecto.get_estado_display()}'. "
                f"Estado requerido: {sorted(_ESTADOS_DESPIECE_PERMITIDOS)}."
            )

        ps, created = ProyectoSistema.objects.get_or_create(
            proyecto   = proyecto,
            sistema    = sistema,
            subsistema = subsistema,
            defaults   = {
                "total_powergip":    Decimal(str(total_powergip)),
                "cuadrilla_personas": cuadrilla,
            },
        )

        if not created:
            # BUG CORREGIDO: update_fields evita pisar campos no relacionados
            ps.total_powergip    = Decimal(str(total_powergip))
            ps.cuadrilla_personas = cuadrilla
            ps.save(update_fields=["total_powergip", "cuadrilla_personas", "updated_at"])

        logger.info(
            "[ProyectoService] PS %s (%s) — total_powergip=%.4f, cuadrilla=%d.",
            ps.pk, "nuevo" if created else "actualizado", float(total_powergip), cuadrilla,
        )

        dep_service  = DependenciaService(ps)
        deps         = dep_service.inyectar()

        desp_service = DespieceService(ps)
        lineas       = desp_service.ejecutar()

        proyecto.avanzar_a_despiece()

        logger.info(
            "[ProyectoService] Proyecto %s ahora en estado '%s'. "
            "%d dependencias | %d lineas despiece.",
            proyecto.consecutivo, proyecto.estado, len(deps), len(lineas),
        )

        return {
            "proyecto_sistema_id":    ps.pk,
            "dependencias_inyectadas": deps,
            "lineas_despiece":         lineas,
            "estado_proyecto":         proyecto.estado,
        }

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
