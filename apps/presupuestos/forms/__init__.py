"""apps/presupuestos/forms — Formularios del módulo de presupuestos."""

from django import forms
from django.forms import inlineformset_factory

from apps.presupuestos.models import (
    ProyectoSistema,
    DespieceLinea,
    ConfiguracionAPU,
    APUProyecto,
    CategoriaItemAPU,
    ItemCatalogoAPU,
    CuadrillaPreset,
    CuadrillaPresetItem,
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
            "nombre", "factor_venta_pct", "iva_pct",
            "aiu_contratista_pct", "margen_ganancia_pct",
            "desperdicio_pct", "activa",
        ]
        widgets = {
            "nombre":              forms.TextInput(attrs={"class": "form-control"}),
            "factor_venta_pct":    forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "iva_pct":             forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aiu_contratista_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "desperdicio_pct":     forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "margen_ganancia_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "activa":              forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


# ── APU (cabecera) ────────────────────────────────────────────────────────────

class APUProyectoForm(forms.ModelForm):
    class Meta:
        model = APUProyecto
        fields = [
            "nombre", "descripcion",
            "factor_venta_pct", "iva_pct", "aplica_iva",
            "aiu_contratista_pct", "margen_ganancia_pct", "dias_duracion",
            "aiu_proyecto_admin_pct", "aiu_proyecto_imprevistos_pct", "aiu_proyecto_utilidad_pct",
        ]
        widgets = {
            "nombre":                       forms.TextInput(attrs={"class": "form-control"}),
            "descripcion":                  forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "factor_venta_pct":             forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "iva_pct":                      forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aplica_iva":                   forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "aiu_contratista_pct":          forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "margen_ganancia_pct":          forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "dias_duracion":                forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "aiu_proyecto_admin_pct":       forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aiu_proyecto_imprevistos_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aiu_proyecto_utilidad_pct":    forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }
        labels = {
            "factor_venta_pct":             "Factor de venta (%)",
            "iva_pct":                      "IVA (%)",
            "aplica_iva":                   "Aplica IVA",
            "aiu_contratista_pct":          "AIU contratista (%)",
            "margen_ganancia_pct":          "Margen de ganancia (%)",
            "dias_duracion":                "Días de duración",
            "aiu_proyecto_admin_pct":       "Administración (%)",
            "aiu_proyecto_imprevistos_pct": "Imprevistos (%)",
            "aiu_proyecto_utilidad_pct":    "Utilidad (%)",
        }


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
            "precio_base", "unidad", "tienda_referencia",
            "salario_base", "prestaciones",
            "vida_util_dias", "activo",
        ]
        widgets = {
            "categoria":         forms.Select(attrs={"class": "form-select"}),
            "codigo":            forms.TextInput(attrs={"class": "form-control"}),
            "nombre":            forms.TextInput(attrs={"class": "form-control"}),
            "descripcion":       forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "precio_base":       forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "unidad":            forms.Select(attrs={"class": "form-select"}),
            "tienda_referencia": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Home Center, Homecenter en línea…"}),
            "salario_base":      forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "prestaciones":      forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
            "vida_util_dias":    forms.NumberInput(attrs={"class": "form-control"}),
            "activo":            forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "salario_base":      "Salario base mensual",
            "prestaciones":      "Prestaciones sociales ($/mes)",
            "vida_util_dias":    "Vida útil (días) — solo herramientas/dotación",
            "tienda_referencia": "Tienda de referencia",
        }


# ── Cuadrilla Preset ──────────────────────────────────────────────────────────

class CuadrillaPresetForm(forms.ModelForm):
    class Meta:
        model = CuadrillaPreset
        fields = ["nombre", "descripcion", "activo"]
        widgets = {
            "nombre":      forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "activo":      forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class CuadrillaPresetItemForm(forms.ModelForm):
    class Meta:
        model = CuadrillaPresetItem
        fields = ["item", "cantidad"]
        widgets = {
            "item":     forms.Select(attrs={"class": "form-select"}),
            "cantidad": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = (
            ItemCatalogoAPU.objects
            .filter(activo=True, categoria__tipo_apu="MANO_DE_OBRA")
            .select_related("categoria")
            .order_by("nombre")
        )


CuadrillaPresetItemFormSet = inlineformset_factory(
    CuadrillaPreset,
    CuadrillaPresetItem,
    form=CuadrillaPresetItemForm,
    extra=3,
    can_delete=True,
)


# ── Formularios legacy (se conservan para compatibilidad) ──────────────────────

class APUManoObraForm(forms.Form):
    cuadrilla_personas = forms.IntegerField(
        label="Personas en la cuadrilla", initial=7, min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )


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
