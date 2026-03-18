"""
apps/presupuestos/services/proyecto_service.py — Orquestador del flujo de proyecto.

ProyectoService coordina la creación de proyectos y las transiciones de estado,
delegando la lógica de cálculo a DespieceService, DependenciaService y APUService.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction

from .despiece_service import DespieceService
from .dependencia_service import DependenciaService
from .apu_service import APUService

logger = logging.getLogger(__name__)


class ProyectoService:
    """Orquesta la creación de proyectos y las transiciones de estado."""

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
            consecutivo = Proyecto.siguiente_consecutivo(),
            solicitud = solicitud,
            cliente = solicitud.cliente,
            creado_por = creado_por,
            tipo_proyecto = tipo_pry,
            nombre = solicitud.nombre,
            descripcion = solicitud.descripcion,
            area_total_m2 = area_total_m2,
            perimetro_ml = perimetro_ml,
            trm = trm,
            margen_comercial_pct = margen_comercial_pct,
            iva_pct = iva_pct,
            aiu_pct = aiu_pct,
            moneda = moneda,
            aplica_exencion_iva = aplica_exencion_iva,
            observaciones = observaciones,
            estado = "SOLICITUD",
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
        Crea ProyectoSistema, inyecta dependencias, ejecuta despiece paramétrico
        y avanza el proyecto a estado DESPIECE.
        """
        from apps.comercial.models import Proyecto
        from apps.ingenieria.models import Sistema, Subsistema
        from apps.presupuestos.models import ProyectoSistema

        proyecto = Proyecto.objects.get(pk=proyecto_id)
        sistema = Sistema.objects.get(pk=sistema_id)
        subsistema = Subsistema.objects.get(pk=subsistema_id)

        ps, _ = ProyectoSistema.objects.get_or_create(
            proyecto=proyecto,
            sistema=sistema,
            subsistema=subsistema,
            defaults={
                "total_powergip": Decimal(str(total_powergip)),
                "cuadrilla_personas": cuadrilla,
            },
        )
        ps.total_powergip = Decimal(str(total_powergip))
        ps.cuadrilla_personas = cuadrilla
        ps.save()

        dep_service = DependenciaService(ps)
        deps = dep_service.inyectar()

        desp_service = DespieceService(ps)
        lineas = desp_service.ejecutar()

        proyecto.avanzar_a_despiece()

        return {
            "proyecto_sistema_id": ps.id,
            "dependencias_inyectadas": deps,
            "lineas_despiece": lineas,
            "estado_proyecto": proyecto.estado,
        }

    @staticmethod
    @transaction.atomic
    def iniciar_apu(proyecto_sistema_id: int, **kwargs_apu):
        """
        Genera el APU completo para un ProyectoSistema.
        Solo se puede iniciar si el proyecto está en DESPIECE_VALIDADO o APU.
        """
        from apps.presupuestos.models import ProyectoSistema
        from apps.common.choices import EstadoProyecto

        ps = ProyectoSistema.objects.get(pk=proyecto_sistema_id)
        proyecto = ps.proyecto

        estados_validos = (
            EstadoProyecto.DESPIECE_VALIDADO,
            EstadoProyecto.APU,
            EstadoProyecto.APU_GENERADO,
        )
        if proyecto.estado not in estados_validos:
            raise ValueError(
                f"El proyecto está en estado '{proyecto.get_estado_display()}'. "
                "Valide el despiece antes de generar el APU."
            )

        service = APUService(ps)
        materiales = service.generar_materiales()
        mo_result = service.generar_mano_obra(
            hya_dia = kwargs_apu.get("hya_dia", 0),
            cuadrilla_dia = kwargs_apu.get("cuadrilla_dia", 0),
            dotacion_dia = kwargs_apu.get("dotacion_dia", 0),
            proteccion_dia = kwargs_apu.get("proteccion_dia", 0),
        )
        herramientas = service.generar_herramientas(kwargs_apu.get("herramientas_items", []))
        transporte = service.generar_transporte(kwargs_apu.get("costo_transporte", 0))
        admin = service.generar_administracion(kwargs_apu.get("costo_admin", 0))
        totales = service.finalizar()

        return {
            "materiales": materiales,
            "mano_obra": mo_result,
            "herramientas": herramientas,
            "transporte": transporte,
            "administracion": admin,
            "totales": totales,
        }
