"""apps/comercial/forms.py — Formularios del módulo comercial."""

from django import forms
from .models import Cliente, ContactoCliente, TipoProyecto, Solicitud, Proyecto


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nit", "razon_social", "ciudad", "direccion",
                  "telefono_principal", "email_principal", "activo"]
        widgets = {
            "nit":              forms.TextInput(attrs={"class": "form-control"}),
            "razon_social":     forms.TextInput(attrs={"class": "form-control"}),
            "ciudad":           forms.TextInput(attrs={"class": "form-control"}),
            "direccion":        forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "telefono_principal": forms.TextInput(attrs={"class": "form-control"}),
            "email_principal":  forms.EmailInput(attrs={"class": "form-control"}),
            "activo":           forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ContactoClienteForm(forms.ModelForm):
    class Meta:
        model = ContactoCliente
        fields = ["cliente", "nombre", "cargo", "email", "telefono", "es_principal", "activo"]
        widgets = {
            "cliente":      forms.Select(attrs={"class": "form-select"}),
            "nombre":       forms.TextInput(attrs={"class": "form-control"}),
            "cargo":        forms.TextInput(attrs={"class": "form-control"}),
            "email":        forms.EmailInput(attrs={"class": "form-control"}),
            "telefono":     forms.TextInput(attrs={"class": "form-control"}),
            "es_principal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "activo":       forms.CheckboxInput(attrs={"class": "form-check-input"}),
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
            "consecutivo", "cliente", "contacto", "creado_por",
            "nombre", "descripcion", "fecha_entrega", "estado", "observaciones",
        ]
        widgets = {
            "consecutivo":   forms.TextInput(attrs={"class": "form-control"}),
            "cliente":       forms.Select(attrs={"class": "form-select"}),
            "contacto":      forms.Select(attrs={"class": "form-select"}),
            "creado_por":    forms.Select(attrs={"class": "form-select"}),
            "nombre":        forms.TextInput(attrs={"class": "form-control"}),
            "descripcion":   forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fecha_entrega": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "estado":        forms.Select(attrs={"class": "form-select"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Auto-rellenar consecutivo si es nuevo
        if not self.instance.pk:
            self.fields["consecutivo"].initial = Solicitud.siguiente_consecutivo()


class ProyectoForm(forms.ModelForm):
    class Meta:
        model = Proyecto
        fields = [
            "consecutivo", "solicitud", "cliente", "creado_por", "tipo_proyecto",
            "nombre", "descripcion", "area_total_m2", "perimetro_ml",
            "trm", "margen_comercial_pct", "iva_pct", "aiu_pct",
            "moneda", "aplica_exencion_iva", "observaciones", "estado",
        ]
        widgets = {
            "consecutivo":        forms.TextInput(attrs={"class": "form-control"}),
            "solicitud":          forms.Select(attrs={"class": "form-select"}),
            "cliente":            forms.Select(attrs={"class": "form-select"}),
            "creado_por":         forms.Select(attrs={"class": "form-select"}),
            "tipo_proyecto":      forms.Select(attrs={"class": "form-select"}),
            "nombre":             forms.TextInput(attrs={"class": "form-control"}),
            "descripcion":        forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "area_total_m2":      forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
            "perimetro_ml":       forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
            "trm":                forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "margen_comercial_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "iva_pct":            forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aiu_pct":            forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "moneda":             forms.Select(attrs={"class": "form-select"}),
            "aplica_exencion_iva": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "observaciones":      forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "estado":             forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["consecutivo"].initial = Proyecto.siguiente_consecutivo()
