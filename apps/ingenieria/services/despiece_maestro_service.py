"""
apps/ingenieria/services/despiece_maestro_service.py

Motor de cálculo para DespieceMaestro (despiece independiente de proyecto).

Diferencias respecto a DespieceService:
  - No requiere ProyectoSistema ni Proyecto.
  - Soporta filtrado por subconjuntos seleccionados.
  - Compatibilidad con componentes legacy (sin subconjunto).
  - Guarda snapshot inmutable en DespieceMaestroLinea.
"""

from __future__ import annotations

import logging
import math
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.db import transaction
from django.core.exceptions import ValidationError

if TYPE_CHECKING:
    from apps.ingenieria.models import DespieceMaestro

logger = logging.getLogger(__name__)

# Nombres matemáticos seguros expuestos al evaluar fórmulas (math.*).
# Se excluyen al capturar valores_usados para no ensuciar el snapshot.
_SAFE_NAMES_KEYS = {k for k in math.__dict__ if not k.startswith("_")}


class DespieceMaestroService:
    def __init__(self, despiece: "DespieceMaestro"):
        self.despiece = despiece
        self.subsistema = despiece.subsistema

    # ── Contexto ─────────────────────────────────────────────────────────────

    def _build_contexto(self, variables_entrada_override: dict | None = None) -> dict:
        """
        Construye el contexto de evaluación combinando:
          1. Defaults de VariableSubsistema (si el usuario no los sobrescribe).
          2. variables_entrada del despiece (o un override para recálculo).
        """
        from apps.ingenieria.models import VariableSubsistema

        ctx: dict = {}
        # Inyectar funciones matemáticas seguras
        ctx.update({k: getattr(math, k) for k in _SAFE_NAMES_KEYS})

        # Paso 1: valores por defecto de las variables del subsistema
        for var in VariableSubsistema.objects.filter(subsistema=self.subsistema).order_by("orden"):
            try:
                ctx[var.variable] = float(var.valor_default)
            except (TypeError, ValueError):
                ctx[var.variable] = 0.0

        # Paso 2: sobreescribir con lo que el usuario ingresó
        variables_a_usar = (
            variables_entrada_override
            if variables_entrada_override is not None
            else self.despiece.variables_entrada
        )
        for k, v in (variables_a_usar or {}).items():
            if v is None or v == "":
                continue
            try:
                ctx[k] = float(v)
            except (TypeError, ValueError):
                ctx[k] = v  # dejar como string si no es numérico

        return ctx

    # ── Cálculo ───────────────────────────────────────────────────────────────

    def calcular(self) -> list[dict]:
        """
        Evalúa las fórmulas de los componentes para los subconjuntos seleccionados.

        NO guarda en base de datos — solo devuelve la lista de resultados.
        Para persistir, llama a guardar() después.

        Retorna:
          Lista de dicts con:
            subconjunto_id, subconjunto_nombre, componente_codigo, componente_nombre,
            formula_texto, cantidad_calculada, unidad, variable_salida,
            variable_referencia_apu, unidad_apu, categoria_nombre, error
        """
        from apps.ingenieria.models import ComponenteSubsistema

        ctx = self._build_contexto()

        # Validar variables OPCION_UNICA antes de calcular
        variables_usuario = self.despiece.variables_entrada or {}
        errores_vars = self.validar_variables_entrada(variables_usuario)
        if errores_vars:
            raise ValueError("\n".join(errores_vars))

        # Filtrar por subconjuntos seleccionados
        sq_ids = list(self.despiece.subconjuntos.values_list("pk", flat=True))

        if sq_ids:
            # Solo los subconjuntos que el usuario marcó
            qs = (
                ComponenteSubsistema.objects
                .filter(subsistema=self.subsistema, subconjunto__in=sq_ids)
                .select_related("subconjunto", "categoria")
                .order_by("subconjunto__orden", "subconjunto__id", "orden")
            )
        else:
            # Compatibilidad: subsistema sin subconjuntos → todos los componentes
            qs = (
                ComponenteSubsistema.objects
                .filter(subsistema=self.subsistema)
                .select_related("subconjunto", "categoria")
                .order_by("orden")
            )

        resultados: list[dict] = []

        import re as _re
        _token_re = _re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b')

        # Para detectar dependencias pendientes
        variables_pendientes = set()

        for comp in qs:
            # Snapshot de los valores usados por ESTA fórmula (variables + salidas
            # intermedias ya resueltas), tomado del contexto ANTES de evaluar.
            valores_usados = {}
            if comp.formula_texto:
                # Corregido: extraer tokens de la fórmula, no de valores_usados
                tokens_formula = set(_token_re.findall(comp.formula_texto or ""))
                for tok in tokens_formula:
                    if tok in ctx and tok not in _SAFE_NAMES_KEYS:
                        val = ctx[tok]
                        valores_usados[tok] = float(val) if isinstance(val, (int, float)) else val

            cantidad_f = None
            cantidad = Decimal("0")
            error = None
            pendiente_producto = False
            pendiente_dependencia = False

            if comp.requiere_presentacion_producto:
                pendiente_producto = True
                if comp.variable_salida:
                    variables_pendientes.add(comp.variable_salida)
                logger.debug(
                    "[DespieceMaestroService] Componente '%s' pendiente de selección de producto.",
                    comp.codigo
                )

            # Corregido: la detección de dependencias debe usar los tokens reales de la fórmula
            elif variables_pendientes.intersection(tokens_formula):
                pendiente_dependencia = True
                if comp.variable_salida:
                    variables_pendientes.add(comp.variable_salida)
                logger.debug(
                    "[DespieceMaestroService] Componente '%s' pendiente por dependencia de %s.",
                    comp.codigo, variables_pendientes.intersection(tokens_formula)
                )

            else:
                try:
                    cantidad_float = comp.evaluar(ctx)
                    if comp.variable_salida:
                        ctx[comp.variable_salida] = cantidad_float
                    cantidad = Decimal(str(cantidad_float)).quantize(
                        Decimal("0.000001"), rounding=ROUND_HALF_UP
                    )
                    cantidad_f = float(cantidad)
                except Exception as exc:
                    cantidad = Decimal("0")
                    cantidad_f = 0.0
                    error = str(exc)
                    logger.warning(
                        "[DespieceMaestroService] Error en '%s' (subsistema %s): %s",
                        comp.codigo, self.subsistema.codigo, exc,
                    )

            resultados.append({
                "subconjunto_id":          comp.subconjunto_id,
                "subconjunto_nombre":      comp.subconjunto.nombre if comp.subconjunto else "General",
                "componente_codigo":       comp.codigo,
                "componente_nombre":       comp.nombre,
                "formula_texto":           comp.formula_texto,
                "valores_usados":          valores_usados,
                "cantidad_calculada":      cantidad_f,
                "cantidad_redondeada":     math.ceil(cantidad_f) if cantidad_f is not None and not error else None,
                "unidad":                  comp.unidad,
                "variable_salida":         comp.variable_salida,
                "variable_referencia_apu": comp.variable_referencia_apu,
                "unidad_apu":              comp.unidad_apu,
                "categoria_nombre":        comp.categoria.nombre if comp.categoria else "",
                "error":                   error,
                # Nuevos campos para el frontend
                "pendiente_producto":      pendiente_producto,
                "pendiente_dependencia":   pendiente_dependencia,
                "requiere_presentacion_producto": comp.requiere_presentacion_producto,
                "variable_presentacion_producto": comp.variable_presentacion_producto,
            })

        logger.info(
            "[DespieceMaestroService] subsistema=%s → %d líneas calculadas.",
            self.subsistema.codigo, len(resultados),
        )
        return resultados

    def _calcular_para_guardado(
        self, variables_entrada: dict, seleccion_productos: dict
    ) -> list[dict]:
        """
        Recalcula el despiece completo desde cero, resolviendo las líneas pendientes
        con los productos seleccionados. Esta es la fuente de verdad para el guardado.

        Lanza ValidationError si falta un producto o la presentación es inválida.
        """
        from apps.ingenieria.models import ComponenteSubsistema
        from apps.catalogos.models import Producto

        # 1. Cargar todos los productos necesarios en una sola consulta
        producto_ids = [
            p["producto_id"] for p in seleccion_productos.values() if p.get("producto_id")
        ]
        productos_db = Producto.objects.filter(pk__in=producto_ids)
        productos_por_id = {p.pk: p for p in productos_db}

        # 2. Construir contexto inicial (reutilizando lógica)
        # Corregido: Construir contexto inicial sin mutar la instancia
        ctx = self._build_contexto(variables_entrada_override=variables_entrada)

        # 3. Obtener el mismo queryset ordenado que en `calcular()`
        sq_ids = list(self.despiece.subconjuntos.values_list("pk", flat=True))
        if sq_ids:
            qs = (
                ComponenteSubsistema.objects.filter(subsistema=self.subsistema, subconjunto__in=sq_ids)
                .select_related("subconjunto", "categoria")
                .order_by("subconjunto__orden", "subconjunto__id", "orden")
            )
        else:
            qs = (
                ComponenteSubsistema.objects
                .filter(subsistema=self.subsistema)
                .select_related("subconjunto", "categoria")
                .order_by("orden")
            )

        resultados_definitivos = []
        import re as _re
        _token_re = _re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b')

        for comp in qs:
            ctx_componente = dict(ctx)

            if comp.requiere_presentacion_producto:
                seleccion = seleccion_productos.get(comp.codigo)
                if not seleccion or not seleccion.get("producto_id"):
                    raise ValidationError(
                        f"El componente '{comp.nombre}' requiere seleccionar un producto."
                    )

                producto = productos_por_id.get(seleccion["producto_id"])
                if not producto:
                    raise ValidationError(
                        f"El producto seleccionado para '{comp.nombre}' no fue encontrado."
                    )

                if not producto.cantidad_presentacion or producto.cantidad_presentacion <= 0:
                    raise ValidationError(
                        f"El producto '{producto.nombre}' no tiene una cantidad por presentación válida."
                    )

                ctx_componente[comp.variable_presentacion_producto] = float(producto.cantidad_presentacion)

            try:
                cantidad_float = comp.evaluar(ctx_componente)
                if comp.variable_salida:
                    ctx[comp.variable_salida] = cantidad_float

                # Corregido: Snapshot de valores usados, incluyendo la presentación si aplica
                valores_usados = {}
                if comp.formula_texto:
                    for tok in _token_re.findall(comp.formula_texto):
                        if tok in ctx_componente and tok not in _SAFE_NAMES_KEYS:
                            val = ctx_componente[tok]
                            valores_usados[tok] = float(val) if isinstance(val, (int, float, Decimal)) else val

                # Corregido: No usar to_dict(), construir el diccionario explícitamente
                resultado_comp = dict({
                    "subconjunto_id":          comp.subconjunto_id,
                    "subconjunto_nombre":      comp.subconjunto.nombre if comp.subconjunto else "General",
                    "componente_codigo":       comp.codigo,
                    "componente_nombre":       comp.nombre,
                    "formula_texto":           comp.formula_texto,
                    "unidad":                  comp.unidad,
                    "variable_salida":         comp.variable_salida,
                    "variable_referencia_apu": comp.variable_referencia_apu,
                    "unidad_apu":              comp.unidad_apu,
                    "categoria_nombre":        comp.categoria.nombre if comp.categoria else "",
                }, **{
                    "cantidad_calculada": float(cantidad_float),
                    "valores_usados": valores_usados,
                    "error": None,
                })
                resultados_definitivos.append(resultado_comp)

            except Exception as exc:
                logger.error(
                    "[DespieceMaestroService._calcular_para_guardado] Error en '%s': %s",
                    comp.codigo, exc
                )
                raise ValidationError(
                    f"Error al recalcular la fórmula para '{comp.nombre}': {exc}"
                )

        return resultados_definitivos

    # ── Guardado ──────────────────────────────────────────────────────────────

    @transaction.atomic
    def guardar(self, variables_entrada: dict, seleccion_productos: dict | None = None) -> None:
        """
        Persiste el cálculo en DespieceMaestroLinea y marca el despiece como GUARDADO.

        Recalcula todas las líneas para resolver pendientes y garantizar consistencia.
        Si el despiece ya tenía líneas previas, las elimina y las reemplaza (idempotente).
        Guarda además un snapshot JSON para mantener la trazabilidad histórica.

        Args:
            seleccion_productos: Dict indexado por componente_codigo con datos del
                                 producto seleccionado:
                                 {
                                   "COMP-001": {
                                     "producto_id": 42,
                                     "producto_codigo": "...",
                                     "producto_nombre": "...",
                                     "precio_unitario": 1500.0,
                                     "moneda": "COP",
                                     "fecha_precio": "2026-05-01T10:00:00",
                                   }
                                 }
        """
        from apps.ingenieria.models import DespieceMaestroLinea
        from apps.catalogos.models import Producto

        dm = self.despiece
        sel = seleccion_productos or {}

        # 1. Recalcular todo desde cero con los datos finales.
        # Este método lanza ValidationError si algo falla, abortando la transacción.
        resultados = self._calcular_para_guardado(variables_entrada, sel)

        # 2. Cargar todos los productos en una sola consulta para el snapshot
        producto_ids = [p["producto_id"] for p in sel.values() if p.get("producto_id")]
        productos_por_id = {p.pk: p for p in Producto.objects.filter(pk__in=producto_ids)}

        # Actualizar variables y snapshot
        dm.variables_entrada  = variables_entrada
        dm.resultado_snapshot = resultados
        dm.estado             = dm.GUARDADO
        dm.save(update_fields=["variables_entrada", "resultado_snapshot", "estado", "updated_at"])

        # Recrear líneas (garantiza idempotencia: guardar varias veces no duplica)
        dm.lineas.all().delete()

        lineas = []
        for idx, r in enumerate(resultados):
            cantidad = Decimal(str(r["cantidad_calculada"]))
            precio_u = None
            precio_t = None
            fecha_precio = None
            seleccion_linea = sel.get(r["componente_codigo"], {})
            producto_db = None
            producto_id = seleccion_linea.get("producto_id")

            if producto_id:
                producto_db = productos_por_id.get(producto_id)

            if seleccion_linea.get("precio_unitario") is not None:
                try:
                    # Usar el precio del payload, pero validando que sea un número
                    precio_u = Decimal(str(seleccion_linea.get("precio_unitario")))
                    precio_t = (cantidad * precio_u).quantize(Decimal("0.01"))
                except (ValueError, TypeError, Decimal.InvalidOperation):
                    # Si el precio del payload no es válido, se ignora.
                    pass

            if seleccion_linea.get("fecha_precio"):
                from django.utils.dateparse import parse_datetime
                fecha_precio = parse_datetime(str(seleccion_linea["fecha_precio"]))

            import math as _math
            cant_redondeada = _math.ceil(float(cantidad)) if not r.get("error") else 0

            lineas.append(DespieceMaestroLinea(
                despiece=dm,
                subconjunto_id=r["subconjunto_id"],
                subconjunto_nombre=r["subconjunto_nombre"],
                componente_codigo=r["componente_codigo"],
                componente_nombre=r["componente_nombre"],
                formula_texto=r["formula_texto"],
                valores_usados=r.get("valores_usados") or {},
                cantidad_calculada=cantidad,
                cantidad_redondeada=cant_redondeada,
                unidad=r["unidad"],
                variable_salida=r["variable_salida"],
                variable_referencia_apu=r["variable_referencia_apu"],
                unidad_apu=r["unidad_apu"],
                categoria_nombre=r["categoria_nombre"],
                orden=idx + 1,
                # Snapshot de producto
                producto_id=producto_id or None,
                producto_codigo=seleccion_linea.get("producto_codigo", ""),
                producto_nombre=seleccion_linea.get("producto_nombre", ""),
                precio_unitario=precio_u,
                precio_total=precio_t,
                moneda=seleccion_linea.get("moneda", ""),
                fecha_precio=fecha_precio,
            ))

        DespieceMaestroLinea.objects.bulk_create(lineas)

        logger.info(
            "[DespieceMaestroService] DespieceMaestro #%s guardado — %d líneas.",
            dm.pk, len(lineas),
        )

    # ── Variables requeridas ──────────────────────────────────────────────────

    def get_variables_requeridas(self) -> list[dict]:
        """
        Retorna las variables de entrada del subsistema para renderizar el formulario.

        [{variable, label, unidad, valor_actual, valor_default, tipo_entrada, opciones}]
        """
        from apps.ingenieria.models import VariableSubsistema

        params = self.despiece.variables_entrada or {}
        result = []
        for var in VariableSubsistema.objects.filter(subsistema=self.subsistema).order_by("orden"):
            valor_actual = params.get(var.variable, "")
            result.append({
                "variable":      var.variable,
                "label":         var.label,
                "unidad":        var.unidad,
                "valor_actual":  valor_actual if valor_actual != "" else float(var.valor_default),
                "valor_default": float(var.valor_default),
                "tipo_entrada":  var.tipo_entrada,
                "opciones":      var.opciones or [],
            })
        return result

    def _tokens_subconjuntos_seleccionados(self) -> set[str] | None:
        """
        Devuelve el conjunto de tokens (identificadores) que aparecen en las
        fórmulas de los componentes de los subconjuntos seleccionados.

        Retorna None si NO hay subconjuntos seleccionados (subsistema sin
        subconjuntos): en ese caso todas las variables se consideran en uso.

        Best-effort: usa regex sobre formula_texto + variable_salida.
        """
        import re
        from apps.ingenieria.models import ComponenteSubsistema

        sq_ids = list(self.despiece.subconjuntos.values_list("pk", flat=True))
        if not sq_ids:
            return None

        formulas = ComponenteSubsistema.objects.filter(
            subsistema=self.subsistema,
            subconjunto__in=sq_ids,
        ).values_list("formula_texto", "variable_salida")

        token_re = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b')
        tokens_usados: set[str] = set()
        for formula, var_salida in formulas:
            if formula:
                tokens_usados.update(token_re.findall(formula))
            if var_salida:
                tokens_usados.add(var_salida)
        return tokens_usados

    def get_variables_para_subconjuntos(self) -> list[dict]:
        """
        Como get_variables_requeridas(), pero filtra solo las variables que
        realmente aparecen en las fórmulas de los subconjuntos seleccionados.

        Si no hay subconjuntos seleccionados (subsistema sin subconjuntos),
        devuelve todas las variables del subsistema.

        Sub-fase A — Sin fallback "devuelve todas si no hay match". Antes:
            return filtradas if filtradas else todas
        ese fallback hacía que el Despiece Maestro mostrara TODAS las variables
        cuando el parser no encontraba tokens en las fórmulas. Ahora se
        devuelve la lista filtrada tal cual; el template muestra un mensaje
        controlado si queda vacía.
        """
        todas = self.get_variables_requeridas()
        tokens_usados = self._tokens_subconjuntos_seleccionados()
        if tokens_usados is None:
            return todas

        return [v for v in todas if v["variable"] in tokens_usados]

    def validar_variables_entrada(self, variables: dict) -> list[str]:
        """
        Valida que los valores ingresados sean válidos para su tipo.
        Retorna lista de errores (vacía = todo OK).

        Solo valida OPCION_UNICA, y SOLO para las variables realmente usadas por
        los componentes de los subconjuntos seleccionados. Una opción única que
        no es usada por la selección actual NO bloquea cálculo ni guardado.
        """
        from apps.ingenieria.models import VariableSubsistema

        tokens_usados = self._tokens_subconjuntos_seleccionados()

        errores = []
        for var in VariableSubsistema.objects.filter(
            subsistema=self.subsistema,
            tipo_entrada=VariableSubsistema.OPCION_UNICA,
        ).order_by("orden"):
            if not var.opciones:
                continue
            # Saltar variables que no usan los subconjuntos seleccionados.
            if tokens_usados is not None and var.variable not in tokens_usados:
                continue
            valor = str(variables.get(var.variable, "")).strip()
            # Comparar como string y como float (para tolerar "4" vs "4.0")
            opciones_norm = []
            for op in var.opciones:
                opciones_norm.append(str(op).strip())
                try:
                    opciones_norm.append(str(float(op)))
                except (ValueError, TypeError):
                    pass
            if valor not in opciones_norm:
                opciones_str = "; ".join(str(o) for o in var.opciones)
                errores.append(
                    f"El valor seleccionado para '{var.label}' no es válido. "
                    f"Opciones permitidas: {opciones_str}."
                )
        return errores
