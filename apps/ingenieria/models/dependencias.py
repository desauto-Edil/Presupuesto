"""
apps/ingenieria/models/dependencias.py — Dependencias técnicas de subsistemas.

DependenciaTecnica define qué componentes se añaden automáticamente al
despiece cuando se selecciona un subsistema específico.

Separación de conceptos:
  - Si producto_dependiente está definido: el componente es un producto concreto.
  - Si categoria_producto está definida: es una categoría genérica; el producto
    se elige después en el módulo de presupuestos (pendiente_seleccion).
"""

from django.db import models
from apps.common.choices import TipoRegla


class DependenciaTecnica(models.Model):
    """
    Relación obligatoria/condicional entre el subsistema
    y los componentes que se deben agregar automáticamente al despiece.
    """
    subsistema = models.ForeignKey(
        "ingenieria.Subsistema", on_delete=models.CASCADE, related_name="dependencias"
    )
    producto_origen = models.ForeignKey(
        "catalogos.Producto",
        on_delete=models.SET_NULL, blank=True, null=True,
        related_name="dependencias_origen",
        help_text="Si es NULL la dependencia aplica a todo el subsistema",
    )
    producto_dependiente = models.ForeignKey(
        "catalogos.Producto",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dependencias_dependiente",
        help_text="Producto concreto (opcional; use categoría para dependencias genéricas)",
    )
    categoria_producto = models.ForeignKey(
        "catalogos.CategoriaProducto",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dependencias_tecnicas",
        help_text="Categoría cuando el producto se elegirá por proyecto",
    )
    nombre = models.CharField(
        max_length=200, blank=True,
        help_text="Nombre descriptivo (obligatorio para dependencias basadas en categoría)",
    )
    variable_entrada = models.CharField(max_length=80, blank=True, null=True)
    condicion_texto = models.TextField(blank=True, null=True)
    obligatoria = models.BooleanField(default=True)
    orden = models.IntegerField(default=1)
    tipo_regla = models.CharField(
        max_length=30, choices=TipoRegla.choices, default=TipoRegla.FIJA
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "dependencias_tecnicas"
        ordering = ["orden"]

    def __str__(self):
        origen = self.producto_origen.nombre if self.producto_origen else "(subsistema)"
        destino = (
            self.nombre
            or (self.producto_dependiente.nombre if self.producto_dependiente else None)
            or (str(self.categoria_producto) if self.categoria_producto else "—")
        )
        return f"{origen} → {destino}"
