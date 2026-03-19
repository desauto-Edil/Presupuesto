"""
apps/ingenieria/models/dependencias.py

⚠️  LEGADO — NO USAR EN FLUJO OPERATIVO NUEVO  ⚠️

DependenciaTecnica existía para inyectar componentes automáticos via DB.
Ese flujo ha sido reemplazado por las definiciones Python en:
    apps/ingenieria/system_defs/powergrip.py   (y futuros sistemas)

Este modelo se conserva SOLO por compatibilidad de datos históricos.
DependenciaService y ProyectoSistema.inyectar_dependencias() ya no se usan.

DependenciaTecnica define qué componentes se añaden automáticamente al
despiece cuando se selecciona un subsistema específico.

Separación de conceptos:
  - Si producto_dependiente está definido: el componente es un producto concreto.
  - Si categoria_producto está definida: es una categoría genérica; el producto
    se elige después en el módulo de presupuestos (pendiente_seleccion).
"""

from django.db import models
from django.core.exceptions import ValidationError
from apps.common.choices import TipoRegla


class DependenciaTecnica(models.Model):
    """
    Define qué componentes (vía categoría o SKU) se añaden 
    automáticamente al despiece de un subsistema.
    """
    subsistema = models.ForeignKey(
        "ingenieria.Subsistema", 
        on_delete=models.CASCADE, 
        related_name="dependencias"
    )
    producto_origen = models.ForeignKey(
        "catalogos.Producto",
        on_delete=models.SET_NULL, blank=True, null=True,
        related_name="dependencias_origen",
        help_text="Si es NULL, el componente se añade siempre que se use el subsistema",
    )
    
    categoria_producto = models.ForeignKey(
        "catalogos.CategoriaProducto",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dependencias_tecnicas",
        help_text="Categoría cuando el producto se elegirá por proyecto",
    )

    producto_dependiente = models.ForeignKey(
        "catalogos.Producto",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dependencias_dependiente",
        help_text="EXCEPCIÓN: Solo si el componente es un SKU específico e inamovible.",
    )
    
    nombre = models.CharField(
        max_length=200, 
        blank=True,
        help_text="Nombre descriptivo",
    )

    obligatoria = models.BooleanField(
        default=True,
        help_text="Si es False, el comercial puede quitar este ítem en el presupuesto."
    )

    orden = models.IntegerField(
        default=1,
        help_text="Secuencia de aparición en el listado de materiales."
    )

    variable_entrada = models.CharField(max_length=80, blank=True, null=True)
    condicion_texto = models.TextField(blank=True, null=True)
    tipo_regla = models.CharField(
        max_length=30, choices=TipoRegla.choices, default=TipoRegla.FIJA
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "dependencias_tecnicas"
        ordering = ["orden"]
        verbose_name = "Dependencia de Componente"
        verbose_name_plural = "Dependencias de Componentes"

    def clean(self):
        """Valida la prioridad de categoría y la presencia de datos."""
        if not self.categoria_producto and not self.producto_dependiente:
            raise ValidationError(
                "Debe definir una Categoría (recomendado) o un Producto para la dependencia."
            )
        
        if self.categoria_producto and not self.nombre:
            raise ValidationError(
                "Si usa una categoría, debe asignar un nombre descriptivo a la dependencia."
            )
        
    def __str__(self):
        origen = self.producto_origen.nombre if self.producto_origen else "GLOBAL"
        # Priorizamos mostrar la categoría en el string para reforzar el concepto
        destino = (
            f"CAT: {self.categoria_producto.nombre}" 
            if self.categoria_producto 
            else f"SKU: {self.producto_dependiente.nombre}"
        )
        return f"[{origen}] → {destino} ({'Oblig' if self.obligatoria else 'Opc'})"
