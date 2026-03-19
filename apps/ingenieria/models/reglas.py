"""
apps/ingenieria/models/reglas.py

⚠️  LEGADO — NO USAR EN FLUJO OPERATIVO NUEVO  ⚠️

ReglaCalculo existía para definir las fórmulas desde la BD (CRUD por pantalla).
Ese flujo ha sido reemplazado por las definiciones Python en:
    apps/ingenieria/system_defs/powergrip.py   (y futuros sistemas)

Este modelo se conserva SOLO por compatibilidad de datos históricos y
para no requerir migraciones de DROP TABLE.
DespieceService ya NO lee de esta tabla.

ReglaCalculo define CÓMO se calcula la cantidad de un componente técnico
dentro de un subsistema.

Separación de conceptos:
  - categoria_producto: qué tipo de componente se necesita (técnico)
  - producto: qué producto comercial concreto
  - formula_python: expresión Python evaluable con variables del contexto

Dependencias de esta app:
  - catalogos.Producto 
  - catalogos.CategoriaProducto 
  - usuarios.UsuarioSistema  
"""

import math as _math
from django.db import models
from django.core.exceptions import ValidationError
from apps.common.choices import TipoRegla


class ReglaCalculo(models.Model):

    subsistema = models.ForeignKey(
        "ingenieria.Subsistema", on_delete=models.CASCADE, related_name="reglas"
    )
    producto = models.ForeignKey(
        "catalogos.Producto",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reglas_calculo",
        help_text="Producto específico (opcional; use categoría si el producto se elige por proyecto)",
    )
    categoria_producto = models.ForeignKey(
        "catalogos.CategoriaProducto",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reglas_calculo",
        help_text="Categoría del producto cuando no hay producto específico asignado",
    )
    codigo = models.CharField(max_length=60)
    nombre = models.CharField(max_length=200)
    variable_entrada = models.CharField(
        max_length=80, blank=True, null=True,
        help_text="Nombre de la variable de contexto usada como base (ej: Total_PowerGrip)",
    )
    coeficiente = models.DecimalField(max_digits=18, decimal_places=6, blank=True, null=True)
    divisor = models.DecimalField(max_digits=18, decimal_places=6, blank=True, null=True)
    factor_desperdicio = models.DecimalField(max_digits=12, decimal_places=6, default=1.01)
    formula_texto = models.TextField(
        help_text="Expresión legible. Ej: (8 × Total_PowerGrip) * 101%"
    )
    formula_python = models.TextField(
        blank=True, null=True,
        help_text="Expresión Python evaluable. Usa variables del contexto.",
    )
    tipo_regla = models.CharField(
        max_length=30, choices=TipoRegla.choices, default=TipoRegla.FIJA
    )
    orden_ejecucion = models.IntegerField(default=1)
    editable_por_proyecto = models.BooleanField(default=False)
    version = models.IntegerField(default=1)
    activa = models.BooleanField(default=True)
    obligatoria = models.BooleanField(
        default=True,
        help_text="Si es False, el componente puede omitirse en el despiece de un proyecto",
    )
    variable_salida = models.CharField(
        max_length=80, blank=True,
        help_text=(
            "Nombre con el que el resultado de esta regla queda disponible en el contexto "
            "para reglas derivadas. Ej: 'Limpiador' → permite que Estopa use "
            "formula_python='Limpiador / 2'"
        ),
    )
    caso_prueba = models.TextField(blank=True, null=True)
    creada_por = models.ForeignKey(
        "usuarios.UsuarioSistema",
        on_delete=models.SET_NULL, blank=True, null=True,
        related_name="reglas_creadas",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ingenieria"
        db_table = "reglas_calculo"
        unique_together = ("subsistema", "codigo", "version")
        ordering = ["orden_ejecucion"]
        verbose_name = "Regla de Cálculo"
        verbose_name_plural = "Reglas de Cálculo"

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"

    def clean(self):
        """Validaciones de integridad técnica."""
        if not self.producto and not self.categoria_producto:
            raise ValidationError(
                "Debe especificar al menos una Categoría de Producto o un Producto concreto."
            )
        
        if self.variable_salida and self.variable_salida.lower() in ['math', 'sum', 'total']:
            raise ValidationError(f"'{self.variable_salida}' es un nombre de variable reservado.")
   
    def evaluar(self, contexto: dict) -> float:
        """
        Evalúa la regla. El contexto se actualiza dinámicamente 
        si la regla genera una 'variable_salida'.
        """
        expr = self.formula_python or self._formula_auto()
        if not expr:
            return 0.0

        # Preparación de contexto seguro
        safe_ctx = {k: float(v) for k, v in contexto.items() if v is not None}
        safe_ctx["math"] = _math

        try:
            resultado = eval(expr, {"__builtins__": {}}, safe_ctx) 
            val_final = float(resultado)
            
            if self.variable_salida:
                contexto[self.variable_salida] = val_final
                
            return val_final
        except Exception as exc:
            raise ValueError(f"Error en Regla {self.codigo} [{expr}]: {exc}")

    def _formula_auto(self):
        """Genera la expresión base: (Coef * Var / Divisor) * Desperdicio"""
        if not self.variable_entrada:
            return "0.0"
        
        coef = float(self.coeficiente or 1.0)
        div = float(self.divisor or 1.0)
        desp = float(self.factor_desperdicio or 1.0)
        
        return f"({coef} * {self.variable_entrada} / {div}) * {desp}"
