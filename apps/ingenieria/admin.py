from django.contrib import admin
from .models import Sistema, Subsistema, ReglaCalculo, DependenciaTecnica


class SubsistemaInline(admin.TabularInline):
    model = Subsistema
    extra = 1
    fields = ("codigo", "nombre", "activo")


class ReglaCalculoInline(admin.TabularInline):
    model = ReglaCalculo
    extra = 1
    fields = (
        "codigo", "nombre", "tipo_regla", "orden_ejecucion",
        "variable_entrada", "coeficiente", "divisor",
        "factor_desperdicio", "formula_python", "variable_salida", "activa",
    )


class DependenciaInline(admin.TabularInline):
    model = DependenciaTecnica
    extra = 1
    fields = ("nombre", "producto_dependiente", "categoria_producto", "obligatoria", "orden")


@admin.register(Sistema)
class SistemaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "linea_negocio", "activo")
    list_filter = ("linea_negocio", "activo")
    search_fields = ("codigo", "nombre")
    inlines = [SubsistemaInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(Subsistema)
class SubsistemaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "sistema", "activo")
    list_filter = ("sistema", "activo")
    search_fields = ("codigo", "nombre")
    inlines = [ReglaCalculoInline, DependenciaInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(ReglaCalculo)
class ReglaCalculoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "subsistema", "tipo_regla", "orden_ejecucion", "activa")
    list_filter = ("tipo_regla", "activa", "subsistema__sistema")
    search_fields = ("codigo", "nombre")
    readonly_fields = ("created_at", "updated_at")


@admin.register(DependenciaTecnica)
class DependenciaTecnicaAdmin(admin.ModelAdmin):
    list_display = ("subsistema", "nombre", "producto_dependiente", "categoria_producto", "obligatoria")
    list_filter = ("obligatoria", "tipo_regla")
    readonly_fields = ("created_at", "updated_at")
