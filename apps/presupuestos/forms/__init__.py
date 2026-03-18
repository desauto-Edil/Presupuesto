"""apps/presupuestos/forms — Formularios del módulo de presupuestos."""

from django import forms
from apps.presupuestos.models import ProyectoSistema, DespieceLinea, ConfiguracionAPU, APUProyecto, APULinea


class ProyectoSistemaForm(forms.ModelForm):
    class Meta:
        model = ProyectoSistema
        fields = [
            "proyecto", "sistema", "subsistema", "orden",
            "total_powergip", "cuadrilla_personas", "observaciones",
        ]
        widgets = {
            "proyecto":           forms.Select(attrs={"class": "form-select"}),
            "sistema":            forms.Select(attrs={"class": "form-select"}),
            "subsistema":         forms.Select(attrs={"class": "form-select"}),
            "orden":              forms.NumberInput(attrs={"class": "form-control"}),
            "total_powergip":     forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
            "cuadrilla_personas": forms.NumberInput(attrs={"class": "form-control"}),
            "observaciones":      forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class DespieceLineaAjusteForm(forms.ModelForm):
    """Formulario para ajustar manualmente una línea de despiece."""
    class Meta:
        model = DespieceLinea
        fields = ["cantidad_ajustada", "motivo_ajuste", "producto"]
        widgets = {
            "cantidad_ajustada": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "motivo_ajuste":     forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "producto":          forms.Select(attrs={"class": "form-select"}),
        }


class ConfiguracionAPUForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionAPU
        fields = [
            "nombre", "porcentaje_ganancia", "aiu_contratista",
            "desperdicio", "margen_ganancia_contratista", "activa",
        ]
        widgets = {
            "nombre":                    forms.TextInput(attrs={"class": "form-control"}),
            "porcentaje_ganancia":       forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aiu_contratista":           forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "desperdicio":               forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "margen_ganancia_contratista": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "activa":                    forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class APUProyectoForm(forms.ModelForm):
    class Meta:
        model = APUProyecto
        fields = [
            "factor_venta_pct", "iva_pct", "aplica_iva",
            "aiu_contratista_pct", "margen_contratista_pct",
            "dias_trabajo", "tiempo_estimado_meses", "rendimiento_und_dia",
        ]
        widgets = {
            "factor_venta_pct":       forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "iva_pct":                forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aplica_iva":             forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "aiu_contratista_pct":    forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "margen_contratista_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "dias_trabajo":           forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "tiempo_estimado_meses":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "rendimiento_und_dia":    forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
        }
