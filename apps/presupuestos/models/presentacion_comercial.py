"""
apps/presupuestos/models/presentacion_comercial.py — Fase 3.D.

Presentación comercial de un ítem del presupuesto del proyecto.

Principio: LA ECONOMÍA DEL APU DEFINE EL DINERO; LA PRESENTACIÓN DEFINE CÓMO LO
VE EL CLIENTE. Estos modelos NO guardan unidad, P.U., total ni la cantidad
económica: todo eso se lee en vivo de APUProyecto (cantidad_base_apu,
unidad_base_apu) y del cálculo del presupuesto.

  - Sin PresentacionItemPresupuesto  → presentación original.
  - Cabecera sin líneas               → una sola línea personalizada.
  - Cabecera con ≥2 líneas            → desglose; válido solo si
                                         Σ cantidad = APUProyecto.cantidad_base_apu.
"""

from django.db import models


class PresentacionItemPresupuesto(models.Model):
    """Cabecera: nombre/descripción comerciales de un APU dentro del presupuesto."""

    apu = models.OneToOneField(
        "presupuestos.APUProyecto",
        on_delete=models.CASCADE,
        related_name="presentacion_comercial",
    )
    nombre_comercial = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Vacío = nombre técnico original (subsistema).",
    )
    descripcion_comercial = models.TextField(
        blank=True, default="",
        help_text="Vacío = descripción del APU. Editarla NO modifica APUProyecto.descripcion.",
    )
    actualizado_por = models.ForeignKey(
        "configuracion.ConfiguracionSistema",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="presentaciones_presupuesto",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "presupuesto_presentaciones_item"
        verbose_name = "Presentación comercial de ítem"
        verbose_name_plural = "Presentaciones comerciales de ítems"

    def __str__(self):
        return f"Presentación APU #{self.apu_id}"


class LineaPresentacionPresupuesto(models.Model):
    """Sublínea del desglose comercial. Solo distribuye cantidad; no guarda dinero."""

    presentacion = models.ForeignKey(
        PresentacionItemPresupuesto,
        on_delete=models.CASCADE,
        related_name="lineas",
    )
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, default="")
    cantidad = models.DecimalField(max_digits=18, decimal_places=4)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        app_label = "presupuestos"
        db_table = "presupuesto_presentaciones_linea"
        ordering = ["presentacion", "orden", "id"]
        verbose_name = "Línea de presentación comercial"
        verbose_name_plural = "Líneas de presentación comercial"
        constraints = [
            models.CheckConstraint(
                check=models.Q(cantidad__gt=0), name="presentacion_linea_cantidad_positiva",
            ),
            models.UniqueConstraint(
                fields=["presentacion", "orden"], name="presentacion_linea_orden_unico",
            ),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.cantidad})"
