"""
apps/presupuestos/services/apu_multi_builder.py
===============================================

Fase 11.4 — Builder de APU multi-despiece.

Patrón: Builder. Recibe un APU raíz (ya creado) y la lista de
DespieceMaestro seleccionados manualmente y reconstruye las líneas de
materiales preservando trazabilidad por sistema/subsistema/despiece.

Reglas (decisión Fase 11.4A aprobada):
  • el despiece raíz (origen) usa el ProyectoSistema raíz del APU y
    conserva la lógica actual de rendimiento (producto principal o
    componente legacy);
  • los despieces secundarios contribuyen sus materiales como bloques
    independientes con `rendimiento = 1` y `precio_referencia` = precio
    snapshot del producto, sin forzar contra la base del raíz;
  • cada APULinea creada se persiste con `despiece_maestro` y los
    snapshots `sistema_nombre_snapshot` / `subsistema_nombre_snapshot`;
  • se actualizan/crean los registros `APUDespieceIncluido` para el APU
    y se desactivan los que ya no estén en la nueva selección.

No toca categorías no-materiales (las maneja APUService a partir del
PS raíz). No duplica configuración base.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List


class APUMultiDespieceBuilder:
    """
    Construye/actualiza las líneas MATERIALES de un APU con base en una
    lista explícita de DespieceMaestro seleccionados manualmente.
    """

    def __init__(self, apu, despieces_seleccionados: List, despiece_origen):
        self.apu = apu
        self.dms = list(despieces_seleccionados)
        self.dm_origen = despiece_origen

    # ── API pública ───────────────────────────────────────────────────────

    def build(self) -> dict:
        """
        Punto de entrada. Devuelve un resumen con contadores para reportes.
        Debe llamarse dentro de transaction.atomic() (lo abre el facade).
        """
        from apps.common.choices import TipoAPU
        from apps.presupuestos.models import APULinea, APUDespieceIncluido
        from apps.presupuestos.models import DespieceLinea
        from apps.presupuestos.services.apu_service import APUService

        # 1) Sync de inclusión explícita
        ids_seleccionados = {dm.pk for dm in self.dms}
        self._sincronizar_inclusiones(ids_seleccionados)

        # 2) Borrar todas las líneas MATERIALES anteriores del APU; se reconstruyen.
        self.apu.lineas.filter(tipo=TipoAPU.MATERIALES).delete()

        # 3) Reconstruir DespieceLinea del PS raíz SOLO con el contenido del DM origen.
        #    (No mezclamos materiales de otros subsistemas en el PS raíz.)
        ps_raiz = self.apu.proyecto_sistema
        if ps_raiz and self.dm_origen and self.dm_origen.pk in ids_seleccionados:
            self._sync_despiece_lineas_origen(ps_raiz, self.dm_origen)

        # 4) Generar líneas MATERIALES del despiece raíz reutilizando APUService.
        materiales_raiz = []
        if ps_raiz and self.dm_origen and self.dm_origen.pk in ids_seleccionados:
            svc = APUService(ps_raiz)
            svc.apu = self.apu  # forzar mismo APU
            materiales_raiz = svc.generar_materiales()
            # Anotar snapshot/despiece en las recién creadas
            sistema_raiz = ps_raiz.sistema.nombre if ps_raiz.sistema_id else ""
            subsistema_raiz = ps_raiz.subsistema.nombre if ps_raiz.subsistema_id else ""
            self.apu.lineas.filter(
                tipo=TipoAPU.MATERIALES,
                despiece_maestro__isnull=True,
            ).update(
                despiece_maestro=self.dm_origen,
                sistema_nombre_snapshot=sistema_raiz,
                subsistema_nombre_snapshot=subsistema_raiz,
            )

        # 5) Materiales de los despieces secundarios — rendimiento=1, bloques crudos.
        secundarios = [dm for dm in self.dms if dm.pk != self.dm_origen.pk]
        materiales_secundarios = 0
        for dm in secundarios:
            materiales_secundarios += self._materiales_secundarios(dm)

        # 6) Recalcular subtotales del APU.
        self.apu.recalcular()

        return {
            "despieces_incluidos": len(self.dms),
            "materiales_raiz": len(materiales_raiz),
            "materiales_secundarios": materiales_secundarios,
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    def _sincronizar_inclusiones(self, ids_seleccionados: set) -> None:
        """Crea/activa APUDespieceIncluido para los seleccionados y desactiva el resto."""
        from apps.presupuestos.models import APUDespieceIncluido

        # Desactivar los que ya no están seleccionados (no borrar — histórico).
        APUDespieceIncluido.objects.filter(apu=self.apu).exclude(
            despiece_maestro_id__in=ids_seleccionados
        ).update(activo=False)

        for orden, dm in enumerate(self.dms):
            sistema = dm.subsistema.sistema.nombre if dm.subsistema_id else ""
            subsistema = dm.subsistema.nombre if dm.subsistema_id else ""
            APUDespieceIncluido.objects.update_or_create(
                apu=self.apu,
                despiece_maestro=dm,
                defaults={
                    "sistema_nombre_snapshot": sistema,
                    "subsistema_nombre_snapshot": subsistema,
                    "orden": orden,
                    "activo": True,
                },
            )

    def _sync_despiece_lineas_origen(self, ps_raiz, dm) -> None:
        """
        Reconstruye DespieceLinea del PS raíz a partir SOLO del DM origen
        (líneas individuales + consolidaciones). Borra las que no estén
        presentes en este DM para no arrastrar contaminación legacy.
        """
        from apps.presupuestos.models import DespieceLinea

        from apps.ingenieria.services.lineas_finales_apu import _redondear_comercial

        consolidado: dict = {}
        pks_consolidados: set = set()
        for c in dm.consolidaciones.all():
            pks_consolidados.update(c.lineas_ids or [])

        for dml in dm.lineas.select_related("producto", "producto__unidad"):
            if dml.pk in pks_consolidados:
                continue
            if dml.producto_id is None:
                continue
            clave = dml.componente_codigo
            precio_snapshot = (
                dml.producto.precio_unitario_real
                if dml.producto_id and dml.producto
                else dml.precio_unitario
            )
            redondeada = _redondear_comercial(
                dml.cantidad_redondeada, dml.cantidad_calculada
            )
            if clave in consolidado:
                consolidado[clave]["cantidad"] += (dml.cantidad_calculada or 0)
                consolidado[clave]["cantidad_redondeada"] += redondeada
            else:
                consolidado[clave] = {
                    "cantidad": dml.cantidad_calculada or 0,
                    "cantidad_redondeada": redondeada,
                    "precio_snapshot": precio_snapshot,
                    "producto": dml.producto,
                }

        for c in dm.consolidaciones.select_related("producto", "producto__unidad"):
            if c.producto_id is None:
                continue
            clave = f"CONS_{c.producto_id}"
            precio_snapshot = (
                c.precio_unitario
                or (c.producto.precio_unitario_real if c.producto else None)
            )
            redondeada = _redondear_comercial(c.cantidad_redondeada, c.cantidad_total)
            if clave in consolidado:
                consolidado[clave]["cantidad"] += (c.cantidad_total or 0)
                consolidado[clave]["cantidad_redondeada"] += redondeada
            else:
                consolidado[clave] = {
                    "cantidad": c.cantidad_total or 0,
                    "cantidad_redondeada": redondeada,
                    "precio_snapshot": precio_snapshot,
                    "producto": c.producto,
                }

        for codigo, datos in consolidado.items():
            DespieceLinea.objects.update_or_create(
                proyecto_sistema=ps_raiz,
                componente_codigo=codigo,
                defaults={
                    "proyecto": dm.proyecto,
                    "cantidad_calculada": datos["cantidad"],
                    # Se arrastra el redondeo del despiece para que el APU
                    # valorice con la cantidad comercial, no con la exacta.
                    "cantidad_redondeada": datos["cantidad_redondeada"],
                    "precio_snapshot": datos["precio_snapshot"],
                    "producto": datos["producto"],
                },
            )

        DespieceLinea.objects.filter(
            proyecto_sistema=ps_raiz
        ).exclude(componente_codigo__in=consolidado.keys()).delete()

    def _materiales_secundarios(self, dm) -> int:
        """
        Crea APULinea(MATERIALES) para cada producto de un DM secundario:
          • cantidad comercial (redondeada) como rendimiento — misma regla
            que los materiales del despiece raíz (decisión Fase 11.4A);
          • rendimiento=1 si la cantidad no se pudo determinar;
          • precio_referencia = precio snapshot del producto;
          • snapshots de sistema/subsistema y FK a despiece_maestro.

        NO crea DespieceLinea para los DMs secundarios; sus materiales solo
        existen como APULinea con `despiece_maestro` para trazabilidad.
        """
        from apps.common.choices import TipoAPU
        from apps.presupuestos.models import APULinea

        sistema = dm.subsistema.sistema.nombre if dm.subsistema_id else ""
        subsistema = dm.subsistema.nombre if dm.subsistema_id else ""

        # Consolidar igual que en origen para evitar duplicados.
        productos_data: dict = {}  # {producto_id: {"cantidad", "precio", "nombre", "unidad"}}
        pks_consolidados: set = set()
        for c in dm.consolidaciones.all():
            pks_consolidados.update(c.lineas_ids or [])

        from apps.ingenieria.services.lineas_finales_apu import _redondear_comercial

        for dml in dm.lineas.select_related("producto", "producto__unidad"):
            if dml.pk in pks_consolidados:
                continue
            if dml.producto_id is None:
                continue
            self._acumular_producto(
                productos_data, dml.producto,
                _redondear_comercial(dml.cantidad_redondeada, dml.cantidad_calculada),
                dml.precio_unitario,
            )

        for c in dm.consolidaciones.select_related("producto", "producto__unidad"):
            if c.producto_id is None:
                continue
            self._acumular_producto(
                productos_data, c.producto,
                _redondear_comercial(c.cantidad_redondeada, c.cantidad_total),
                c.precio_unitario,
            )

        creadas = 0
        for producto_id, data in productos_data.items():
            cantidad = Decimal(str(data["cantidad"] or 0))
            if cantidad <= 0:
                cantidad = Decimal("1")
            precio = Decimal(str(data["precio"] or 0))
            linea = APULinea.objects.create(
                apu=self.apu,
                tipo=TipoAPU.MATERIALES,
                descripcion=data["nombre"],
                rendimiento=cantidad,
                unidad=(data["unidad"] or "und"),
                precio_referencia=precio,
                iva_aplicado=self.apu.aplica_iva,
                editable=False,
                despiece_maestro=dm,
                sistema_nombre_snapshot=sistema,
                subsistema_nombre_snapshot=subsistema,
            )
            linea.calcular()
            creadas += 1
        return creadas

    @staticmethod
    def _acumular_producto(bucket: dict, producto, cantidad, precio_directo) -> None:
        precio_ref = (
            getattr(producto, "precio_unitario_real", None)
            if producto is not None else None
        )
        precio = precio_directo if precio_directo not in (None, 0) else precio_ref
        unidad = getattr(getattr(producto, "unidad", None), "codigo", "und") if producto else "und"
        nombre = producto.nombre if producto else "(sin producto)"
        key = producto.pk if producto else None
        if key in bucket:
            bucket[key]["cantidad"] = (bucket[key]["cantidad"] or 0) + (cantidad or 0)
        else:
            bucket[key] = {
                "cantidad": cantidad or 0,
                "precio": precio,
                "nombre": nombre,
                "unidad": unidad,
            }
