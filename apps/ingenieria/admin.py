"""
apps/ingenieria/admin.py — Admin para catálogo de sistemas y subsistemas.

Sistemas y Subsistemas son catálogo maestro — se gestionan desde aquí.
Las recetas técnicas (fórmulas, componentes) están definidas en Python:
  → apps/ingenieria/system_defs/powergrip.py (y futuros sistemas)

ReglaCalculo y DependenciaTecnica quedan registradas como LEGADO —
    solo para consulta de datos históricos. No forman parte del flujo operativo.
"""

from django.contrib import admin
from .models import Sistema, Subsistema, ReglaCalculo, DependenciaTecnica
from apps.presupuestos.models import ReglaAPUSubsistema


# ── Catálogo activo ───────────────────────────────────────────────────────────

class ReglaAPUSubsistemaInline(admin.TabularInline):
    model = ReglaAPUSubsistema
    extra = 1
    fields = ("tipo_apu", "formula_costo_unitario", "orden")
    ordering = ("orden",)
    verbose_name = "Regla de cálculo APU"
    verbose_name_plural = "Reglas de cálculo APU (Herramientas, Transporte, MO, Admin)"


class SubsistemaInline(admin.TabularInline):
    model = Subsistema
    extra = 0
    fields = ("codigo", "nombre", "activo")
    show_change_link = True


@admin.register(Sistema)
class SistemaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "linea_negocio", "activo")
    list_filter  = ("linea_negocio", "activo")
    search_fields = ("codigo", "nombre")
    inlines = [SubsistemaInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(Subsistema)
class SubsistemaAdmin(admin.ModelAdmin):
    list_display  = ("codigo", "nombre", "sistema", "activo")
    list_filter   = ("sistema", "activo")
    search_fields = ("codigo", "nombre")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ReglaAPUSubsistemaInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("sistema")


# ── Legado — solo lectura ─────────────────────────────────────────────────────
# ReglaCalculo y DependenciaTecnica ya no forman parte del flujo operativo.
# Registradas aquí únicamente para consultar datos históricos si los hubiera.

@admin.register(ReglaCalculo)
class ReglaCalculoAdmin(admin.ModelAdmin):
    list_display  = ("codigo", "nombre", "subsistema", "activa")
    list_filter   = ("activa", "subsistema__sistema")
    search_fields = ("codigo", "nombre")
    readonly_fields = (
        "subsistema", "producto", "categoria_producto", "codigo", "nombre",
        "variable_entrada", "coeficiente", "divisor", "factor_desperdicio",
        "formula_texto", "formula_python", "tipo_regla", "orden_ejecucion",
        "variable_salida", "activa", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DependenciaTecnica)
class DependenciaTecnicaAdmin(admin.ModelAdmin):
    list_display  = ("subsistema", "nombre", "categoria_producto", "obligatoria")
    list_filter   = ("obligatoria",)
    readonly_fields = (
        "subsistema", "producto_origen", "producto_dependiente",
        "categoria_producto", "nombre", "obligatoria", "orden",
        "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
