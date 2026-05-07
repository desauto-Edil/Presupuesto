"""
apps/ingenieria/models/sistemas.py — Sistemas y subsistemas técnicos.

Sistema:    conjunto de productos técnicos
Subsistema: variante concreta dentro del sistema, con su propia receta
            de componentes, fórmulas y dependencias.

Un subsistema es una receta técnica REUTILIZABLE.
No define el producto comercial final; eso ocurre en presupuestos.
"""

from django.db import models
from apps.common.choices import (
    LineaNegocio, TipoSistema, TipoProductoConsumo,
    EstadoFisicoProducto, InteriorExterior,
)
import math
import re


class Sistema(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=200)
    linea_negocio = models.CharField(max_length=20,
                                     choices=LineaNegocio.choices)
    tipo_sistema = models.CharField(
        max_length=20,
        choices=TipoSistema.choices,
        default=TipoSistema.CONSTRUCTIVO,
        verbose_name="Tipo de sistema",
        help_text="Constructivo: receta técnica con componentes y fórmulas. Consumo: tabla de capas y consumo de producto.",
    )
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "sistemas"
        verbose_name = "Sistema"
        verbose_name_plural = "Sistemas"

    def __str__(self):
        return f"[{self.codigo}] {self.nombre}"

    @property
    def es_consumo(self):
        return self.tipo_sistema == TipoSistema.CONSUMO


# ---------------------------------------------------------------------------
# CATÁLOGOS PARA SISTEMAS DE CONSUMO
# ---------------------------------------------------------------------------

class FuncionConsumo(models.Model):
    """Función técnica que puede cumplir un producto de consumo."""
    nombre = models.CharField(max_length=200, unique=True,
                              help_text="Ej: Imprimación, Impermeabilización, Capa intermedia")
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "funciones_consumo"
        ordering = ["nombre"]
        verbose_name = "Función de consumo"
        verbose_name_plural = "Funciones de consumo"

    def __str__(self):
        return self.nombre


class ProblemaResuelto(models.Model):
    """Problema técnico que el sistema de consumo ayuda a resolver."""
    nombre = models.CharField(max_length=200, unique=True,
                              help_text="Ej: Filtraciones, Carbonatación, Fisuras")
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "problemas_resueltos"
        ordering = ["nombre"]
        verbose_name = "Problema resuelto"
        verbose_name_plural = "Problemas resueltos"

    def __str__(self):
        return self.nombre


class SuperficieCompatible(models.Model):
    """Tipo de superficie sobre la que se puede aplicar el sistema."""
    nombre = models.CharField(max_length=200, unique=True,
                              help_text="Ej: Concreto, Metal, Madera, Ladrillo")
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "superficies_compatibles"
        ordering = ["nombre"]
        verbose_name = "Superficie compatible"
        verbose_name_plural = "Superficies compatibles"

    def __str__(self):
        return self.nombre


# ---------------------------------------------------------------------------
# SUBSISTEMA
# ---------------------------------------------------------------------------

class Subsistema(models.Model):
    sistema = models.ForeignKey(
        Sistema,
        on_delete=models.CASCADE,
        related_name="subsistemas",
        help_text="Sistema padre al que pertenece esta variante técnica"
    )
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    imagen_tecnica = models.ImageField(
        upload_to="ingenieria/subsistemas/imagenes_tecnicas/",
        null=True, blank=True,
        verbose_name="Imagen técnica",
        help_text="Imagen técnica o diagrama del subsistema (opcional).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "subsistemas"
        verbose_name = "Subsistema (Receta Técnica)"
        verbose_name_plural = "Subsistemas (Recetas)"
        unique_together = ['sistema', 'codigo']

    def __str__(self):
        return f"{self.sistema.nombre} >> {self.nombre}"

    # ── APU: referencia de cantidad ───────────────────────────────────────────
    variable_referencia_apu = models.CharField(
        max_length=80, blank=True, default="",
        verbose_name="Variable de referencia APU",
        help_text=(
            "Nombre de la variable de entrada que representa la cantidad principal "
            "del sistema para el APU. Ej: 'total_powergrip'. "
            "Se usa como divisor para calcular el rendimiento por unidad. "
            "Si se deja vacío, se usa el área del proyecto."
        ),
    )
    unidad_apu = models.CharField(
        max_length=40, blank=True, default="und",
        verbose_name="Unidad del APU",
        help_text="Unidad de la referencia. Ej: 'soporte', 'm²', 'ml'.",
    )

    def tiene_componentes_db(self) -> bool:
        return self.componentes_db.exists()

    # ── Campos exclusivos para Sistema de CONSUMO ─────────────────────────────

    # Múltiples funciones vía M2M (reemplaza CharField funcion)
    funciones = models.ManyToManyField(
        FuncionConsumo,
        blank=True,
        related_name="subsistemas",
        verbose_name="Funciones",
        help_text="Funciones técnicas que cumple este sistema (ej: Imprimación, Impermeabilización)",
    )

    # Problemas que resuelve
    problemas_resuelve = models.ManyToManyField(
        ProblemaResuelto,
        blank=True,
        related_name="subsistemas",
        verbose_name="Problemas que resuelve",
    )

    # Superficies compatibles
    superficies_compatibles = models.ManyToManyField(
        SuperficieCompatible,
        blank=True,
        related_name="subsistemas",
        verbose_name="Superficies compatibles",
    )

    tipo_producto = models.CharField(
        max_length=20,
        choices=TipoProductoConsumo.choices,
        blank=True, default="",
        verbose_name="Tipo de producto",
        help_text="Monocomponente, Bicomponente o Multicomponente",
    )

    resistencia_quimica = models.CharField(
        max_length=300, blank=True, default="",
        verbose_name="Resistencia química",
    )

    temperatura_min = models.DecimalField(
        max_digits=6, decimal_places=1,
        null=True, blank=True,
        verbose_name="Temperatura mínima de aplicación (°C)",
    )
    temperatura_max = models.DecimalField(
        max_digits=6, decimal_places=1,
        null=True, blank=True,
        verbose_name="Temperatura máxima de aplicación (°C)",
    )

    interior_exterior = models.CharField(
        max_length=20,
        choices=InteriorExterior.choices,
        blank=True, default="",
        verbose_name="Interior / Exterior",
    )

    # Consumo numérico — usado por la calculadora
    consumo_min_g_m2 = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Consumo mínimo (g/m² por capa)",
        help_text="Consumo mínimo del producto por m² por capa. Ej: 200",
    )
    consumo_max_g_m2 = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Consumo máximo (g/m² por capa)",
        help_text="Consumo máximo del producto por m² por capa. Ej: 400",
    )


# ---------------------------------------------------------------------------
# VARIABLES DE ENTRADA — definidas en DB para un Subsistema
# ---------------------------------------------------------------------------

class VariableSubsistema(models.Model):
    """
    Variable de entrada que el usuario debe ingresar para un subsistema.
    Equivalente a VariableRequerida en system_defs pero persistida en DB.
    """
    subsistema = models.ForeignKey(
        Subsistema, on_delete=models.CASCADE, related_name="variables_db",
    )
    variable = models.CharField(
        max_length=80,
        help_text="Nombre interno de la variable, sin espacios. Ej: total_powergrip",
    )
    label = models.CharField(max_length=200, help_text="Etiqueta legible para el usuario")
    unidad = models.CharField(max_length=40, blank=True, default="")
    valor_default = models.DecimalField(
        max_digits=18, decimal_places=6, default=0,
        help_text="Valor por defecto si el usuario no lo modifica",
    )
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        app_label = "ingenieria"
        db_table = "variables_subsistema"
        ordering = ["orden"]
        verbose_name = "Variable de subsistema"
        verbose_name_plural = "Variables de subsistema"

    def __str__(self):
        return f"{self.subsistema.codigo} / {self.variable}"


# ---------------------------------------------------------------------------
# SUBCONJUNTOS DE RECETA TÉCNICA — agrupaciones de componentes
# ---------------------------------------------------------------------------

class SubconjuntoRecetaTecnica(models.Model):
    """
    Agrupa componentes de la receta técnica en bloques funcionales.

    Permite organizar la receta de un subsistema complejo en partes:
    Ej: "Estructura metálica", "Aislamiento térmico", "Membrana TPO", "Remates".

    Subsistema → SubconjuntoRecetaTecnica → ComponenteSubsistema
    """
    subsistema = models.ForeignKey(
        Subsistema, on_delete=models.CASCADE, related_name="subconjuntos_receta",
    )
    nombre = models.CharField(
        max_length=200,
        help_text="Nombre del grupo. Ej: Estructura metálica, Aislamiento térmico",
    )
    descripcion = models.TextField(blank=True, default="")
    orden = models.PositiveIntegerField(default=1)
    activo = models.BooleanField(default=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "subconjuntos_receta_tecnica"
        ordering = ["orden", "id"]
        verbose_name = "Subconjunto de Receta Técnica"
        verbose_name_plural = "Subconjuntos de Receta Técnica"

    def __str__(self):
        return f"{self.subsistema.codigo} / {self.nombre}"


# ---------------------------------------------------------------------------
# COMPONENTES — fórmulas definidas en DB para un Subsistema (CONSTRUCTIVO)
# ---------------------------------------------------------------------------

_SAFE_NAMES = {
    k: v for k, v in math.__dict__.items()
    if not k.startswith("_")
}

class ComponenteSubsistema(models.Model):
    """
    Componente de la receta técnica de un subsistema.
    La fórmula es una expresión Python segura (solo operaciones aritméticas
    y variables del contexto) evaluada por el DespieceService.

    Relación estructural: Subsistema → SubconjuntoRecetaTecnica → ComponenteSubsistema
    El campo `subconjunto` puede ser null para componentes legacy creados antes
    de la versión con subconjuntos.
    """
    subsistema = models.ForeignKey(
        Subsistema, on_delete=models.CASCADE, related_name="componentes_db",
    )
    subconjunto = models.ForeignKey(
        SubconjuntoRecetaTecnica,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="componentes",
        verbose_name="Subconjunto",
        help_text="Grupo al que pertenece este componente dentro de la receta técnica",
    )
    codigo = models.CharField(
        max_length=80,
        help_text="Identificador único dentro del subsistema. Ej: fijaciones_plus",
    )
    nombre = models.CharField(max_length=200, help_text="Nombre descriptivo del componente")
    categoria = models.ForeignKey(
        "catalogos.CategoriaProducto",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="componentes_subsistema",
        help_text="Categoría de producto donde se seleccionará el material",
    )
    formula_texto = models.TextField(
        help_text=(
            "Expresión aritmética Python. Puede usar variables de entrada y salidas previas. "
            "Ej: (total_powergrip * tornilleria) * desperdicio"
        ),
    )
    variable_salida = models.CharField(
        max_length=80, blank=True, default="",
        help_text=(
            "Si este componente produce un valor que otros componentes necesitan, "
            "indica aquí el nombre de esa variable. Ej: limpiador"
        ),
    )
    unidad = models.CharField(max_length=40, blank=True, default="")
    orden = models.PositiveIntegerField(default=1)

    # ── APU por componente ────────────────────────────────────────────────────
    variable_referencia_apu = models.CharField(
        max_length=80, blank=True, default="",
        verbose_name="Variable de referencia APU",
        help_text=(
            "Variable de entrada que actúa como denominador del rendimiento. "
            "Ej: 'total_powergrip'. Si se deja vacío, usa la configuración del subsistema."
        ),
    )
    unidad_apu = models.CharField(
        max_length=40, blank=True, default="",
        verbose_name="Unidad APU",
        help_text="Unidad de la referencia. Ej: 'soporte', 'm²', 'ml'.",
    )

    class Meta:
        app_label = "ingenieria"
        db_table = "componentes_subsistema"
        ordering = ["orden"]
        unique_together = [("subsistema", "codigo")]
        verbose_name = "Componente de subsistema"
        verbose_name_plural = "Componentes de subsistema"

    def __str__(self):
        return f"{self.subsistema.codigo} / {self.nombre}"

    def evaluar(self, contexto: dict) -> float:
        """
        Evalúa la fórmula con el contexto dado.
        Sólo permite nombres matemáticos seguros + variables del contexto.
        Lanza ValueError si la fórmula es inválida.
        """
        safe_ctx = {**_SAFE_NAMES, **contexto}
        try:
            result = eval(self.formula_texto, {"__builtins__": {}}, safe_ctx)  # noqa: S307
            return float(result)
        except Exception as exc:
            raise ValueError(
                f"Error evaluando fórmula '{self.formula_texto}': {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# PRODUCTOS TÉCNICOS ASOCIADOS — productos de referencia para subsistemas CONSUMO
# ---------------------------------------------------------------------------

class ProductoTecnicoAsociado(models.Model):
    """
    Producto técnico de referencia asociado a un subsistema de consumo.

    No es una capa de cálculo: es la ficha de producto comercial real
    que el sistema puede usar, con su estado físico y consumo de referencia.

    Ejemplo:
        Subsistema KB-POX 008 + KB-PUR 214
          → ProductoTecnicoAsociado: "KÖSTER KB-Pox 008"   — Líquido — 300–500 g/m²
          → ProductoTecnicoAsociado: "KÖSTER KB-Pur 214"   — Pastoso — 200–350 g/m²
    """
    subsistema = models.ForeignKey(
        Subsistema, on_delete=models.CASCADE, related_name="productos_tecnicos",
    )
    nombre = models.CharField(
        max_length=300,
        help_text="Nombre comercial del producto. Ej: KÖSTER KB-Pox 008",
    )
    descripcion = models.TextField(blank=True)
    estado_fisico = models.CharField(
        max_length=20,
        choices=EstadoFisicoProducto.choices,
        blank=True, default="",
        verbose_name="Estado físico",
    )
    consumo_min_g_m2 = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Consumo mínimo (g/m²)",
    )
    consumo_max_g_m2 = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Consumo máximo (g/m²)",
    )
    unidad = models.CharField(max_length=40, default="kg")
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        app_label = "ingenieria"
        db_table = "productos_tecnicos_asociados"
        ordering = ["orden"]
        verbose_name = "Producto técnico asociado"
        verbose_name_plural = "Productos técnicos asociados"

    def __str__(self):
        return f"{self.subsistema.codigo} / {self.nombre}"


# ---------------------------------------------------------------------------
# COMPONENTES QUÍMICOS — mezcla de un subsistema bi/multicomponente
# ---------------------------------------------------------------------------

class ComponenteQuimico(models.Model):
    """
    Componente de la mezcla para subsistemas bi/multicomponente.

    Los porcentajes de todos los ComponenteQuimico del mismo subsistema
    deben sumar exactamente 100. La validación se realiza en el servicio
    y en el formulario de administración.

    Ejemplo (impermeabilizante bicomponente):
        Componente A (Base)        — Líquido — 60 %
        Componente B (Endurecedor) — Pastoso — 40 %
    """
    subsistema = models.ForeignKey(
        Subsistema, on_delete=models.CASCADE, related_name="componentes_quimicos",
    )
    nombre = models.CharField(
        max_length=200,
        help_text="Ej: Componente A (Base), Componente B (Endurecedor)",
    )
    porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="% dentro de la mezcla total. Todos los componentes deben sumar 100.",
    )
    estado_fisico = models.CharField(
        max_length=20,
        choices=EstadoFisicoProducto.choices,
        blank=True, default="",
        verbose_name="Estado físico",
    )
    categoria = models.ForeignKey(
        "catalogos.CategoriaProducto",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="componentes_quimicos",
        help_text="Categoría de producto para este componente",
    )
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        app_label = "ingenieria"
        db_table = "componentes_quimicos"
        ordering = ["orden"]
        verbose_name = "Componente Químico"
        verbose_name_plural = "Componentes Químicos"

    def __str__(self):
        return f"{self.subsistema.codigo} / {self.nombre} ({self.porcentaje}%)"


# ---------------------------------------------------------------------------
# CAPAS DE CONSUMO — DEPRECATED: use ProductoTecnicoAsociado instead
# Kept in DB for backward compatibility; not shown in UI.
# ---------------------------------------------------------------------------

class CapaConsumo(models.Model):
    """
    DEPRECATED — reemplazada por ProductoTecnicoAsociado.
    Se mantiene en DB para no perder datos existentes.
    """
    subsistema = models.ForeignKey(
        Subsistema, on_delete=models.CASCADE, related_name="capas",
    )
    nombre = models.CharField(max_length=200)
    categoria = models.ForeignKey(
        "catalogos.CategoriaProducto",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="capas_consumo",
    )
    consumo_m2 = models.DecimalField(max_digits=10, decimal_places=4)
    num_capas = models.PositiveSmallIntegerField(default=1)
    unidad = models.CharField(max_length=40, default="kg")
    desperdicio_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    requiere_accesorio = models.BooleanField(default=False)
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        app_label = "ingenieria"
        db_table = "capas_consumo"
        ordering = ["orden"]
        verbose_name = "Capa de Consumo (deprecated)"
        verbose_name_plural = "Capas de Consumo (deprecated)"

    def __str__(self):
        return f"{self.subsistema.codigo} / {self.nombre}"
