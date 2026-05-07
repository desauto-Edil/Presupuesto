"""
apps/ingenieria/models/despiece_maestro.py — Despiece maestro independiente.

Un DespieceMaestro es un cálculo de despiece que no está atado a un proyecto
comercial. Permite calcular, guardar y revisar el despiece de un subsistema
con variables propias y subconjuntos seleccionados por el usuario.

Flujo:
  Sistema → Subsistema → DespieceMaestro (variables + subconjuntos)
    → DespieceMaestroLinea (resultados calculados)
    → [Generar APU básico]
"""

from django.db import models


class DespieceMaestro(models.Model):
    BORRADOR = "BORRADOR"
    GUARDADO = "GUARDADO"
    ESTADOS = [
        (BORRADOR, "Borrador"),
        (GUARDADO, "Guardado"),
    ]

    subsistema = models.ForeignKey(
        "ingenieria.Subsistema",
        on_delete=models.PROTECT,
        related_name="despieces_maestro",
        verbose_name="Subsistema",
    )
    subconjuntos = models.ManyToManyField(
        "ingenieria.SubconjuntoRecetaTecnica",
        blank=True,
        related_name="despieces",
        verbose_name="Subconjuntos incluidos",
        help_text="Subconjuntos de la receta técnica que se calculan en este despiece.",
    )
    nombre = models.CharField(
        max_length=200, blank=True,
        help_text="Nombre descriptivo opcional. Ej: 'Cubierta oficinas – Lote Norte'",
    )
    estado = models.CharField(
        max_length=20, choices=ESTADOS, default=BORRADOR,
        db_index=True,
    )
    variables_entrada = models.JSONField(
        default=dict, blank=True,
        help_text="Snapshot de las variables ingresadas al momento del último cálculo/guardado.",
    )
    resultado_snapshot = models.JSONField(
        default=list, blank=True,
        help_text="Snapshot inmutable del resultado del cálculo (lista de líneas).",
    )
    notas = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "despieces_maestro"
        ordering = ["-created_at"]
        verbose_name = "Despiece Maestro"
        verbose_name_plural = "Despieces Maestro"

    def __str__(self):
        nombre = self.nombre or f"Despiece #{self.pk}"
        return f"{nombre} — {self.subsistema.codigo}"

    @property
    def esta_guardado(self):
        return self.estado == self.GUARDADO

    @property
    def tiene_lineas(self):
        return self.lineas.exists()


class DespieceMaestroLinea(models.Model):
    """
    Una línea de resultado dentro de un DespieceMaestro guardado.

    Guarda el snapshot completo del componente calculado: fórmula, cantidad,
    subconjunto al que pertenece y demás datos para reconstruirlo sin depender
    de que la receta técnica no haya cambiado.

    Incluye además el snapshot del producto seleccionado y su precio al momento
    de guardar, para mantener trazabilidad histórica de valorización.
    """
    despiece = models.ForeignKey(
        DespieceMaestro,
        on_delete=models.CASCADE,
        related_name="lineas",
    )
    subconjunto = models.ForeignKey(
        "ingenieria.SubconjuntoRecetaTecnica",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="lineas_despiece",
    )
    # Snapshots técnicos (no dependen de que el modelo de ingeniería cambie)
    subconjunto_nombre = models.CharField(max_length=200, blank=True, default="General")
    componente_codigo  = models.CharField(max_length=80)
    componente_nombre  = models.CharField(max_length=200, blank=True)
    formula_texto      = models.TextField(blank=True)
    cantidad_calculada = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    unidad             = models.CharField(max_length=40, blank=True)
    variable_salida    = models.CharField(max_length=80, blank=True)
    variable_referencia_apu = models.CharField(max_length=80, blank=True)
    unidad_apu         = models.CharField(max_length=40, blank=True)
    categoria_nombre   = models.CharField(max_length=200, blank=True)
    orden              = models.PositiveIntegerField(default=1)

    # ── Snapshot de producto seleccionado ─────────────────────────────────────
    producto = models.ForeignKey(
        "catalogos.Producto",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="lineas_despiece_maestro",
        help_text="Producto del catálogo seleccionado para este componente.",
    )
    producto_codigo  = models.CharField(max_length=50, blank=True)
    producto_nombre  = models.CharField(max_length=300, blank=True)
    precio_unitario  = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    precio_total     = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    moneda           = models.CharField(max_length=3, blank=True)
    fecha_precio     = models.DateTimeField(null=True, blank=True,
                         help_text="Snapshot de fecha_actualizacion_precio del producto al guardar.")

    class Meta:
        app_label = "ingenieria"
        db_table = "despieces_maestro_lineas"
        ordering = ["orden"]
        verbose_name = "Línea de Despiece Maestro"
        verbose_name_plural = "Líneas de Despiece Maestro"

    def __str__(self):
        return f"[{self.despiece_id}] {self.componente_codigo} → {self.cantidad_calculada}"
