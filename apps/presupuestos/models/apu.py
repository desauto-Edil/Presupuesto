"""
apps/presupuestos/models/apu.py — Análisis de Precios Unitarios (APU).

"""

import math
from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.db.models import Sum

from apps.common.choices import TipoAPU


# Nombres matemáticos seguros para eval() — misma técnica que ComponenteSubsistema
_SAFE_MATH = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}


class ConfiguracionAPU(models.Model):
    """
    Valores predeterminados del APU, configurables por Administrador.
    Solo debe existir un registro activo (se crea automáticamente si no existe).
    """

    nombre = models.CharField(max_length=100, default="Configuración global")
    factor_venta_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("20"),
        help_text="Margen de venta (%). Se suma al costo para obtener el valor unitario. Ej: 20 → multiplica × 1.20.",
    )
    iva_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("19"),
        help_text="Porcentaje de IVA aplicado a materiales cuando corresponda.",
    )
    aiu_contratista_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("30"),
        help_text="AIU del contratista (%).",
    )
    margen_ganancia_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("20"),
        help_text="Margen de ganancia general (%).",
    )
    desperdicio_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("3"),
        help_text="Porcentaje de desperdicio sobre materiales.",
    )
    activa = models.BooleanField(default=True)
    modificado_por = models.ForeignKey(
        "configuracion.ConfiguracionSistema",
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name="configs_apu",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "configuracion_apu"
        verbose_name = "Configuración APU"
        verbose_name_plural = "Configuraciones APU"

    def __str__(self):
        return self.nombre

    @classmethod
    def activa_o_default(cls):
        cfg = cls.objects.filter(activa=True).first()
        if not cfg:
            cfg = cls.objects.create()
        return cfg


# ---------------------------------------------------------------------------
# 2. Catálogo de ítems APU
# ---------------------------------------------------------------------------

class CategoriaItemAPU(models.Model):
    """
    Categoría del catálogo APU: agrupa ítems por TipoAPU.
    Permite organizar la UI del catálogo (p. ej. "Herramienta eléctrica",
    "Herramienta soldadura TPO", "Personal", "Cuadrilla cubierta"…).
    """

    tipo_apu = models.CharField(
        max_length=30, choices=TipoAPU.choices,
        help_text="Tipo de APU al que pertenecen los ítems de esta categoría.",
    )
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0, help_text="Orden en la UI.")
    aplica_dias_mensuales = models.BooleanField(
        default=False,
        help_text=(
            "Si True, los días de duración se dividen entre 30 en la fórmula de costo. "
            "Usar en categorías de personal donde el salario es mensual."
        ),
    )

    class Meta:
        app_label = "presupuestos"
        db_table = "catalogo_apu_categorias"
        ordering = ["orden", "nombre"]
        verbose_name = "Categoría de ítem APU"
        verbose_name_plural = "Categorías de ítems APU"

    def __str__(self):
        return f"{self.nombre} [{self.get_tipo_apu_display()}]"


class ItemCatalogoAPU(models.Model):
    """
    Ítem reutilizable del catálogo APU.

    Representa cualquier recurso que compone un APU:
      - Personal       (Oficial de obra, Ayudante práctico, Ayudante razo…)
      - Herramienta    (Atornilladora inalámbrica, Taladro percutor, Triac Leister…)
      - Dotación       (Jean, Chaleco reflectivo, Botas de seguridad…)
      - Transporte     (Flete, Viáticos…)
      - Administración (Gerente de proyecto, Residente, Secretaria…)

    Campos adicionales para personal:
      salario_base y prestaciones_pct permiten calcular el costo mensual real.

    Campos adicionales para herramientas:
      vida_util_dias permite derivar el costo por jornada (depreciación).
    """

    UNIDAD_CHOICES = [
        ("dia",    "Día"),
        ("mes",    "Mes"),
        ("hora",   "Hora"),
        ("und",    "Unidad"),
        ("mts",    "Metros"),
        ("global", "Global"),
    ]

    categoria = models.ForeignKey(
        CategoriaItemAPU,
        on_delete=models.PROTECT,
        related_name="items",
    )
    codigo = models.CharField(max_length=50, unique=True, blank=True, null=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)

    # Precio base: interpreta según la unidad
    precio_base = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Precio/salario base del ítem por unidad ($/und, $/día, $/mes…).",
    )
    unidad = models.CharField(max_length=20, choices=UNIDAD_CHOICES, default="und")

    tienda_referencia = models.CharField(
        max_length=200, blank=True, default="",
        verbose_name="Tienda de referencia",
        help_text="Proveedor o tienda donde se cotizó el precio base.",
    )

    # Solo para personal: prestaciones sociales
    salario_base = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"), blank=True,
        help_text="Salario base mensual del cargo (solo personal).",
    )
    prestaciones = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"), blank=True,
        help_text="Valor de prestaciones sociales mensuales (solo personal).",
    )

    # Solo para herramientas/dotación: vida útil para calcular depreciación
    vida_util_dias = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Vida útil en días. Permite calcular costo por jornada.",
    )

    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "catalogo_apu_items"
        ordering = ["categoria", "nombre"]
        verbose_name = "Ítem de catálogo APU"
        verbose_name_plural = "Ítems de catálogo APU"

    def __str__(self):
        return f"{self.nombre} — ${self.precio_base:,.0f}/{self.get_unidad_display()}"

    @property
    def total_mes_personal(self) -> Decimal:
        """Salario base + prestaciones (solo aplica a personal)."""
        return self.salario_base + self.prestaciones

    @property
    def costo_por_dia_herramienta(self) -> Decimal:
        """
        Depreciación diaria de una herramienta.
        costo_por_dia = precio_base / vida_util_dias
        Retorna 0 si no aplica.
        """
        if self.vida_util_dias and self.vida_util_dias > 0:
            return (self.precio_base / Decimal(self.vida_util_dias)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        return Decimal("0")

    @property
    def costo_por_dia(self) -> Decimal:
        """Alias de costo_por_dia_herramienta para uso en plantillas."""
        return self.costo_por_dia_herramienta


# ---------------------------------------------------------------------------
# 3. Cuadrillas preset
# ---------------------------------------------------------------------------

class CuadrillaPreset(models.Model):
    """
    Plantilla de cuadrilla reutilizable.

    Ejemplos:
        - "Cuadrilla básica"   (Oficial ×1, Ayudante práctico ×1, Ayudante razo ×1)
        - "Cuadrilla cubierta" (Oficial ×1, Ayudante práctico ×2, Ayudante razo ×4)
    """

    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "cuadrilla_presets"
        ordering = ["nombre"]
        verbose_name = "Preset de cuadrilla"
        verbose_name_plural = "Presets de cuadrilla"

    def __str__(self):
        return self.nombre

    @property
    def total_personas(self) -> int:
        return sum(i.cantidad for i in self.items.all())

    @property
    def costo_mes_total(self) -> Decimal:
        """Suma de (salario_base + prestaciones) × cantidad de cada cargo."""
        return sum(
            i.item.total_mes_personal * i.cantidad
            for i in self.items.select_related("item").all()
        )


class CuadrillaPresetItem(models.Model):
    """Línea de composición de una cuadrilla preset (un cargo × cantidad)."""

    preset = models.ForeignKey(
        CuadrillaPreset, on_delete=models.CASCADE, related_name="items"
    )
    item = models.ForeignKey(
        ItemCatalogoAPU,
        on_delete=models.PROTECT,
        related_name="cuadrilla_uses",
    )
    cantidad = models.PositiveIntegerField(default=1)

    class Meta:
        app_label = "presupuestos"
        db_table = "cuadrilla_preset_items"
        unique_together = [["preset", "item"]]
        verbose_name = "Ítem de cuadrilla preset"
        verbose_name_plural = "Ítems de cuadrilla preset"

    def __str__(self):
        return f"{self.preset.nombre} / {self.item.nombre} ×{self.cantidad}"


# ---------------------------------------------------------------------------
# 4. Reglas de cálculo APU por subsistema
# ---------------------------------------------------------------------------

class ReglaAPUSubsistema(models.Model):
    """
    Fórmula de costo unitario para una categoría de APU, definida en el subsistema.

    Se crea desde la edición del Subsistema (inline en SubsistemaAdmin) para que
    cada receta técnica defina sus propios factores de cálculo.

    Una regla por subsistema × tipo_apu (excepto MATERIALES, que se calcula desde
    las líneas del despiece).

    Variables disponibles en formula_costo_unitario:
        suma      — suma del costo de todos los ítems de la categoría (float)
        aiu       — factor AIU, e.g. 1.30 si AIU=30%
        margen    — factor margen, e.g. 1.20 si margen=20%
        dias      — días efectivos (ya ajustados si aplica_dias_mensuales)
        tp        — total_powergrip (denominador)
        personas  — número de personas en cuadrilla (solo MO)
        factor_venta — factor de venta, e.g. 1.21 si factor_venta=121%

    Ejemplo Herramientas:  suma * aiu * margen * dias / tp
    Ejemplo Mano de Obra:  suma * aiu * margen * dias * personas / tp
    Ejemplo Transporte:    suma / tp
    Ejemplo Administración: suma * aiu * margen * dias / tp
    """

    subsistema = models.ForeignKey(
        "ingenieria.Subsistema",
        on_delete=models.CASCADE,
        related_name="reglas_apu",
    )
    tipo_apu = models.CharField(
        max_length=30,
        choices=[c for c in TipoAPU.choices if c[0] != TipoAPU.MATERIALES],
        help_text="Tipo de APU al que aplica esta regla (no aplica a MATERIALES).",
    )
    formula_costo_unitario = models.TextField(
        help_text=(
            "Expresión Python que devuelve el costo unitario de la categoría. "
            "Variables: suma, aiu, margen, dias, tp, personas, factor_venta. "
            "Ej (herramientas): suma * aiu * margen * dias / tp"
        ),
    )
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "presupuestos"
        db_table = "reglas_apu_subsistema"
        unique_together = [["subsistema", "tipo_apu"]]
        ordering = ["subsistema", "orden"]
        verbose_name = "Regla APU de subsistema"
        verbose_name_plural = "Reglas APU de subsistema"

    def __str__(self):
        return f"{self.subsistema} — {self.get_tipo_apu_display()}"

    def evaluar(self, contexto: dict) -> float:
        """
        Evalúa formula_costo_unitario con el contexto dado.
        Usa eval() restringido (mismo patrón que ComponenteSubsistema).
        """
        safe_ctx = {**_SAFE_MATH, **contexto}
        result = eval(self.formula_costo_unitario, {"__builtins__": {}}, safe_ctx)
        return float(result)


# ---------------------------------------------------------------------------
# 5. APU (cabecera)
# ---------------------------------------------------------------------------

class APUProyecto(models.Model):
    """
    Cabecera del Análisis de Precios Unitarios (APUProyecto).

    Contiene:
      - Identificación (nombre, descripción).
      - Vínculo opcional a un ProyectoSistema.
      - Parámetros de cálculo (IVA, factor de venta, AIU…).
      - Subtotales y totales calculados desde las APULineas.

    El recálculo se lanza con APUProyecto.recalcular() o automáticamente
    desde las señales post_save / post_delete de APULinea.
    """

    # -- Identificación --
    nombre = models.CharField(
        max_length=200,
        help_text="Nombre del APU, p. ej. 'APU Cubierta TPO — Edificio Central'.",
    )
    descripcion = models.TextField(
        blank=True,
        help_text="Descripción detallada del alcance y condiciones del APU.",
    )

    # -- Vínculo al proyecto (opcional para APUs genéricos del catálogo) --
    proyecto_sistema = models.OneToOneField(
        "presupuestos.ProyectoSistema",
        on_delete=models.CASCADE,
        related_name="apu",
        null=True, blank=True,
        help_text="ProyectoSistema al que pertenece este APU (si aplica).",
    )

    # ── Fase 11.5 — Consolidación opcional de APUs ────────────────────────
    # `tipo_apu` distingue APUs individuales (flujo histórico) de APUs
    # consolidados creados por confirmación explícita del usuario.
    # `proyecto` permite que un APU consolidado pertenezca al proyecto sin
    # estar atado a un ProyectoSistema raíz (los individuales mantienen su
    # OneToOneField como llave natural).
    class TipoAPUConsolidacion(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "APU individual"
        CONSOLIDADO = "CONSOLIDADO", "APU consolidado"

    tipo_apu = models.CharField(
        max_length=20,
        choices=TipoAPUConsolidacion.choices,
        default=TipoAPUConsolidacion.INDIVIDUAL,
        db_index=True,
        help_text="INDIVIDUAL (flujo histórico) o CONSOLIDADO (unión opcional de varios APUs).",
    )
    proyecto = models.ForeignKey(
        "comercial.Proyecto",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="apus_consolidados",
        help_text="Proyecto contenedor. Sólo se usa en APUs consolidados; los individuales lo derivan de proyecto_sistema.",
    )

    # -- Parámetros de cálculo --
    factor_venta_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("20"),
        help_text="Margen de venta (%). Valor unit = Costo unit × (1 + factor/100). Ej: 20 → × 1.20.",
    )
    iva_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("19"),
    )
    aplica_iva = models.BooleanField(default=True)
    aiu_contratista_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("30"),
        help_text="AIU del contratista (%). Se aplica al calcular costo unitario de MO, herramientas, transporte y admin.",
    )
    margen_ganancia_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("20"),
        help_text="Margen de ganancia (%). Se aplica junto al AIU en el costo unitario.",
    )
    dias_duracion = models.PositiveIntegerField(
        default=30,
        help_text="Días de duración del proyecto. Se usa para calcular el costo unitario de MO, herramientas, etc.",
    )

    # -- Subtotales por categoría (calculados) --
    subtotal_materiales = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Suma de costo_total de todas las líneas de MATERIALES.",
    )
    subtotal_herramientas = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Suma de costo_total de todas las líneas de HERRAMIENTAS_EQUIPOS.",
    )
    subtotal_transporte = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
    )
    subtotal_mano_obra = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
    )
    subtotal_administracion = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
    )

    # -- Totales generales (calculados) --
    total_costo = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Suma de todos los costo_total (sin margen de venta).",
    )
    total_valor_venta = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Suma de todos los valor_total (con margen de venta).",
    )

    # -- AIU del proyecto (tres porcentajes separados del AIU del contratista) --
    aiu_proyecto_admin_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("10"),
        help_text="Administración del proyecto (%). Se aplica sobre los costos directos para la modalidad AIU del proyecto.",
    )
    aiu_proyecto_imprevistos_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("5"),
        help_text="Imprevistos del proyecto (%).",
    )
    aiu_proyecto_utilidad_pct = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("8"),
        help_text="Utilidad del proyecto (%).",
    )

    # --- AIU final aprobado por el revisor (Fase 10A). Snapshot opcional. ---
    # Si están NULL, calcular_modalidades_aiu() usa los porcentajes base.
    aiu_final_admin_pct = models.DecimalField(
        max_digits=8, decimal_places=4,
        null=True, blank=True,
        help_text="Snapshot de Administración (%) aprobado por el revisor. Si NULL usa aiu_proyecto_admin_pct.",
    )
    aiu_final_imprevistos_pct = models.DecimalField(
        max_digits=8, decimal_places=4,
        null=True, blank=True,
        help_text="Snapshot de Imprevistos (%) aprobado por el revisor. Si NULL usa aiu_proyecto_imprevistos_pct.",
    )
    aiu_final_utilidad_pct = models.DecimalField(
        max_digits=8, decimal_places=4,
        null=True, blank=True,
        help_text="Snapshot de Utilidad (%) aprobado por el revisor. Si NULL usa aiu_proyecto_utilidad_pct.",
    )

    # -- Garantía comercial (Fase 9). No afecta cálculo. --
    aplica_garantia = models.BooleanField(
        default=False,
        help_text="Indica si la propuesta incluye garantía. No afecta el cálculo.",
    )
    tipo_garantia = models.ForeignKey(
        "comercial.TipoGarantia",
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="apus",
        help_text="Tipo de garantía ofrecida en la propuesta (opcional).",
    )

    # --- Recargo comercial de garantía (Fase 9R) ---
    GARANTIA_MODO_TOTAL = "TOTAL_MATERIALES"
    GARANTIA_MODO_ESPECIFICO = "MATERIAL_ESPECIFICO"
    GARANTIA_MODO_CHOICES = [
        (GARANTIA_MODO_TOTAL, "Sobre el total de materiales"),
        (GARANTIA_MODO_ESPECIFICO, "Sobre un material específico"),
    ]
    garantia_porcentaje_aplicado = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="Snapshot del % de recargo tomado del catálogo al armar/editar la garantía.",
    )
    garantia_modo_aplicacion = models.CharField(
        max_length=24, blank=True, default="",
        choices=GARANTIA_MODO_CHOICES,
        help_text="Cómo se aplica la garantía: sobre el total de materiales o sobre un material específico.",
    )
    garantia_material_linea = models.ForeignKey(
        "presupuestos.APULinea",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="+",
        help_text="APULinea tipo Materiales sobre la que se aplica el recargo (modo MATERIAL_ESPECIFICO).",
    )
    garantia_material_nombre_snapshot = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Snapshot textual del material objetivo (para trazabilidad si la línea se elimina).",
    )
    garantia_base_valor = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        help_text="Base sobre la que se calculó el recargo.",
    )
    garantia_valor_recargo = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        help_text="Recargo comercial sumado a total_valor_venta.",
    )

    # -- Flujo de revisión --
    revisor = models.ForeignKey(
        "configuracion.ConfiguracionSistema",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="apus_en_revision",
        verbose_name="Revisor asignado",
    )
    fecha_envio_revision = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Fecha de envío a revisión",
    )
    MODALIDAD_CHOICES = [
        ("1", "Modalidad 1 — AIU sobre todos los costos directos"),
        ("2", "Modalidad 2 — AIU sobre costos directos sin materiales"),
    ]
    modalidad_aiu_seleccionada = models.CharField(
        max_length=2, blank=True, null=True,
        choices=MODALIDAD_CHOICES,
        verbose_name="Modalidad AIU seleccionada",
    )
    aprobado_por = models.ForeignKey(
        "configuracion.ConfiguracionSistema",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="apus_aprobados",
        verbose_name="Aprobado por",
    )
    fecha_aprobacion = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Fecha de aprobación",
    )

    # ── Fase 11.5.3 — Archivado lógico ─────────────────────────────────────
    # APUProyecto no tiene estado propio de anulado/archivado (su "estado"
    # surge de modalidad + aprobación). Para preservar trazabilidad cuando
    # un APU individual está incluido en un consolidado (PROTECT en
    # APUConsolidadoOrigen.apu_origen), introducimos un flag de archivado
    # ortogonal a la maquinaria de AIU/garantía.
    archivado = models.BooleanField(
        default=False, db_index=True,
        help_text="Si True, el APU está archivado: oculto en listas por defecto, preserva trazabilidad.",
    )
    fecha_archivado = models.DateTimeField(null=True, blank=True)
    archivado_por = models.ForeignKey(
        "configuracion.ConfiguracionSistema",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="apus_archivados",
    )
    motivo_archivado = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "apus"
        verbose_name = "APU"
        verbose_name_plural = "APUs"

    def __str__(self):
        return self.nombre

    # ------------------------------------------------------------------
    # Fase 11.5 — Consolidado: helpers
    # ------------------------------------------------------------------

    @property
    def es_consolidado(self) -> bool:
        return self.tipo_apu == self.TipoAPUConsolidacion.CONSOLIDADO

    @property
    def cotizacion_vigente(self):
        """Fase 12 — Último snapshot APROBADA de cotización, o None."""
        return self.cotizaciones.filter(estado="APROBADA").order_by("-version").first()

    def get_proyecto(self):
        """Devuelve el Proyecto contenedor (sea individual o consolidado)."""
        if self.proyecto_id:
            return self.proyecto
        if self.proyecto_sistema_id and self.proyecto_sistema.proyecto_id:
            return self.proyecto_sistema.proyecto
        return None

    def get_apus_origen(self):
        """En consolidado: lista de APUProyecto individuales que lo originaron."""
        if not self.es_consolidado:
            return self.__class__.objects.none()
        return (
            self.__class__.objects
            .filter(consolidaciones_destino__apu_consolidado=self)
            .order_by("consolidaciones_destino__orden", "id")
        )

    # ------------------------------------------------------------------
    # Despieces incluidos (Fase 11.3 — aproximado, sin migración)
    # ------------------------------------------------------------------

    def get_despieces_incluidos(self):
        """
        Fase 11.4: devuelve los DespieceMaestro realmente seleccionados para
        este APU según la relación explícita `APUDespieceIncluido`.

        Fallback legacy: si no existe ningún registro de inclusión explícita
        (APUs creados antes de Fase 11.4), regresa al filtro aproximado por
        proyecto+subsistema usado en Fase 11.3 — solo para lectura.
        """
        from apps.ingenieria.models import DespieceMaestro
        # Camino moderno: relación explícita.
        incluidos = (
            self.despieces_incluidos
            .filter(activo=True)
            .select_related(
                "despiece_maestro",
                "despiece_maestro__subsistema",
                "despiece_maestro__subsistema__sistema",
            )
            .order_by("orden", "id")
        )
        dms = [inc.despiece_maestro for inc in incluidos if inc.despiece_maestro_id]
        if dms:
            return dms

        # Fallback legacy (APUs pre-11.4): inferir por proyecto+subsistema.
        ps = self.proyecto_sistema
        if not ps or not ps.proyecto_id or not ps.subsistema_id:
            return []
        return list(
            DespieceMaestro.objects.filter(
                proyecto=ps.proyecto,
                subsistema=ps.subsistema,
                estado=DespieceMaestro.GUARDADO,
            ).select_related("subsistema", "subsistema__sistema")
        )

    def es_legacy_sin_seleccion(self) -> bool:
        """
        Fase 11.4: True cuando el APU no tiene registros de APUDespieceIncluido
        activos (creado antes de la selección manual). Sirve para mostrar
        banner de advertencia en apu_detail y para fallback de lectura.
        """
        return not self.despieces_incluidos.filter(activo=True).exists()

    # ------------------------------------------------------------------
    # Recálculo
    # ------------------------------------------------------------------

    def recalcular(self):
        """
        Recalcula los subtotales y totales del APU agregando desde la BD.
        NO vuelve a llamar linea.calcular() para evitar recursión en signals.
        """
        # Agregar por tipo
        _TIPO_CAMPO = {
            TipoAPU.MATERIALES:          "subtotal_materiales",
            TipoAPU.HERRAMIENTAS_EQUIPOS: "subtotal_herramientas",
            TipoAPU.TRANSPORTE:          "subtotal_transporte",
            TipoAPU.MANO_DE_OBRA:        "subtotal_mano_obra",
            TipoAPU.ADMINISTRACION:      "subtotal_administracion",
        }

        total_costo = Decimal("0")
        total_valor = Decimal("0")

        for tipo, campo in _TIPO_CAMPO.items():
            if tipo == TipoAPU.MATERIALES:
                # Materiales: sumar todas las líneas (cada una es un componente del despiece)
                qs = self.lineas.filter(tipo=tipo)
            else:
                # No-materiales: sumar solo las líneas resumen (item_catalogo=None, despiece_linea=None).
                # Estas son las líneas que contienen el costo agregado por categoría.
                # Si no existen líneas resumen (APU en formato antiguo), se usa fallback a todas las líneas.
                qs_resumen = self.lineas.filter(
                    tipo=tipo,
                    item_catalogo__isnull=True,
                    despiece_linea__isnull=True,
                )
                qs = qs_resumen if qs_resumen.exists() else self.lineas.filter(tipo=tipo)

            agg = qs.aggregate(
                costo=Sum("costo_total"),
                valor=Sum("valor_total"),
            )
            costo = Decimal(str(agg["costo"] or 0))
            valor = Decimal(str(agg["valor"] or 0))
            setattr(self, campo, costo)
            total_costo += costo
            total_valor += valor

        self.total_costo = total_costo
        self.total_valor_venta = total_valor

        # Fase 9R — recargo comercial de garantía sobre Materiales.
        # No afecta subtotal_materiales técnico; solo suma a total_valor_venta.
        self._recalcular_garantia_inline()
        self.total_valor_venta = total_valor + (self.garantia_valor_recargo or Decimal("0"))

        self.save(update_fields=[
            "subtotal_materiales", "subtotal_herramientas",
            "subtotal_transporte", "subtotal_mano_obra",
            "subtotal_administracion",
            "total_costo", "total_valor_venta",
            "garantia_base_valor", "garantia_valor_recargo",
            "updated_at",
        ])

    def _recalcular_garantia_inline(self):
        """
        Recalcula garantia_base_valor y garantia_valor_recargo a partir del
        estado actual del APU. NO toca el snapshot porcentaje_aplicado (eso
        solo cambia cuando el usuario edita la garantía).
        """
        if not self.aplica_garantia or not self.tipo_garantia_id:
            self.garantia_base_valor = Decimal("0")
            self.garantia_valor_recargo = Decimal("0")
            return

        pct = self.garantia_porcentaje_aplicado
        if pct is None:
            # APU legacy Fase 9 sin snapshot — no aplicar recargo silencioso.
            self.garantia_base_valor = Decimal("0")
            self.garantia_valor_recargo = Decimal("0")
            return

        if (
            self.garantia_modo_aplicacion == self.GARANTIA_MODO_ESPECIFICO
            and self.garantia_material_linea_id
        ):
            base = Decimal(str(self.garantia_material_linea.valor_total or 0))
        else:
            base = Decimal(str(self.subtotal_materiales or 0))

        recargo = (base * Decimal(str(pct)) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        self.garantia_base_valor = base
        self.garantia_valor_recargo = recargo

    @property
    def subtotal_materiales_ajustado(self) -> Decimal:
        """Subtotal de Materiales + recargo comercial de garantía."""
        return (self.subtotal_materiales or Decimal("0")) + (self.garantia_valor_recargo or Decimal("0"))

    @property
    def garantia_legacy_sin_snapshot(self) -> bool:
        """True si la garantía fue creada antes de Fase 9R y no tiene snapshot %."""
        return bool(self.aplica_garantia and self.tipo_garantia_id and self.garantia_porcentaje_aplicado is None)

    def get_aiu_pct_efectivos(self) -> dict:
        """
        Devuelve los porcentajes A/I/U efectivos para el cálculo del AIU final
        del proyecto. Si el revisor aprobó porcentajes finales (aiu_final_*_pct),
        se usan esos; si están NULL, se usan los porcentajes base del proyecto
        (aiu_proyecto_*_pct).
        """
        admin = self.aiu_final_admin_pct if self.aiu_final_admin_pct is not None else self.aiu_proyecto_admin_pct
        imprev = self.aiu_final_imprevistos_pct if self.aiu_final_imprevistos_pct is not None else self.aiu_proyecto_imprevistos_pct
        utilidad = self.aiu_final_utilidad_pct if self.aiu_final_utilidad_pct is not None else self.aiu_proyecto_utilidad_pct
        return {
            "admin": Decimal(str(admin or 0)),
            "imprevistos": Decimal(str(imprev or 0)),
            "utilidad": Decimal(str(utilidad or 0)),
            "es_final": self.aiu_final_admin_pct is not None
                        or self.aiu_final_imprevistos_pct is not None
                        or self.aiu_final_utilidad_pct is not None,
        }

    def calcular_modalidades_aiu(self, pct_override=None) -> dict:
        """
        Calcula las dos modalidades de AIU del proyecto sobre subtotales técnicos.

        Modalidad 1 — AIU sobre todos los costos directos técnicos:
          base = materiales + herramientas + transporte + mano_obra + administracion

        Modalidad 2 — AIU sobre costos directos técnicos sin materiales:
          base_aiu = herramientas + transporte + mano_obra + administracion

        Decisión Fase 10A-2: la garantía Red Shield NO entra en la base AIU.
        Sigue afectando total_valor_venta como recargo comercial posterior.

        Porcentajes:
          - Si `pct_override` está dado (preview en revisor), se usa.
          - Si no, get_aiu_pct_efectivos() (finales del revisor o base del proyecto).

        Gran total aprobado = subtotal_directos_tecnico + total_aiu + garantia_valor_recargo
        """
        mat  = self.subtotal_materiales
        herr = self.subtotal_herramientas
        tran = self.subtotal_transporte
        mo   = self.subtotal_mano_obra
        adm  = self.subtotal_administracion

        if pct_override is not None:
            pct_a = Decimal(str(pct_override.get("admin", 0)))
            pct_i = Decimal(str(pct_override.get("imprevistos", 0)))
            pct_u = Decimal(str(pct_override.get("utilidad", 0)))
        else:
            efectivos = self.get_aiu_pct_efectivos()
            pct_a = efectivos["admin"]
            pct_i = efectivos["imprevistos"]
            pct_u = efectivos["utilidad"]

        subtotal = mat + herr + tran + mo + adm
        # Fase 10A-2: garantía se suma DESPUÉS del AIU, no entra en su base.
        garantia = Decimal(str(self.garantia_valor_recargo or 0))

        # Modalidad 1: base = todos los costos directos técnicos
        base1 = subtotal
        a1 = (base1 * pct_a / 100).quantize(Decimal("0.01"))
        i1 = (base1 * pct_i / 100).quantize(Decimal("0.01"))
        u1 = (base1 * pct_u / 100).quantize(Decimal("0.01"))
        total_aiu1 = a1 + i1 + u1
        gran_total1 = subtotal + total_aiu1 + garantia

        # Modalidad 2: base AIU = costos directos técnicos sin materiales
        base2 = herr + tran + mo + adm
        a2 = (base2 * pct_a / 100).quantize(Decimal("0.01"))
        i2 = (base2 * pct_i / 100).quantize(Decimal("0.01"))
        u2 = (base2 * pct_u / 100).quantize(Decimal("0.01"))
        total_aiu2 = a2 + i2 + u2
        gran_total2 = subtotal + total_aiu2 + garantia

        return {
            "subtotales": {
                "materiales":    mat,
                "herramientas":  herr,
                "transporte":    tran,
                "mano_obra":     mo,
                "administracion": adm,
                "total":         subtotal,
            },
            "porcentajes": {
                "admin":       pct_a,
                "imprevistos": pct_i,
                "utilidad":    pct_u,
                "es_final":    (pct_override is None) and self.get_aiu_pct_efectivos()["es_final"],
            },
            "garantia_recargo": garantia,
            "modalidad1": {
                "label":       "AIU sobre todos los costos directos",
                "base":        base1,
                "admin":       a1,
                "imprevistos": i1,
                "utilidad":    u1,
                "total_aiu":   total_aiu1,
                "gran_total":  gran_total1,
            },
            "modalidad2": {
                "label":       "AIU sobre costos directos sin materiales",
                "base":        base2,
                "admin":       a2,
                "imprevistos": i2,
                "utilidad":    u2,
                "total_aiu":   total_aiu2,
                "gran_total":  gran_total2,
            },
        }

    def get_resumen_cotizacion(self) -> dict:
        """
        Fase 11 — Resumen comercial para la vista de cotización final.

        Centraliza la matemática para que el template no calcule totales.
        Reglas (Excel técnico + decisiones Fase 9R/10A/11):
          - Si hay modalidad aprobada: usa esa modalidad como bloque oficial.
          - Si no hay modalidad aprobada: es_preliminar=True, modalidades como referencia.
          - Garantía Red Shield: recargo separado, fuera de base AIU y base IVA.
          - IVA sobre la Utilidad (decisión Fase 11): iva_valor = valor_utilidad * iva_pct / 100.
          - Si aplica_iva=False: iva_valor=0, label "Exento / No aplica".
          - Fórmula final:
                total_final = subtotal_directos_tecnico
                            + total_aiu
                            + garantia_valor_recargo
                            + iva_sobre_utilidad
        """
        modalidades = self.calcular_modalidades_aiu()
        modalidad_aprobada = (self.modalidad_aiu_seleccionada or "").strip()
        es_preliminar = modalidad_aprobada not in ("1", "2")

        if es_preliminar:
            # Para preliminar, mostramos M1 como bloque "principal" de referencia
            modalidad_key = "modalidad1"
            modalidad_label_oficial = None
        else:
            modalidad_key = f"modalidad{modalidad_aprobada}"
            modalidad_label_oficial = modalidades[modalidad_key]["label"]

        bloque = modalidades[modalidad_key]
        subtotales = modalidades["subtotales"]
        porcentajes = modalidades["porcentajes"]

        subtotal_directos = subtotales["total"]
        total_aiu = bloque["total_aiu"]
        valor_admin = bloque["admin"]
        valor_imprevistos = bloque["imprevistos"]
        valor_utilidad = bloque["utilidad"]

        garantia_recargo = Decimal(str(self.garantia_valor_recargo or 0))
        subtotal_con_aiu = subtotal_directos + total_aiu

        iva_pct = Decimal(str(self.iva_pct or 0))
        aplica_iva = bool(self.aplica_iva) and iva_pct > 0
        if aplica_iva:
            iva_base = valor_utilidad
            iva_valor = (iva_base * iva_pct / Decimal("100")).quantize(Decimal("0.01"))
            iva_label = f"IVA {iva_pct}% sobre Utilidad"
        else:
            iva_base = Decimal("0")
            iva_valor = Decimal("0")
            iva_label = "Exento / No aplica"

        total_final = subtotal_directos + total_aiu + garantia_recargo + iva_valor

        # Garantía detalle
        garantia_info = {
            "aplica": bool(self.aplica_garantia and (self.tipo_garantia_id or self.garantia_valor_recargo)),
            "tipo": self.tipo_garantia,
            "tipo_nombre": (self.tipo_garantia.nombre if self.tipo_garantia_id else ""),
            "porcentaje_aplicado": self.garantia_porcentaje_aplicado,
            "modo_aplicacion": self.garantia_modo_aplicacion,
            "material_snapshot": self.garantia_material_nombre_snapshot,
            "base_valor": self.garantia_base_valor,
            "valor_recargo": garantia_recargo,
            "condiciones": (self.tipo_garantia.condiciones if self.tipo_garantia_id else ""),
        }

        # Contexto relacional
        ps = self.proyecto_sistema
        proyecto = ps.proyecto if ps else None
        solicitud = proyecto.solicitud if (proyecto and proyecto.solicitud_id) else None
        cliente = proyecto.cliente if (proyecto and proyecto.cliente_id) else None
        sistema = ps.sistema if ps else None
        subsistema = ps.subsistema if ps else None
        contacto = cliente.contacto_principal if cliente else None

        return {
            "es_preliminar": es_preliminar,
            "modalidad_oficial": (modalidad_aprobada if not es_preliminar else None),
            "modalidad_oficial_label": modalidad_label_oficial,
            "modalidades_disponibles": modalidades if es_preliminar else None,
            # Subtotales técnicos
            "subtotal_materiales": subtotales["materiales"],
            "garantia_valor_recargo": garantia_recargo,
            "subtotal_materiales_ajustado": self.subtotal_materiales_ajustado,
            "subtotal_herramientas": subtotales["herramientas"],
            "subtotal_transporte": subtotales["transporte"],
            "subtotal_mano_obra": subtotales["mano_obra"],
            "subtotal_administracion": subtotales["administracion"],
            "subtotal_directos_tecnico": subtotal_directos,
            # AIU
            "porcentaje_admin": porcentajes["admin"],
            "porcentaje_imprevistos": porcentajes["imprevistos"],
            "porcentaje_utilidad": porcentajes["utilidad"],
            "valor_admin": valor_admin,
            "valor_imprevistos": valor_imprevistos,
            "valor_utilidad": valor_utilidad,
            "total_aiu": total_aiu,
            "subtotal_con_aiu": subtotal_con_aiu,
            "aiu_es_final": porcentajes["es_final"],
            # IVA
            "aplica_iva": aplica_iva,
            "iva_pct": iva_pct,
            "iva_base": iva_base,
            "iva_valor": iva_valor,
            "iva_label": iva_label,
            # Total
            "total_final": total_final,
            # Bloques relacionales
            "garantia": garantia_info,
            "cliente": cliente,
            "contacto": contacto,
            "proyecto": proyecto,
            "solicitud": solicitud,
            "sistema": sistema,
            "subsistema": subsistema,
            # Aprobación
            "aprobado_por": self.aprobado_por,
            "fecha_aprobacion": self.fecha_aprobacion,
        }


# backward compatibility alias
APU = APUProyecto

# ---------------------------------------------------------------------------
# 5. APULinea (ítems individuales)
# ---------------------------------------------------------------------------

class APULinea(models.Model):
    """
    Línea individual del APU: un recurso con su rendimiento y precios.

    Tipos posibles (TipoAPU):
        MATERIALES          — componentes seleccionados del despiece
        HERRAMIENTAS_EQUIPOS — herramientas, dotación, equipos
        TRANSPORTE          — fletes, viáticos
        MANO_DE_OBRA        — personal / cuadrilla
        ADMINISTRACION      — costos administrativos

    Fórmulas:
        costo_unitario = precio_referencia × IVA_factor
        costo_total    = rendimiento × costo_unitario
        valor_unitario = costo_unitario × (1 + factor_venta_pct / 100)
        valor_total    = rendimiento × valor_unitario
    """

    UNIDAD_CHOICES = [
        ("und",    "Unidad"),
        ("m2",     "Metro cuadrado"),
        ("ml",     "Metro lineal"),
        ("mts",    "Metros"),
        ("kg",     "Kilogramo"),
        ("galon",  "Galón"),
        ("kilo",   "Kilo"),
        ("cartucho", "Cartucho"),
        ("dia",    "Día"),
        ("mes",    "Mes"),
        ("hora",   "Hora"),
        ("global", "Global"),
    ]

    apu = models.ForeignKey(
        "presupuestos.APUProyecto",
        on_delete=models.CASCADE,
        related_name="lineas",
    )
    tipo = models.CharField(
        max_length=30,
        choices=TipoAPU.choices,
        db_index=True,
    )

    # -- Origen del ítem --
    item_catalogo = models.ForeignKey(
        ItemCatalogoAPU,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="apu_lineas",
        help_text="Ítem del catálogo APU del que proviene esta línea.",
    )
    despiece_linea = models.ForeignKey(
        "presupuestos.DespieceLinea",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="apu_lineas",
        help_text="Ítem del despiece de materiales (solo para tipo MATERIALES).",
    )

    # ── Fase 11.4 — Trazabilidad multi-despiece ───────────────────────────
    # Sólo aplica a líneas de tipo MATERIALES. Permite agrupar materiales por
    # sistema/subsistema/despiece en apu_detail y PDFs cuando el APU consolida
    # varios DespieceMaestro seleccionados manualmente.
    despiece_maestro = models.ForeignKey(
        "ingenieria.DespieceMaestro",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="apu_lineas",
        help_text="DespieceMaestro de origen (sólo MATERIALES). NULL en líneas legacy.",
    )
    sistema_nombre_snapshot = models.CharField(
        max_length=120, blank=True, default="",
        help_text="Snapshot textual del sistema asociado a la línea (Fase 11.4).",
    )
    subsistema_nombre_snapshot = models.CharField(
        max_length=120, blank=True, default="",
        help_text="Snapshot textual del subsistema asociado a la línea (Fase 11.4).",
    )

    # ── Fase 11.5 — Trazabilidad de APU origen en consolidados ────────────
    # En APUs consolidados cada línea conserva el APU individual del que
    # proviene. En APUs individuales queda NULL.
    apu_origen = models.ForeignKey(
        "presupuestos.APUProyecto",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="lineas_consolidadas",
        help_text="APU individual de origen (sólo en APUs consolidados, Fase 11.5).",
    )

    # -- Descripción editable (se copia del catálogo pero puede ajustarse) --
    descripcion = models.CharField(max_length=300)

    # -- Entradas del cálculo --
    rendimiento = models.DecimalField(
        max_digits=14, decimal_places=6, default=Decimal("1"),
        help_text="Cantidad del recurso necesaria por unidad de APU.",
    )
    unidad = models.CharField(
        max_length=20,
        choices=UNIDAD_CHOICES,
        default="und",
        help_text="Unidad de medida del rendimiento.",
    )
    precio_referencia = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("0"),
        help_text="Precio unitario del insumo/recurso (sin IVA).",
    )
    iva_aplicado = models.BooleanField(
        default=True,
        help_text="Si True, se multiplica precio_referencia por el factor IVA del APU.",
    )

    # -- Campos adicionales para herramientas (depreciación) --
    vida_util_dias = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Vida útil en días (herramientas/dotación). "
                  "Permite mostrar el costo por jornada en reportes.",
    )
    costo_por_dia = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("0"),
        help_text="Precio_referencia / vida_util_dias. Calculado automáticamente.",
    )

    # -- Campos adicionales para personal --
    salario_base = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"), blank=True,
        help_text="Salario base mensual (solo personal).",
    )
    prestaciones = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"), blank=True,
        help_text="Prestaciones sociales mensuales (solo personal).",
    )

    # -- Resultados calculados --
    costo_unitario = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("0"),
        help_text="precio_referencia × IVA_factor.",
    )
    costo_total = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("0"),
        help_text="rendimiento × costo_unitario.",
    )
    valor_unitario = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("0"),
        help_text="costo_unitario × (1 + factor_venta_pct / 100).",
    )
    valor_total = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("0"),
        help_text="rendimiento × valor_unitario.",
    )

    tienda_referencia = models.CharField(
        max_length=200, blank=True, default="",
        verbose_name="Tienda de referencia",
        help_text="Proveedor o tienda de referencia (copiado del catálogo).",
    )

    # -- Control de edición manual --
    editable = models.BooleanField(
        default=False,
        help_text="Si True, la configuracion puede modificar precio_referencia y rendimiento.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "apu_lineas"
        ordering = ["tipo", "descripcion"]
        verbose_name = "Línea APU"
        verbose_name_plural = "Líneas APU"

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.descripcion}"

    def calcular(self):

        apu = self.apu

        if (
            self.tipo == TipoAPU.MANO_DE_OBRA
            and self.item_catalogo_id
            and self.salario_base == 0
        ):
            self.salario_base = self.item_catalogo.salario_base
            self.prestaciones = self.item_catalogo.prestaciones

        vu = self.vida_util_dias or (
            self.item_catalogo.vida_util_dias if self.item_catalogo_id else None
        )
        if vu and vu > 0 and self.precio_referencia:
            self.costo_por_dia = (
                Decimal(str(self.precio_referencia)) / Decimal(str(vu))
            ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        else:
            self.costo_por_dia = Decimal("0")

        iva_factor = (
            Decimal("1") + Decimal(str(apu.iva_pct)) / Decimal("100")
            if (self.iva_aplicado and apu.aplica_iva)
            else Decimal("1")
        )
        # factor_venta: mismo convenio que AIU/margen → 20 = 20% markup → ×1.20
        factor_venta = Decimal("1") + Decimal(str(apu.factor_venta_pct)) / Decimal("100")
        rendimiento  = Decimal(str(self.rendimiento)) if self.rendimiento else Decimal("1")
        precio       = Decimal(str(self.precio_referencia))

        # Costo unit  = precio_ref × IVA
        self.costo_unitario = (precio * iva_factor).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        # Costo total = Costo unit × rendimiento
        self.costo_total = (rendimiento * self.costo_unitario).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        # Valor unit  = Costo unit × (1 + factor_venta_pct/100)   (Ej: 20% → ×1.20)
        self.valor_unitario = (self.costo_unitario * factor_venta).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        # Valor total = Valor unit × rendimiento
        self.valor_total = (rendimiento * self.valor_unitario).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )

        self.save(update_fields=[
            "salario_base", "prestaciones",
            "costo_por_dia",
            "costo_unitario", "costo_total",
            "valor_unitario", "valor_total",
            "updated_at",
        ])



# ---------------------------------------------------------------------------
# 6. SubsistemaItemAPU — Ítems APU predeterminados por subsistema (Fase 6L-B)
# ---------------------------------------------------------------------------

class SubsistemaItemAPU(models.Model):
    """
    Asociación entre un Subsistema y un ItemCatalogoAPU.

    Define los ítems APU predeterminados que aplican a un subsistema para
    las categorías NO-Materiales (Herramientas, Transporte, Mano de Obra,
    Administración). Materiales se generan siempre desde el despiece y
    NO usa este modelo.

    Reemplaza el patrón anterior donde APUService traía todo el catálogo
    activo por tipo_apu. Con este modelo, APUService consulta SOLO los
    ítems explícitamente asociados al subsistema.

    Si un subsistema no tiene ítems configurados para una categoría, esa
    categoría queda vacía (no se llena con todo el catálogo como antes).

    Restricciones:
        UNIQUE (subsistema, item_catalogo, tipo)
            — un mismo ítem solo puede asociarse una vez por tipo a un
              subsistema. El tipo está en la asociación (no solo derivado
              del ítem) porque permite escenarios en los que un ítem del
              catálogo se reusa entre categorías compatibles.
    """

    subsistema = models.ForeignKey(
        "ingenieria.Subsistema",
        on_delete=models.CASCADE,
        related_name="items_apu",
        help_text="Subsistema al que aplica este ítem APU predeterminado.",
    )
    item_catalogo = models.ForeignKey(
        ItemCatalogoAPU,
        on_delete=models.CASCADE,
        related_name="asociaciones_subsistema",
        help_text="Ítem del catálogo APU asociado al subsistema.",
    )
    tipo = models.CharField(
        max_length=30,
        choices=[c for c in TipoAPU.choices if c[0] != TipoAPU.MATERIALES],
        help_text=(
            "Tipo de APU bajo el cual aplica el ítem. Debe coincidir con "
            "categoria.tipo_apu del item_catalogo en flujos normales."
        ),
    )
    cantidad = models.PositiveIntegerField(
        default=1,
        help_text="Cantidad predeterminada del ítem para este subsistema.",
    )
    orden = models.PositiveIntegerField(
        default=0,
        help_text="Orden de presentación dentro de la categoría.",
    )
    activo = models.BooleanField(
        default=True,
        help_text="Si False, el ítem se ignora al generar el APU.",
    )
    rendimiento_override = models.DecimalField(
        max_digits=14, decimal_places=6,
        null=True, blank=True,
        help_text=(
            "Rendimiento explícito para sobrescribir el cálculo por fórmula. "
            "Si es NULL, se respeta el cálculo estándar de APUService."
        ),
    )
    observaciones = models.TextField(
        blank=True, default="",
        help_text="Notas internas sobre por qué este ítem aplica al subsistema.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "subsistema_items_apu"
        unique_together = [["subsistema", "item_catalogo", "tipo"]]
        ordering = ["subsistema", "tipo", "orden", "item_catalogo__nombre"]
        verbose_name = "Ítem APU del subsistema"
        verbose_name_plural = "Ítems APU del subsistema"

    def __str__(self):
        return (
            f"{self.subsistema} · {self.get_tipo_display()} · "
            f"{self.item_catalogo.nombre} ×{self.cantidad}"
        )


# ---------------------------------------------------------------------------
# 7. APUDespieceIncluido — Trazabilidad APU ↔ DespieceMaestro (Fase 11.4)
# ---------------------------------------------------------------------------

class APUDespieceIncluido(models.Model):
    """
    Asociación explícita entre un APU y los DespieceMaestro seleccionados
    para él (Fase 11.4). Reemplaza la inferencia por proyecto+subsistema.

    El APU mantiene `proyecto_sistema` como PS raíz (configuración base de
    no-materiales). Los despieces adicionales seleccionados se registran
    aquí con snapshots de sistema/subsistema para que el PDF y las vistas
    sigan mostrando información incluso si los nombres cambian.
    """

    apu = models.ForeignKey(
        "presupuestos.APUProyecto",
        on_delete=models.CASCADE,
        related_name="despieces_incluidos",
        help_text="APU al que pertenece este despiece.",
    )
    despiece_maestro = models.ForeignKey(
        "ingenieria.DespieceMaestro",
        on_delete=models.PROTECT,
        related_name="apus_incluidos",
        help_text="DespieceMaestro seleccionado para el APU.",
    )
    sistema_nombre_snapshot = models.CharField(
        max_length=120, blank=True, default="",
        help_text="Snapshot textual del sistema en el momento de la inclusión.",
    )
    subsistema_nombre_snapshot = models.CharField(
        max_length=120, blank=True, default="",
        help_text="Snapshot textual del subsistema en el momento de la inclusión.",
    )
    orden = models.PositiveSmallIntegerField(
        default=0,
        help_text="Orden de presentación dentro del APU.",
    )
    activo = models.BooleanField(
        default=True,
        help_text="Si False, no se considera incluido (no se borra para preservar histórico).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "apu_despieces_incluidos"
        unique_together = [["apu", "despiece_maestro"]]
        ordering = ["apu", "orden", "id"]
        verbose_name = "Despiece incluido en APU"
        verbose_name_plural = "Despieces incluidos en APU"

    def __str__(self):
        return (
            f"APU #{self.apu_id} ⇐ DM #{self.despiece_maestro_id} "
            f"({self.subsistema_nombre_snapshot or 'sin subsistema'})"
        )


class APUConsolidadoOrigen(models.Model):
    """
    Asociación M2M-through entre un APU consolidado (Fase 11.5) y los APUs
    individuales que lo originaron.

    La consolidación es **opcional** y solo ocurre por confirmación explícita
    del usuario. Los APUs origen conservan su independencia y trazabilidad.
    """

    apu_consolidado = models.ForeignKey(
        "presupuestos.APUProyecto",
        on_delete=models.CASCADE,
        related_name="origenes_consolidado",
        help_text="APU consolidado contenedor.",
    )
    apu_origen = models.ForeignKey(
        "presupuestos.APUProyecto",
        on_delete=models.PROTECT,
        related_name="consolidaciones_destino",
        help_text="APU individual de origen.",
    )
    orden = models.PositiveSmallIntegerField(default=0)
    incluido_en_pdf_cliente = models.BooleanField(
        default=True,
        help_text="Si False, este origen no se lista en el PDF Cliente del consolidado.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "apu_consolidado_origenes"
        unique_together = [["apu_consolidado", "apu_origen"]]
        ordering = ["apu_consolidado", "orden", "id"]
        verbose_name = "Origen de APU consolidado"
        verbose_name_plural = "Orígenes de APUs consolidados"

    def __str__(self):
        return f"APU consolidado #{self.apu_consolidado_id} ⇐ APU #{self.apu_origen_id}"


from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


@receiver(post_save, sender=APULinea)
def _linea_post_save(sender, instance, **kwargs):
    """Recalcula los totales del APU padre cuando se guarda una línea."""
    if kwargs.get("update_fields") and "costo_total" in (kwargs["update_fields"] or []):
        instance.apu.recalcular()


@receiver(post_delete, sender=APULinea)
def _linea_post_delete(sender, instance, **kwargs):
    """Recalcula los totales del APU padre cuando se elimina una línea."""
    instance.apu.recalcular()