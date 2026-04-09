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
            total_costo += costo
            total_valor += valor

        self.total_costo = total_costo
        self.total_valor_venta = total_valor

        self.save(update_fields=[
            "subtotal_materiales", "subtotal_herramientas",
            "subtotal_transporte", "subtotal_mano_obra",
            "subtotal_administracion",
            "total_costo", "total_valor_venta", "updated_at",
        ])


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