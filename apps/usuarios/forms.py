"""apps/usuarios/forms.py — Formularios del módulo de usuarios."""

from django import forms
from .models import UsuarioSistema


class UsuarioSistemaForm(forms.ModelForm):
    class Meta:
        model = UsuarioSistema
        fields = ["email", "nombre_completo", "password_hash", "rol", "activo"]
        labels = {
            "email": "Email",
            "nombre_completo": "Nombre completo",
            "password_hash": "Contraseña (hash)",
            "rol": "Rol",
            "activo": "Activo",
        }
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "nombre_completo": forms.TextInput(attrs={"class": "form-control"}),
            "password_hash": forms.TextInput(attrs={"class": "form-control"}),
            "rol": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
