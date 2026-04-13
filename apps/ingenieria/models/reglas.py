"""
apps/ingenieria/models/reglas.py — Modelos LEGADO para reglas de cálculo.
"""

from django.db import models
from apps.ingenieria.models.sistemas import Subsistema
from apps.catalogos.models import Producto, CategoriaProducto


class ReglaCalculo(models.Model):
    subsistema = models.ForeignKey(
        Subsistema,
        on_delete=models.CASCADE,
        related_name="reglas_calculo",
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reglas_calculo",
    )
    categoria_producto = models.ForeignKey(
        CategoriaProducto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reglas_calculo",
    )
    codigo = models.CharField(max_length=100, unique=True)
    nombre = models.CharField(max_length=200)
    variable_entrada = models.CharField(max_length=100, blank=True, null=True)
    coeficiente = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    divisor = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    factor_desperdicio = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    formula_texto = models.TextField(blank=True, null=True)
    formula_python = models.TextField(blank=True, null=True)
    tipo_regla = models.CharField(max_length=100, blank=True, null=True)
    orden_ejecucion = models.IntegerField(default=0)
    variable_salida = models.CharField(max_length=100, blank=True, null=True)
    activa = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "reglas_calculo"
        ordering = ["subsistema", "orden_ejecucion"]

    def __str__(self):
        return f"{self.subsistema} > {self.nombre}"
