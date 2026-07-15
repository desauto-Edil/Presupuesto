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
        fields = ["codigo", "nombre", "descripcion", "activa"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
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
            "proveedor", "precio_actual", "moneda", "unidades_por_presentacion",
            "origen", "marca", "linea", "precio_en_dolares",
            "presentacion_nombre", "ancho_presentacion", "largo_presentacion",
            "unidad_dimension", "cantidad_presentacion", "unidad_presentacion",
            "ficha_tecnica", "activo",
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
            "unidades_por_presentacion": forms.NumberInput(attrs={
                "class": "form-control", "min": "1",
                "placeholder": "Ej: 1000 si el precio es por bolsa de 1000 und",
            }),
            "origen": forms.Select(attrs={"class": "form-select"}),
            "marca": forms.TextInput(attrs={"class": "form-control"}),
            "linea": forms.TextInput(attrs={"class": "form-control"}),
            "precio_en_dolares": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "presentacion_nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Rollo 3.05 x 30.48 m",
            }),
            "ancho_presentacion": forms.NumberInput(attrs={
                "class": "form-control", "step": "0.0001", "placeholder": "Ej: 3.05",
            }),
            "largo_presentacion": forms.NumberInput(attrs={
                "class": "form-control", "step": "0.0001", "placeholder": "Ej: 30.48",
            }),
            "unidad_dimension": forms.Select(attrs={"class": "form-select"}),
            "cantidad_presentacion": forms.NumberInput(attrs={
                "class": "form-control", "step": "0.0001", "placeholder": "Ej: 92.96",
            }),
            "unidad_presentacion": forms.Select(attrs={"class": "form-select"}),
            "ficha_tecnica": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "ficha_tecnica": "Ficha técnica (PDF / imagen, opcional)",
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
    """
    Form de Proveedor. Los IDs de los widgets se fijan explícitamente
    (prov_*) porque el offcanvas en catalogos.html los direcciona
    desde JavaScript (prepareProvForm).
    """

    class Meta:
        model = Proveedor
        fields = ["nit", "nombre", "ciudad", "direccion", "telefono", "email", "activo"]
        widgets = {
            "nit":       forms.TextInput(attrs={"class": "form-control", "id": "prov_nit", "required": True}),
            "nombre":    forms.TextInput(attrs={"class": "form-control", "id": "prov_nombre", "required": True}),
            "ciudad":    forms.TextInput(attrs={"class": "form-control", "id": "prov_ciudad"}),
            "direccion": forms.TextInput(attrs={"class": "form-control", "id": "prov_direccion"}),
            "telefono":  forms.TextInput(attrs={"class": "form-control", "id": "prov_telefono"}),
            "email":     forms.EmailInput(attrs={"class": "form-control", "id": "prov_email"}),
            "activo":    forms.CheckboxInput(attrs={"class": "form-check-input", "id": "prov_activo"}),
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
