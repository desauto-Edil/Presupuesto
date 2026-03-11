"""
core/forms.py — Formularios Django para captura de variables de proyecto.

Formularios:
  1. ProyectoSistemaVariablesForm — total_powergip, cuadrilla_personas, variables_extra
  2. IniciarDespieceForm          — para seleccionar sistema/subsistema e ingresar TP
  3. APUCostosForm                — costos de mano de obra, herramientas, transporte
  4. AjusteLineaForm              — ajuste manual de cantidad en DespieceLinea
"""

import json
from django import forms
from django.core.exceptions import ValidationError

from .models import (
    ProyectoSistema,
    Sistema,
    Subsistema,
    DespieceLinea,
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
