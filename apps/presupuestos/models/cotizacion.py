"""
apps/presupuestos/models/cotizacion.py — Snapshot inmutable de cotización aprobada (Fase 12).

Una CotizacionAPU es el documento congelado en el momento exacto en que se
aprueba la modalidad AIU del APU. NO se guardan archivos PDF físicos: solo los
datos finales aprobados, para que los PDFs Interno/Cliente puedan generarse
después en memoria sin depender de los datos vivos del APU.

Reglas:
  - Cada aprobación crea una nueva versión (version = max_version + 1).
  - El último snapshot con estado=APROBADA es el vigente.
  - Snapshots anteriores se marcan REEMPLAZADA — nunca se eliminan.
  - FK al APU con on_delete=PROTECT: un APU con snapshot no puede eliminarse
    físicamente, debe archivarse (refuerza Fase 11.5.3).
"""

from decimal import Decimal

from django.db import models


class CotizacionAPU(models.Model):
    """
    Snapshot inmutable de una cotización aprobada (Fase 12).

    Toda la matemática viva (subtotales, AIU, garantía, IVA, total_final) queda
    congelada en columnas dedicadas. El detalle completo de líneas, secciones
    comerciales y orígenes de consolidado se persiste en `data_snapshot` JSON.
    """

    class Estado(models.TextChoices):
        APROBADA = "APROBADA", "Aprobada (vigente)"
        REEMPLAZADA = "REEMPLAZADA", "Reemplazada"

    # ── Identificación / referencias vivas ────────────────────────────────────
    apu = models.ForeignKey(
        "presupuestos.APUProyecto",
        on_delete=models.PROTECT,
        related_name="cotizaciones",
        help_text="APU del que proviene el snapshot. PROTECT — un APU con cotización aprobada debe archivarse, no eliminarse.",
    )
    proyecto = models.ForeignKey(
        "comercial.Proyecto",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="cotizaciones_aprobadas",
    )
    solicitud = models.ForeignKey(
        "comercial.Solicitud",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="cotizaciones_aprobadas",
    )
    cliente = models.ForeignKey(
        "comercial.Cliente",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="cotizaciones_aprobadas",
    )

    # ── Snapshots textuales (sobreviven a renombres o borrados) ──────────────
    apu_nombre_snapshot = models.CharField(max_length=200, blank=True, default="")
    tipo_apu_snapshot = models.CharField(
        max_length=20, blank=True, default="",
        help_text="INDIVIDUAL o CONSOLIDADO al momento de la aprobación.",
    )
    proyecto_nombre_snapshot = models.CharField(max_length=200, blank=True, default="")
    proyecto_consecutivo_snapshot = models.CharField(max_length=30, blank=True, default="")
    solicitud_consecutivo_snapshot = models.CharField(max_length=30, blank=True, default="")
    cliente_nombre_snapshot = models.CharField(max_length=255, blank=True, default="")
    cliente_nit_snapshot = models.CharField(max_length=50, blank=True, default="")
    moneda_snapshot = models.CharField(max_length=10, blank=True, default="COP")

    # ── Modalidad y aprobación ───────────────────────────────────────────────
    modalidad_aiu_snapshot = models.CharField(
        max_length=2, blank=True, default="",
        help_text="'1' o '2' — modalidad aprobada al momento del snapshot.",
    )
    aprobado_por = models.ForeignKey(
        "configuracion.ConfiguracionSistema",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="cotizaciones_aprobadas",
    )
    aprobado_por_snapshot = models.CharField(max_length=200, blank=True, default="")
    fecha_aprobacion_snapshot = models.DateTimeField(null=True, blank=True)

    # ── Subtotales técnicos ──────────────────────────────────────────────────
    subtotal_materiales = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    subtotal_herramientas = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    subtotal_transporte = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    subtotal_mano_obra = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    subtotal_administracion = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    subtotal_directos_tecnico = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))

    # ── AIU final aprobado ───────────────────────────────────────────────────
    aiu_admin_pct = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0"))
    aiu_imprevistos_pct = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0"))
    aiu_utilidad_pct = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0"))
    aiu_admin_valor = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    aiu_imprevistos_valor = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    aiu_utilidad_valor = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    total_aiu = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))

    # ── Garantía Red Shield ──────────────────────────────────────────────────
    garantia_aplica = models.BooleanField(default=False)
    garantia_nombre_snapshot = models.CharField(max_length=200, blank=True, default="")
    garantia_porcentaje_snapshot = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    garantia_modo_snapshot = models.CharField(max_length=24, blank=True, default="")
    garantia_material_snapshot = models.CharField(max_length=255, blank=True, default="")
    garantia_base_valor = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    garantia_valor_recargo = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    # ── IVA ──────────────────────────────────────────────────────────────────
    aplica_iva = models.BooleanField(default=True)
    iva_pct = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0"))
    iva_base = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    iva_valor = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    iva_label = models.CharField(max_length=120, blank=True, default="")

    # ── Total final aprobado ─────────────────────────────────────────────────
    total_final = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))

    # ── Versionamiento + estado ──────────────────────────────────────────────
    version = models.PositiveIntegerField(
        default=1, db_index=True,
        help_text="Versión por APU. La última con estado=APROBADA es la vigente.",
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.APROBADA,
        db_index=True,
    )

    # ── Detalle completo (líneas, secciones, consolidación) ──────────────────
    data_snapshot = models.JSONField(
        default=dict, blank=True,
        help_text="JSON con líneas, secciones comerciales, despieces incluidos, APUs origen, resumen de consolidación, observaciones.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "cotizaciones_apu"
        unique_together = [["apu", "version"]]
        ordering = ["-apu_id", "-version"]
        verbose_name = "Cotización APU aprobada"
        verbose_name_plural = "Cotizaciones APU aprobadas"

    def __str__(self):
        ref = self.proyecto_consecutivo_snapshot or f"APU#{self.apu_id}"
        return f"Cotización {ref} v{self.version} ({self.get_estado_display()})"

    @property
    def es_vigente(self) -> bool:
        return self.estado == self.Estado.APROBADA

    @property
    def consecutivo_cotizacion(self) -> str:
        """Etiqueta legible: '<proyecto.consecutivo>-COT-v<n>' o fallback."""
        base = self.proyecto_consecutivo_snapshot or f"APU{self.apu_id}"
        return f"{base}-COT-v{self.version}"
