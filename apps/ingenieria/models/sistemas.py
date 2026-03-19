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
