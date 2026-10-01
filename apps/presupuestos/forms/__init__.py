"""apps/presupuestos/forms — Formularios del módulo de presupuestos."""

from decimal import Decimal

from django import forms

from apps.presupuestos.models import (
    ProyectoSistema,
    DespieceLinea,
    ConfiguracionAPU,
    APUProyecto,
    CategoriaItemAPU,
    ItemCatalogoAPU,
    PaqueteAPU,
)
from apps.catalogos.models import Producto


# ── ProyectoSistema ───────────────────────────────────────────────────────────

class ProyectoSistemaForm(forms.ModelForm):
    class Meta:
        model = ProyectoSistema
        fields = ["proyecto", "sistema", "subsistema"]
        widgets = {
            "proyecto":   forms.Select(attrs={"class": "form-select"}),
            "sistema":    forms.Select(attrs={"class": "form-select"}),
            "subsistema": forms.Select(attrs={"class": "form-select"}),
        }


# ── DespieceLinea ─────────────────────────────────────────────────────────────

class DespieceLineaAjusteForm(forms.ModelForm):
    class Meta:
        model = DespieceLinea
        fields = ["cantidad_ajustada", "motivo_ajuste", "producto"]
        widgets = {
            "cantidad_ajustada": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "motivo_ajuste":     forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "producto":          forms.Select(attrs={"class": "form-select"}),
        }


# ── ConfiguracionAPU ──────────────────────────────────────────────────────────

class ConfiguracionAPUForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionAPU
        fields = [
            "nombre", "margen_material_pct", "iva_pct",
            "aiu_contratista_pct", "margen_mano_obra_pct",
            "desperdicio_pct", "activa",
        ]
        widgets = {
            "nombre":              forms.TextInput(attrs={"class": "form-control"}),
            "margen_material_pct":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "iva_pct":              forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aiu_contratista_pct":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "desperdicio_pct":      forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "margen_mano_obra_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "activa":               forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "margen_material_pct":  "Margen de material (%)",
            "margen_mano_obra_pct": "Margen de mano de obra (%)",
            "aiu_contratista_pct":  "AIU contratista (%)",
        }


# ── APU (cabecera) ────────────────────────────────────────────────────────────

class APUProyectoForm(forms.ModelForm):
    class Meta:
        model = APUProyecto
        fields = [
            "nombre", "descripcion",
            "margen_material_pct", "iva_pct", "aplica_iva",
            "aiu_contratista_pct", "margen_mano_obra_pct", "margen_contratista_pct",
            "dias_duracion",
        ]
        widgets = {
            "nombre":              forms.TextInput(attrs={"class": "form-control"}),
            "descripcion":         forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "margen_material_pct":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "iva_pct":              forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aplica_iva":           forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "aiu_contratista_pct":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "margen_mano_obra_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "margen_contratista_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "dias_duracion":        forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
        }
        labels = {
            "margen_material_pct":  "Margen de material (%)",
            "iva_pct":              "IVA (%)",
            "aplica_iva":           "Aplica IVA",
            "aiu_contratista_pct":  "AIU contratista (%)",
            "margen_mano_obra_pct": "Margen de mano de obra (%)",
            "margen_contratista_pct": "Margen de contratista (%)",
            "dias_duracion":        "Días de duración",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Opcional: si no se envía, se conserva el valor actual del APU.
        self.fields["margen_contratista_pct"].required = False

    def clean_margen_contratista_pct(self):
        valor = self.cleaned_data.get("margen_contratista_pct")
        if valor is None:
            return self.instance.margen_contratista_pct or Decimal("0")
        if valor < 0:
            raise forms.ValidationError("El margen no puede ser negativo.")
        return valor


# ── Catálogo APU — Categorías ─────────────────────────────────────────────────

class CategoriaItemAPUForm(forms.ModelForm):
    class Meta:
        model = CategoriaItemAPU
        fields = ["tipo_apu", "nombre", "descripcion", "orden", "activa"]
        widgets = {
            "tipo_apu":    forms.Select(attrs={"class": "form-select"}),
            "nombre":      forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "orden":       forms.NumberInput(attrs={"class": "form-control"}),
            "activa":      forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


# ── Catálogo APU — Ítems ──────────────────────────────────────────────────────

class ItemCatalogoAPUForm(forms.ModelForm):
    class Meta:
        model = ItemCatalogoAPU
        fields = [
            "categoria", "codigo", "nombre", "descripcion",
            "valor_base", "unidad", "tienda_referencia",
            "vida_util_dias", "activo",
        ]
        widgets = {
            "categoria":         forms.Select(attrs={"class": "form-select"}),
            "codigo":            forms.TextInput(attrs={"class": "form-control"}),
            "nombre":            forms.TextInput(attrs={"class": "form-control"}),
            "descripcion":       forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "valor_base":        forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0"}),
            "unidad":            forms.Select(attrs={"class": "form-select"}),
            "tienda_referencia": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Home Center, Homecenter en línea…"}),
            "vida_util_dias":    forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "activo":            forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "valor_base":        "Valor base",
            "vida_util_dias":    "Vida útil (días)",
            "tienda_referencia": "Tienda de referencia",
        }


class PaqueteAPUForm(forms.ModelForm):
    """
    Datos generales de un paquete maestro (Fase 3.A). La composición se envía
    aparte y la valida `paquete_service.parse_componentes`.

    El TipoAPU queda bloqueado cuando el paquete ya tiene componentes guardados:
    `PaqueteAPU.clean()` impide cambiarlo mientras existan componentes.
    """

    class Meta:
        model = PaqueteAPU
        fields = ["nombre", "tipo_apu", "descripcion", "activo"]
        widgets = {
            "nombre":      forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Herramientas de instalación", "autocomplete": "off"}),
            "tipo_apu":    forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Para qué se usa este paquete (opcional)"}),
            "activo":      forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
        }
        labels = {"tipo_apu": "Tipo APU", "activo": "Paquete activo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tipo_bloqueado = bool(self.instance.pk and self.instance.items.exists())
        if self.tipo_bloqueado:
            self.fields["tipo_apu"].disabled = True


# ── Formularios legacy (se conservan para compatibilidad) ──────────────────────

class APUAdminForm(forms.Form):
    MODO_CHOICES = [
        ("porcentaje", "% sobre base (materiales + MO + herramientas)"),
        ("valor",      "Valor fijo ($)"),
    ]
    modo = forms.ChoiceField(
        label="Tipo de administrativo", choices=MODO_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    valor = forms.DecimalField(
        label="Valor (% o $)", min_value=0, decimal_places=4, max_digits=18,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0"}),
    )
