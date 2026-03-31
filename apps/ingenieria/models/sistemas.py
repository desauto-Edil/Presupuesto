"""
apps/ingenieria/models/sistemas.py — Sistemas y subsistemas técnicos.

Sistema:    conjunto de productos técnicos
Subsistema: variante concreta dentro del sistema, con su propia receta
            de componentes, fórmulas y dependencias.

Un subsistema es una receta técnica REUTILIZABLE.
No define el producto comercial final; eso ocurre en presupuestos.
"""

from django.db import models
from apps.common.choices import LineaNegocio
import math
import re


class Sistema(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=200)
    linea_negocio = models.CharField(max_length=20, 
                                     choices=LineaNegocio.choices)
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

    def tiene_componentes_db(self) -> bool:
        return self.componentes_db.exists()


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
# COMPONENTES — fórmulas definidas en DB para un Subsistema
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
    """
    subsistema = models.ForeignKey(
        Subsistema, on_delete=models.CASCADE, related_name="componentes_db",
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
