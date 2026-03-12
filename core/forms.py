"""
core/forms.py — Formularios Django para captura de variables de proyecto.

Formularios:
  1.  ProyectoSistemaVariablesForm — total_powergip, cuadrilla_personas, variables_extra
  2.  IniciarDespieceForm          — para seleccionar sistema/subsistema e ingresar TP
  3.  APUCostosForm                — costos de mano de obra, herramientas, transporte
  4.  AjusteLineaForm              — ajuste manual de cantidad en DespieceLinea
  5.  ClienteForm                  — crear/editar cliente
  6.  ContactoClienteFormSet       — inline formset de contactos (tipo Django admin)
  7.  SolicitudForm                — crear/editar solicitud
  8.  ProyectoCrearForm            — crear proyecto desde solicitud (con variables financieras)
  9.  AdminRevisionForm            — variables del proyecto + aprobación/rechazo por Admin
  10. ProductoProveedorForm        — crear/actualizar precio de producto por proveedor (Compras)
  11. ProveedorForm                — crear/editar proveedor
  12. ProductoForm                 — crear/editar producto con código auto y vínculo proveedor
"""

import json
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import (
    ProyectoSistema,
    Sistema,
    Subsistema,
    DespieceLinea,
    Cliente,
    ContactoCliente,
    Solicitud,
    Proyecto,
    TipoProyecto,
    Proveedor,
    Producto,
    ProductoProveedor,
    CategoriaProducto,
    UnidadMedida,
    Moneda,
    LineaNegocio,
)


# ---------------------------------------------------------------------------
# 1. Variables del ProyectoSistema (total_powergip, cuadrilla, extra)
# ---------------------------------------------------------------------------

class ProyectoSistemaVariablesForm(forms.ModelForm):
    """
    Captura las variables dinámicas del sistema en el proyecto:
      - total_powergip    : cantidad total de fijaciones PowerGrip
      - cuadrilla_personas: número de personas en la cuadrilla de instalación
      - variables_extra   : JSON con variables adicionales del subsistema
    """

    variables_extra_raw = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 4,
            "class": "form-control font-monospace",
            "placeholder": '{"variable_clave": 100, "otra_variable": 50}',
        }),
        label="Variables extra (JSON)",
        help_text="Ingrese un objeto JSON con variables adicionales del sistema.",
    )

    class Meta:
        model  = ProyectoSistema
        fields = ["total_powergip", "cuadrilla_personas", "observaciones"]
        widgets = {
            "total_powergip": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "placeholder": "Ej: 500",
            }),
            "cuadrilla_personas": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "max": "50",
                "placeholder": "Ej: 4",
            }),
            "observaciones": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Observaciones técnicas del sistema...",
            }),
        }
        labels = {
            "total_powergip":     "Total PowerGrip (cantidad de fijaciones)",
            "cuadrilla_personas": "Personas en cuadrilla",
            "observaciones":      "Observaciones",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-poblar el campo JSON si ya hay datos
        if self.instance and self.instance.variables_extra:
            self.initial["variables_extra_raw"] = json.dumps(
                self.instance.variables_extra, indent=2, ensure_ascii=False
            )

    def clean_total_powergip(self):
        val = self.cleaned_data.get("total_powergip")
        if val is not None and val <= 0:
            raise ValidationError("El total de PowerGrip debe ser un número positivo.")
        return val

    def clean_cuadrilla_personas(self):
        val = self.cleaned_data.get("cuadrilla_personas")
        if val is not None and val < 1:
            raise ValidationError("La cuadrilla debe tener al menos 1 persona.")
        return val

    def clean_variables_extra_raw(self):
        raw = self.cleaned_data.get("variables_extra_raw", "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValidationError("Las variables extra deben ser un objeto JSON (clave: valor).")
            return data
        except json.JSONDecodeError as e:
            raise ValidationError(f"JSON inválido: {e}")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.variables_extra = self.cleaned_data.get("variables_extra_raw", {})
        if commit:
            instance.save()
        return instance


# ---------------------------------------------------------------------------
# 2. Iniciar despiece (selección de sistema y variables iniciales)
# ---------------------------------------------------------------------------

class IniciarDespieceForm(forms.Form):
    """
    Formulario para iniciar el despiece de un proyecto.
    Permite seleccionar sistema/subsistema e ingresar Total_PowerGrip.
    """

    sistema = forms.ModelChoiceField(
        queryset=Sistema.objects.filter(activo=True),
        empty_label="── Seleccione un sistema ──",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_sistema"}),
        label="Sistema",
    )

    subsistema = forms.ModelChoiceField(
        queryset=Subsistema.objects.filter(activo=True),
        empty_label="── Seleccione un subsistema ──",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_subsistema"}),
        label="Subsistema / Variante",
    )

    total_powergip = forms.DecimalField(
        min_value=1,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Ej: 500",
            "step": "0.01",
        }),
        label="Total PowerGrip (cantidad de fijaciones)",
        help_text="Número total de fijaciones para este sistema en el proyecto.",
    )

    cuadrilla_personas = forms.IntegerField(
        min_value=1,
        max_value=50,
        initial=4,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Ej: 4",
        }),
        label="Personas en cuadrilla",
    )

    def clean(self):
        cleaned = super().clean()
        sistema    = cleaned.get("sistema")
        subsistema = cleaned.get("subsistema")

        if sistema and subsistema:
            if subsistema.sistema != sistema:
                self.add_error(
                    "subsistema",
                    f"El subsistema '{subsistema.nombre}' no pertenece al sistema '{sistema.nombre}'."
                )
        return cleaned


# ---------------------------------------------------------------------------
# 3. Costos de entrada para APU
# ---------------------------------------------------------------------------

class APUCostosForm(forms.Form):
    """
    Captura los costos de entrada para generar el APU completo.
    Todos los valores son en COP/día o COP/viaje según el campo.
    """

    # ── Mano de obra ─────────────────────────────────────────────────────────
    hya_dia = forms.DecimalField(
        min_value=0,
        max_digits=14,
        decimal_places=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "0",
        }),
        label="H&A por día (Herramientas y andamios, COP/día)",
        help_text="Costo diario de herramientas menores y andamios.",
    )

    cuadrilla_dia = forms.DecimalField(
        min_value=0,
        max_digits=14,
        decimal_places=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "0",
        }),
        label="Cuadrilla por día (COP/día)",
        help_text="Salario diario de cada persona de la cuadrilla.",
    )

    dotacion_dia = forms.DecimalField(
        min_value=0,
        max_digits=14,
        decimal_places=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "0",
        }),
        label="Dotación por día (COP/día)",
        help_text="Costo diario de dotación y EPP por persona.",
    )

    proteccion_dia = forms.DecimalField(
        min_value=0,
        max_digits=14,
        decimal_places=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "0",
        }),
        label="Protección por día (COP/día)",
        help_text="Costo diario de elementos de protección adicionales.",
    )

    # ── Herramientas específicas ──────────────────────────────────────────────
    herramientas_raw = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control font-monospace",
            "rows": 5,
            "placeholder": '[{"descripcion": "Tornillo automático", "precio_total": 150000}]',
        }),
        label="Herramientas específicas (JSON)",
        help_text='Lista JSON: [{"descripcion": "...", "precio_total": 0}]',
    )

    # ── Transporte ────────────────────────────────────────────────────────────
    costo_transporte = forms.DecimalField(
        min_value=0,
        max_digits=14,
        decimal_places=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "0",
        }),
        label="Costo total transporte (COP)",
        help_text="Flete y movilización total del proyecto.",
    )

    # ── Administración ────────────────────────────────────────────────────────
    costo_admin = forms.DecimalField(
        min_value=0,
        max_digits=14,
        decimal_places=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "0",
        }),
        label="Costo total administración (COP)",
        help_text="Gastos de administración y gastos generales del proyecto.",
    )

    def clean_herramientas_raw(self):
        raw = self.cleaned_data.get("herramientas_raw", "").strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValidationError("Herramientas debe ser una lista JSON.")
            for item in data:
                if "descripcion" not in item or "precio_total" not in item:
                    raise ValidationError(
                        'Cada herramienta debe tener "descripcion" y "precio_total".'
                    )
            return data
        except json.JSONDecodeError as e:
            raise ValidationError(f"JSON inválido: {e}")

    def to_service_kwargs(self) -> dict:
        """Convierte los datos del formulario a kwargs para APUService."""
        d = self.cleaned_data
        return {
            "hya_dia":           float(d.get("hya_dia") or 0),
            "cuadrilla_dia":     float(d.get("cuadrilla_dia") or 0),
            "dotacion_dia":      float(d.get("dotacion_dia") or 0),
            "proteccion_dia":    float(d.get("proteccion_dia") or 0),
            "herramientas_items": d.get("herramientas_raw") or [],
            "costo_transporte":  float(d.get("costo_transporte") or 0),
            "costo_admin":       float(d.get("costo_admin") or 0),
        }


# ---------------------------------------------------------------------------
# 4. Ajuste manual de una línea de despiece
# ---------------------------------------------------------------------------

class AjusteLineaForm(forms.ModelForm):
    """
    Permite que el usuario ajuste manualmente la cantidad de una DespieceLinea.
    """

    class Meta:
        model  = DespieceLinea
        fields = ["cantidad_ajustada", "motivo_ajuste"]
        widgets = {
            "cantidad_ajustada": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
            }),
            "motivo_ajuste": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Razón del ajuste manual...",
            }),
        }
        labels = {
            "cantidad_ajustada": "Cantidad ajustada",
            "motivo_ajuste":     "Motivo del ajuste",
        }

    def clean(self):
        cleaned = super().clean()
        cantidad = cleaned.get("cantidad_ajustada")
        motivo   = cleaned.get("motivo_ajuste", "")

        if cantidad is not None and not motivo:
            raise ValidationError(
                {"motivo_ajuste": "Debe ingresar un motivo al ajustar la cantidad."}
            )
        return cleaned


# ---------------------------------------------------------------------------
# 5. Formulario de Cliente
# ---------------------------------------------------------------------------

class ClienteForm(forms.ModelForm):
    """Crear o editar un cliente. Usado por el Asesor Comercial."""

    class Meta:
        model  = Cliente
        fields = ["nit", "razon_social", "ciudad", "direccion",
                  "telefono_principal", "email_principal"]
        widgets = {
            "nit": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: 900123456-1"}),
            "razon_social": forms.TextInput(attrs={"class": "form-control"}),
            "ciudad": forms.TextInput(attrs={"class": "form-control"}),
            "direccion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "telefono_principal": forms.TextInput(attrs={"class": "form-control"}),
            "email_principal": forms.EmailInput(attrs={"class": "form-control"}),
        }
        labels = {
            "nit": "NIT",
            "razon_social": "Razón social",
            "ciudad": "Ciudad",
            "direccion": "Dirección",
            "telefono_principal": "Teléfono principal",
            "email_principal": "Correo electrónico",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Los campos del modelo son blank/null=True, pero en el formulario
        # todos son obligatorios por política del negocio.
        for field in self.fields.values():
            field.required = True


# ---------------------------------------------------------------------------
# 6. Inline formset de ContactoCliente (estilo Django admin)
# ---------------------------------------------------------------------------

class _ContactoBaseForm(forms.ModelForm):
    """
    Formulario base para cada fila del inline formset de contactos.
    Aplica clases Bootstrap a todos los widgets y
    hace obligatorios nombre, cargo, email y teléfono en filas no vacías.
    """

    class Meta:
        model  = ContactoCliente
        fields = ["nombre", "cargo", "email", "telefono", "es_principal", "activo"]
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Nombre completo",
            }),
            "cargo": forms.TextInput(attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Cargo",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-control form-control-sm",
                "placeholder": "correo@empresa.com",
            }),
            "telefono": forms.TextInput(attrs={
                "class": "form-control form-control-sm",
                "placeholder": "310 123 4567",
            }),
            "es_principal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "activo":       forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "nombre":      "Nombre",
            "cargo":       "Cargo",
            "email":       "Email",
            "telefono":    "Teléfono",
            "es_principal": "Es principal",
            "activo":      "Activo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # cargo, email y teléfono son opcionales en el modelo
        # pero obligatorios según política de negocio cuando la fila tiene datos
        self.fields["cargo"].required    = False
        self.fields["email"].required    = False
        self.fields["telefono"].required = False

    def _fila_tiene_datos(self):
        """True si el usuario escribió algo en la fila (detecta filas extra vacías)."""
        for fname in ["nombre", "cargo", "email", "telefono"]:
            if self.cleaned_data.get(fname, "").strip():
                return True
        return False

    def clean(self):
        cleaned = super().clean()
        if self._fila_tiene_datos():
            # Si la fila tiene datos, todos los campos son obligatorios
            for fname, label in [
                ("nombre",   "Nombre"),
                ("cargo",    "Cargo"),
                ("email",    "Email"),
                ("telefono", "Teléfono"),
            ]:
                if not cleaned.get(fname, "").strip():
                    self.add_error(fname, f"{label} es obligatorio.")
        return cleaned


# Formset inline listo para usar en las vistas
ContactoClienteFormSet = inlineformset_factory(
    Cliente,
    ContactoCliente,
    form=_ContactoBaseForm,
    extra=1,          # Una fila vacía adicional para agregar
    can_delete=True,  # Muestra la columna ¿Eliminar?
    min_num=1,        # Al menos un contacto requerido
    validate_min=True,
)


# ---------------------------------------------------------------------------
# 7. Formulario de Solicitud
# ---------------------------------------------------------------------------

class SolicitudForm(forms.ModelForm):
    """Crear o editar una solicitud. Usado por el Asesor Comercial."""

    class Meta:
        model  = Solicitud
        fields = ["cliente", "contacto", "nombre", "descripcion",
                  "fecha_entrega", "observaciones"]
        widgets = {
            "cliente": forms.Select(attrs={"class": "form-select"}),
            "contacto": forms.Select(attrs={"class": "form-select"}),
            "nombre": forms.TextInput(attrs={"class": "form-control",
                                             "placeholder": "Nombre del proyecto solicitado"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fecha_entrega": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
        labels = {
            "cliente": "Cliente",
            "contacto": "Contacto del cliente",
            "nombre": "Nombre / descripción del requerimiento",
            "descripcion": "Descripción detallada",
            "fecha_entrega": "Fecha de entrega requerida",
            "observaciones": "Observaciones",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El consecutivo se asigna automáticamente
        # Filtrar contactos activos solo si hay cliente
        if self.instance and self.instance.cliente_id:
            self.fields["contacto"].queryset = ContactoCliente.objects.filter(
                cliente=self.instance.cliente, activo=True
            )
        else:
            self.fields["contacto"].queryset = ContactoCliente.objects.none()
        self.fields["contacto"].required = False


# ---------------------------------------------------------------------------
# 7. Formulario de creación de Proyecto desde Solicitud
# ---------------------------------------------------------------------------

class ProyectoCrearForm(forms.Form):
    """
    Usado por Presupuestos para crear un proyecto desde una solicitud.
    Captura el tipo de proyecto y las variables financieras del proyecto.
    """

    tipo_proyecto = forms.ModelChoiceField(
        queryset=TipoProyecto.objects.filter(activo=True),
        empty_label="── Seleccione tipo de proyecto ──",
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Tipo de proyecto",
    )

    area_total_m2 = forms.DecimalField(
        required=False, min_value=0, max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01",
                                        "placeholder": "Ej: 500.00"}),
        label="Área total (m²)",
        help_text="Se puede ingresar después.",
    )

    perimetro_ml = forms.DecimalField(
        required=False, min_value=0, max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        label="Perímetro (ml)",
    )

    trm = forms.DecimalField(
        initial=4200, min_value=1, max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
        label="TRM (COP/USD)",
    )

    margen_comercial_pct = forms.DecimalField(
        initial=20, min_value=0, max_digits=8, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
        label="Margen comercial (%)",
    )

    iva_pct = forms.DecimalField(
        initial=19, min_value=0, max_digits=8, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
        label="IVA (%)",
    )

    aiu_pct = forms.DecimalField(
        initial=0, min_value=0, max_digits=8, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
        label="AIU (%)",
    )

    aplica_exencion_iva = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Aplica exención de IVA",
    )

    observaciones = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        label="Observaciones",
    )


# ---------------------------------------------------------------------------
# 8. Formulario de Revisión Administrativa (Admin aprueba o rechaza APU)
# ---------------------------------------------------------------------------

class AdminRevisionForm(forms.Form):
    """
    Usado por el Administrador para ingresar datos variables del proyecto
    y aprobar o rechazar el APU generado.
    """

    trm = forms.DecimalField(
        min_value=1, max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
        label="TRM vigente (COP/USD)",
    )

    margen_comercial_pct = forms.DecimalField(
        min_value=0, max_digits=8, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
        label="Margen comercial (%)",
    )

    iva_pct = forms.DecimalField(
        min_value=0, max_digits=8, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
        label="IVA (%)",
    )

    aiu_pct = forms.DecimalField(
        min_value=0, max_digits=8, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
        label="AIU (%)",
    )

    DECISION_CHOICES = [
        ("aprobar", "Aprobar — La cotización está lista para enviar al cliente"),
        ("rechazar", "Rechazar — Devolver a Presupuestos para ajuste"),
    ]

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        label="Decisión",
    )

    motivo_devolucion = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3,
                                     "placeholder": "Indique el motivo del rechazo..."}),
        label="Motivo de devolución",
        help_text="Requerido si la decisión es Rechazar.",
    )

    def clean(self):
        cleaned = super().clean()
        decision = cleaned.get("decision")
        motivo   = cleaned.get("motivo_devolucion", "").strip()
        if decision == "rechazar" and not motivo:
            raise ValidationError(
                {"motivo_devolucion": "Debe indicar el motivo al rechazar el APU."}
            )
        return cleaned


# ---------------------------------------------------------------------------
# 9. Formulario para que Compras actualice precios de productos
# ---------------------------------------------------------------------------

class ProductoProveedorForm(forms.ModelForm):
    """
    Usado por Compras para crear o actualizar el precio de un producto
    asociado a un proveedor.
    """

    class Meta:
        model  = ProductoProveedor
        fields = ["proveedor", "precio_unitario", "moneda", "activo"]
        widgets = {
            "proveedor": forms.Select(attrs={"class": "form-select"}),
            "precio_unitario": forms.NumberInput(attrs={
                "class": "form-control", "step": "0.01", "min": "0"
            }),
            "moneda": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "proveedor": "Proveedor",
            "precio_unitario": "Precio unitario",
            "moneda": "Moneda",
            "activo": "Activo",
        }


# ---------------------------------------------------------------------------
# 10. Formulario para que Compras registre motivo de rechazo de precios
# ---------------------------------------------------------------------------

class ComprasRechazarForm(forms.Form):
    """Compras notifica a Presupuestos por qué no puede actualizar un precio."""

    motivo = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3,
                                     "placeholder": "Explique por qué no se puede actualizar el precio..."}),
        label="Motivo",
    )


# ---------------------------------------------------------------------------
# 11. Formulario de Proveedor
# ---------------------------------------------------------------------------

class ProveedorForm(forms.ModelForm):
    """Crear o editar un proveedor. Todos los campos son obligatorios."""

    class Meta:
        model  = Proveedor
        fields = ["nit", "nombre", "ciudad", "direccion", "telefono", "email"]
        widgets = {
            "nit": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: 900123456-1",
            }),
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Razón social del proveedor",
            }),
            "ciudad": forms.TextInput(attrs={"class": "form-control"}),
            "direccion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }
        labels = {
            "nit":       "NIT",
            "nombre":    "Nombre / Razón social",
            "ciudad":    "Ciudad",
            "direccion": "Dirección",
            "telefono":  "Teléfono",
            "email":     "Correo electrónico",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Los campos del modelo permiten blank/null, pero son obligatorios en el negocio
        for field in self.fields.values():
            field.required = True


# ---------------------------------------------------------------------------
# 12. Formulario de Producto con código auto-generado y vínculo a proveedor
# ---------------------------------------------------------------------------

class ProductoForm(forms.ModelForm):
    """
    Crear o editar un producto del catálogo.

    - El código (Producto.codigo) se genera automáticamente en la vista
      según la categoría seleccionada; no se muestra en el formulario.
    - proveedor_nit    : NIT del proveedor para buscar/crear ProductoProveedor.
    - precio_unitario  : Precio con el que se registra la relación.
    - moneda_proveedor : Moneda del precio (COP, USD, EUR).
    """

    # ── Campos extra (relación ProductoProveedor) ──────────────────────────
    proveedor_nit = forms.CharField(
        required=True,
        max_length=50,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Ej: 900123456-1",
            "autocomplete": "off",
        }),
        label="NIT del proveedor",
        help_text="El proveedor debe estar registrado en el sistema.",
    )

    precio_unitario = forms.DecimalField(
        required=True,
        min_value=0,
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "placeholder": "Ej: 15000.00",
        }),
        label="Precio unitario",
    )

    moneda_proveedor = forms.ChoiceField(
        choices=Moneda.choices,
        initial=Moneda.COP,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Moneda del precio",
    )

    # ── Campos del modelo Producto ─────────────────────────────────────────
    class Meta:
        model  = Producto
        fields = ["nombre", "categoria", "unidad", "origen",
                  "marca", "linea", "rendimiento", "activo"]
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombre completo del producto",
            }),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "unidad": forms.Select(attrs={"class": "form-select"}),
            "origen": forms.Select(attrs={"class": "form-select"}),
            "marca": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Marca (opcional)",
            }),
            "linea": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Línea de producto (opcional)",
            }),
            "rendimiento": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.000001",
                "placeholder": "Ej: 1.000000",
            }),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "nombre":      "Nombre del producto",
            "categoria":   "Categoría",
            "unidad":      "Unidad de medida",
            "origen":      "Origen",
            "marca":       "Marca",
            "linea":       "Línea",
            "rendimiento": "Rendimiento",
            "activo":      "Activo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["marca"].required      = False
        self.fields["linea"].required      = False
        self.fields["rendimiento"].required = False

        # Al editar, pre-rellenar datos del proveedor activo principal
        if self.instance and self.instance.pk:
            pp = (
                self.instance.proveedores_producto
                .filter(activo=True)
                .order_by("precio_unitario")
                .first()
            )
            if pp:
                self.fields["proveedor_nit"].initial    = pp.proveedor.nit
                self.fields["precio_unitario"].initial  = pp.precio_unitario
                self.fields["moneda_proveedor"].initial = pp.moneda

    def clean_proveedor_nit(self):
        nit = self.cleaned_data.get("proveedor_nit", "").strip()
        if not nit:
            raise ValidationError("El NIT del proveedor es obligatorio.")
        try:
            proveedor = Proveedor.objects.get(nit=nit, activo=True)
        except Proveedor.DoesNotExist:
            raise ValidationError(
                f"No existe ningún proveedor activo con NIT '{nit}'. "
                "Regístrelo primero en el catálogo de Proveedores."
            )
        # Guardar referencia para uso en la vista
        self._proveedor_obj = proveedor
        return nit

    def get_proveedor(self):
        """Retorna la instancia de Proveedor validada (llamar después de is_valid())."""
        return getattr(self, "_proveedor_obj", None)


# ---------------------------------------------------------------------------
# 13. Formulario de Sistema
# ---------------------------------------------------------------------------

class SistemaForm(forms.ModelForm):
    """Crear o editar un sistema. Todos los campos obligatorios excepto descripción."""

    class Meta:
        model  = Sistema
        fields = ["codigo", "nombre", "linea_negocio", "descripcion", "activo"]
        widgets = {
            "codigo": forms.TextInput(attrs={
                "class": "form-control text-uppercase",
                "placeholder": "Ej: CUB-SINUSOIDAL",
            }),
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombre completo del sistema",
            }),
            "linea_negocio": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Descripción técnica del sistema (opcional)",
            }),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "codigo":       "Código",
            "nombre":       "Nombre del sistema",
            "linea_negocio": "Línea de negocio",
            "descripcion":  "Descripción",
            "activo":       "Activo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["descripcion"].required = False


# ---------------------------------------------------------------------------
# 14. Inline formset de Subsistemas (estilo Django admin)
# ---------------------------------------------------------------------------

class _SubsistemaBaseForm(forms.ModelForm):
    """
    Formulario base para cada fila del inline formset de subsistemas.
    Hace obligatorios codigo y nombre en filas que tengan datos.
    """

    class Meta:
        model  = Subsistema
        fields = ["codigo", "nombre", "descripcion", "activo"]
        widgets = {
            "codigo": forms.TextInput(attrs={
                "class": "form-control form-control-sm text-uppercase",
                "placeholder": "Ej: CUB-SIN-STD",
            }),
            "nombre": forms.TextInput(attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Nombre del subsistema",
            }),
            "descripcion": forms.TextInput(attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Descripción (opcional)",
            }),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "codigo":      "Código",
            "nombre":      "Nombre",
            "descripcion": "Descripción",
            "activo":      "Activo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["descripcion"].required = False

    def _fila_tiene_datos(self):
        for fname in ["codigo", "nombre"]:
            if self.cleaned_data.get(fname, "").strip():
                return True
        return False

    def clean(self):
        cleaned = super().clean()
        if self._fila_tiene_datos():
            for fname, label in [("codigo", "Código"), ("nombre", "Nombre")]:
                if not cleaned.get(fname, "").strip():
                    self.add_error(fname, f"{label} es obligatorio.")
        return cleaned


SubsistemaFormSet = inlineformset_factory(
    Sistema,
    Subsistema,
    form=_SubsistemaBaseForm,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)
