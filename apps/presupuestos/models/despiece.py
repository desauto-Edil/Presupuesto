"""
apps/presupuestos/models/despiece.py — Ejecución del despiece por proyecto.

"""

from __future__ import annotations

from django.db import models
from django.core.exceptions import ValidationError


class ProyectoSistema(models.Model):
    """
    Instancia de ejecución de un sistema/subsistema para un proyecto concreto.
    Almacena las variables de entrada dinámicas en parametros_entrada (JSONField).
    """
    proyecto = models.ForeignKey(
        "comercial.Proyecto", on_delete=models.CASCADE, related_name="proyecto_sistemas"
    )
    solicitud = models.ForeignKey(
        "comercial.Solicitud", on_delete=models.CASCADE, related_name="proyecto_sistemas",
        null=True, blank=True,
    )
    sistema = models.ForeignKey(
        "ingenieria.Sistema", on_delete=models.PROTECT, related_name="proyecto_sistemas"
    )
    subsistema = models.ForeignKey(
        "ingenieria.Subsistema",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="proyecto_sistemas",
    )
    parametros_entrada = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Variables de entrada específicas de este sistema. "
            "Ej: {'total_powergrip': 2883, 'tornilleria_u7': 8, 'desperdicio': 1.01}"
        ),
    )

    class Meta:
        app_label = "presupuestos"
        db_table = "proyecto_sistemas"
        unique_together = ("proyecto", "sistema", "subsistema")
        verbose_name = "Ejecución de Sistema"
        verbose_name_plural = "Ejecuciones de Sistemas"

    def __str__(self):
        try:
            sub = f" / {self.subsistema.nombre}" if self.subsistema_id and self.subsistema else ""
            return f"{self.proyecto.consecutivo} — {self.sistema.nombre}{sub}"
        except Exception:
            return f"ProyectoSistema #{self.pk}"

    # ── Bloqueo por APU aprobado ───────────────────────────────────────────────

    @property
    def tiene_apu_aprobado(self) -> bool:
        """
        True si el APU individual de este sistema ya está aprobado, o si el
        proyecto contenedor tiene algún APU (consolidado) aprobado.
        Se usa para pasar el despiece/selección de productos a solo lectura.
        """
        apu = getattr(self, "apu", None)  # OneToOne related_name="apu"
        if apu is not None and apu.esta_aprobado:
            return True
        return self.proyecto.tiene_apu_aprobado if self.proyecto_id else False

    # ── Contexto ──────────────────────────────────────────────────────────────

    def get_contexto(self) -> dict:
        """
        Construye el diccionario de contexto para evaluar las fórmulas.

        Incluye:
          1. Variables base del proyecto (area_m2, perimetro_ml).
          2. Todos los campos de parametros_entrada convertidos a float.
             Los strings no numéricos pasan sin convertir.
          3. trm — TRM contractual del proyecto (si está definida), o la TRM
             global vigente del día. Disponible en todas las fórmulas.
        """
        ctx: dict = {
            "area_m2":      float(getattr(self.proyecto, "area_total_m2", 0) or 0),
            "perimetro_ml": float(getattr(self.proyecto, "perimetro_ml", 0) or 0),
        }
        for k, v in (self.parametros_entrada or {}).items():
            if v is None or v == "":
                continue
            try:
                ctx[k] = float(v)
            except (ValueError, TypeError):
                ctx[k] = v

        # TRM: preferir la contractual del proyecto; fallback a la global.
        proyecto_trm = getattr(self.proyecto, "trm", None)
        if proyecto_trm is not None and float(proyecto_trm) > 0:
            ctx["trm"] = float(proyecto_trm)
        else:
            try:
                from apps.common.trm_service import obtener_trm_vigente
                ctx["trm"] = float(obtener_trm_vigente())
            except Exception:
                ctx["trm"] = 0.0

        return ctx

    def get_variables_requeridas(self) -> list[dict]:
        """
        Devuelve las variables de entrada que este subsistema necesita.
        Prioridad: variables en DB (VariableSubsistema) > system_defs registry.

        Retorna: [{variable, label, valor, unidad, default}]
        para que la UI las renderice como formulario dinámico.
        Excluye las variables del proyecto (area_m2, perimetro_ml).
        """
        if not self.sistema_id or not self.subsistema_id:
            return []

        VARS_PROYECTO = {"area_m2", "perimetro_ml"}
        params = self.parametros_entrada or {}

        # ── Prioridad 1: variables DB ─────────────────────────────────────────
        from apps.ingenieria.models import VariableSubsistema
        vars_db = list(
            VariableSubsistema.objects.filter(subsistema=self.subsistema).order_by("orden")
        )
        def _fmt(v):
            """Convierte a int si es entero, a float si tiene decimales, sin trailing zeros."""
            if v is None or v == "":
                return ""
            try:
                f = float(v)
                return int(f) if f == int(f) else f
            except (TypeError, ValueError):
                return v

        if vars_db:
            return [
                {
                    "variable": v.variable,
                    "label": v.label,
                    "unidad": v.unidad,
                    "default": _fmt(v.valor_default),
                    "valor": _fmt(params.get(v.variable, v.valor_default)),
                }
                for v in vars_db
                if v.variable not in VARS_PROYECTO
            ]

        # ── Prioridad 2: registry Python ──────────────────────────────────────
        from apps.ingenieria.system_defs.registry import get_subsistema_def
        sub_def = get_subsistema_def(self.sistema.codigo, self.subsistema.codigo)
        if not sub_def:
            return []

        return [
            {
                "variable": v.variable,
                "label": v.label,
                "unidad": v.unidad,
                "default": _fmt(v.default),
                "valor": _fmt(params.get(v.variable, v.default if v.default is not None else "")),
            }
            for v in sub_def.variables
            if v.variable not in VARS_PROYECTO
        ]


class DespieceLinea(models.Model):

    proyecto = models.ForeignKey(
        "comercial.Proyecto", on_delete=models.CASCADE, related_name="despiece_lineas"
    )
    proyecto_sistema = models.ForeignKey(
        ProyectoSistema, on_delete=models.CASCADE,
        blank=True, null=True, related_name="despiece_lineas",
    )
    componente_codigo = models.CharField(
        max_length=80, blank=True, db_index=True,
        help_text=(
            "Código del componente según la definición backend del sistema "
            "(system_defs). Ej: 'fijaciones_u7', 'limpiador_plus'."
        ),
    )
    producto = models.ForeignKey(
        "catalogos.Producto", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="despiece_lineas",
        help_text="Producto resuelto; NULL si aún está pendiente de selección.",
    )
    categoria_producto = models.ForeignKey(
        "catalogos.CategoriaProducto", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="despiece_lineas",
        help_text="Categoría cuando el producto aún no ha sido seleccionado.",
    )
    # ── Legacy FKs (conservados para compatibilidad de datos históricos) ──────
    # No se usan en el flujo nuevo. Quedan como referencia si la BD los tiene.
    regla = models.ForeignKey(
        "ingenieria.ReglaCalculo", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="despiece_lineas",
        help_text="[LEGADO] Regla que generó esta línea en el flujo anterior.",
    )
    dependencia_tecnica = models.ForeignKey(
        "ingenieria.DependenciaTecnica", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="despiece_lineas",
        help_text="[LEGADO] Dependencia automática en el flujo anterior.",
    )
    # ─────────────────────────────────────────────────────────────────────────
    cantidad_calculada = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True,
        help_text=(
            "Cantidad calculada por la fórmula. None cuando el componente requiere "
            "selección de producto para calcular (ver pendiente_producto)."
        ),
    )
    cantidad_ajustada  = models.DecimalField(
        max_digits=18, decimal_places=6, blank=True, null=True,
        help_text="Valor manual que reemplaza al calculado si el usuario lo ajusta.",
    )
    motivo_ajuste = models.TextField(blank=True, null=True)
    precio_snapshot = models.DecimalField(
        max_digits=18, decimal_places=6, blank=True, null=True,
        help_text="Precio unitario capturado al momento de calcular el despiece.",
    )
    es_dependencia_automatica = models.BooleanField(default=False)
    pendiente_producto = models.BooleanField(
        default=False,
        help_text=(
            "True cuando el componente tiene requiere_presentacion_producto=True "
            "y aún no se ha seleccionado el producto. "
            "En este estado cantidad_calculada es None."
        ),
    )
    presentacion_snapshot = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        help_text=(
            "Valor de Producto.cantidad_presentacion usado en el último cálculo. "
            "Se guarda para trazabilidad aunque el producto cambie después."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "despiece_lineas"
        verbose_name = "Línea de Despiece"
        verbose_name_plural = "Líneas de Despiece"
        ordering = ["proyecto_sistema", "id"]

    def __str__(self):
        nombre = (
            self.producto.nombre if self.producto
            else f"[{self.categoria_producto}]" if self.categoria_producto
            else self.componente_codigo or "—"
        )
        return f"{self.proyecto.consecutivo} / {nombre}"

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @property
    def cantidad_final(self):
        """Cantidad definitiva: ajustada si existe, calculada si no."""
        return self.cantidad_ajustada if self.cantidad_ajustada is not None else self.cantidad_calculada

    @property
    def pendiente_seleccion(self):
        """True si la línea tiene categoría pero aún no tiene producto concreto."""
        return self.producto_id is None and self.categoria_producto_id is not None

    @property
    def estado_tecnico(self):
        """Estado de resolución del componente."""
        if self.pendiente_producto:
            return "PENDIENTE_PRODUCTO"
        if self.producto:
            return "RESUELTO"
        if self.categoria_producto:
            return "PENDIENTE_SELECCION"
        return "ERROR_CONFIGURACION"

    # ── Operaciones ───────────────────────────────────────────────────────────

    def capturar_precio(self):
        """
        Toma snapshot del mejor precio activo del producto.
        - Divide por unidades_por_presentacion para obtener el precio unitario real.
        - Si producto.precio_en_dolares es True, convierte a COP usando proyecto.trm.
        """
        if not self.producto_id:
            return
        pp = (
            self.producto.proveedores_producto
            .filter(activo=True)
            .order_by("precio_unitario")
            .first()
        )
        precio_base = None
        if pp:
            precio_base = pp.precio_unitario
        elif self.producto.precio_actual:
            precio_base = self.producto.precio_actual

        if precio_base is not None:
            from decimal import Decimal
            divisor = Decimal(str(self.producto.unidades_por_presentacion or 1))
            precio = Decimal(str(precio_base)) / divisor

            # Si el precio está en USD, convertir a COP con la TRM del proyecto
            # (o la TRM global si el despiece no tiene proyecto asociado).
            if self.producto.precio_en_dolares:
                try:
                    proyecto_trm = None
                    try:
                        proyecto_trm = self.proyecto_sistema.proyecto.trm
                    except Exception:
                        pass
                    if proyecto_trm and float(proyecto_trm) > 0:
                        trm = Decimal(str(proyecto_trm))
                    else:
                        from apps.common.trm_service import obtener_trm_vigente
                        trm = obtener_trm_vigente()
                    precio = precio / trm
                except Exception:
                    pass  # Si no hay TRM disponible, dejar el precio sin convertir

            self.precio_snapshot = precio
            self.save(update_fields=["precio_snapshot", "updated_at"])

    def resolver_producto(self, producto_seleccionado):
        """Asigna un producto real a una línea que era solo categoría."""
        if self.categoria_producto and producto_seleccionado.categoria == self.categoria_producto:
            self.producto = producto_seleccionado
            self.capturar_precio()
            self.save()
        else:
            raise ValidationError("El producto no pertenece a la categoría requerida.")
