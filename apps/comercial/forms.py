"""apps/comercial/forms.py — Formularios del módulo comercial."""

from django import forms
from .models import Cliente, ContactoCliente, TipoProyecto, Solicitud, Proyecto


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nit", "razon_social", "ciudad", "direccion",
                  "telefono_principal", "email_principal", "activo"]
        widgets = {
            "nit": forms.TextInput(attrs={"class": "form-control"}),
            "razon_social": forms.TextInput(attrs={"class": "form-control"}),
            "ciudad": forms.TextInput(attrs={"class": "form-control"}),
            "direccion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "telefono_principal": forms.TextInput(attrs={"class": "form-control"}),
            "email_principal": forms.EmailInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ContactoClienteForm(forms.ModelForm):
    class Meta:
        model = ContactoCliente
        fields = ["cliente", "nombre", "cargo", "email", "telefono", "es_principal", "activo"]
        widgets = {
            "cliente": forms.Select(attrs={"class": "form-select"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "cargo": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "es_principal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class TipoProyectoForm(forms.ModelForm):
    class Meta:
        model = TipoProyecto
        fields = ["codigo", "nombre", "activo"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SolicitudForm(forms.ModelForm):

    class Meta:
        model = Solicitud
        fields = [
            "cliente", "contacto",
            "nombre", "descripcion", "fecha_entrega", "observaciones",
        ]
        widgets = {

            "cliente": forms.Select(attrs={"class": "form-select"}),
            "contacto": forms.Select(attrs={"class": "form-select"}),
            "nombre": forms.TextInput(attrs={"class": "form-control", 
                                             "placeholder": "Nombre del proyecto o requerimiento"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", 
                                                 "rows": 3}),
            "fecha_entrega": forms.DateInput(attrs={"class": "form-control", 
                                                    "type": "date"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", 
                                                   "rows": 2}),
        }


class ProyectoForm(forms.ModelForm):

    class Meta:
        model = Proyecto
        fields = [
            "solicitud", "cliente", "tipo_proyecto",
            "nombre", "descripcion", "area_total_m2", "perimetro_ml",
            "trm", "margen_comercial_pct", "iva_pct", "aiu_pct",
            "moneda", "aplica_exencion_iva", "observaciones",
        ]
        widgets = {

            "solicitud": forms.Select(
                attrs={"class": "form-select"}),
            "cliente": forms.Select(
                attrs={"class": "form-select"}),
            "tipo_proyecto": forms.Select(
                attrs={"class": "form-select"}),
            "nombre": forms.TextInput(
                attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(
                attrs={"class": "form-control", 
                       "rows": 3}),
            "area_total_m2": forms.NumberInput(
                attrs={"class": "form-control", 
                       "step": "0.0001"}),
            "perimetro_ml": forms.NumberInput(
                attrs={"class": "form-control", 
                       "step": "0.0001"}),
            "trm": forms.NumberInput(
                attrs={"class": "form-control", 
                       "step": "0.01"}),
            "margen_comercial_pct": forms.NumberInput(
                attrs={"class": "form-control", 
                       "step": "0.01"}),
            "iva_pct": forms.NumberInput(
                attrs={"class": "form-control", 
                       "step": "0.01"}),
            "aiu_pct": forms.NumberInput(
                attrs={"class": "form-control", 
                       "step": "0.01"}),
            "moneda": forms.Select(
                attrs={"class": "form-select"}),
            "aplica_exencion_iva": forms.CheckboxInput(
                attrs={"class": "form-check-input"}),
            "observaciones": forms.Textarea(
                attrs={"class": "form-control", "rows": 2}),
        }
