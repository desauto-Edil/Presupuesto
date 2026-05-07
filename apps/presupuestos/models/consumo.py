"""
apps/presupuestos/models/consumo.py — Resultado del cálculo de consumo por proyecto.

CalculoConsumoLinea es el equivalente de DespieceLinea para sistemas de CONSUMO.
Una línea por capa del sistema; si el subsistema es bicomponente, cada
ComponenteQuimico genera una sub-línea hija (linea_padre FK).

Flujo:
    ProyectoSistema (sistema.tipo == CONSUMO)
        └─ CalculoConsumoLinea  (una por CapaConsumo)
               └─ CalculoConsumoLinea  (hijas — una por ComponenteQuimico, solo bicomponente)
"""

from __future__ import annotations
from django.db import models
from django.core.exceptions import ValidationError


class CalculoConsumoLinea(models.Model):
    """
    Línea de resultado del cálculo de consumo para un ProyectoSistema.

    La cantidad se calcula con:
        cantidad = area_m2 × consumo_m2 × num_capas × (1 + desperdicio_pct/100)

    Para subsistemas bicomponente, las líneas padre tienen
    es_componente_quimico=False; las hijas (una por ComponenteQuimico)
    tienen es_componente_quimico=True y linea_padre apuntando a la capa principal.
    """
    proyecto_sistema = models.ForeignKey(
        "ProyectoSistema",
        on_delete=models.CASCADE,
        related_name="calculo_consumo_lineas",
    )
    capa_nombre = models.CharField(
        max_length=200,
        help_text="Nombre de la capa o componente. Ej: 'Impermeabilizante', 'Comp. A (Base)'",
    )

    # Producto / categoría pendiente (mismo patrón que DespieceLinea)
    producto = models.ForeignKey(
        "catalogos.Producto",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="calculo_consumo_lineas",
        help_text="Producto concreto; NULL mientras no se haya seleccionado.",
    )
    categoria_producto = models.ForeignKey(
        "catalogos.CategoriaProducto",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="calculo_consumo_lineas",
        help_text="Categoría para selección del producto cuando aún no está resuelto.",
    )

    # Parámetros del cálculo (trazabilidad)
    area_m2 = models.DecimalField(
        max_digits=14, decimal_places=4,
        help_text="Área usada en el cálculo.",
    )
    consumo_m2 = models.DecimalField(
        max_digits=10, decimal_places=4,
        help_text="Consumo unitario de la capa (kg/m², gal/m², etc.)",
    )
    num_capas = models.PositiveSmallIntegerField(default=1)
    desperdicio_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Resultado
    cantidad_calculada = models.DecimalField(
        max_digits=18, decimal_places=6,
        help_text="Cantidad calculada automáticamente.",
    )
    cantidad_ajustada = models.DecimalField(
        max_digits=18, decimal_places=6,
        null=True, blank=True,
        help_text="Ajuste manual del usuario; reemplaza la cantidad calculada.",
    )
    motivo_ajuste = models.TextField(blank=True, null=True)
    unidad = models.CharField(max_length=40, default="kg")
    precio_snapshot = models.DecimalField(
        max_digits=18, decimal_places=6,
        null=True, blank=True,
        help_text="Precio unitario capturado en el momento del cálculo.",
    )

    # Bicomponente: jerarquía padre/hijo
    linea_padre = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="componentes_quimicos",
        help_text="Si es componente químico, apunta a la línea de capa principal.",
    )
    es_componente_quimico = models.BooleanField(
        default=False,
        help_text="True para líneas generadas por ComponenteQuimico (bicomponente).",
    )
    porcentaje_componente = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Porcentaje del componente dentro de la mezcla (sólo bicomponente).",
    )

    orden = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "calculo_consumo_lineas"
        ordering = ["orden", "id"]
        verbose_name = "Línea de Cálculo Consumo"
        verbose_name_plural = "Líneas de Cálculo Consumo"

    def __str__(self):
        nombre = (
            self.producto.nombre if self.producto
            else f"[{self.categoria_producto}]" if self.categoria_producto
            else self.capa_nombre or "—"
        )
        try:
            return f"{self.proyecto_sistema} / {nombre}"
        except Exception:
            return f"CalculoConsumoLinea #{self.pk}"

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @property
    def cantidad_final(self):
        return self.cantidad_ajustada if self.cantidad_ajustada is not None else self.cantidad_calculada

    @property
    def pendiente_seleccion(self):
        return self.producto_id is None and self.categoria_producto_id is not None

    @property
    def estado_tecnico(self):
        if self.producto:
            return "RESUELTO"
        if self.categoria_producto:
            return "PENDIENTE_SELECCION"
        return "SIN_CATEGORIA"

    @property
    def subtotal(self):
        if self.precio_snapshot and self.cantidad_final:
            return self.precio_snapshot * self.cantidad_final
        return None

    # ── Operaciones ───────────────────────────────────────────────────────────

    def capturar_precio(self):
        """Snapshot del mejor precio activo. Mismo patrón que DespieceLinea."""
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
            if self.producto.precio_en_dolares:
                try:
                    trm = Decimal(str(self.proyecto_sistema.proyecto.trm or 4200))
                    precio = precio / trm
                except Exception:
                    pass
            self.precio_snapshot = precio
            self.save(update_fields=["precio_snapshot", "updated_at"])

    def resolver_producto(self, producto_seleccionado):
        """Asigna un producto concreto a una línea pendiente de selección."""
        if self.categoria_producto and producto_seleccionado.categoria == self.categoria_producto:
            self.producto = producto_seleccionado
            self.capturar_precio()
            self.save()
        else:
            raise ValidationError("El producto no pertenece a la categoría requerida.")
