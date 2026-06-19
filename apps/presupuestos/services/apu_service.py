from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

from django.db import transaction

logger = logging.getLogger(__name__)


def _resolver_config_apu():
    """Resuelve la ConfiguracionAPU activa con cache-aside (Fase 5C).

    Camino feliz: get_cached_config_apu_id() → ConfiguracionAPU.objects.get(pk=id).
    Si el cache devuelve None (sin registro activo en DB) o el id no se puede
    cargar, cae al flujo original ConfiguracionAPU.activa_o_default() — que
    además garantiza la auto-creación del registro por defecto. Esto preserva
    el comportamiento visible y el efecto colateral de inicialización.
    Invalidación: signals post_save/post_delete sobre ConfiguracionAPU
    (apps/presupuestos/signals.py).
    """
    from apps.presupuestos.models import ConfiguracionAPU
    from apps.common.cache import get_cached_config_apu_id
    cfg_id = get_cached_config_apu_id()
    if cfg_id is not None:
        try:
            return ConfiguracionAPU.objects.get(pk=cfg_id)
        except ConfiguracionAPU.DoesNotExist:
            pass
    return ConfiguracionAPU.activa_o_default()


def calcular_rendimiento_por_producto_principal(cantidad_linea, cantidad_base) -> Decimal:
    """Fase 6F — Rendimiento de una línea APU contra la cantidad base del
    producto principal.

    Fórmula:
        rendimiento = cantidad_linea / cantidad_base

    Reglas (verbatim del usuario):
      - cantidad_base no puede ser 0.
      - cantidad_base no puede ser None.
      - cantidad_linea no puede ser None.
      - Usar Decimal.
      - Redondear a 6 decimales (misma precisión que APULinea.rendimiento).

    Para la línea del producto principal aplica el mismo helper:
        cantidad_linea == cantidad_base  →  rendimiento = 1.

    Raises:
        ValueError si cantidad_base es None / 0 / negativa, o si
        cantidad_linea es None.
    """
    if cantidad_base is None:
        raise ValueError("cantidad_base no puede ser None.")
    if cantidad_linea is None:
        raise ValueError("cantidad_linea no puede ser None.")
    base = Decimal(str(cantidad_base))
    if base <= Decimal("0"):
        raise ValueError(
            f"cantidad_base debe ser mayor que cero (recibido: {cantidad_base})."
        )
    linea = Decimal(str(cantidad_linea))
    return (linea / base).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


_CLAVES_UNIDAD_REFERENCIA = (
    "total_powergrip",
    "total_unidades",
    "cantidad",
    "n_apoyos",
    "ml_fachada",
    "m2",
    "area_m2",
)

class APUService:
    """Motor de APU automático."""

    # ── Constructor ───────────────────────────────────────────────────────────

    def __init__(self, proyecto_sistema):
        from apps.presupuestos.models import APU

        self.ps  = proyecto_sistema
        self.cfg = _resolver_config_apu()

        # Nombre y descripción predeterminados derivados del proyecto sistema
        nombre_default = (
            f"APU {proyecto_sistema.sistema} — "
            f"{proyecto_sistema.proyecto}"
        )

        _proyecto = proyecto_sistema.proyecto
        _dias = getattr(_proyecto, "dias_duracion", None) or 30

        self.apu, created = APU.objects.get_or_create(
            proyecto_sistema=proyecto_sistema,
            defaults={
                "nombre": nombre_default,
                "descripcion": "",
                "factor_venta_pct": self.cfg.factor_venta_pct,
                "iva_pct": getattr(_proyecto, "iva_pct", self.cfg.iva_pct),
                "aplica_iva": not getattr(_proyecto, "aplica_exencion_iva", False),
                "aiu_contratista_pct": self.cfg.aiu_contratista_pct,
                "margen_ganancia_pct": self.cfg.margen_ganancia_pct,
                "dias_duracion": _dias,
            },
        )
        logger.info(
            "[APUService] APU %s (%s) para PS %s | config='%s'.",
            self.apu.pk, "nuevo" if created else "existente",
            proyecto_sistema.pk, self.cfg.nombre,
        )

    # ── Classmethod de entrada ────────────────────────────────────────────────

    @classmethod
    def for_apu(cls, apu) -> "APUService":
        """Crea un APUService adjunto a un APU existente (sin get_or_create)."""
        instance = object.__new__(cls)
        instance.ps  = apu.proyecto_sistema
        instance.cfg = _resolver_config_apu()
        instance.apu = apu
        return instance

    @classmethod
    def generar(cls, proyecto_sistema) -> "APU":
        """
        Punto de entrada principal.
        Genera líneas de materiales + auto-puebla desde catálogo activo, finaliza.
        """
        svc = cls(proyecto_sistema)
        svc.generar_materiales()
        svc._auto_generar_desde_catalogo()
        svc.finalizar()
        return svc.apu

    def _items_apu_subsistema(self, tipo_apu: str) -> list:
        """Fase 6L-D — Devuelve items_data para una categoría leyendo SOLO
        SubsistemaItemAPU asociados al subsistema del proyecto.

        Reemplaza el patrón anterior `ItemCatalogoAPU.objects.filter(activo=True,
        categoria__tipo_apu=tipo)` que traía todo el catálogo. Ahora el APU
        solo trae los ítems que el subsistema explícitamente configuró.

        Devuelve una lista de dicts compatible con
        `_generar_categoria_desde_catalogo`:
            [{"item_id": int, "cantidad": int}, ...]

        Si el subsistema no tiene ítems configurados para `tipo_apu` →
        devuelve lista vacía (la categoría queda sin generar y el detalle
        APU muestra mensaje claro en la vista).
        """
        from apps.presupuestos.models import SubsistemaItemAPU

        ps = self.ps
        if not ps or not ps.subsistema_id:
            return []

        qs = (
            SubsistemaItemAPU.objects
            .filter(subsistema_id=ps.subsistema_id, tipo=tipo_apu, activo=True,
                    item_catalogo__activo=True)
            .order_by("orden", "item_catalogo__nombre")
            .values("item_catalogo_id", "cantidad")
        )
        return [
            {"item_id": row["item_catalogo_id"], "cantidad": row["cantidad"]}
            for row in qs
        ]

    def _auto_generar_desde_catalogo(self) -> None:
        """
        Auto-puebla el APU con los ítems APU predeterminados del subsistema
        (Fase 6L-D). Por cada categoría no-Materiales que aún no tenga
        líneas generadas, consulta SubsistemaItemAPU y solo genera si hay
        ítems asociados. Si no hay ítems configurados para una categoría,
        NO se llena con todo el catálogo (cambio respecto al comportamiento
        anterior): la categoría queda vacía y el template muestra mensaje
        explicativo.
        """
        from apps.common.choices import TipoAPU

        tipos_existentes = set(self.apu.lineas.values_list("tipo", flat=True))

        if TipoAPU.MANO_DE_OBRA not in tipos_existentes:
            items_data = self._items_apu_subsistema(TipoAPU.MANO_DE_OBRA)
            if items_data:
                self.generar_mano_obra_desde_catalogo(items_data)
            else:
                logger.info(
                    "[APUService] PS=%s subsistema=%s sin ítems APU configurados para MO; "
                    "la categoría queda vacía.",
                    self.ps.pk, getattr(self.ps.subsistema, "codigo", None),
                )

        if TipoAPU.HERRAMIENTAS_EQUIPOS not in tipos_existentes:
            items_data = self._items_apu_subsistema(TipoAPU.HERRAMIENTAS_EQUIPOS)
            if items_data:
                self.generar_herramientas_desde_catalogo(items_data)
            else:
                logger.info(
                    "[APUService] PS=%s subsistema=%s sin ítems APU configurados para "
                    "HERRAMIENTAS; la categoría queda vacía.",
                    self.ps.pk, getattr(self.ps.subsistema, "codigo", None),
                )

        if TipoAPU.TRANSPORTE not in tipos_existentes:
            items_data = self._items_apu_subsistema(TipoAPU.TRANSPORTE)
            if items_data:
                self.generar_transporte_desde_catalogo(items_data)
            else:
                logger.info(
                    "[APUService] PS=%s subsistema=%s sin ítems APU configurados para "
                    "TRANSPORTE; la categoría queda vacía.",
                    self.ps.pk, getattr(self.ps.subsistema, "codigo", None),
                )

        if TipoAPU.ADMINISTRACION not in tipos_existentes:
            items_data = self._items_apu_subsistema(TipoAPU.ADMINISTRACION)
            if items_data:
                self.generar_administracion_desde_catalogo(items_data)
            else:
                logger.info(
                    "[APUService] PS=%s subsistema=%s sin ítems APU configurados para "
                    "ADMINISTRACION; la categoría queda vacía.",
                    self.ps.pk, getattr(self.ps.subsistema, "codigo", None),
                )

    # ── Helpers: referencia del producto base (PowerGrip) ─────────────────────

    def _get_total_unidades(self) -> float:
        """
        Determina la cantidad de referencia del sistema (denominador del APU por unidad).
        Prioridad:
          1. variable_referencia_apu del subsistema (si está definida en parametros_entrada)
          2. Búsqueda genérica por _CLAVES_UNIDAD_REFERENCIA
          3. Fallback: area_total_m2 del proyecto
        Mínimo devuelto: 1.0
        """
        params = self.ps.parametros_entrada or {}

        # 1. Variable explícita definida en el subsistema
        sub = self.ps.subsistema
        if sub and getattr(sub, "variable_referencia_apu", ""):
            val = params.get(sub.variable_referencia_apu)
            if val:
                try:
                    total = float(val)
                    if total > 0:
                        logger.debug(
                            "[APUService] _get_total_unidades: subsistema var='%s' valor=%.4f (PS %s)",
                            sub.variable_referencia_apu, total, self.ps.pk,
                        )
                        return total
                except (ValueError, TypeError):
                    pass

        # 2. Búsqueda estándar
        for clave in _CLAVES_UNIDAD_REFERENCIA:
            val = params.get(clave)
            if val:
                try:
                    total = float(val)
                    if total > 0:
                        logger.debug(
                            "[APUService] _get_total_unidades: clave='%s' valor=%.4f (PS %s)",
                            clave, total, self.ps.pk,
                        )
                        return total
                except (ValueError, TypeError):
                    pass

        # 3. Fallback: usar 1 como denominador neutro
        fallback = 1.0
        logger.debug(
            "[APUService] _get_total_unidades: fallback area_m2=%.4f (PS %s)",
            fallback, self.ps.pk,
        )
        return fallback

    def _get_total_powergrip(self) -> Decimal:
        """
        Devuelve el total del producto base (PowerGrip) como Decimal.

        Reglas de validación:
          - El APU debe estar vinculado a un ProyectoSistema.
          - El valor encontrado debe ser estrictamente mayor que cero.
          - Si no se puede determinar, lanza ValueError con mensaje descriptivo.

        Este valor es el denominador universal para el costo unitario por categoría:
          costo_unitario = costo_componente / total_powergrip
        """
        if not self.ps:
            raise ValueError(
                "Este APU no está vinculado a un ProyectoSistema. "
                "No es posible calcular el costo unitario sin un producto base de referencia."
            )

        tp = self._get_total_unidades()

        if tp <= 0:
            raise ValueError(
                f"El total del producto base (PowerGrip) debe ser mayor que cero (valor actual: {tp}). "
                "Verifique los parámetros de entrada del ProyectoSistema."
            )

        return Decimal(str(tp)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def _get_num_personas(self, items_personal: list | None = None) -> int:
        """
        Determina el número total de personas en la cuadrilla.

        Prioridad:
          1. Suma de cantidades en items_personal (cargos personales del lote actual).
          2. proyecto.num_personas si está definido.
          3. Fallback: 1.

        Args:
            items_personal: lista de {"cantidad": int} con solo los ítems de personal
                            del lote que se está procesando actualmente.
        """
        # 1. Suma de personas en el lote de personal recibido
        if items_personal:
            total = sum(max(int(d.get("cantidad", 1)), 1) for d in items_personal)
            if total > 0:
                return total

        # 2. Campo num_personas del proyecto comercial
        if self.ps:
            try:
                np = self.ps.proyecto.num_personas
                if np and int(np) > 0:
                    return int(np)
            except Exception:
                pass

        return 1

    # ── Helper: contexto de regla APU ─────────────────────────────────────────

    def _build_regla_context(
        self,
        suma: float,
        dias_efectivos: float,
        aiu: float,
        mg: float,
        tp,
        num_personas: int = 1,
    ) -> dict:
        """
        Construye el diccionario de variables para evaluar ReglaAPUSubsistema.formula_costo_unitario.

        Variables:
          suma        — suma de costos de todos los ítems de la categoría
          aiu         — factor AIU, e.g. 1.30 si AIU=30%
          margen      — factor margen, e.g. 1.20 si margen=20%
          dias        — días efectivos (ya ajustados si aplica_dias_mensuales)
          tp          — total_powergrip (denominador)
          personas    — número de personas en cuadrilla
          factor_venta — factor de venta, e.g. 1.21 si factor_venta=121%
        """
        tp_float = float(tp)
        # El denominador se expone como "tp" Y como el nombre real de la variable
        # definida en el subsistema (ej: "total_powergrip"), para que las fórmulas
        # puedan usar el nombre natural que el usuario escribe en el subsistema.
        sub = self.ps.subsistema if self.ps else None
        var_ref = (sub.variable_referencia_apu or "tp") if sub else "tp"
        ctx = {
            "suma":         float(suma),
            "aiu":          float(aiu),
            "margen":       float(mg),
            "dias":         float(dias_efectivos),
            "tp":           tp_float,
            "personas":     int(num_personas),
            "factor_venta": 1.0 + float(self.apu.factor_venta_pct) / 100.0,
        }
        # Inyectar el valor bajo el nombre de la variable de referencia del subsistema
        # (ej: total_powergrip=2883) para que la fórmula pueda escribirlo directamente.
        if var_ref and var_ref != "tp":
            ctx[var_ref] = tp_float
        # También inyectar cualquier parámetro de entrada del proyecto para máxima flexibilidad
        if self.ps:
            for k, v in (self.ps.parametros_entrada or {}).items():
                if k not in ctx:
                    try:
                        ctx[k] = float(v)
                    except (TypeError, ValueError):
                        pass
        return ctx

    # ── Generador unificado por categoría (no-MATERIALES) ────────────────────

    @transaction.atomic
    def _generar_categoria_desde_catalogo(
        self,
        tipo_apu: str,
        items_data: List[Dict],
    ) -> List[dict]:
        """
        Genera APULineas para cualquier tipo de APU distinto de MATERIALES,
        usando ReglaAPUSubsistema para obtener el costo unitario.

        Patrón: por cada CategoriaItemAPU presente en items_data se crean:
          - N líneas detalle (item_catalogo set, costo_total=0) — referencia visual
          - 1 línea resumen (item_catalogo=None) — contiene el costo real

        items_data: [{"item_id": int, "cantidad": int}]

        La fórmula se busca en ReglaAPUSubsistema filtrada por:
            subsistema = self.ps.subsistema
            tipo_apu   = tipo_apu
        Si no existe regla, lanza ValueError descriptivo.
        """
        from apps.presupuestos.models import APULinea, ItemCatalogoAPU, ReglaAPUSubsistema
        from collections import defaultdict

        dias_duracion = float(self.apu.dias_duracion or 0)
        if dias_duracion <= 0:
            raise ValueError("El parámetro 'Días de duración' del APU debe ser mayor que cero.")

        tp  = self._get_total_powergrip()
        aiu = 1 + float(self.apu.aiu_contratista_pct) / 100
        mg  = 1 + float(self.apu.margen_ganancia_pct) / 100

        # Obtener regla de cálculo para este subsistema + tipo
        try:
            regla = ReglaAPUSubsistema.objects.get(
                subsistema=self.ps.subsistema,
                tipo_apu=tipo_apu,
            )
        except ReglaAPUSubsistema.DoesNotExist:
            raise ValueError(
                f"No existe ReglaAPUSubsistema para subsistema='{self.ps.subsistema}' "
                f"y tipo_apu='{tipo_apu}'. Defínala en la edición del Subsistema."
            )

        # Cargar ítems
        items_cargados = []
        for d in items_data:
            item     = ItemCatalogoAPU.objects.select_related("categoria").get(pk=d["item_id"])
            cantidad = max(int(d.get("cantidad", 1)), 1)
            items_cargados.append((item, cantidad))

        # Número de personas (relevante para MO)
        items_personal_data = [
            {"cantidad": cant}
            for item, cant in items_cargados
            if item.salario_base or item.prestaciones
        ]
        num_personas = self._get_num_personas(items_personal_data)

        # Eliminar líneas existentes del tipo para regenerar limpio
        self.apu.lineas.filter(tipo=tipo_apu).delete()

        # Agrupar por categoría
        por_categoria: dict = defaultdict(list)
        for item, cantidad in items_cargados:
            por_categoria[item.categoria_id].append((item, cantidad))

        creadas = []
        for cat_id, items_en_cat in por_categoria.items():
            categoria = items_en_cat[0][0].categoria

            # Días efectivos: si la categoría tiene aplica_dias_mensuales → dias/30
            dias_efectivos = dias_duracion / 30.0 if categoria.aplica_dias_mensuales else dias_duracion

            # Suma del costo de los ítems de la categoría
            # No-personal: precio/día = precio_base / vida_util_dias
            # Personal (salario): salario_base + prestaciones (tarifa mensual/periodo)
            suma = 0.0
            for item, cantidad in items_en_cat:
                if (item.salario_base and item.salario_base > 0) or (item.prestaciones and item.prestaciones > 0):
                    precio_efectivo = float(item.salario_base + item.prestaciones)
                elif item.vida_util_dias:
                    precio_efectivo = float(item.precio_base) / float(item.vida_util_dias)
                else:
                    precio_efectivo = float(item.precio_base)
                suma += precio_efectivo * cantidad

            # Evaluar fórmula → costo unitario de la categoría
            ctx = self._build_regla_context(suma, dias_efectivos, aiu, mg, tp, num_personas)
            costo_unitario_cat = regla.evaluar(ctx)
            logger.debug(
                "[APUService] %s cat='%s' | suma=%.2f | dias_ef=%.2f | ctx=%s | cu=%.6f",
                tipo_apu, categoria.nombre, suma, dias_efectivos, ctx, costo_unitario_cat,
            )

            # Líneas detalle (referencia visual, costo_total=0)
            for item, cantidad in items_en_cat:
                es_personal = bool(
                    (item.salario_base and item.salario_base > 0)
                    or (item.prestaciones and item.prestaciones > 0)
                )
                if es_personal:
                    precio_ref_detalle = Decimal(str(item.salario_base + item.prestaciones))
                elif item.vida_util_dias:
                    precio_ref_detalle = (
                        Decimal(str(item.precio_base)) / Decimal(str(item.vida_util_dias))
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                else:
                    precio_ref_detalle = Decimal(str(item.precio_base))
                APULinea.objects.create(
                    apu=self.apu,
                    tipo=tipo_apu,
                    item_catalogo=item,
                    descripcion=item.nombre,
                    rendimiento=Decimal(str(cantidad)),
                    unidad=item.unidad,
                    precio_referencia=precio_ref_detalle,
                    vida_util_dias=item.vida_util_dias,
                    costo_unitario=Decimal("0"),
                    costo_total=Decimal("0"),
                    valor_unitario=Decimal("0"),
                    valor_total=Decimal("0"),
                    salario_base=item.salario_base if es_personal else Decimal("0"),
                    prestaciones=item.prestaciones if es_personal else Decimal("0"),
                    iva_aplicado=False,
                    editable=False,
                    tienda_referencia=item.tienda_referencia,
                )

            # Línea resumen (con el costo real calculado por la regla)
            precio_ref = Decimal(str(costo_unitario_cat)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
            linea_resumen = APULinea.objects.create(
                apu=self.apu,
                tipo=tipo_apu,
                item_catalogo=None,
                despiece_linea=None,
                descripcion=categoria.nombre,
                rendimiento=Decimal("1"),
                unidad="global",
                precio_referencia=precio_ref,
                iva_aplicado=False,
                editable=True,
            )
            linea_resumen.calcular()

            creadas.append({
                "descripcion": categoria.nombre,
                "suma_items":  suma,
                "costo_total": float(linea_resumen.costo_total),
            })
            logger.info(
                "[APUService] %s cat='%s' | n=%d | suma=%.2f | tp=%.4f | cu=%.6f",
                tipo_apu, categoria.nombre, len(items_en_cat), suma, float(tp), costo_unitario_cat,
            )

        return creadas

    # ── Generadores de líneas ─────────────────────────────────────────────────

    def _get_total_unidades_componente(self, componente_codigo: str, comp_cache: dict) -> float:
        """
        Devuelve el total de referencia para calcular el rendimiento de un componente específico.
        Prioridad:
          1. variable_referencia_apu del componente (ComponenteSubsistema)
          2. variable_referencia_apu del subsistema (fallback global)
          3. Búsqueda genérica + área del proyecto
        """
        params = self.ps.parametros_entrada or {}

        # 1. Referencia definida en el componente
        comp = comp_cache.get(componente_codigo)
        if comp and comp.variable_referencia_apu:
            val = params.get(comp.variable_referencia_apu)
            if val:
                try:
                    total = float(val)
                    if total > 0:
                        logger.debug(
                            "[APUService] ref componente '%s' var='%s' total=%.4f (PS %s)",
                            componente_codigo, comp.variable_referencia_apu, total, self.ps.pk,
                        )
                        return total
                except (ValueError, TypeError):
                    pass

        # 2. Fallback al método global del subsistema
        return self._get_total_unidades()

    @transaction.atomic
    def generar_materiales(self) -> List[dict]:
        """
        Genera APULineas tipo MATERIALES desde las DespieceLineas resueltas.
        rendimiento = total_unidades / cantidad_final
        Omite líneas pendientes_seleccion o sin producto.

        Tarea 10: elimina automáticamente las líneas de materiales generadas
        desde despiece (despiece_linea IS NOT NULL) antes de regenerar, para
        evitar duplicados cuando se llama varias veces.
        """
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        from apps.ingenieria.models import ComponenteSubsistema

        # ── Fix 6E-C: regenerar materiales desde cero ─────────────────────────
        # Antes filtrábamos por despiece_linea__isnull=False para "preservar"
        # APULineas materiales legacy sin FK. Eso convertía a las líneas
        # huérfanas (despiece_linea=NULL por SET_NULL al borrar DespieceLineas
        # obsoletas en APUArmarDesdeDespieceView) en "materiales fantasma" que
        # sobrevivían entre regeneraciones.
        # Regla: las APULineas tipo MATERIALES son SIEMPRE derivadas del
        # despiece. Se borran completas y se reconstruyen desde ps.despiece_lineas.
        self.apu.lineas.filter(tipo=TipoAPU.MATERIALES).delete()

        lineas_despiece = self.ps.despiece_lineas.select_related(
            "producto", "producto__unidad", "categoria_producto",
        )

        # Cache de componentes para no hacer N queries
        _comp_cache: dict = {}
        if self.ps.subsistema_id:
            for c in ComponenteSubsistema.objects.filter(subsistema=self.ps.subsistema):
                _comp_cache[c.codigo] = c

        # ── Fase 6F: modo de rendimiento ─────────────────────────────────────
        # Si el flujo "Armar mi APU" persistió producto_principal + cantidad_base
        # en parametros_entrada, usamos esa cantidad_base como denominador
        # uniforme para TODAS las líneas. La línea cuyo producto coincide con
        # el producto principal queda con rendimiento = 1.
        # Si no hay modo configurado (APUs legacy o flujo APUGenerarDesdeDespiece),
        # se preserva el cálculo legacy por componente (total_powergrip/área).
        _params = self.ps.parametros_entrada or {}
        _modo_rendimiento = _params.get("modo_rendimiento")
        _usar_producto_principal = _modo_rendimiento == "PRODUCTO_PRINCIPAL"
        _cantidad_base_pp = None
        _producto_principal_id = None
        if _usar_producto_principal:
            try:
                _cantidad_base_pp = Decimal(str(_params.get("cantidad_base") or 0))
                _producto_principal_id = int(_params.get("producto_principal_id") or 0)
            except (TypeError, ValueError):
                _cantidad_base_pp = None
                _producto_principal_id = None
            if not _cantidad_base_pp or _cantidad_base_pp <= 0 or not _producto_principal_id:
                # Si los datos persistidos están corruptos, fallback al modo legacy
                # para no romper la generación.
                logger.warning(
                    "[APUService] modo_rendimiento=PRODUCTO_PRINCIPAL pero datos inválidos "
                    "(cantidad_base=%s, producto_principal_id=%s); fallback al modo legacy (PS=%s).",
                    _params.get("cantidad_base"), _params.get("producto_principal_id"), self.ps.pk,
                )
                _usar_producto_principal = False

        creadas = []

        for dl in lineas_despiece:
            if dl.pendiente_seleccion:
                logger.warning(
                    "[APUService] Línea %s omitida: pendiente de selección (PS=%s).",
                    dl.pk, self.ps.pk,
                )
                continue
            if not dl.producto_id:
                logger.warning(
                    "[APUService] Línea %s omitida: sin producto (PS=%s).",
                    dl.pk, self.ps.pk,
                )
                continue

            nombre   = dl.producto.nombre
            precio   = float(dl.precio_snapshot or 0)
            cantidad = float(dl.cantidad_final)

            # ── Cálculo de rendimiento ───────────────────────────────────────
            if _usar_producto_principal:
                # Fase 6F: rendimiento = cantidad_linea / cantidad_base_producto_principal.
                # Si la línea corresponde al producto principal, el helper devuelve 1
                # automáticamente (cantidad == cantidad_base).
                try:
                    rendimiento = float(
                        calcular_rendimiento_por_producto_principal(
                            cantidad, _cantidad_base_pp
                        )
                    )
                except ValueError as exc:
                    # Esto no debería pasar (cantidad_base se validó arriba) pero
                    # protegemos al servicio de un crash en runtime.
                    logger.error(
                        "[APUService] Línea %s: error de rendimiento PP (%s); usando 1.0",
                        dl.pk, exc,
                    )
                    rendimiento = 1.0
            else:
                # Legacy: ref. del componente → ref. del subsistema → fallback área.
                # Ej: 25947 fijaciones / 2883 soportes = 9 fijaciones/soporte.
                tp = self._get_total_unidades_componente(dl.componente_codigo, _comp_cache)
                rendimiento = (cantidad / tp) if tp > 0 else 1.0

            linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.MATERIALES,
                despiece_linea=dl,
                defaults={
                    "descripcion": nombre,
                    "rendimiento": Decimal(str(round(rendimiento, 6))),
                    "unidad": getattr(dl.producto.unidad, "codigo", "und"),
                    "precio_referencia": Decimal(str(precio)),
                    "iva_aplicado": self.apu.aplica_iva,
                    "editable": False,
                },
            )
            linea.calcular()
            creadas.append({
                "descripcion": nombre,
                "rendimiento": round(rendimiento, 4),
                "precio": precio,
                "costo_unitario": float(linea.costo_unitario),
                "valor_unitario": float(linea.valor_unitario),
                "costo_total": float(linea.costo_total),
                "valor_total": float(linea.valor_total),
            })
            logger.debug(
                "[APUService] Material '%s' | cantidad=%.4f | rend=%.6f | cu=%.4f",
                nombre, cantidad, rendimiento, float(linea.costo_unitario),
            )

        logger.info(
            "[APUService] %d líneas de materiales generadas para APU %s.",
            len(creadas), self.apu.pk,
        )
        return creadas

    @transaction.atomic
    def generar_mano_obra_desde_catalogo(self, items_data: List[Dict]) -> List[dict]:
        """Genera APULineas MANO_DE_OBRA usando ReglaAPUSubsistema del subsistema."""
        from apps.common.choices import TipoAPU
        creadas = self._generar_categoria_desde_catalogo(TipoAPU.MANO_DE_OBRA, items_data)
        logger.info("[APUService] %d categorías MO para APU %s.", len(creadas), self.apu.pk)
        return creadas

    @transaction.atomic
    def generar_herramientas_desde_catalogo(self, items_data: List[Dict]) -> List[dict]:
        """Genera APULineas HERRAMIENTAS_EQUIPOS usando ReglaAPUSubsistema del subsistema."""
        from apps.common.choices import TipoAPU
        creadas = self._generar_categoria_desde_catalogo(TipoAPU.HERRAMIENTAS_EQUIPOS, items_data)
        logger.info("[APUService] %d categorías herramientas para APU %s.", len(creadas), self.apu.pk)
        return creadas

    @transaction.atomic
    def generar_transporte_desde_catalogo(self, items_data: List[Dict]) -> List[dict]:
        """Genera APULineas TRANSPORTE usando ReglaAPUSubsistema del subsistema."""
        from apps.common.choices import TipoAPU
        creadas = self._generar_categoria_desde_catalogo(TipoAPU.TRANSPORTE, items_data)
        logger.info("[APUService] %d categorías transporte para APU %s.", len(creadas), self.apu.pk)
        return creadas

    @transaction.atomic
    def generar_administracion_desde_catalogo(self, items_data: List[Dict]) -> List[dict]:
        """Genera APULineas ADMINISTRACION usando ReglaAPUSubsistema del subsistema."""
        from apps.common.choices import TipoAPU
        creadas = self._generar_categoria_desde_catalogo(TipoAPU.ADMINISTRACION, items_data)
        logger.info("[APUService] %d categorías administración para APU %s.", len(creadas), self.apu.pk)
        return creadas

    # ── Métodos legados (mantenidos por compatibilidad con vistas existentes) ──

    @transaction.atomic
    def generar_transporte_items(self, items: List[Dict]) -> List[dict]:
        """
        Legado: genera APULineas TRANSPORTE a partir de ítems libres (sin catálogo).
        items: [{"descripcion": str, "precio_total": float}]
        Para proyectos nuevos, use generar_transporte_desde_catalogo.
        """
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        tp = self._get_total_powergrip()
        creadas = []

        for item in items:
            desc = item["descripcion"].strip()
            precio_total = float(item["precio_total"])
            precio_ref = precio_total / float(tp)

            linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.TRANSPORTE,
                descripcion=desc,
                defaults={
                    "rendimiento": Decimal("1"),
                    "unidad": "global",
                    "precio_referencia": Decimal(str(round(precio_ref, 6))),
                    "iva_aplicado": False,
                    "editable": True,
                },
            )
            linea.calcular()
            creadas.append({"descripcion": linea.descripcion, "costo_unitario": float(linea.costo_unitario)})

        logger.info("[APUService] %d líneas transporte (legado) para APU %s.", len(creadas), self.apu.pk)
        return creadas

    @transaction.atomic
    def generar_administracion(self, costo_total_admin: float) -> dict:
        """Legado: genera una APULinea ADMINISTRACION con costo absoluto."""
        return self.generar_administracion_item("Administración", costo_total_admin)

    @transaction.atomic
    def generar_administracion_item(self, descripcion: str, costo_total: float) -> dict:
        """
        Legado: genera/actualiza una APULinea ADMINISTRACION con descripción específica.
        Para proyectos nuevos, use generar_administracion_desde_catalogo.
        """
        from apps.presupuestos.models import APULinea
        from apps.common.choices import TipoAPU

        tp = self._get_total_powergrip()
        precio_ref = costo_total / float(tp)

        linea, _ = APULinea.objects.update_or_create(
            apu=self.apu,
            tipo=TipoAPU.ADMINISTRACION,
            descripcion=descripcion,
            defaults={
                "rendimiento": Decimal("1"),
                "unidad": "global",
                "precio_referencia": Decimal(str(round(precio_ref, 6))),
                "iva_aplicado": False,
                "editable": True,
            },
        )
        linea.calcular()
        logger.debug(
            "[APUService] Admin '%s' APU %s | costo_total=%.2f | tp=%.4f | precio_ref=%.6f",
            descripcion, self.apu.pk, costo_total, float(tp), precio_ref,
        )
        return {"descripcion": descripcion, "costo_unitario": float(linea.costo_unitario)}

    # ── Helper: estimar días de trabajo ───────────────────────────────────────

    def _estimar_dias(self) -> float:
        """
        Estima los días de trabajo necesarios.
        Prioridad:
        1. proyecto.num_personas si está definido.
        2. Líneas MO ya registradas (infiere personas desde su cantidad).
        Fallback: 7 personas estándar (cuadrilla de instalación).
        """
        from apps.common.choices import TipoAPU

        # Intentar obtener num_personas del proyecto
        num_personas_proyecto = None
        if self.apu.proyecto_sistema_id:
            try:
                proyecto = self.apu.proyecto_sistema.proyecto
                num_personas_proyecto = proyecto.num_personas
            except Exception:
                pass

        total_personas = (
            num_personas_proyecto
            or self.apu.lineas.filter(tipo=TipoAPU.MANO_DE_OBRA).count()
            or 7  # cuadrilla estándar
        )

        tp   = self._get_total_unidades()
        dias = tp / (total_personas * 40)
        return max(dias, 1.0)

    # ── Cierre ────────────────────────────────────────────────────────────────

    def finalizar(self) -> dict:
        """
        Recalcula totales del APU y avanza el estado del proyecto a APU en proceso.
        Devuelve un resumen de totales.
        """
        from apps.common.choices import EstadoProyecto

        self.apu.recalcular()
        proyecto = self.ps.proyecto

        if proyecto.estado not in (EstadoProyecto.APU, EstadoProyecto.APU_GENERADO):
            proyecto.avanzar_a_apu()

        logger.info(
            "[APUService] APU %s finalizado | costo=%.2f | venta=%.2f | estado='%s'.",
            self.apu.pk,
            float(self.apu.total_costo),
            float(self.apu.total_valor_venta),
            proyecto.estado,
        )

        return {
            "total_costo": float(self.apu.total_costo),
            "total_valor_venta": float(self.apu.total_valor_venta),
            "subtotales": {
                "materiales": float(self.apu.subtotal_materiales),
                "herramientas": float(self.apu.subtotal_herramientas),
                "transporte": float(self.apu.subtotal_transporte),
                "mano_obra": float(self.apu.subtotal_mano_obra),
                "administracion": float(self.apu.subtotal_administracion),
            },
        }
    