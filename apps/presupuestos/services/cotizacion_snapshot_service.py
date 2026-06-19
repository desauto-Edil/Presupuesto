"""
apps/presupuestos/services/cotizacion_snapshot_service.py — Fase 12.

Construye, persiste y recupera snapshots inmutables de cotización aprobada.

Reglas:
  - `crear_snapshot(apu)` se invoca desde APUAprobarModalidadView después de
    guardar modalidad + AIU finales + estados de Proyecto/Solicitud.
  - Cada llamada crea una nueva versión. La versión anterior (si existía como
    APROBADA) se marca REEMPLAZADA. NUNCA se borra histórico.
  - El reset de modalidad y la devolución de solicitud NO tocan los snapshots.
  - `obtener_snapshot_vigente(apu)` devuelve el último APROBADA o None.
  - `construir_contexto_pdf(snapshot)` rehidrata un dict con la misma forma
    que `get_resumen_cotizacion()` para que las plantillas WeasyPrint puedan
    reutilizarse tal cual.
"""

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.common.choices import TipoAPU
from apps.presupuestos.models import CotizacionAPU


class CotizacionSnapshotService:
    """Construye y administra snapshots inmutables de CotizacionAPU."""

    # ------------------------------------------------------------------ #
    # API pública                                                         #
    # ------------------------------------------------------------------ #

    @classmethod
    @transaction.atomic
    def crear_snapshot(cls, apu) -> CotizacionAPU:
        """
        Crea una nueva versión de cotización aprobada para el APU dado.

        - Marca cualquier versión previa con estado=APROBADA como REEMPLAZADA.
        - Calcula `version = max_version_existente + 1`.
        - Congela todos los campos desde `apu.get_resumen_cotizacion()` y
          desde las líneas vivas del APU.
        - Persiste detalle completo en `data_snapshot` JSON.
        """
        # Rollover de la vigente anterior.
        (
            CotizacionAPU.objects
            .filter(apu=apu, estado=CotizacionAPU.Estado.APROBADA)
            .update(estado=CotizacionAPU.Estado.REEMPLAZADA, updated_at=timezone.now())
        )

        ultima_version = (
            CotizacionAPU.objects.filter(apu=apu).aggregate(m=Max("version"))["m"] or 0
        )
        version_nueva = ultima_version + 1

        resumen = apu.get_resumen_cotizacion()
        proyecto = apu.get_proyecto()
        solicitud = resumen.get("solicitud")
        cliente = resumen.get("cliente")
        garantia = resumen.get("garantia") or {}

        snapshot = CotizacionAPU.objects.create(
            apu=apu,
            proyecto=proyecto,
            solicitud=solicitud,
            cliente=cliente,
            # Identificación textual
            apu_nombre_snapshot=apu.nombre or "",
            tipo_apu_snapshot=apu.tipo_apu or "",
            proyecto_nombre_snapshot=(getattr(proyecto, "nombre", "") or "") if proyecto else "",
            proyecto_consecutivo_snapshot=(getattr(proyecto, "consecutivo", "") or "") if proyecto else "",
            solicitud_consecutivo_snapshot=(getattr(solicitud, "consecutivo", "") or "") if solicitud else "",
            cliente_nombre_snapshot=(getattr(cliente, "razon_social", "") or "") if cliente else "",
            cliente_nit_snapshot=(getattr(cliente, "nit", "") or "") if cliente else "",
            moneda_snapshot=(getattr(proyecto, "moneda", "") or "COP") if proyecto else "COP",
            # Modalidad + aprobación
            modalidad_aiu_snapshot=(apu.modalidad_aiu_seleccionada or ""),
            aprobado_por=apu.aprobado_por,
            aprobado_por_snapshot=(apu.aprobado_por.__str__() if apu.aprobado_por_id else ""),
            fecha_aprobacion_snapshot=apu.fecha_aprobacion,
            # Subtotales
            subtotal_materiales=_D(resumen.get("subtotal_materiales")),
            subtotal_herramientas=_D(resumen.get("subtotal_herramientas")),
            subtotal_transporte=_D(resumen.get("subtotal_transporte")),
            subtotal_mano_obra=_D(resumen.get("subtotal_mano_obra")),
            subtotal_administracion=_D(resumen.get("subtotal_administracion")),
            subtotal_directos_tecnico=_D(resumen.get("subtotal_directos_tecnico")),
            # AIU
            aiu_admin_pct=_D(resumen.get("porcentaje_admin")),
            aiu_imprevistos_pct=_D(resumen.get("porcentaje_imprevistos")),
            aiu_utilidad_pct=_D(resumen.get("porcentaje_utilidad")),
            aiu_admin_valor=_D(resumen.get("valor_admin")),
            aiu_imprevistos_valor=_D(resumen.get("valor_imprevistos")),
            aiu_utilidad_valor=_D(resumen.get("valor_utilidad")),
            total_aiu=_D(resumen.get("total_aiu")),
            # Garantía
            garantia_aplica=bool(garantia.get("aplica")),
            garantia_nombre_snapshot=garantia.get("tipo_nombre") or "",
            garantia_porcentaje_snapshot=garantia.get("porcentaje_aplicado"),
            garantia_modo_snapshot=garantia.get("modo_aplicacion") or "",
            garantia_material_snapshot=garantia.get("material_snapshot") or "",
            garantia_base_valor=_D(garantia.get("base_valor")),
            garantia_valor_recargo=_D(garantia.get("valor_recargo")),
            # IVA
            aplica_iva=bool(resumen.get("aplica_iva")),
            iva_pct=_D(resumen.get("iva_pct")),
            iva_base=_D(resumen.get("iva_base")),
            iva_valor=_D(resumen.get("iva_valor")),
            iva_label=resumen.get("iva_label") or "",
            # Total final
            total_final=_D(resumen.get("total_final")),
            # Versionamiento
            version=version_nueva,
            estado=CotizacionAPU.Estado.APROBADA,
            # Detalle JSON
            data_snapshot=cls._construir_data_snapshot(apu, resumen),
        )
        return snapshot

    @staticmethod
    def obtener_snapshot_vigente(apu) -> Optional[CotizacionAPU]:
        """Último snapshot con estado=APROBADA, o None."""
        return (
            CotizacionAPU.objects
            .filter(apu=apu, estado=CotizacionAPU.Estado.APROBADA)
            .order_by("-version")
            .first()
        )

    @classmethod
    def construir_contexto_pdf(cls, snapshot: CotizacionAPU) -> dict:
        """
        Rehidrata un dict con la misma forma que get_resumen_cotizacion() para
        reutilizar las plantillas WeasyPrint sin tocar datos vivos.
        """
        resumen = {
            "es_preliminar": False,
            "modalidad_oficial": snapshot.modalidad_aiu_snapshot or None,
            "modalidad_oficial_label": cls._label_modalidad(snapshot.modalidad_aiu_snapshot),
            "modalidades_disponibles": None,
            "subtotal_materiales": snapshot.subtotal_materiales,
            "garantia_valor_recargo": snapshot.garantia_valor_recargo,
            "subtotal_materiales_ajustado": (snapshot.subtotal_materiales or Decimal("0")) + (snapshot.garantia_valor_recargo or Decimal("0")),
            "subtotal_herramientas": snapshot.subtotal_herramientas,
            "subtotal_transporte": snapshot.subtotal_transporte,
            "subtotal_mano_obra": snapshot.subtotal_mano_obra,
            "subtotal_administracion": snapshot.subtotal_administracion,
            "subtotal_directos_tecnico": snapshot.subtotal_directos_tecnico,
            "porcentaje_admin": snapshot.aiu_admin_pct,
            "porcentaje_imprevistos": snapshot.aiu_imprevistos_pct,
            "porcentaje_utilidad": snapshot.aiu_utilidad_pct,
            "valor_admin": snapshot.aiu_admin_valor,
            "valor_imprevistos": snapshot.aiu_imprevistos_valor,
            "valor_utilidad": snapshot.aiu_utilidad_valor,
            "total_aiu": snapshot.total_aiu,
            "subtotal_con_aiu": (snapshot.subtotal_directos_tecnico or Decimal("0")) + (snapshot.total_aiu or Decimal("0")),
            "aiu_es_final": True,
            "aplica_iva": snapshot.aplica_iva,
            "iva_pct": snapshot.iva_pct,
            "iva_base": snapshot.iva_base,
            "iva_valor": snapshot.iva_valor,
            "iva_label": snapshot.iva_label,
            "total_final": snapshot.total_final,
            "garantia": {
                "aplica": snapshot.garantia_aplica,
                "tipo": None,
                "tipo_nombre": snapshot.garantia_nombre_snapshot,
                "porcentaje_aplicado": snapshot.garantia_porcentaje_snapshot,
                "modo_aplicacion": snapshot.garantia_modo_snapshot,
                "material_snapshot": snapshot.garantia_material_snapshot,
                "base_valor": snapshot.garantia_base_valor,
                "valor_recargo": snapshot.garantia_valor_recargo,
                "condiciones": (snapshot.data_snapshot or {}).get("garantia_condiciones", ""),
            },
            "cliente": snapshot.cliente,
            "contacto": None,
            "proyecto": snapshot.proyecto,
            "solicitud": snapshot.solicitud,
            "sistema": None,
            "subsistema": None,
            "aprobado_por": snapshot.aprobado_por,
            "fecha_aprobacion": snapshot.fecha_aprobacion_snapshot,
        }
        return {
            "resumen": resumen,
            "snapshot": snapshot,
            "es_aprobada": True,
        }

    # ------------------------------------------------------------------ #
    # Internos                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _label_modalidad(modalidad: str) -> str:
        if modalidad == "1":
            return "AIU sobre todos los costos directos"
        if modalidad == "2":
            return "AIU sobre costos directos sin materiales"
        return ""

    @classmethod
    def _construir_data_snapshot(cls, apu, resumen) -> dict:
        """Congela el detalle completo: líneas, secciones, consolidación."""
        lineas = list(
            apu.lineas
            .order_by("tipo", "descripcion")
            .values(
                "id", "tipo", "descripcion", "unidad",
                "rendimiento", "precio_referencia", "iva_aplicado",
                "costo_unitario", "costo_total",
                "valor_unitario", "valor_total",
                "tienda_referencia",
                "sistema_nombre_snapshot", "subsistema_nombre_snapshot",
                "despiece_maestro_id", "apu_origen_id",
            )
        )
        # Serializar Decimals para JSON.
        lineas_serializables = [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in ln.items()}
            for ln in lineas
        ]

        bloque = {
            "lineas": lineas_serializables,
            "garantia_condiciones": (
                apu.tipo_garantia.condiciones if apu.tipo_garantia_id else ""
            ),
            "factor_venta_pct": str(apu.factor_venta_pct or 0),
            "dias_duracion": apu.dias_duracion,
            "descripcion": apu.descripcion or "",
        }

        if apu.es_consolidado:
            bloque["consolidado"] = cls._serializar_consolidado(apu)

        # Despieces incluidos (sirve para PDF interno).
        incluidos = list(
            apu.despieces_incluidos.filter(activo=True)
            .values(
                "despiece_maestro_id",
                "sistema_nombre_snapshot",
                "subsistema_nombre_snapshot",
                "orden",
            )
        )
        bloque["despieces_incluidos"] = incluidos

        return bloque

    @staticmethod
    def _serializar_consolidado(apu) -> dict:
        """APUs origen + agrupación de materiales por origen."""
        origenes = []
        for orig in apu.get_apus_origen():
            origenes.append({
                "apu_id": orig.pk,
                "nombre_snapshot": orig.nombre,
                "tipo": orig.tipo_apu,
            })
        materiales = list(
            apu.lineas.filter(tipo=TipoAPU.MATERIALES)
            .values(
                "id", "descripcion", "apu_origen_id", "despiece_maestro_id",
                "sistema_nombre_snapshot", "subsistema_nombre_snapshot",
                "costo_total", "valor_total",
            )
        )
        materiales_serial = [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in m.items()}
            for m in materiales
        ]
        return {
            "apus_origen": origenes,
            "materiales": materiales_serial,
            "total_origenes": len(origenes),
        }


def _D(value) -> Decimal:
    """Coerción defensiva a Decimal para columnas numéricas del snapshot."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")
