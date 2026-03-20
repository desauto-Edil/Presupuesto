"""apps/comercial/forms.py — Formularios del módulo comercial."""

from django import forms
from django.core.exceptions import ValidationError
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
    """
    Formulario de Solicitud.
    · contacto se filtra dinámicamente por cliente vía JS (AJAX).
    · clean() garantiza que contacto pertenezca al cliente seleccionado.
    """

    class Meta:
        model = Solicitud
        fields = [
            "cliente", "contacto",
            "nombre", "descripcion", "fecha_entrega", "observaciones",
        ]
        widgets = {
            "cliente": forms.Select(attrs={
                "class": "form-select",
                "id": "id_cliente",
            }),
            "contacto": forms.Select(attrs={
                "class": "form-select",
                "id": "id_contacto",
            }),
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombre del proyecto o requerimiento",
            }),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fecha_entrega": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # En edición: filtrar contactos al cliente ya seleccionado
        # (el JS los actualiza dinámicamente cuando el usuario cambia el cliente)
        if self.instance and self.instance.pk and self.instance.cliente_id:
            self.fields["contacto"].queryset = ContactoCliente.objects.filter(
                cliente_id=self.instance.cliente_id, activo=True
            ).order_by("-es_principal", "nombre")
        else:
            # Creación: empty queryset — el JS carga los contactos via AJAX
            self.fields["contacto"].queryset = ContactoCliente.objects.none()
        self.fields["contacto"].required = False

    def clean(self):
        """Garantiza que el contacto pertenezca al cliente seleccionado."""
        cd = super().clean()
        cliente = cd.get("cliente")
        contacto = cd.get("contacto")
        if contacto and cliente:
            if contacto.cliente_id != cliente.pk:
                raise ValidationError({
                    "contacto": "El contacto seleccionado no pertenece a este cliente."
                })
        return cd


class ProyectoForm(forms.ModelForm):
    """Formulario de Proyecto (edición directa). solicitud/estado/consecutivo excluidos."""

    class Meta:
        model = Proyecto
        fields = [
            "cliente", "tipo_proyecto",
            "nombre", "descripcion", "area_total_m2", "perimetro_ml",
            "trm", "margen_comercial_pct", "iva_pct", "aiu_pct",
            "moneda", "aplica_exencion_iva", "observaciones",
        ]
        widgets = {
            "cliente":             forms.Select(attrs={"class": "form-select"}),
            "tipo_proyecto":       forms.Select(attrs={"class": "form-select"}),
            "nombre":              forms.TextInput(attrs={"class": "form-control"}),
            "descripcion":         forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "area_total_m2":       forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
            "perimetro_ml":        forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
            "trm":                 forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "margen_comercial_pct":forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "iva_pct":             forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aiu_pct":             forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "moneda":              forms.Select(attrs={"class": "form-select"}),
            "aplica_exencion_iva": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "observaciones":       forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Formulario especializado: crear Proyecto DESDE una Solicitud
# cliente y solicitud los asigna la vista automáticamente
# ─────────────────────────────────────────────────────────────────────────────

class ProyectoFromSolicitudForm(forms.ModelForm):
    """
    Formulario simplificado para crear un Proyecto a partir de una Solicitud.
    No incluye cliente ni solicitud (los asigna CrearProyectoDesdeSolicitudView).
    """

    class Meta:
        model = Proyecto
        fields = [
            "tipo_proyecto",
            "nombre", "descripcion", "area_total_m2", "perimetro_ml",
            "trm", "margen_comercial_pct", "iva_pct", "aiu_pct",
            "moneda", "aplica_exencion_iva", "observaciones",
        ]
        widgets = {
            "tipo_proyecto":       forms.Select(attrs={"class": "form-select"}),
            "nombre":              forms.TextInput(attrs={"class": "form-control"}),
            "descripcion":         forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "area_total_m2":       forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "perimetro_ml":        forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "trm":                 forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "margen_comercial_pct":forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "iva_pct":             forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aiu_pct":             forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "moneda":              forms.Select(attrs={"class": "form-select"}),
            "aplica_exencion_iva": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "observaciones":       forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
