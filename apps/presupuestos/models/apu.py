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

    class TipoAPUConsolidacion(models.TextChoices):
        INDIVIDUAL  = "INDIVIDUAL",  "APU individual"
        CONSOLIDADO = "CONSOLIDADO", "APU consolidado"

    MODALIDAD_AIU_CHOICES = [
        ("1", "Modalidad 1 — AIU sobre todos los costos directos"),
        ("2", "Modalidad 2 — AIU sobre costos directos sin materiales"),
    ]

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

    # -- Tipo de APU y proyecto contenedor (Fase 11.5) --
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
        blank=True, null=True,
        related_name="apus_consolidados",
        help_text="Proyecto contenedor. Sólo se usa en APUs consolidados; los individuales lo derivan de proyecto_sistema.",
    )

    # -- AIU del proyecto (Fase 11.3) --
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

    # -- AIU final (snapshot aprobado) --
    aiu_final_admin_pct = models.DecimalField(
        max_digits=8, decimal_places=4, blank=True, null=True,
        help_text="Snapshot de Administración (%) aprobado por el revisor. Si NULL usa aiu_proyecto_admin_pct.",
    )
    aiu_final_imprevistos_pct = models.DecimalField(
        max_digits=8, decimal_places=4, blank=True, null=True,
        help_text="Snapshot de Imprevistos (%) aprobado por el revisor. Si NULL usa aiu_proyecto_imprevistos_pct.",
    )
    aiu_final_utilidad_pct = models.DecimalField(
        max_digits=8, decimal_places=4, blank=True, null=True,
        help_text="Snapshot de Utilidad (%) aprobado por el revisor. Si NULL usa aiu_proyecto_utilidad_pct.",
    )

    # -- Modalidad AIU seleccionada --
    modalidad_aiu_seleccionada = models.CharField(
        max_length=2,
        choices=MODALIDAD_AIU_CHOICES,
        blank=True, null=True,
        verbose_name="Modalidad AIU seleccionada",
    )

    # -- Revisión y aprobación --
    revisor = models.ForeignKey(
        "configuracion.ConfiguracionSistema",
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name="apus_en_revision",
        verbose_name="Revisor asignado",
    )
    fecha_envio_revision = models.DateTimeField(
        blank=True, null=True,
        verbose_name="Fecha de envío a revisión",
    )
    aprobado_por = models.ForeignKey(
        "configuracion.ConfiguracionSistema",
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name="apus_aprobados",
        verbose_name="Aprobado por",
    )
    fecha_aprobacion = models.DateTimeField(
        blank=True, null=True,
        verbose_name="Fecha de aprobación",
    )

    # -- APUs incluidos en el presupuesto final (Fase 13) --
    apus_presupuesto_ids = models.JSONField(
        default=list, blank=True,
        help_text=(
            "Lista de PKs de otros APUProyecto del mismo proyecto que se incluyen "
            "en el cálculo del presupuesto final consolidado. Se guarda al enviar a revisión."
        ),
    )

    # -- Base APU (cantidad de referencia para el presupuesto por proyecto) --
    cantidad_base_apu = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True,
        help_text=(
            "Cantidad de referencia del APU (p. ej. m², ml). "
            "Se calcula automáticamente al ejecutar «Guardar APU» desde el panel confirmado. "
            "valor_total_proyecto = cantidad_base_apu × total_valor_venta."
        ),
    )
    unidad_base_apu = models.CharField(
        max_length=30, blank=True, default="",
        help_text="Unidad de medida de la base APU (m², ml, und, …).",
    )

    # -- Archivo --
    archivado = models.BooleanField(
        default=False, db_index=True,
        help_text="Si True, el APU está archivado: oculto en listas por defecto, preserva trazabilidad.",
    )
    archivado_por = models.ForeignKey(
        "configuracion.ConfiguracionSistema",
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name="apus_archivados",
    )
    fecha_archivado = models.DateTimeField(blank=True, null=True)
    motivo_archivado = models.TextField(blank=True, default="")

    # -- Subtotales por categoría (calculados) --
    subtotal_materiales = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Suma de costo_total de todas las líneas de MATERIALES.",
    )
    valor_materiales = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Suma de valor_total de todas las líneas de MATERIALES (con margen de venta e IVA).",
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
    subtotal_polizas = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Suma de valor_calculado de las pólizas activas del APU. Calculado automáticamente.",
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
            if tipo == TipoAPU.MATERIALES:
                self.valor_materiales = valor   # guardar valor de materiales por separado
            total_costo += costo
            total_valor += valor

        self.total_costo = total_costo
        self.total_valor_venta = total_valor

        # Recalcular pólizas usando los subtotales recién calculados.
        # _recalcular_polizas actualiza self.subtotal_polizas (sin hacer save)
        # y persiste los valores de cada APUPoliza con bulk_update.
        _recalcular_polizas(self)

        self.save(update_fields=[
            "subtotal_materiales", "valor_materiales",
            "subtotal_herramientas",
            "subtotal_transporte", "subtotal_mano_obra",
            "subtotal_administracion", "subtotal_polizas",
            "total_costo", "total_valor_venta", "updated_at",
        ])

    # ------------------------------------------------------------------
    # Propiedades de estado
    # ------------------------------------------------------------------

    @property
    def es_consolidado(self) -> bool:
        """True si este APU es de tipo CONSOLIDADO (une varios APUs individuales)."""
        return self.tipo_apu == self.TipoAPUConsolidacion.CONSOLIDADO

    @property
    def esta_aprobado(self) -> bool:
        """True si ya se seleccionó una modalidad AIU oficial."""
        return bool(self.modalidad_aiu_seleccionada)

    # ------------------------------------------------------------------
    # Navegación de relaciones
    # ------------------------------------------------------------------

    def get_proyecto(self):
        """
        Devuelve el Proyecto comercial contenedor.
        - APU individual: lo deriva desde proyecto_sistema.proyecto.
        - APU consolidado: usa el FK directo a proyecto.
        """
        if self.proyecto_id:
            return self.proyecto
        if self.proyecto_sistema_id:
            ps = self.proyecto_sistema
            return getattr(ps, "proyecto", None)
        return None

    def get_apus_origen(self):
        """
        Queryset de APUs individuales que componen este APU consolidado
        (vía APUConsolidadoOrigen). Vacío si no es consolidado.
        """
        return (
            APUProyecto.objects
            .filter(consolidaciones_destino__apu_consolidado=self)
            .order_by("consolidaciones_destino__orden", "pk")
        )

    # ------------------------------------------------------------------
    # Cálculo AIU
    # ------------------------------------------------------------------

    def get_aiu_pct_efectivos(self) -> dict:
        """
        Devuelve los porcentajes A/I/U efectivos del APU.
        Usa el snapshot final (aiu_final_*) si fue aprobado; de lo contrario
        los porcentajes base configurados en el proyecto.

        Retorna:
            {
              "admin":        Decimal,
              "imprevistos":  Decimal,
              "utilidad":     Decimal,
              "es_final":     bool,   # True si provienen del snapshot aprobado
            }
        """
        tiene_final = (
            self.aiu_final_admin_pct is not None
            or self.aiu_final_imprevistos_pct is not None
            or self.aiu_final_utilidad_pct is not None
        )
        return {
            "admin": (
                self.aiu_final_admin_pct
                if self.aiu_final_admin_pct is not None
                else self.aiu_proyecto_admin_pct
            ),
            "imprevistos": (
                self.aiu_final_imprevistos_pct
                if self.aiu_final_imprevistos_pct is not None
                else self.aiu_proyecto_imprevistos_pct
            ),
            "utilidad": (
                self.aiu_final_utilidad_pct
                if self.aiu_final_utilidad_pct is not None
                else self.aiu_proyecto_utilidad_pct
            ),
            "es_final": tiene_final,
        }

    def calcular_modalidades_aiu(self, pct_override=None) -> dict:  # pct_override: Optional[dict]
        """
        Calcula las dos modalidades de AIU del proyecto.

        Modalidad 1 — base = todos los costos directos (mat + herr + transp + MO).
        Modalidad 2 — base = costos directos sin materiales (herr + transp + MO);
                       materiales se suman al precio de venta.

        La Administración (A) es el subtotal_administracion real de las líneas APU,
        no un porcentaje configurado. admin_pct se DERIVA de él para display.
        Imprevistos (I) y Utilidad (U) se aplican como % sobre la base.

        Args:
            pct_override: dict opcional con claves "imprevistos" y "utilidad"
                          (Decimal) para el preview del revisor.

        Retorna:
            {
              "porcentajes": {"admin": Decimal, "imprevistos": Decimal,
                              "utilidad": Decimal, "es_final": bool},
              "subtotales": OrderedDict (label → valor),
              "modalidad1": {...},
              "modalidad2": {...},
            }
        """
        from collections import OrderedDict

        _Q = Decimal("0.01")   # cuantificación para display

        efectivos = self.get_aiu_pct_efectivos()
        pct_imprevistos = Decimal(str(
            pct_override.get("imprevistos", efectivos["imprevistos"])
            if pct_override else efectivos["imprevistos"]
        ))
        pct_utilidad = Decimal(str(
            pct_override.get("utilidad", efectivos["utilidad"])
            if pct_override else efectivos["utilidad"]
        ))

        # Issue 3+6 fix: usar Valores Totales (valor_total con margen de venta)
        # en lugar de los subtotales de costo (subtotal_materiales, etc.).
        from django.db.models import Sum as _Sum
        def _valor(tipo_filter):
            return Decimal(str(
                self.lineas.filter(tipo=tipo_filter)
                .aggregate(v=_Sum("valor_total"))["v"] or 0
            ))
        mat    = _valor(TipoAPU.MATERIALES)
        herr   = _valor(TipoAPU.HERRAMIENTAS_EQUIPOS)
        transp = _valor(TipoAPU.TRANSPORTE)
        mo     = _valor(TipoAPU.MANO_DE_OBRA)
        admin  = _valor(TipoAPU.ADMINISTRACION)
        polizas = Decimal(str(self.subtotal_polizas or 0))  # ya calculado con valores

        # admin_total agrupa administración y pólizas como overhead conjunto
        admin_total = admin + polizas

        # Valor de venta de materiales para Modalidad 2 (mismo que mat, ya es valor)
        mat_valor_venta = mat

        # ── Modalidad 1 ─────────────────────────────────────────────────
        base_m1 = mat + herr + transp + mo       # sin admin ni pólizas
        pct_admin_m1 = (
            (admin_total / base_m1 * 100).quantize(_Q)
            if base_m1 else Decimal("0")
        )
        I_m1 = (base_m1 * pct_imprevistos / 100).quantize(_Q)
        U_m1 = (base_m1 * pct_utilidad    / 100).quantize(_Q)
        sub_aiu_m1 = base_m1 + admin_total + I_m1 + U_m1

        iva_factor_m1 = Decimal("0")
        if self.aplica_iva:
            iva_pct = Decimal(str(self.iva_pct or 0))
            iva_factor_m1 = (sub_aiu_m1 * iva_pct / 100).quantize(_Q)

        total_m1 = sub_aiu_m1 + iva_factor_m1

        # ── Modalidad 2 ─────────────────────────────────────────────────
        base_m2 = herr + transp + mo             # sin mat ni admin ni pólizas
        pct_admin_m2 = (
            (admin_total / base_m2 * 100).quantize(_Q)
            if base_m2 else Decimal("0")
        )
        I_m2 = (base_m2 * pct_imprevistos / 100).quantize(_Q)
        U_m2 = (base_m2 * pct_utilidad    / 100).quantize(_Q)
        sub_aiu_m2 = mat_valor_venta + base_m2 + admin_total + I_m2 + U_m2

        iva_factor_m2 = Decimal("0")
        if self.aplica_iva:
            iva_pct = Decimal(str(self.iva_pct or 0))
            iva_factor_m2 = (sub_aiu_m2 * iva_pct / 100).quantize(_Q)

        total_m2 = sub_aiu_m2 + iva_factor_m2

        subtotales = OrderedDict([
            ("materiales",    mat),
            ("herramientas",  herr),
            ("mano_de_obra",  mo),   # guión bajo para compatibilidad con dot-notation en templates
            ("transporte",    transp),
            ("administracion", admin),
            ("polizas",        polizas),
            ("total",          mat + herr + transp + mo + admin_total),
        ])
        # Alias para templates que usan mano_obra (sin de) — compatibilidad
        subtotales["mano_obra"] = mo

        return {
            "porcentajes": {
                "admin":       pct_admin_m1,  # % derivado de admin_total sobre base M1 (referencia)
                "imprevistos": pct_imprevistos,
                "utilidad":    pct_utilidad,
                "es_final":    efectivos["es_final"],
            },
            "subtotales": subtotales,
            "modalidad1": {
                "label":          "AIU sobre todos los costos directos",
                "base":           base_m1,
                "admin":          admin,
                "polizas":        polizas,
                "admin_total":    admin_total,
                "admin_pct":      pct_admin_m1,
                "imprevistos":    I_m1,
                "utilidad":       U_m1,
                "total_aiu":      admin_total + I_m1 + U_m1,
                "subtotal_con_aiu": sub_aiu_m1,
                "iva_valor":      iva_factor_m1,
                "total_con_iva":  total_m1,
                "gran_total":     total_m1,
                "valor_total_mat": mat,
            },
            "modalidad2": {
                "label":          "AIU sobre costos directos sin materiales",
                "base":           base_m2,
                "admin":          admin,
                "polizas":        polizas,
                "admin_total":    admin_total,
                "admin_pct":      pct_admin_m2,
                "imprevistos":    I_m2,
                "utilidad":       U_m2,
                "total_aiu":      admin_total + I_m2 + U_m2,
                "subtotal_con_aiu": sub_aiu_m2,
                "iva_valor":      iva_factor_m2,
                "total_con_iva":  total_m2,
                "gran_total":     total_m2,
                "valor_total_mat": mat_valor_venta,
            },
        }

    def get_resumen_cotizacion(self) -> dict:
        """
        Calcula el resumen de cotización del APU usando la modalidad AIU aprobada
        (o la Modalidad 1 si aún no hay aprobación).

        La forma del dict que devuelve coincide con lo que
        CotizacionSnapshotService.construir_contexto_pdf() rehidrata,
        para que las plantillas WeasyPrint puedan reutilizarse tal cual.
        """
        modalidad = self.modalidad_aiu_seleccionada or "1"
        modalidades = self.calcular_modalidades_aiu()
        md = modalidades["modalidad1" if modalidad == "1" else "modalidad2"]
        porcentajes = modalidades["porcentajes"]

        # Subtotales de costo
        mat    = Decimal(str(self.subtotal_materiales    or 0))
        herr   = Decimal(str(self.subtotal_herramientas  or 0))
        transp = Decimal(str(self.subtotal_transporte    or 0))
        mo     = Decimal(str(self.subtotal_mano_obra     or 0))
        admin  = Decimal(str(self.subtotal_administracion or 0))
        polizas = Decimal(str(self.subtotal_polizas      or 0))

        # Base directa sin admin → subtotal_directos_tecnico
        if modalidad == "2":
            base_tecnico = herr + transp + mo
        else:
            base_tecnico = mat + herr + transp + mo

        sub_con_aiu = md["subtotal_con_aiu"]
        iva_pct     = Decimal(str(self.iva_pct or 0))
        iva_valor   = md["iva_valor"]
        total_final = md["gran_total"]

        # Proyecto, cliente, solicitud
        proyecto  = self.get_proyecto()
        solicitud = getattr(proyecto, "solicitud", None) if proyecto else None
        cliente   = getattr(proyecto, "cliente",   None) if proyecto else None
        ps        = self.proyecto_sistema if self.proyecto_sistema_id else None
        sistema   = getattr(ps, "sistema",    None) if ps else None
        subsistema= getattr(ps, "subsistema", None) if ps else None
        contacto  = None
        if cliente:
            contacto = (
                getattr(cliente, "contactos", None)
                and cliente.contactos.order_by("pk").first()
            )

        _label_modal = {
            "1": "AIU sobre todos los costos directos",
            "2": "AIU sobre costos directos sin materiales",
        }

        return {
            "es_preliminar":           not self.esta_aprobado,
            "modalidad_oficial":       self.modalidad_aiu_seleccionada,
            "modalidad_oficial_label": _label_modal.get(modalidad, ""),
            "modalidades_disponibles": modalidades,
            # Subtotales
            "subtotal_materiales":       mat,
            "subtotal_herramientas":     herr,
            "subtotal_transporte":       transp,
            "subtotal_mano_obra":        mo,
            "subtotal_administracion":   admin,
            "subtotal_polizas":          polizas,
            "subtotal_directos_tecnico": base_tecnico,
            # AIU
            "porcentaje_admin":          porcentajes["admin"],
            "porcentaje_imprevistos":    porcentajes["imprevistos"],
            "porcentaje_utilidad":       porcentajes["utilidad"],
            "valor_admin":               md["admin"],
            "valor_imprevistos":         md["imprevistos"],
            "valor_utilidad":            md["utilidad"],
            "total_aiu":                 md["total_aiu"],
            "subtotal_con_aiu":          sub_con_aiu,
            "aiu_es_final":              porcentajes["es_final"],
            # IVA
            "aplica_iva":  self.aplica_iva,
            "iva_pct":     iva_pct,
            "iva_base":    sub_con_aiu,
            "iva_valor":   iva_valor,
            "iva_label":   f"IVA ({iva_pct:.0f}%) sobre subtotal con AIU" if self.aplica_iva else "IVA (no aplica)",
            # Totales
            "total_final": total_final,
            # Relaciones
            "cliente":          cliente,
            "contacto":         contacto,
            "proyecto":         proyecto,
            "solicitud":        solicitud,
            "sistema":          sistema,
            "subsistema":       subsistema,
            "aprobado_por":     self.aprobado_por if self.aprobado_por_id else None,
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
# 6. SubsistemaItemAPU (ítems APU predeterminados por subsistema)
# ---------------------------------------------------------------------------

class SubsistemaItemAPU(models.Model):
    """
    Ítem APU predeterminado asociado a un subsistema.
    Define qué recursos (herramientas, transporte, mano de obra, administración)
    se incluyen por defecto al generar el APU de un proyecto para este subsistema.
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
            "Tipo de APU bajo el cual aplica el ítem. "
            "Debe coincidir con categoria.tipo_apu del item_catalogo en flujos normales."
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
        ordering = ["subsistema", "tipo", "orden", "item_catalogo__nombre"]
        verbose_name = "Ítem APU del subsistema"
        verbose_name_plural = "Ítems APU del subsistema"
        unique_together = [("subsistema", "item_catalogo", "tipo")]

    def __str__(self):
        return f"{self.subsistema} – {self.item_catalogo} ({self.get_tipo_display()})"


# ---------------------------------------------------------------------------
# 7. APUDespieceIncluido (vínculo APU ↔ DespieceMaestro)
# ---------------------------------------------------------------------------

class APUDespieceIncluido(models.Model):
    """
    Vínculo explícito entre un APU y los DespieceMaestro seleccionados para él.

    Fuente de verdad para saber "qué despiece está en qué APU" (Fase 11.4).
    El campo `activo` permite desactivar sin borrar para preservar histórico.
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
        ordering = ["apu", "orden", "id"]
        verbose_name = "Despiece incluido en APU"
        verbose_name_plural = "Despieces incluidos en APU"
        unique_together = [("apu", "despiece_maestro")]

    def __str__(self):
        return f"{self.apu} ← {self.despiece_maestro}"


# ---------------------------------------------------------------------------
# 8. APUConsolidadoOrigen (trazabilidad de APUs consolidados)
# ---------------------------------------------------------------------------

class APUConsolidadoOrigen(models.Model):
    """
    Registro de qué APUs individuales componen un APU consolidado (Fase 11.5).
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
        ordering = ["apu_consolidado", "orden", "id"]
        verbose_name = "Origen de APU consolidado"
        verbose_name_plural = "Orígenes de APUs consolidados"
        unique_together = [("apu_consolidado", "apu_origen")]

    def __str__(self):
        return f"{self.apu_consolidado} ← {self.apu_origen}"


# ---------------------------------------------------------------------------
# 7. APUPoliza — pólizas de cumplimiento y seguros
# ---------------------------------------------------------------------------

class APUPoliza(models.Model):
    """
    Póliza de cumplimiento o seguro asociada a un APU.

    El backend calcula base_calculada y valor_calculado durante recalcular();
    el frontend NUNCA envía valores calculados — solo nombre, porcentaje,
    base_calculo y activa.  La persistencia masiva se hace con bulk_update
    para evitar disparar signals de APULinea.
    """

    BASE_CHOICES = [
        ("total_directo", "Total costos directos (mat + herr + transp + MO)"),
        ("mano_obra",     "Mano de obra"),
        ("materiales",    "Materiales"),
        ("transporte",    "Transporte"),
        ("herramientas",  "Herramientas y equipos"),
    ]

    apu = models.ForeignKey(
        "presupuestos.APUProyecto",
        on_delete=models.CASCADE,
        related_name="polizas",
    )
    nombre = models.CharField(max_length=200, verbose_name="Nombre de la póliza")
    porcentaje = models.DecimalField(
        max_digits=8, decimal_places=4,
        verbose_name="Porcentaje (%)",
        help_text="Porcentaje sobre la base seleccionada. Ej: 1.5 → 1.5 %.",
    )
    base_calculo = models.CharField(
        max_length=40,
        choices=BASE_CHOICES,
        default="total_directo",
        verbose_name="Base de cálculo (legacy, una sola)",
        help_text="Campo heredado. Usar bases_calculo para selección múltiple.",
    )
    bases_calculo = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Bases de cálculo",
        help_text=(
            "Lista de bases seleccionadas. Ej: ['materiales', 'mano_obra']. "
            "Si está vacía, se usa base_calculo (compatibilidad). "
            "Valores válidos: total_directo, mano_obra, materiales, transporte, herramientas."
        ),
    )
    # Campos calculados — solo escritura del backend
    base_calculada = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="Valor de la base en el último recálculo. Actualizado automáticamente.",
    )
    valor_calculado = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0"),
        help_text="base_calculada × porcentaje / 100. Actualizado automáticamente.",
    )
    activa = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "apu_polizas"
        ordering = ["orden", "id"]
        verbose_name = "Póliza APU"
        verbose_name_plural = "Pólizas APU"

    def __str__(self):
        return f"{self.nombre} ({self.porcentaje} %) → APU #{self.apu_id}"


def _recalcular_polizas(apu: "APUProyecto") -> None:
    """
    Recalcula base_calculada y valor_calculado de todas las pólizas activas
    del APU y actualiza apu.subtotal_polizas en memoria (sin hacer save;
    el caller incluye 'subtotal_polizas' en su update_fields).

    Usa bulk_update para persistir los cambios en APUPoliza sin disparar
    signals de APULinea que causarían recursión.
    """
    polizas = list(apu.polizas.filter(activa=True))
    if not polizas:
        apu.subtotal_polizas = Decimal("0")
        return

    # Issue 6 fix: usar Valores Totales (valor_total con margen) como base.
    from django.db.models import Sum as _SumP
    def _vt(tipo):
        return Decimal(str(
            apu.lineas.filter(tipo=tipo).aggregate(v=_SumP("valor_total"))["v"] or 0
        ))
    _vt_mat  = _vt("MATERIALES")
    _vt_herr = _vt("HERRAMIENTAS_EQUIPOS")
    _vt_transp = _vt("TRANSPORTE")
    _vt_mo   = _vt("MANO_DE_OBRA")

    _BASE_MAP = {
        "total_directo": _vt_mat + _vt_herr + _vt_transp + _vt_mo,
        "mano_obra":     _vt_mo,
        "materiales":    _vt_mat,
        "transporte":    _vt_transp,
        "herramientas":  _vt_herr,
    }

    total = Decimal("0")
    for p in polizas:
        # Issue 6: soportar múltiples bases (JSONField bases_calculo).
        # Si bases_calculo es lista no vacía, sumar cada base; si no, usar base_calculo legacy.
        bases_lista = []
        if isinstance(getattr(p, "bases_calculo", None), list) and p.bases_calculo:
            bases_lista = p.bases_calculo
        elif p.base_calculo:
            bases_lista = [p.base_calculo]

        base_total = sum(_BASE_MAP.get(b, Decimal("0")) for b in bases_lista)
        p.base_calculada  = base_total
        p.valor_calculado = (base_total * Decimal(str(p.porcentaje)) / 100).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        total += p.valor_calculado

    APUPoliza.objects.bulk_update(polizas, ["base_calculada", "valor_calculado"])
    apu.subtotal_polizas = total


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