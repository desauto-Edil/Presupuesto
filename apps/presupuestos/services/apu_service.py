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


# Diferencia máxima entre un precio recibido del modal y el valor diario del
# catálogo para considerarlo "el mismo" (el modal redondea a 2 decimales).
TOLERANCIA_OVERRIDE = Decimal("0.005")


def _parse_override(precio_override):
    if precio_override is None or precio_override == "":
        return None
    try:
        valor = Decimal(str(precio_override))
    except (TypeError, ValueError, ArithmeticError):
        return None
    if valor < 0:
        return None
    return valor.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def resolver_precio_item(item, precio_override=None):
    """
    Precio diario efectivo de un ItemCatalogoAPU para el APU y si es override.

    Regla universal (Fase 1), idéntica para HERRAMIENTAS_EQUIPOS, MANO_DE_OBRA,
    TRANSPORTE y ADMINISTRACION:
        valor_diario = valor_base / vida_util_dias   (apps.presupuestos.economia)

    `precio_override` es un valor diario escrito por el usuario para ESTE APU;
    nunca modifica el catálogo. Si coincide con el valor diario del catálogo
    (±TOLERANCIA_OVERRIDE) no se considera override.

    Devuelve (Decimal precio, bool personalizado). Lanza ValorDiarioError si no
    hay override y el ítem no es calculable (p. ej. vida útil vacía).
    """
    from apps.presupuestos.economia import ValorDiarioError

    valor_diario = None
    error = None
    try:
        valor_diario = item.valor_diario
    except ValorDiarioError as exc:
        error = exc

    override = _parse_override(precio_override)
    if override is not None:
        if valor_diario is not None and abs(override - valor_diario) < TOLERANCIA_OVERRIDE:
            return valor_diario, False
        return override, True
    if error is not None:
        raise error
    return valor_diario, False


def normalizar_cantidad(valor) -> Decimal:
    """Cantidad de un componente como Decimal > 0 (4 decimales).

    Vacía, no numérica o <= 0 → 1, igual que el contrato de Fase 1 para los
    modales (que solo envían enteros >= 1). Los paquetes admiten decimales.
    """
    try:
        cantidad = Decimal(str(valor)) if valor not in (None, "") else Decimal("1")
    except (TypeError, ValueError, ArithmeticError):
        return Decimal("1")
    if cantidad <= 0:
        return Decimal("1")
    return cantidad.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def cantidad_para_formulario(cantidad):
    """int si la cantidad es entera (los inputs numéricos no aceptan '2.0000')."""
    cantidad = Decimal(str(cantidad))
    return int(cantidad) if cantidad == cantidad.to_integral_value() else cantidad.normalize()


def precio_efectivo_item(item, precio_override=None) -> Decimal:
    """Precio diario efectivo (ver `resolver_precio_item`)."""
    return resolver_precio_item(item, precio_override)[0]


_CLAVES_UNIDAD_REFERENCIA = (
    "total_powergrip",
    "total_unidades",
    "cantidad",
    "n_apoyos",
    "ml_fachada",
    "m2",
    "area_m2",
)

# ---------------------------------------------------------------------------
# Contexto canónico para el motor de fórmulas
# ---------------------------------------------------------------------------

def build_formula_context(
    suma: float,
    dias: float,
    aiu: float,
    margen_mo: float,
    tp,
    num_personas: int = 1,
    margen_material_pct=None,
    proyecto=None,
    ps=None,
) -> dict:
    """
    Construye el diccionario de variables disponibles para evaluar cualquier
    fórmula del sistema (ReglaAPUSubsistema, componentes de garantía, etc.).

    Esta es la función pública canónica. El resto del sistema (APUService,
    calculadores, previews) debe llamar siempre a esta función — nunca construir
    el diccionario de forma ad-hoc.

    Variables inyectadas:
        suma             — suma de costos de todos los ítems de la categoría
        aiu              — factor AIU contratista (e.g. 1.30 si AIU=30%)
        margen_mano_obra — factor margen de mano de obra (e.g. 1.20 si margen=20%)
        margen_material  — factor margen de material (e.g. 1.20 si margen=20%)
        dias             — días efectivos
        tp               — total_powergrip (unidades del producto base, denominador)
        personas         — número de personas en cuadrilla
        trm              — TRM vigente (COP/USD). Si el proyecto tiene trm guardada,
                           se usa esa; si no, se obtiene la TRM global.
        margen           — alias histórico de margen_mano_obra
        factor_venta     — alias histórico de margen_material
        <var_ref>        — variable de referencia del subsistema (ej: "total_powergrip")
                           si difiere de "tp"; inyectada con el mismo valor que tp.
        <param_*>        — parámetros de entrada del ProyectoSistema (ps).

    Los alias existen para que las reglas escritas antes del renombramiento
    sigan evaluando. En reglas nuevas usar los nombres explícitos.

    Args:
        suma:                suma de costos de la categoría
        dias:                días efectivos
        aiu:                 factor AIU contratista
        margen_mo:           factor margen de mano de obra
        tp:                  total unidades del producto base
        num_personas:        personas en cuadrilla
        margen_material_pct: porcentaje de margen de material (None=0)
        proyecto:            instancia de Proyecto (opcional; para leer proyecto.trm)
        ps:                  instancia de ProyectoSistema (opcional; var_ref y params)
    """
    from apps.common.trm_service import obtener_trm_vigente, TRMNoDisponibleError

    tp_float = float(tp) if tp is not None else 0.0
    mat_pct = float(margen_material_pct) if margen_material_pct is not None else 0.0

    # TRM: preferir la del proyecto (contractual); fallback a la global.
    trm_val: float
    proyecto_trm = getattr(proyecto, "trm", None) if proyecto else None
    if proyecto_trm is not None and float(proyecto_trm) > 0:
        trm_val = float(proyecto_trm)
    else:
        try:
            trm_val = float(obtener_trm_vigente())
        except TRMNoDisponibleError:
            trm_val = 0.0  # Sin TRM disponible; la fórmula fallará explícitamente
            logger.warning("TRM no disponible al evaluar fórmula; trm=0.0")

    margen_mano_obra = float(margen_mo)
    margen_material  = 1.0 + mat_pct / 100.0

    ctx: dict = {
        "suma":             float(suma),
        "aiu":              float(aiu),
        "margen_mano_obra": margen_mano_obra,
        "margen_material":  margen_material,
        "dias":             float(dias),
        "tp":               tp_float,
        "personas":         int(num_personas),
        "trm":              trm_val,
        # Alias de compatibilidad con reglas anteriores al renombramiento
        "margen":           margen_mano_obra,
        "factor_venta":     margen_material,
    }

    # Variable de referencia del subsistema (si difiere de "tp")
    if ps is not None:
        sub = getattr(ps, "subsistema", None)
        var_ref = (getattr(sub, "variable_referencia_apu", None) or "tp") if sub else "tp"
        if var_ref and var_ref != "tp":
            ctx[var_ref] = tp_float

        # Parámetros de entrada del ProyectoSistema
        for k, v in (getattr(ps, "parametros_entrada", None) or {}).items():
            if k not in ctx:
                try:
                    ctx[k] = float(v)
                except (TypeError, ValueError):
                    pass

    return ctx


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

        def _pct(campo: str):
            """Valor del proyecto si está definido; si no, el de la configuración global."""
            valor = getattr(_proyecto, campo, None)
            return self.cfg_valor(campo) if valor is None else valor

        self.apu, created = APU.objects.get_or_create(
            proyecto_sistema=proyecto_sistema,
            defaults={
                "nombre": nombre_default,
                "descripcion": "",
                # Los márgenes y el AIU se siembran desde el proyecto (el asesor los
                # fija al crearlo); la ConfiguracionAPU global queda como respaldo.
                "margen_material_pct": _pct("margen_material_pct"),
                "iva_pct": getattr(_proyecto, "iva_pct", self.cfg.iva_pct),
                "aplica_iva": not getattr(_proyecto, "aplica_exencion_iva", False),
                "aiu_contratista_pct": _pct("aiu_contratista_pct"),
                "margen_mano_obra_pct": _pct("margen_mano_obra_pct"),
                # Sin respaldo global: 0 % si el proyecto no lo define.
                "margen_contratista_pct": getattr(_proyecto, "margen_contratista_pct", None) or Decimal("0"),
                "dias_duracion": _dias,
            },
        )
        logger.info(
            "[APUService] APU %s (%s) para PS %s | config='%s'.",
            self.apu.pk, "nuevo" if created else "existente",
            proyecto_sistema.pk, self.cfg.nombre,
        )

    def cfg_valor(self, campo: str):
        """Lee un porcentaje de la ConfiguracionAPU global."""
        return getattr(self.cfg, campo)

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
    def generar(cls, proyecto_sistema, despiece_origen=None) -> "APU":
        """
        Punto de entrada principal.
        Regenera materiales del despiece raíz, conserva los de los despieces
        secundarios activos (multi-despiece), auto-puebla los tipos
        no-materiales vacíos desde SubsistemaItemAPU y finaliza.

        `despiece_origen`: DespieceMaestro cuyo contenido acaba de volcarse en
        el ProyectoSistema (flujo "Armar mi APU"). Si es None se conserva el
        origen que el APU ya tenía.
        """
        svc = cls(proyecto_sistema)
        origen_previo_id = svc._despiece_origen_actual_id()
        svc.generar_materiales()
        svc._restaurar_multidespiece(origen_previo_id, despiece_origen)
        svc._auto_generar_desde_catalogo()
        svc.finalizar()
        return svc.apu

    # ── Multi-despiece: conservar despieces secundarios ──────────────────────

    def _despiece_origen_actual_id(self):
        """DespieceMaestro de las líneas MATERIALES que vienen del ProyectoSistema
        raíz (despiece_linea no nulo). None si no hay (APU nuevo o legacy)."""
        from apps.common.choices import TipoAPU
        return (
            self.apu.lineas
            .filter(
                tipo=TipoAPU.MATERIALES,
                despiece_linea__isnull=False,
                despiece_maestro__isnull=False,
            )
            .values_list("despiece_maestro_id", flat=True)
            .first()
        )

    def _restaurar_multidespiece(self, origen_previo_id, despiece_origen=None) -> int:
        """Tras `generar_materiales()` (que borra TODOS los materiales), vuelve a
        anotar el despiece raíz y reconstruye los materiales de cada despiece
        secundario activo en APUDespieceIncluido.

        - Si llega `despiece_origen` y reemplaza a otro origen previo, la
          inclusión del origen previo se desactiva (su contenido ya no está
          en el ProyectoSistema).
        - Devuelve el número de líneas secundarias creadas.
        """
        from apps.common.choices import TipoAPU
        from apps.presupuestos.services.apu_multi_builder import APUMultiDespieceBuilder

        inclusiones = list(
            self.apu.despieces_incluidos
            .filter(activo=True)
            .select_related("despiece_maestro", "despiece_maestro__subsistema",
                            "despiece_maestro__subsistema__sistema")
            .order_by("orden", "id")
        )
        if despiece_origen is not None:
            origen_id = despiece_origen.pk
            if origen_previo_id and origen_previo_id != origen_id:
                self.apu.despieces_incluidos.filter(
                    despiece_maestro_id=origen_previo_id
                ).update(activo=False)
                inclusiones = [i for i in inclusiones if i.despiece_maestro_id != origen_previo_id]
        elif origen_previo_id:
            origen_id = origen_previo_id
        elif inclusiones:
            # Legacy sin anotación: el origen es la primera inclusión (orden 0).
            origen_id = inclusiones[0].despiece_maestro_id
        else:
            return 0

        # Re-anotar las líneas del PS raíz con su despiece de origen.
        inc_origen = next((i for i in inclusiones if i.despiece_maestro_id == origen_id), None)
        if inc_origen is not None:
            self.apu.lineas.filter(
                tipo=TipoAPU.MATERIALES, despiece_maestro__isnull=True,
            ).update(
                despiece_maestro_id=origen_id,
                sistema_nombre_snapshot=inc_origen.sistema_nombre_snapshot,
                subsistema_nombre_snapshot=inc_origen.subsistema_nombre_snapshot,
            )

        secundarios = [i.despiece_maestro for i in inclusiones if i.despiece_maestro_id != origen_id]
        if not secundarios:
            return 0
        builder = APUMultiDespieceBuilder(
            apu=self.apu,
            despieces_seleccionados=[i.despiece_maestro for i in inclusiones],
            despiece_origen=inc_origen.despiece_maestro if inc_origen else None,
        )
        creadas = sum(builder._materiales_secundarios(dm) for dm in secundarios)
        logger.info(
            "[APUService] APU %s: %d materiales restaurados de %d despiece(s) secundario(s).",
            self.apu.pk, creadas, len(secundarios),
        )
        return creadas

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
            .values("item_catalogo_id", "cantidad", "rendimiento_override")
        )
        return [
            {
                "item_id": row["item_catalogo_id"],
                "cantidad": row["cantidad"],
                "porcentaje": row["rendimiento_override"],
            }
            for row in qs
        ]

    def _paquetes_subsistema(self, tipo_apu: str) -> list:
        """Fase 2 — paquetes maestros activos asignados al subsistema para el tipo."""
        from apps.presupuestos.models import SubsistemaPaqueteAPU

        ps = self.ps
        if not ps or not ps.subsistema_id:
            return []
        return [
            asig.paquete
            for asig in SubsistemaPaqueteAPU.objects
            .filter(subsistema_id=ps.subsistema_id, activo=True,
                    paquete__activo=True, paquete__tipo_apu=tipo_apu)
            .select_related("paquete")
            .order_by("orden", "id")
        ]

    def _auto_generar_desde_catalogo(self) -> None:
        """
        Auto-puebla el APU por cada TipoAPU no-material que aún no tenga líneas.

        Fase 2: si el subsistema tiene paquetes activos para el tipo, se
        instancian (APUPaquete + APULinea snapshot) y SubsistemaItemAPU NO se
        suma. Si no tiene paquetes, se usa SubsistemaItemAPU como respaldo
        (comportamiento de Fase 1). Sin ninguno de los dos, el tipo queda vacío:
        nunca se llena con todo el catálogo.
        """
        from apps.common.choices import TipoAPU

        tipos_existentes = set(self.apu.lineas.values_list("tipo", flat=True))
        generadores = (
            (TipoAPU.MANO_DE_OBRA, "MO", self.generar_mano_obra_desde_catalogo),
            (TipoAPU.HERRAMIENTAS_EQUIPOS, "HERRAMIENTAS", self.generar_herramientas_desde_catalogo),
            (TipoAPU.TRANSPORTE, "TRANSPORTE", self.generar_transporte_desde_catalogo),
            (TipoAPU.ADMINISTRACION, "ADMINISTRACION", self.generar_administracion_desde_catalogo),
        )
        for tipo, etiqueta, generar in generadores:
            if tipo in tipos_existentes:
                continue
            paquetes = self._paquetes_subsistema(tipo)
            if paquetes:
                self.instanciar_paquetes(paquetes)
                continue
            items_data = self._items_apu_subsistema(tipo)
            if items_data:
                generar(items_data)
            else:
                logger.info(
                    "[APUService] PS=%s subsistema=%s sin ítems APU configurados para %s; "
                    "la categoría queda vacía.",
                    self.ps.pk, getattr(self.ps.subsistema, "codigo", None), etiqueta,
                )

    # ── Helpers: referencia del producto base (PowerGrip) ─────────────────────

    def _get_total_unidades(self) -> float:
        """
        Determina la cantidad de referencia del sistema (denominador del APU por unidad).
        Prioridad (Sub-fase D — base APU declarativa):
          0. Suma de variables con `participa_en_base_apu=True` (NUEVO).
             Si hay al menos una variable marcada y el resultado es > 0, se usa.
          1. variable_referencia_apu del subsistema (si está definida en parametros_entrada)
          2. Búsqueda genérica por _CLAVES_UNIDAD_REFERENCIA
          3. Fallback: area_total_m2 del proyecto
        Mínimo devuelto: 1.0
        """
        params = self.ps.parametros_entrada or {}

        # 0. Sub-fase D — Suma de variables marcadas como base APU.
        sub = self.ps.subsistema
        if sub is not None:
            try:
                from apps.ingenieria.models import VariableSubsistema
                vars_base = VariableSubsistema.objects.filter(
                    subsistema=sub, participa_en_base_apu=True,
                ).values_list("variable", flat=True)
                area_base_apu = 0.0
                hubo_marcadas = False
                for nombre in vars_base:
                    hubo_marcadas = True
                    raw = params.get(nombre)
                    if raw in (None, ""):
                        continue
                    try:
                        area_base_apu += float(raw)
                    except (ValueError, TypeError):
                        continue
                if hubo_marcadas and area_base_apu > 0:
                    logger.debug(
                        "[APUService] _get_total_unidades: area_base_apu=%.4f desde "
                        "variables marcadas (PS %s)",
                        area_base_apu, self.ps.pk,
                    )
                    return area_base_apu
                if hubo_marcadas:
                    # Hay variables marcadas pero suma <= 0: advertencia y caer al fallback.
                    logger.warning(
                        "[APUService] PS=%s: variables con participa_en_base_apu=True "
                        "presentes pero su suma es 0 o no numérica. Cayendo al "
                        "comportamiento anterior (variable_referencia_apu / producto principal).",
                        self.ps.pk,
                    )
            except Exception:
                logger.exception(
                    "[APUService] PS=%s: error calculando area_base_apu — fallback al flujo previo.",
                    self.ps.pk,
                )

        # 1. Variable explícita definida en el subsistema
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

    def _get_num_personas(self) -> int:
        """
        Valor de la variable `personas` de ReglaAPUSubsistema.

        Fase 1: ya no se detecta "personal" por salario/prestaciones.
        personas = Proyecto.num_personas si está definido; si no, 1.
        """
        if self.ps is not None:
            np = getattr(self.ps.proyecto, "num_personas", None)
            if np and int(np) > 0:
                return int(np)
        return 1

    # ── Helper: contexto de regla APU ─────────────────────────────────────────

    def _build_regla_context(
        self,
        suma: float,
        dias_efectivos: float,
        aiu: float,
        margen_mo: float,
        tp,
        num_personas: int = 1,
    ) -> dict:
        """
        Delegado a build_formula_context() — mantiene la interfaz interna
        para no romper llamadas existentes dentro de APUService.

        El Proyecto se pasa para que `trm` use Proyecto.trm cuando exista
        (build_formula_context aplica el respaldo global si es NULL).
        """
        proyecto = self.ps.proyecto if self.ps is not None else None
        return build_formula_context(
            suma=suma,
            dias=dias_efectivos,
            aiu=aiu,
            margen_mo=margen_mo,
            tp=tp,
            num_personas=num_personas,
            margen_material_pct=self.apu.margen_material_pct,
            proyecto=proyecto,
            ps=self.ps,
        )

    # ── Carga de ítems de catálogo (regla económica universal) ───────────────

    def _cargar_items_catalogo(self, tipo_apu: str, items_data: List[Dict]) -> List[dict]:
        """Resuelve cada fila de `items_data` a su precio diario efectivo.

        Devuelve dicts {item, cantidad, precio, personalizado, porcentaje}.
        Si algún ítem no tiene valor diario calculable (p. ej. vida útil
        vacía) y no trae override, lanza ValorDiarioError listándolos todos:
        el APU no se calcula con datos incompletos.
        """
        from apps.presupuestos.models import ItemCatalogoAPU
        from apps.presupuestos.economia import ValorDiarioError

        cargados: List[dict] = []
        pendientes: List[str] = []
        for d in items_data:
            item = ItemCatalogoAPU.objects.select_related("categoria").get(pk=d["item_id"])
            cantidad = normalizar_cantidad(d.get("cantidad"))
            try:
                precio, personalizado = resolver_precio_item(item, d.get("precio_override"))
            except ValorDiarioError as exc:
                pendientes.append(f"«{item.nombre}» ({exc})")
                continue
            porcentaje = d.get("porcentaje")
            cargados.append({
                "item": item,
                "cantidad": cantidad,
                "precio": precio,
                "personalizado": personalizado,
                "porcentaje": 1.0 if porcentaje is None else float(porcentaje),
            })
        if pendientes:
            raise ValorDiarioError(
                f"No se puede calcular {tipo_apu}: hay ítems sin valor diario calculable "
                f"(configure su vida útil en el catálogo APU): {'; '.join(pendientes)}."
            )
        return cargados

    def _crear_linea_detalle(self, tipo_apu: str, cargado: dict, rendimiento: Decimal,
                             apu_paquete=None):
        """Línea detalle de catálogo (costo 0; el costo real vive en la resumen)."""
        from apps.presupuestos.models import APULinea

        item = cargado["item"]
        return APULinea.objects.create(
            apu=self.apu,
            apu_paquete=apu_paquete,
            tipo=tipo_apu,
            item_catalogo=item,
            descripcion=item.nombre,
            rendimiento=rendimiento,
            cantidad=Decimal(cargado["cantidad"]),
            unidad=item.unidad,
            precio_referencia=cargado["precio"],
            precio_personalizado=cargado["personalizado"],
            vida_util_dias=item.vida_util_dias,
            costo_unitario=Decimal("0"),
            costo_total=Decimal("0"),
            valor_unitario=Decimal("0"),
            valor_total=Decimal("0"),
            iva_aplicado=False,
            editable=False,
            tienda_referencia=item.tienda_referencia,
        )

    # ── Generador unificado por categoría (no-MATERIALES) ────────────────────

    @transaction.atomic
    def _generar_categoria_desde_catalogo(
        self,
        tipo_apu: str,
        items_data: List[Dict],
    ) -> List[dict]:
        """
        Genera APULineas para HERRAMIENTAS_EQUIPOS, MANO_DE_OBRA y TRANSPORTE
        usando ReglaAPUSubsistema para obtener el costo unitario.

        Patrón: por cada CategoriaItemAPU presente en items_data se crean:
          - N líneas detalle (item_catalogo set, costo_total=0) — referencia visual
          - 1 línea resumen (item_catalogo=None) — contiene el costo real

        items_data: [{"item_id": int, "cantidad": int, "precio_override": num|None}]

        Regla económica universal (Fase 1):
            valor_diario = valor_base / vida_util_dias   (o override del APU)
            suma         = Σ(valor_diario × cantidad)    por categoría
        `suma` y el resto del contexto llegan a la fórmula sin cambios de nombre.
        El catálogo nunca se modifica.
        """
        from apps.presupuestos.models import APULinea, ReglaAPUSubsistema
        from apps.presupuestos.economia import calcular_aporte
        from collections import defaultdict

        if self._tipo_usa_paquetes(tipo_apu):
            return self._reemplazar_sueltos(tipo_apu, items_data)

        dias_duracion = float(self.apu.dias_duracion or 0)
        if dias_duracion <= 0:
            raise ValueError("El parámetro 'Días de duración' del APU debe ser mayor que cero.")

        tp  = self._get_total_powergrip()
        aiu = 1 + float(self.apu.aiu_contratista_pct) / 100
        mmo = 1 + float(self.apu.margen_mano_obra_pct) / 100

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

        cargados = self._cargar_items_catalogo(tipo_apu, items_data)
        num_personas = self._get_num_personas()

        # Eliminar líneas existentes del tipo para regenerar limpio
        self.apu.lineas.filter(tipo=tipo_apu).delete()

        # Agrupar por categoría
        por_categoria: dict = defaultdict(list)
        for c in cargados:
            por_categoria[c["item"].categoria_id].append(c)

        creadas = []
        for cat_id, items_en_cat in por_categoria.items():
            categoria = items_en_cat[0]["item"].categoria

            suma = sum(
                (calcular_aporte(c["precio"], c["cantidad"]) for c in items_en_cat),
                Decimal("0"),
            )

            # Evaluar fórmula → costo unitario de la categoría
            ctx = self._build_regla_context(float(suma), dias_duracion, aiu, mmo, tp, num_personas)
            costo_unitario_cat = regla.evaluar(ctx)

            logger.debug(
                "[APUService] %s cat='%s' | suma=%s | ctx=%s | cu=%.6f",
                tipo_apu, categoria.nombre, suma, ctx, costo_unitario_cat,
            )

            # Líneas detalle: guardan cantidad, valor diario usado y si es override.
            for c in items_en_cat:
                self._crear_linea_detalle(tipo_apu, c, rendimiento=Decimal(c["cantidad"]))

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
                "suma_items":  float(suma),
                "costo_total": float(linea_resumen.costo_total),
            })
            logger.info(
                "[APUService] %s cat='%s' | n=%d | suma=%s | tp=%.4f | cu=%.6f",
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
        rendimiento = cantidad_comercial / base   (ver `cantidad_final_apu`)
        Omite líneas pendientes_seleccion o sin producto.

        Redondeo: se usa la cantidad COMERCIAL redondeada de cada línea
        (la que el usuario vio en el Despiece Maestro), no el resultado
        exacto de la fórmula. En modo PRODUCTO_PRINCIPAL la base también es
        comercial, de modo que la línea del producto principal mantiene
        rendimiento = 1 exacto.

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
            # Cantidad COMERCIAL (redondeada), no la exacta del cálculo: el APU
            # debe valorizar lo que realmente se compra, igual que el despiece.
            cantidad = float(dl.cantidad_final_apu or 0)

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
    def _generar_administracion_con_regla(self, items_data: List[Dict]) -> List[dict]:
        """
        Genera APULineas ADMINISTRACION usando ReglaAPUSubsistema × porcentaje.

        Por cada CategoriaItemAPU crea:
          - N líneas detalle (item_catalogo set, costo_total=0):
              cantidad          = cantidad del ítem
              precio_referencia = valor diario (catálogo u override)
              rendimiento       = porcentaje individual (fracción) → re-marcado del modal
          - 1 línea resumen (item_catalogo=None):
              precio_referencia = resultado bruto de la fórmula del subsistema
              rendimiento       = porcentaje promedio de la categoría (fracción 0–2)
              costo_total       = precio_referencia × rendimiento   (via calcular())

        `suma` = Σ(valor_diario × cantidad), igual que en las demás categorías.
        """
        from apps.presupuestos.models import APULinea, ReglaAPUSubsistema
        from apps.presupuestos.economia import calcular_aporte
        from collections import defaultdict
        from apps.common.choices import TipoAPU

        if not items_data:
            return []

        if self._tipo_usa_paquetes(TipoAPU.ADMINISTRACION):
            return self._reemplazar_sueltos(TipoAPU.ADMINISTRACION, items_data)

        dias_duracion = float(self.apu.dias_duracion or 0)
        if dias_duracion <= 0:
            raise ValueError("El parámetro 'Días de duración' del APU debe ser mayor que cero.")

        tp  = self._get_total_powergrip()
        aiu = 1 + float(self.apu.aiu_contratista_pct) / 100
        mmo = 1 + float(self.apu.margen_mano_obra_pct) / 100

        try:
            regla = ReglaAPUSubsistema.objects.get(
                subsistema=self.ps.subsistema,
                tipo_apu=TipoAPU.ADMINISTRACION,
            )
        except ReglaAPUSubsistema.DoesNotExist:
            raise ValueError(
                f"No existe ReglaAPUSubsistema para subsistema='{self.ps.subsistema}' "
                f"y tipo_apu='ADMINISTRACION'. Defínala en la edición del Subsistema."
            )

        cargados = self._cargar_items_catalogo(TipoAPU.ADMINISTRACION, items_data)
        num_personas = self._get_num_personas()

        # Eliminar líneas ADMINISTRACION existentes
        self.apu.lineas.filter(tipo=TipoAPU.ADMINISTRACION).delete()

        por_categoria: dict = defaultdict(list)
        for c in cargados:
            por_categoria[c["item"].categoria_id].append(c)

        creadas = []
        for cat_id, items_en_cat in por_categoria.items():
            categoria = items_en_cat[0]["item"].categoria

            suma = sum(
                (calcular_aporte(c["precio"], c["cantidad"]) for c in items_en_cat),
                Decimal("0"),
            )

            # Evaluar fórmula del subsistema → resultado BRUTO (sin porcentaje)
            ctx        = self._build_regla_context(float(suma), dias_duracion, aiu, mmo, tp, num_personas)
            costo_bruto = regla.evaluar(ctx)

            # Porcentaje promedio de la categoría
            pcts_cat = [c["porcentaje"] for c in items_en_cat]
            escala   = sum(pcts_cat) / len(pcts_cat) if pcts_cat else 1.0

            # ── Líneas detalle (referencia visual + re-marcado de modal) ─────
            for c in items_en_cat:
                self._crear_linea_detalle(
                    TipoAPU.ADMINISTRACION, c,
                    rendimiento=Decimal(str(round(c["porcentaje"], 6))),
                )

            # ── Línea resumen ─────────────────────────────────────────────────
            precio_ref = Decimal(str(costo_bruto)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            linea_resumen = APULinea.objects.create(
                apu=self.apu,
                tipo=TipoAPU.ADMINISTRACION,
                item_catalogo=None,
                despiece_linea=None,
                descripcion=categoria.nombre,
                rendimiento=Decimal(str(round(escala, 6))),
                unidad="global",
                precio_referencia=precio_ref,
                iva_aplicado=False,
                editable=True,
            )
            linea_resumen.calcular()

            creadas.append({
                "descripcion": categoria.nombre,
                "suma_items":  float(suma),
                "costo_bruto": costo_bruto,
                "escala":      escala,
                "costo_total": float(linea_resumen.costo_total),
            })
            logger.info(
                "[APUService] Admin cat='%s' | suma=%s | bruto=%.2f | escala=%.4f | total=%.2f",
                categoria.nombre, suma, costo_bruto, escala, float(linea_resumen.costo_total),
            )

        return creadas

    @transaction.atomic
    def generar_administracion_desde_catalogo(self, items_data: List[Dict]) -> List[dict]:
        """Genera APULineas ADMINISTRACION usando ReglaAPUSubsistema × porcentaje.

        Fórmula:
            costo = regla_subsistema(ítems_categoría) × porcentaje_usuario

        El porcentaje (0.0–1.0, fracción) se promedia por categoría y se almacena
        en `rendimiento` de la línea resumen. La línea detalle guarda el porcentaje
        individual por ítem para pre-llenar el modal al reabrirlo.
        """
        creadas = self._generar_administracion_con_regla(items_data)
        logger.info(
            "[APUService] %d categoría(s) de administración (regla × porcentaje) para APU %s.",
            len(creadas), self.apu.pk,
        )
        return creadas

    # ── Recálculo por cambio de parámetros (Fase 1) ──────────────────────────

    def items_data_desde_lineas(self, tipo_apu: str) -> List[Dict]:
        """Reconstruye la selección aplicada al APU para `tipo_apu` a partir de
        sus líneas detalle (ítem de catálogo, cantidad, override y % admin).

        Es la fuente de verdad de lo que el usuario/subsistema dejó en el APU;
        NUNCA se completa con el resto del catálogo activo.

        Líneas anteriores a la Fase 1 (sin `cantidad`): en no-materiales la
        cantidad se guardaba en `rendimiento`; en ADMINISTRACION `rendimiento`
        es el porcentaje y la cantidad no se guardaba (→ 1).
        """
        from apps.common.choices import TipoAPU

        data: List[Dict] = []
        # Solo ítems sueltos: los componentes de paquetes (apu_paquete) tienen su
        # propio ciclo de vida y nunca se reconstruyen desde aquí.
        lineas = (
            self.apu.lineas
            .filter(tipo=tipo_apu, item_catalogo__isnull=False, apu_paquete__isnull=True)
            .order_by("id")
        )
        for ln in lineas:
            if tipo_apu == TipoAPU.ADMINISTRACION:
                cantidad = ln.cantidad if ln.cantidad is not None else Decimal("1")
                porcentaje = float(ln.rendimiento) if ln.rendimiento is not None else None
            else:
                cantidad = ln.cantidad if ln.cantidad is not None else ln.rendimiento
                porcentaje = None
            data.append({
                "item_id": ln.item_catalogo_id,
                "cantidad": cantidad_para_formulario(normalizar_cantidad(cantidad)),
                "precio_override": ln.precio_referencia if ln.precio_personalizado else None,
                "porcentaje": porcentaje,
            })
        return data

    @transaction.atomic
    def recalcular_por_parametros(self) -> dict:
        """Recalcula el APU tras cambiar parámetros (márgenes, IVA, AIU, días).

        - MATERIALES: `iva_aplicado` se alinea con `apu.aplica_iva` y cada línea
          vuelve a ejecutar `calcular()` con el margen/IVA vigentes. No toca el
          despiece.
        - No-materiales: cada tipo se regenera con SU PROPIA selección
          (`items_data_desde_lineas`): mismos ítems, cantidades, overrides
          válidos y porcentajes de Administración. Tipos sin líneas de
          catálogo no se tocan.
        """
        from apps.common.choices import TipoAPU

        self._verificar_editable()
        materiales = 0
        for ln in self.apu.lineas.filter(tipo=TipoAPU.MATERIALES):
            if ln.iva_aplicado != self.apu.aplica_iva:
                ln.iva_aplicado = self.apu.aplica_iva
                ln.save(update_fields=["iva_aplicado", "updated_at"])
            ln.calcular()
            materiales += 1

        regenerados = []
        if self.ps is not None:
            for tipo in (
                TipoAPU.MANO_DE_OBRA,
                TipoAPU.HERRAMIENTAS_EQUIPOS,
                TipoAPU.TRANSPORTE,
                TipoAPU.ADMINISTRACION,
            ):
                if self.recalcular_tipo(tipo, refrescar_catalogo=True):
                    regenerados.append(tipo)

        # Tipos que no se regeneran (p. ej. líneas manuales sin ítem de catálogo):
        # se recalculan con sus mismos datos para aplicar márgenes/IVA vigentes
        # (margen de contratista en el valor unitario).
        for ln in self.apu.lineas.exclude(tipo=TipoAPU.MATERIALES).exclude(tipo__in=regenerados):
            ln.calcular()

        self.apu.recalcular()
        return {"materiales": materiales, "tipos_regenerados": regenerados}

    # ── Paquetes APU (Fase 2) ─────────────────────────────────────────────────

    def _verificar_editable(self) -> None:
        """Un APU aprobado es de solo lectura (regla de apps.common.apu_lock)."""
        from apps.common.apu_lock import MENSAJE_BLOQUEO
        if self.apu.esta_aprobado:
            raise PermissionError(MENSAJE_BLOQUEO)

    def _tipo_usa_paquetes(self, tipo_apu: str) -> bool:
        return self.apu.paquetes.filter(tipo_apu=tipo_apu).exists()

    def _lineas_componentes(self, tipo_apu: str):
        """Líneas detalle del tipo: componentes de paquetes + ítems sueltos."""
        from django.db.models import Q
        return (
            self.apu.lineas
            .filter(tipo=tipo_apu)
            .filter(Q(item_catalogo__isnull=False) | Q(apu_paquete__isnull=False))
            .select_related("item_catalogo", "apu_paquete")
            .order_by("apu_paquete__orden", "apu_paquete_id", "id")
        )

    def _lineas_resumen(self, tipo_apu: str):
        return self.apu.lineas.filter(
            tipo=tipo_apu, item_catalogo__isnull=True,
            despiece_linea__isnull=True, apu_paquete__isnull=True,
        )

    @staticmethod
    def _cantidad_linea(ln, tipo_apu: str) -> Decimal:
        """Cantidad del componente; líneas previas a Fase 1 la guardaban en rendimiento."""
        from apps.common.choices import TipoAPU
        if ln.cantidad is not None:
            return Decimal(str(ln.cantidad))
        if tipo_apu == TipoAPU.ADMINISTRACION:
            return Decimal("1")
        return Decimal(str(ln.rendimiento or 1))

    def _recalcular_tipo_paquetes(self, tipo_apu: str, refrescar_catalogo: bool = False):
        """Resumen única del TipoAPU cuando el tipo tiene paquetes instanciados.

            aporte          = precio_referencia × cantidad        (por componente)
            valor_paquete   = Σ aportes del APUPaquete
            suma            = Σ valor_paquete + Σ aportes de ítems sueltos del tipo
            resumen         = ReglaAPUSubsistema(suma)  — evaluada UNA vez
            ADMINISTRACION  : rendimiento de la resumen = promedio simple de los
                              porcentajes (rendimiento) de todos sus componentes

        La categoría no fragmenta la suma. `refrescar_catalogo` aplica el
        contrato de Fase 1: los componentes sin precio_personalizado toman el
        valor diario vigente del catálogo; los personalizados conservan el suyo.
        Nunca se consulta PaqueteAPUItem.
        """
        from apps.common.choices import TipoAPU
        from apps.presupuestos.economia import ValorDiarioError, calcular_aporte
        from apps.presupuestos.models import APULinea, ReglaAPUSubsistema

        componentes = list(self._lineas_componentes(tipo_apu))

        if refrescar_catalogo:
            pendientes = []
            for ln in componentes:
                if ln.precio_personalizado or ln.item_catalogo_id is None:
                    continue
                try:
                    vd = ln.item_catalogo.valor_diario
                except ValorDiarioError as exc:
                    pendientes.append(f"«{ln.descripcion}» ({exc})")
                    continue
                if ln.precio_referencia != vd:
                    ln.precio_referencia = vd
                    ln.save(update_fields=["precio_referencia", "updated_at"])
            if pendientes:
                raise ValorDiarioError(
                    f"No se puede calcular {tipo_apu}: hay ítems sin valor diario calculable "
                    f"(configure su vida útil en el catálogo APU): {'; '.join(pendientes)}."
                )

        if not componentes:
            self._lineas_resumen(tipo_apu).delete()
            return None

        dias_duracion = float(self.apu.dias_duracion or 0)
        if dias_duracion <= 0:
            raise ValueError("El parámetro 'Días de duración' del APU debe ser mayor que cero.")
        tp  = self._get_total_powergrip()
        aiu = 1 + float(self.apu.aiu_contratista_pct) / 100
        mmo = 1 + float(self.apu.margen_mano_obra_pct) / 100
        try:
            regla = ReglaAPUSubsistema.objects.get(subsistema=self.ps.subsistema, tipo_apu=tipo_apu)
        except ReglaAPUSubsistema.DoesNotExist:
            raise ValueError(
                f"No existe ReglaAPUSubsistema para subsistema='{self.ps.subsistema}' "
                f"y tipo_apu='{tipo_apu}'. Defínala en la edición del Subsistema."
            )

        suma = sum(
            (calcular_aporte(ln.precio_referencia, self._cantidad_linea(ln, tipo_apu))
             for ln in componentes),
            Decimal("0"),
        )
        ctx = self._build_regla_context(
            float(suma), dias_duracion, aiu, mmo, tp, self._get_num_personas(),
        )
        costo = regla.evaluar(ctx)

        # Rendimiento de la resumen: el que fijó el usuario (se conserva al
        # recalcular); si no, 1 — o, en ADMINISTRACION, el promedio de los %.
        previa = self._lineas_resumen(tipo_apu).filter(rendimiento_personalizado=True).first()
        if previa is not None:
            rendimiento = Decimal(str(previa.rendimiento))
        else:
            rendimiento = self._rendimiento_resumen_default(tipo_apu, componentes)

        self._lineas_resumen(tipo_apu).delete()
        resumen = APULinea.objects.create(
            apu=self.apu,
            tipo=tipo_apu,
            item_catalogo=None,
            despiece_linea=None,
            descripcion=TipoAPU(tipo_apu).label,
            rendimiento=rendimiento,
            rendimiento_personalizado=previa is not None,
            unidad="global",
            precio_referencia=Decimal(str(costo)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP),
            iva_aplicado=False,
            editable=True,
        )
        resumen.calcular()
        logger.info(
            "[APUService] %s (paquetes) APU %s | n=%d | suma=%s | cu=%.6f | rend=%s",
            tipo_apu, self.apu.pk, len(componentes), suma, costo, rendimiento,
        )
        return resumen

    @staticmethod
    def _rendimiento_resumen_default(tipo_apu: str, componentes) -> Decimal:
        """1 por defecto; ADMINISTRACION = promedio simple de los % de sus componentes."""
        from apps.common.choices import TipoAPU
        if tipo_apu == TipoAPU.ADMINISTRACION and componentes:
            pcts = [Decimal(str(ln.rendimiento if ln.rendimiento is not None else 1))
                    for ln in componentes]
            return (sum(pcts) / len(pcts)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        return Decimal("1")

    def actualizar_rendimiento_resumen(self, tipo_apu: str, rendimiento) -> None:
        """Fija (o restablece con None) el rendimiento de la resumen de un tipo
        calculado por paquetes y recalcula el APU. Solo cambia el rendimiento:
        costo unitario (fórmula) y componentes quedan igual."""
        if not self._tipo_usa_paquetes(tipo_apu):
            raise ValueError("Solo los tipos calculados por paquetes tienen rendimiento editable.")
        self._verificar_editable()
        with transaction.atomic():
            resumen = self._lineas_resumen(tipo_apu).first()
            if resumen is None:
                raise ValueError("El tipo no tiene resultado calculado.")
            if rendimiento is None:
                resumen.rendimiento = self._rendimiento_resumen_default(
                    tipo_apu, list(self._lineas_componentes(tipo_apu)))
                resumen.rendimiento_personalizado = False
            else:
                resumen.rendimiento = rendimiento
                resumen.rendimiento_personalizado = True
            resumen.save(update_fields=["rendimiento", "rendimiento_personalizado", "updated_at"])
            resumen.calcular()
            self.apu.recalcular()

    def recalcular_tipo(self, tipo_apu: str, refrescar_catalogo: bool = False) -> bool:
        """Recalcula un TipoAPU no-material con su propia estructura local.

        - Con paquetes instanciados → resumen única del tipo (_recalcular_tipo_paquetes).
        - Sin paquetes (APU histórico o solo ítems sueltos) → flujo de Fase 1
          por categoría a partir de sus propias líneas.
        Devuelve True si el tipo tenía algo que recalcular.
        """
        from apps.common.choices import TipoAPU

        if self._tipo_usa_paquetes(tipo_apu):
            self._recalcular_tipo_paquetes(tipo_apu, refrescar_catalogo=refrescar_catalogo)
            return True
        items_data = self.items_data_desde_lineas(tipo_apu)
        if not items_data:
            # Tipo sin componentes (p. ej. se eliminó su último paquete): sin resumen.
            if not self._lineas_componentes(tipo_apu).exists():
                self._lineas_resumen(tipo_apu).delete()
            return False
        if tipo_apu == TipoAPU.ADMINISTRACION:
            self._generar_administracion_con_regla(items_data)
        else:
            self._generar_categoria_desde_catalogo(tipo_apu, items_data)
        return True

    def _reemplazar_sueltos(self, tipo_apu: str, items_data: List[Dict]) -> List[dict]:
        """Modales en un tipo con paquetes: reemplaza SOLO los ítems sueltos
        (sin apu_paquete) y recalcula la resumen del tipo. Nunca toca los
        componentes de paquetes."""
        from apps.common.choices import TipoAPU

        cargados = self._cargar_items_catalogo(tipo_apu, items_data)
        self.apu.lineas.filter(
            tipo=tipo_apu, item_catalogo__isnull=False, apu_paquete__isnull=True,
        ).delete()
        for c in cargados:
            rendimiento = (
                Decimal(str(round(c["porcentaje"], 6)))
                if tipo_apu == TipoAPU.ADMINISTRACION else Decimal(c["cantidad"])
            )
            self._crear_linea_detalle(tipo_apu, c, rendimiento=rendimiento)
        resumen = self._recalcular_tipo_paquetes(tipo_apu)
        return [{
            "descripcion": resumen.descripcion if resumen else tipo_apu,
            "costo_total": float(resumen.costo_total) if resumen else 0.0,
        }]

    def instanciar_paquetes(self, paquetes) -> list:
        """Siembra el APU con uno o varios paquetes maestros del mismo o distinto
        tipo y recalcula la resumen de cada tipo afectado."""
        from apps.presupuestos.economia import ValorDiarioError

        creados = []
        tipos = []
        with transaction.atomic():
            for paquete in paquetes:
                creados.append(self._instanciar_paquete(paquete))
                if paquete.tipo_apu not in tipos:
                    tipos.append(paquete.tipo_apu)
            for tipo in tipos:
                self._recalcular_tipo_paquetes(tipo)
        return creados

    def _instanciar_paquete(self, paquete):
        """Crea el snapshot APUPaquete + una APULinea por componente:
            cantidad          = PaqueteAPUItem.cantidad
            precio_referencia = valor diario vigente del ítem (sin override)
            rendimiento       = cantidad; en ADMINISTRACION, 1 (100 %: el % es del APU)
        Si algún ítem no tiene valor diario calculable, no crea nada."""
        from apps.common.choices import TipoAPU
        from apps.presupuestos.economia import ValorDiarioError
        from apps.presupuestos.models import APUPaquete

        if paquete.tipo_apu == TipoAPU.MATERIALES:
            raise ValueError("MATERIALES no admite paquetes APU.")
        if self.apu.paquetes.filter(paquete_origen=paquete).exists():
            raise ValueError(f"El paquete «{paquete.nombre}» ya está en este APU.")

        componentes = list(paquete.componentes())
        cargados, pendientes = [], []
        for comp in componentes:
            item = comp.item_catalogo
            try:
                precio, _ = resolver_precio_item(item)
            except ValorDiarioError as exc:
                pendientes.append(f"«{item.nombre}» ({exc})")
                continue
            cargados.append({
                "item": item,
                "cantidad": Decimal(str(comp.cantidad)),
                "precio": precio,
                "personalizado": False,
                "porcentaje": 1.0,
            })
        if pendientes:
            raise ValorDiarioError(
                f"No se puede instanciar el paquete «{paquete.nombre}»: hay ítems sin valor "
                f"diario calculable (configure su vida útil en el catálogo APU): "
                f"{'; '.join(pendientes)}."
            )

        orden = self.apu.paquetes.filter(tipo_apu=paquete.tipo_apu).count()
        ap = APUPaquete.objects.create(
            apu=self.apu,
            paquete_origen=paquete,
            nombre_snapshot=paquete.nombre,
            tipo_apu=paquete.tipo_apu,
            orden=orden,
        )
        for c in cargados:
            rendimiento = (
                Decimal("1") if paquete.tipo_apu == TipoAPU.ADMINISTRACION else c["cantidad"]
            )
            self._crear_linea_detalle(paquete.tipo_apu, c, rendimiento=rendimiento, apu_paquete=ap)
        logger.info(
            "[APUService] APU %s: paquete «%s» instanciado (%d componentes).",
            self.apu.pk, paquete.nombre, len(cargados),
        )
        return ap

    def agregar_paquete(self, paquete):
        """Agrega un paquete maestro activo a un APU editable."""
        self._verificar_editable()
        if not paquete.activo:
            raise ValueError(f"El paquete «{paquete.nombre}» está inactivo.")
        with transaction.atomic():
            ap = self.instanciar_paquetes([paquete])[0]
            self.apu.recalcular()
        return ap

    def eliminar_paquete(self, apu_paquete) -> None:
        """Operación de dominio atómica: elimina los componentes del paquete, el
        APUPaquete y recalcula la resumen de su tipo. Sin eliminación parcial."""
        if apu_paquete.apu_id != self.apu.pk:
            raise ValueError("El paquete no pertenece a este APU.")
        self._verificar_editable()
        tipo = apu_paquete.tipo_apu
        with transaction.atomic():
            self.apu.lineas.filter(apu_paquete=apu_paquete).delete()
            apu_paquete.delete()
            self.recalcular_tipo(tipo)
            self.apu.recalcular()

    def actualizar_componente(self, linea, cantidad=None, precio=None, porcentaje=None):
        """Override local de un componente (paquete o ítem suelto) del APU:
        cantidad, valor diario (marca precio_personalizado) y, en
        ADMINISTRACION, porcentaje (rendimiento). No toca catálogo ni maestro."""
        from apps.common.choices import TipoAPU

        if linea.apu_id != self.apu.pk:
            raise ValueError("La línea no pertenece a este APU.")
        if linea.tipo == TipoAPU.MATERIALES or (
            linea.item_catalogo_id is None and linea.apu_paquete_id is None
        ):
            raise ValueError("Solo se pueden editar componentes de catálogo no materiales.")
        self._verificar_editable()

        campos = ["updated_at"]
        if cantidad is not None:
            cantidad = Decimal(str(cantidad))
            if cantidad <= 0:
                raise ValueError("La cantidad debe ser mayor que cero.")
            linea.cantidad = cantidad
            campos.append("cantidad")
            if linea.tipo != TipoAPU.ADMINISTRACION:
                linea.rendimiento = cantidad
                campos.append("rendimiento")
        if precio is not None:
            precio = Decimal(str(precio))
            if precio < 0:
                raise ValueError("El valor diario no puede ser negativo.")
            linea.precio_referencia = precio.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            linea.precio_personalizado = True
            campos += ["precio_referencia", "precio_personalizado"]
        if porcentaje is not None:
            if linea.tipo != TipoAPU.ADMINISTRACION:
                raise ValueError("El porcentaje solo aplica a Administración.")
            porcentaje = Decimal(str(porcentaje))
            if porcentaje < 0:
                raise ValueError("El porcentaje no puede ser negativo.")
            linea.rendimiento = porcentaje
            campos.append("rendimiento")

        with transaction.atomic():
            linea.save(update_fields=campos)
            self.recalcular_tipo(linea.tipo)
            self.apu.recalcular()

    def restablecer_precio_catalogo(self, linea) -> None:
        """Fase 3.C — deshace el override local de precio de un componente:
            precio_referencia    = valor diario vigente del ItemCatalogoAPU
            precio_personalizado = False
        y recalcula el TipoAPU. Conserva cantidad, rendimiento (% en
        Administración) y la composición del APUPaquete. No toca catálogo,
        paquete maestro ni subsistema. Lanza ValorDiarioError si el ítem no
        tiene valor diario calculable."""
        from apps.common.choices import TipoAPU

        if linea.apu_id != self.apu.pk:
            raise ValueError("La línea no pertenece a este APU.")
        if linea.tipo == TipoAPU.MATERIALES or linea.item_catalogo_id is None:
            raise ValueError("Solo los componentes de catálogo tienen precio de catálogo.")
        self._verificar_editable()
        valor_diario = linea.item_catalogo.valor_diario  # ValorDiarioError si no es calculable
        with transaction.atomic():
            linea.precio_referencia = valor_diario
            linea.precio_personalizado = False
            linea.save(update_fields=["precio_referencia", "precio_personalizado", "updated_at"])
            self.recalcular_tipo(linea.tipo)
            self.apu.recalcular()

    def lineas_reemplazadas_al_convertir(self, tipo_apu: str) -> list:
        """Fase 3.C — si el TipoAPU todavía no usa paquetes, devuelve las líneas
        que `_recalcular_tipo_paquetes` reemplazaría al agregar el primer
        paquete (las que el servicio trata como resumen: sin ítem de catálogo,
        sin paquete y sin despiece). Lista vacía si el tipo ya usa paquetes o
        no tiene líneas. Solo lectura: no modifica nada."""
        if self._tipo_usa_paquetes(tipo_apu):
            return []
        return list(self._lineas_resumen(tipo_apu).order_by("id"))

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
    