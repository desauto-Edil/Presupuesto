"""apps/comercial/forms.py — Formularios del módulo comercial."""

import mimetypes

from django import forms
from django.conf import settings
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
    · El campo cliente se filtra por unidad_negocio si se provee.
    """

    class Meta:
        model = Solicitud
        fields = [
            "consecutivo", "link_salesforce", "cliente",
            "nombre", "descripcion", "fecha_entrega", "observaciones",
        ]
        widgets = {
            "consecutivo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: SEL-2026-0042",
            }),
            "link_salesforce": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://salesforce.example.com/solicitud/42",
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

    def __init__(self, *args, unidad_negocio=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True
        self._unidad_negocio = unidad_negocio
        if unidad_negocio:
            self.fields["cliente"].queryset = Cliente.objects.filter(
                unidad_negocio=unidad_negocio, activo=True
            ).order_by("razon_social")
        else:
            self.fields["cliente"].queryset = Cliente.objects.filter(
                activo=True
            ).order_by("razon_social")

    def clean_cliente(self):
        cliente = self.cleaned_data.get("cliente")
        if cliente and self._unidad_negocio:
            if cliente.unidad_negocio != self._unidad_negocio:
                raise ValidationError(
                    "El cliente seleccionado no pertenece a la unidad de negocio actual."
                )
        return cliente


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
    "dias_duracion":        forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
    "num_personas":         forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
    "trm":                  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    "margen_material_pct":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    "margen_mano_obra_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    "iva_pct":              forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    "aiu_contratista_pct":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    "moneda":               forms.Select(attrs={"class": "form-select"}),
    "aplica_exencion_iva":  forms.CheckboxInput(attrs={"class": "form-check-input"}),
    "observaciones":        forms.Textarea(attrs={"class": "form-control", "rows": 2}),
}

_PROYECTO_LABELS = {
    "margen_material_pct":  "Margen de material (%)",
    "margen_mano_obra_pct": "Margen de mano de obra (%)",
    "aiu_contratista_pct":  "AIU contratista (%)",
    "iva_pct":              "IVA (%)",
    "trm":                  "TRM (COP/USD)",
}


class ProyectoForm(forms.ModelForm):
    class Meta:
        model = Proyecto
        fields = [
            "cliente", "nombre", "descripcion",
            "dias_duracion", "num_personas",
            "trm", "margen_material_pct", "margen_mano_obra_pct",
            "iva_pct", "aiu_contratista_pct",
            "moneda", "aplica_exencion_iva", "observaciones",
        ]
        widgets = {"cliente": forms.Select(attrs={"class": "form-select"}), **_PROYECTO_WIDGETS}
        labels = _PROYECTO_LABELS


class ProyectoFromSolicitudForm(forms.ModelForm):
    """Formulario para crear Proyecto desde una Solicitud (cliente y solicitud los asigna la vista)."""
    class Meta:
        model = Proyecto
        fields = [
            "nombre", "descripcion",
            "dias_duracion", "num_personas",
            "trm", "margen_material_pct", "margen_mano_obra_pct",
            "iva_pct", "aiu_contratista_pct",
            "moneda", "aplica_exencion_iva", "observaciones",
        ]
        widgets = _PROYECTO_WIDGETS
        labels = _PROYECTO_LABELS


_EXTENSIONES_PERMITIDAS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png",
}

_MIME_PERMITIDOS = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/png",
}


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

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if not archivo:
            return archivo

        max_mb = getattr(settings, "MAX_UPLOAD_SIZE_MB", 10)
        max_bytes = max_mb * 1024 * 1024
        if archivo.size > max_bytes:
            raise ValidationError(
                f"El archivo supera el tamaño máximo permitido ({max_mb} MB). "
                f"El archivo pesa {archivo.size / 1024 / 1024:.1f} MB."
            )

        nombre = archivo.name.lower()
        ext = "." + nombre.rsplit(".", 1)[-1] if "." in nombre else ""
        if ext not in _EXTENSIONES_PERMITIDAS:
            raise ValidationError(
                f"Tipo de archivo no permitido («{ext or 'sin extensión'}»). "
                f"Formatos aceptados: {', '.join(sorted(_EXTENSIONES_PERMITIDAS))}."
            )

        mime, _ = mimetypes.guess_type(archivo.name)
        if mime and mime not in _MIME_PERMITIDOS:
            raise ValidationError(
                "El tipo de contenido del archivo no está permitido. "
                "Use PDF, Word, Excel o imágenes JPG/PNG."
            )

        return archivo


