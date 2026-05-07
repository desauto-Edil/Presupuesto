"""
apps/ingenieria/forms.py — Formularios del módulo de ingeniería.

Solo Sistema y Subsistema tienen formularios operativos.
ReglaCalculoForm y DependenciaTecnicaForm han sido eliminados del flujo —
las recetas técnicas están definidas en system_defs/ como código Python.

Nota sobre campos M2M (funciones, problemas_resuelve, superficies_compatibles):
    No se incluyen en el ModelForm porque se gestionan desde el template
    con checkboxes manuales y se guardan en la vista con set().
"""

from django import forms
from .models import Sistema, Subsistema


class SistemaForm(forms.ModelForm):
    class Meta:
        model = Sistema
        fields = ["codigo", "nombre", "linea_negocio", "tipo_sistema", "descripcion", "activo"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "linea_negocio": forms.Select(attrs={"class": "form-select"}),
            "tipo_sistema": forms.Select(attrs={"class": "form-select", "id": "id_tipo_sistema"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SubsistemaForm(forms.ModelForm):
    class Meta:
        model = Subsistema
        fields = [
            "sistema", "codigo", "nombre", "descripcion", "activo",
            "imagen_tecnica",
            # Constructivo
            "variable_referencia_apu", "unidad_apu",
            # Consumo — campos escalares (M2M se gestionan en la vista)
            "tipo_producto", "resistencia_quimica",
            "temperatura_min", "temperatura_max", "interior_exterior",
            "consumo_min_g_m2", "consumo_max_g_m2",
        ]
        widgets = {
            "sistema": forms.Select(attrs={"class": "form-select"}),
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "variable_referencia_apu": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: total_powergrip",
                "style": "font-family:monospace;",
            }),
            "unidad_apu": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: soporte, m², ml",
            }),
            # Consumo
            "tipo_producto": forms.Select(attrs={"class": "form-select"}),
            "resistencia_quimica": forms.TextInput(attrs={"class": "form-control"}),
            "temperatura_min": forms.NumberInput(attrs={
                "class": "form-control", "step": "0.1",
                "placeholder": "Ej: 5",
            }),
            "temperatura_max": forms.NumberInput(attrs={
                "class": "form-control", "step": "0.1",
                "placeholder": "Ej: 35",
            }),
            "imagen_tecnica": forms.FileInput(attrs={"class": "form-control form-control-sm", "accept": "image/*"}),
            "interior_exterior": forms.Select(attrs={"class": "form-select"}),
            "consumo_min_g_m2": forms.NumberInput(attrs={
                "class": "form-control", "min": 0, "step": "0.01",
                "placeholder": "Ej: 200",
            }),
            "consumo_max_g_m2": forms.NumberInput(attrs={
                "class": "form-control", "min": 0, "step": "0.01",
                "placeholder": "Ej: 400",
            }),
        }
