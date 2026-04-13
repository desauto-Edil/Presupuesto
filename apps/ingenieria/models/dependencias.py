"""
apps/ingenieria/models/dependencias.py — Modelos LEGADO para dependencias técnicas.
"""

from django.db import models
from apps.ingenieria.models.sistemas import Subsistema
from apps.catalogos.models import Producto, CategoriaProducto


class DependenciaTecnica(models.Model):
    subsistema = models.ForeignKey(
        Subsistema,
        on_delete=models.CASCADE,
        related_name="dependencias_tecnicas",
    )
    producto_origen = models.ForeignKey(
        Producto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dependencias_origen",
    )
    producto_dependiente = models.ForeignKey(
        Producto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dependencias_dependiente",
    )
    categoria_producto = models.ForeignKey(
        CategoriaProducto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dependencias_tecnicas",
    )
    nombre = models.CharField(max_length=200, blank=True, null=True)
    obligatoria = models.BooleanField(default=False)
    orden = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "dependencias_tecnicas"

    def __str__(self):
        return f"{self.subsistema} -> {self.nombre or 'dependencia'}"
