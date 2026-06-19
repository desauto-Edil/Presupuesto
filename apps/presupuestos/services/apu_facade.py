"""
apps/presupuestos/services/apu_facade.py
========================================

Facade del dominio APU. **Punto de entrada único** previsto para que las
vistas no construyan `APUService` directamente.

ESTADO: **semilla (Fase 2 — Lote E)**.
    - Las vistas **no** la adoptan todavía.
    - Cada método es un wrapper delgado sobre `APUService`.
    - Cero cambio funcional respecto al uso directo del service.
    - NO incluye todavía "Armar mi APU" (eso es una fase posterior).

Plan de migración (fase posterior):
    1. Sustituir progresivamente en las vistas:
         APUService.generar(proyecto_sistema)
       por:
         APUFacade.generar_desde_despiece(proyecto_sistema)
    2. Cuando todas las vistas usen la facade, los services internos pueden
       refactorizarse sin tocar capas superiores.
"""

from __future__ import annotations

from typing import Dict, List

from apps.common.patterns import Facade


class APUFacade(Facade):
    """API estable para generación y finalización de APUs."""

    # ── Generación desde despiece ────────────────────────────────────────

    @staticmethod
    def generar_desde_despiece(proyecto_sistema):
        """Genera (o recupera) el APU asociado a un ProyectoSistema a partir
        de su despiece.

        Wrapper sobre `APUService.generar(proyecto_sistema)`.
        """
        from apps.presupuestos.services.apu_service import APUService
        return APUService.generar(proyecto_sistema)

    @staticmethod
    def for_apu(apu):
        """Devuelve un `APUService` posicionado sobre un APU existente.

        Útil cuando una vista necesita orquestar varias operaciones sobre el
        mismo APU sin reinstanciar el service.
        """
        from apps.presupuestos.services.apu_service import APUService
        return APUService.for_apu(apu)

    # ── Cálculo de materiales y secciones ────────────────────────────────

    @staticmethod
    def generar_materiales(proyecto_sistema) -> List[dict]:
        """Wrapper sobre `APUService.generar_materiales`."""
        from apps.presupuestos.services.apu_service import APUService
        return APUService(proyecto_sistema).generar_materiales()

    @staticmethod
    def generar_mano_obra_desde_catalogo(proyecto_sistema, items_data: List[Dict]) -> List[dict]:
        from apps.presupuestos.services.apu_service import APUService
        return APUService(proyecto_sistema).generar_mano_obra_desde_catalogo(items_data)

    @staticmethod
    def generar_herramientas_desde_catalogo(proyecto_sistema, items_data: List[Dict]) -> List[dict]:
        from apps.presupuestos.services.apu_service import APUService
        return APUService(proyecto_sistema).generar_herramientas_desde_catalogo(items_data)

    @staticmethod
    def generar_transporte_desde_catalogo(proyecto_sistema, items_data: List[Dict]) -> List[dict]:
        from apps.presupuestos.services.apu_service import APUService
        return APUService(proyecto_sistema).generar_transporte_desde_catalogo(items_data)

    @staticmethod
    def generar_administracion_desde_catalogo(proyecto_sistema, items_data: List[Dict]) -> List[dict]:
        from apps.presupuestos.services.apu_service import APUService
        return APUService(proyecto_sistema).generar_administracion_desde_catalogo(items_data)

    # ── Finalización ─────────────────────────────────────────────────────

    @staticmethod
    def finalizar(proyecto_sistema) -> dict:
        """Wrapper sobre `APUService.finalizar`."""
        from apps.presupuestos.services.apu_service import APUService
        return APUService(proyecto_sistema).finalizar()

    # ── Fase 11.4 — Generación multi-despiece desde selección manual ─────

    @staticmethod
    def generar_desde_seleccion(despiece_origen, dm_ids_seleccionados):
        """
        Fase 11.4 — orquestador del flujo de generación con selección manual.

        Pasos (todo en `transaction.atomic`):
          1. `DespieceSelectionStrategy.validar_seleccion` filtra y valida.
          2. `get_or_create` del ProyectoSistema raíz (subsistema del origen).
          3. `get_or_create` del APUProyecto vinculado al PS raíz; si no
             existía, lo crea con `APUService.generar` para arrancar la
             configuración base de no-materiales del subsistema raíz.
          4. `APUMultiDespieceBuilder.build()` reconstruye MATERIALES
             usando solo los despieces seleccionados (raíz + secundarios).
          5. Devuelve `(apu, resumen, errores)`.
        """
        from django.db import transaction

        from apps.presupuestos.models import ProyectoSistema, APUProyecto
        from apps.presupuestos.services.apu_service import APUService
        from apps.presupuestos.services.despiece_selection import (
            DespieceSelectionStrategy,
        )
        from apps.presupuestos.services.apu_multi_builder import (
            APUMultiDespieceBuilder,
        )

        validacion = DespieceSelectionStrategy.validar_seleccion(
            despiece_origen, dm_ids_seleccionados
        )
        if not validacion["ok"]:
            return None, None, validacion["errores"]

        dms = validacion["dms"]
        with transaction.atomic():
            ps_raiz, _ = ProyectoSistema.objects.get_or_create(
                proyecto=despiece_origen.proyecto,
                sistema=despiece_origen.subsistema.sistema,
                subsistema=despiece_origen.subsistema,
            )

            if despiece_origen.variables_entrada:
                ps_raiz.parametros_entrada = {
                    **(ps_raiz.parametros_entrada or {}),
                    **despiece_origen.variables_entrada,
                }
                ps_raiz.save(update_fields=["parametros_entrada"])

            apu_existia = APUProyecto.objects.filter(proyecto_sistema=ps_raiz).exists()
            if not apu_existia:
                apu = APUService.generar(ps_raiz)
            else:
                apu = APUProyecto.objects.get(proyecto_sistema=ps_raiz)

            builder = APUMultiDespieceBuilder(
                apu=apu,
                despieces_seleccionados=dms,
                despiece_origen=despiece_origen,
            )
            resumen = builder.build()

        return apu, {"apu_existia": apu_existia, **resumen}, []

    # ── Reservado para fases futuras ─────────────────────────────────────
    # `recalcular(apu_id)`, `calcular_modalidades_aiu(apu_id)`,
    # `enviar_a_revision(apu_id, usuario_id)`, `aprobar(apu_id, usuario_id)`
    # quedarán expuestas aquí cuando se extraigan de las vistas / signals.
