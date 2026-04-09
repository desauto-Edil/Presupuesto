"""apps/comercial/forms.py — Formularios del módulo comercial."""

from django import forms
from django.core.exceptions import ValidationError
from .models import Cliente, ContactoCliente, TipoProyecto, Solicitud, SolicitudArchivo, Proyecto


class ClienteForm(forms.ModelForm):
    """Formulario base de Cliente (solo datos de la empresa)."""

    class Meta:
        model = Cliente
        fields = ["nit", "razon_social", "activo"]
        widgets = {
            "nit": forms.TextInput(attrs={"class": "form-control"}),
            "razon_social": forms.TextInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ClienteConContactoForm(forms.ModelForm):
    """
    Formulario combinado: Cliente + Contacto principal en una sola pantalla.
    · Creación: la vista crea el ContactoCliente con es_principal=True.
    · Edición: la vista actualiza el ContactoCliente principal existente.
    contacto_nombre es obligatorio; los demás campos del contacto son opcionales.
    """

    contacto_nombre = forms.CharField(
        max_length=200, label="Nombre del contacto",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre completo"}),
    )
    contacto_cargo = forms.CharField(
        max_length=120, label="Cargo", required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Gerente de proyectos"}),
    )
    contacto_email = forms.EmailField(
        max_length=120, label="Email del contacto", required=False,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    contacto_telefono = forms.CharField(
        max_length=30, label="Teléfono del contacto", required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Cliente
        fields = ["nit", "razon_social", "activo"]
        widgets = {
            "nit": forms.TextInput(attrs={"class": "form-control"}),
            "razon_social": forms.TextInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            cp = self.instance.contacto_principal
            if cp:
                self.fields["contacto_nombre"].initial = cp.nombre
                self.fields["contacto_cargo"].initial = cp.cargo or ""
                self.fields["contacto_email"].initial = cp.email or ""
                self.fields["contacto_telefono"].initial = cp.telefono or ""


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


class SolicitudForm(forms.ModelForm):
    """
    Formulario de Solicitud.
    · Todos los campos son obligatorios (backend + frontend).
    · estado y creado_por son controlados por el sistema (excluidos).
    """

    class Meta:
        model = Solicitud
        fields = [
            "consecutivo", "link_selford", "cliente",
            "nombre", "descripcion", "fecha_entrega", "observaciones",
        ]
        widgets = {
            "consecutivo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: SEL-2026-0042",
            }),
            "link_selford": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://selford.example.com/solicitud/42",
            }),
            "cliente": forms.Select(attrs={"class": "form-select"}),
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombre del proyecto o requerimiento",
            }),
            "descripcion": forms.Textarea(attrs={
                "class": "form-control", "rows": 3,
                "placeholder": "Descripción detallada del requerimiento",
            }),
            "fecha_entrega": forms.DateInput(attrs={
                "class": "form-control", "type": "date",
            }),
            "observaciones": forms.Textarea(attrs={
                "class": "form-control", "rows": 2,
                "placeholder": "Observaciones adicionales",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True


class TipoProyectoForm(forms.ModelForm):
    class Meta:
        model = TipoProyecto
        fields = ["codigo", "nombre", "activo"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


_PROYECTO_WIDGETS = {
    "nombre":               forms.TextInput(attrs={"class": "form-control"}),
    "descripcion":          forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    "area_total_m2":        forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
    "perimetro_ml":         forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
    "dias_duracion":        forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
    "num_personas":         forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
    "trm":                  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    "margen_comercial_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    "iva_pct":              forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    "aiu_pct":              forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    "moneda":               forms.Select(attrs={"class": "form-select"}),
    "aplica_exencion_iva":  forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "observaciones":        forms.Textarea(attrs={"class": "form-control", "rows": 2}),
}


class ProyectoForm(forms.ModelForm):
    class Meta:
        model = Proyecto
        fields = [
            "cliente", "tipo_proyecto", "nombre", "descripcion",
            "area_total_m2", "perimetro_ml", "dias_duracion", "num_personas",
            "trm", "margen_comercial_pct", "iva_pct", "aiu_pct",
            "moneda", "aplica_exencion_iva", "observaciones",
        ]
        widgets = {"cliente": forms.Select(attrs={"class": "form-select"}), **_PROYECTO_WIDGETS}


class ProyectoFromSolicitudForm(forms.ModelForm):
    """Formulario para crear Proyecto desde una Solicitud (cliente y solicitud los asigna la vista)."""
    class Meta:
        model = Proyecto
        fields = [
            "nombre", "descripcion",
            "area_total_m2", "perimetro_ml", "dias_duracion", "num_personas",
            "trm", "margen_comercial_pct", "iva_pct", "aiu_pct",
            "moneda", "aplica_exencion_iva", "observaciones",
        ]
        widgets = _PROYECTO_WIDGETS


class SolicitudArchivoForm(forms.ModelForm):
    """Formulario para subir archivos adjuntos a una Solicitud."""

    class Meta:
        model = SolicitudArchivo
        fields = ["archivo", "nombre"]
        widgets = {
            "archivo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombre descriptivo del archivo",
            }),
        }
