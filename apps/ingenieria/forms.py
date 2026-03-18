"""apps/ingenieria/forms.py — Formularios del módulo de ingeniería."""

from django import forms
from .models import Sistema, Subsistema, ReglaCalculo, DependenciaTecnica


class SistemaForm(forms.ModelForm):
    class Meta:
        model = Sistema
        fields = ["codigo", "nombre", "linea_negocio", "descripcion", "activo"]
        widgets = {
            "codigo":        forms.TextInput(attrs={"class": "form-control"}),
            "nombre":        forms.TextInput(attrs={"class": "form-control"}),
            "linea_negocio": forms.Select(attrs={"class": "form-select"}),
            "descripcion":   forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "activo":        forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SubsistemaForm(forms.ModelForm):
    class Meta:
        model = Subsistema
        fields = ["sistema", "codigo", "nombre", "descripcion", "activo"]
        widgets = {
            "sistema":     forms.Select(attrs={"class": "form-select"}),
            "codigo":      forms.TextInput(attrs={"class": "form-control"}),
            "nombre":      forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "activo":      forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ReglaCalculoForm(forms.ModelForm):
    class Meta:
        model = ReglaCalculo
        fields = [
            "subsistema", "producto", "categoria_producto",
            "codigo", "nombre", "variable_entrada",
            "coeficiente", "divisor", "factor_desperdicio",
            "formula_texto", "formula_python",
            "tipo_regla", "orden_ejecucion", "editable_por_proyecto",
            "version", "activa", "obligatoria", "variable_salida",
            "caso_prueba", "creada_por",
        ]
        widgets = {
            "subsistema":           forms.Select(attrs={"class": "form-select"}),
            "producto":             forms.Select(attrs={"class": "form-select"}),
            "categoria_producto":   forms.Select(attrs={"class": "form-select"}),
            "codigo":               forms.TextInput(attrs={"class": "form-control"}),
            "nombre":               forms.TextInput(attrs={"class": "form-control"}),
            "variable_entrada":     forms.TextInput(attrs={"class": "form-control"}),
            "coeficiente":          forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "divisor":              forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "factor_desperdicio":   forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "formula_texto":        forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "formula_python":       forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Expresión Python evaluable"}),
            "tipo_regla":           forms.Select(attrs={"class": "form-select"}),
            "orden_ejecucion":      forms.NumberInput(attrs={"class": "form-control"}),
            "editable_por_proyecto": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "version":              forms.NumberInput(attrs={"class": "form-control"}),
            "activa":               forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "obligatoria":          forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "variable_salida":      forms.TextInput(attrs={"class": "form-control"}),
            "caso_prueba":          forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "creada_por":           forms.Select(attrs={"class": "form-select"}),
        }


class DependenciaTecnicaForm(forms.ModelForm):
    class Meta:
        model = DependenciaTecnica
        fields = [
            "subsistema", "producto_origen", "producto_dependiente",
            "categoria_producto", "nombre", "variable_entrada",
            "condicion_texto", "obligatoria", "orden", "tipo_regla",
        ]
        widgets = {
            "subsistema":          forms.Select(attrs={"class": "form-select"}),
            "producto_origen":     forms.Select(attrs={"class": "form-select"}),
            "producto_dependiente": forms.Select(attrs={"class": "form-select"}),
            "categoria_producto":  forms.Select(attrs={"class": "form-select"}),
            "nombre":              forms.TextInput(attrs={"class": "form-control"}),
            "variable_entrada":    forms.TextInput(attrs={"class": "form-control"}),
            "condicion_texto":     forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "obligatoria":         forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "orden":               forms.NumberInput(attrs={"class": "form-control"}),
            "tipo_regla":          forms.Select(attrs={"class": "form-select"}),
        }
