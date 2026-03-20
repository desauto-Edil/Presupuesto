"""
apps/ingenieria/forms.py — Formularios del módulo de ingeniería.

Solo Sistema y Subsistema tienen formularios operativos.
ReglaCalculoForm y DependenciaTecnicaForm han sido eliminados del flujo —
las recetas técnicas están definidas en system_defs/ como código Python.
"""

from django import forms
from .models import Sistema, Subsistema


class SistemaForm(forms.ModelForm):
    class Meta:
        model = Sistema
        fields = ["codigo", "nombre", "linea_negocio", "descripcion", "activo"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "linea_negocio": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SubsistemaForm(forms.ModelForm):
    class Meta:
        model = Subsistema
        fields = ["sistema", "codigo", "nombre", "descripcion", "activo"]
        widgets = {
            "sistema": forms.Select(attrs={"class": "form-select"}),
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
