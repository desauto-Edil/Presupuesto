"""apps/catalogos/forms.py — Formularios del módulo de catálogos."""

from django import forms
from django.core.exceptions import ValidationError
from .models import UnidadMedida, CategoriaProducto, Producto, Proveedor, ProductoProveedor


class UnidadMedidaForm(forms.ModelForm):
    class Meta:
        model = UnidadMedida
        fields = ["codigo", "nombre", "abreviatura"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "abreviatura": forms.TextInput(attrs={"class": "form-control"}),
        }


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = CategoriaProducto
        fields = ["codigo", "nombre", "descripcion", "imagen", "activa"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "imagen": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "activa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ProductoForm(forms.ModelForm):
    """
    Formulario de Producto con precio y proveedor integrados.
    · precio_actual es obligatorio (validado en clean()).
    · Al guardar, la vista sincroniza ProductoProveedor para el DespieceService.
    """

    class Meta:
        model = Producto
        fields = [
            "codigo", "nombre", "categoria", "unidad",
            "proveedor", "precio_actual", "moneda",
            "origen", "marca", "linea", "rendimiento", "activo",
        ]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control",
                                                    "placeholder": "Auto-generado al guardar"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "unidad": forms.Select(attrs={"class": "form-select"}),
            "proveedor": forms.Select(attrs={"class": "form-select"}),
            "precio_actual": forms.NumberInput(attrs={"class": "form-control", "step": "0.01",
                                                      "placeholder": "Ej: 8500"}),
            "moneda": forms.Select(attrs={"class": "form-select"}),
            "origen": forms.Select(attrs={"class": "form-select"}),
            "marca": forms.TextInput(attrs={"class": "form-control"}),
            "linea": forms.TextInput(attrs={"class": "form-control"}),
            "rendimiento": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_precio_actual(self):
            precio = self.cleaned_data.get("precio_actual")
            if precio is not None and precio < 0:
                raise ValidationError("El precio no puede ser negativo.")
            return precio

    def clean(self):
        cd = super().clean()
        precio = cd.get("precio_actual")
        proveedor = cd.get("proveedor")
        moneda = cd.get("moneda")
        if precio is None:
            raise ValidationError({"precio_actual": "El precio es obligatorio."})
        if precio <= 0:
            raise ValidationError({"precio_actual": "El precio debe ser mayor a cero."})
        if not proveedor:
            raise ValidationError({"proveedor": "Debe asignar un proveedor al producto."})
        if not moneda:
            raise ValidationError({"moneda": "Selecciona la moneda del precio."})
        return cd

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # codigo no es required en el form — se auto-genera en la vista si está vacío
        self.fields["codigo"].required = False


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nit", "nombre", "ciudad", "direccion", "telefono", "email", "activo"]
        widgets = {
            "nit": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "ciudad": forms.TextInput(attrs={"class": "form-control"}),
            "direccion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ProductoProveedorForm(forms.ModelForm):
    class Meta:
        model = ProductoProveedor
        fields = ["producto", "proveedor", "precio_unitario", "moneda", "activo"]
        widgets = {
            "producto": forms.Select(attrs={"class": "form-select"}),
            "proveedor": forms.Select(attrs={"class": "form-select"}),
            "precio_unitario": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "moneda": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
