"""apps/usuarios/forms.py — Formularios del módulo de usuarios."""

from django import forms
from .models import UsuarioSistema


class UsuarioSistemaForm(forms.ModelForm):
    """
    Formulario de usuario.
    - Creación: password_hash obligatorio.
    - Edición: si se deja vacío, se conserva la contraseña existente.
    """

    password_hash = forms.CharField(
        required=False,
        label="Contraseña",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
        help_text="Dejar vacío al editar para conservar la contraseña actual.",
    )

    class Meta:
        model = UsuarioSistema
        fields = ["email", "nombre_completo", "password_hash", "unidad_negocio", "rol", "activo"]
        labels = {
            "email": "Email",
            "nombre_completo": "Nombre completo",
            "unidad_negocio": "Unidad de negocio",
            "rol": "Rol",
            "activo": "Activo",
        }
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "nombre_completo": forms.TextInput(attrs={"class": "form-control"}),
            "unidad_negocio": forms.Select(attrs={"class": "form-select"}),
            "rol": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_password_hash(self):
        password = self.cleaned_data.get("password_hash", "").strip()
        # Creación: la contraseña es obligatoria
        if not self.instance.pk and not password:
            raise forms.ValidationError("La contraseña es obligatoria al crear un usuario.")
        return password
