from django.contrib import admin
from .models import ProyectoSistema, DespieceLinea, ConfiguracionAPU, APUProyecto, APULinea


class DespieceLineaInline(admin.TabularInline):
    model = DespieceLinea
    extra = 0
    fields = ("producto", "categoria_producto", "cantidad_calculada", "cantidad_ajustada", "precio_snapshot", "pendiente_seleccion")
    readonly_fields = ("pendiente_seleccion",)


@admin.register(ProyectoSistema)
class ProyectoSistemaAdmin(admin.ModelAdmin):
    list_display = ("proyecto", "sistema", "subsistema", "parametros_entrada")
    list_filter = ("sistema",)
    inlines = [DespieceLineaInline]


@admin.register(DespieceLinea)
class DespieceLineaAdmin(admin.ModelAdmin):
    list_display = ("proyecto", "producto", "categoria_producto", "cantidad_calculada", "precio_snapshot")
    list_filter = ("es_dependencia_automatica",)
    readonly_fields = ("cantidad_final", "pendiente_seleccion", "created_at", "updated_at")


@admin.register(ConfiguracionAPU)
class ConfiguracionAPUAdmin(admin.ModelAdmin):
    list_display = ("nombre", "porcentaje_ganancia", "aiu_contratista", "activa")
    list_filter = ("activa",)
    readonly_fields = ("created_at", "updated_at")


class APULineaInline(admin.TabularInline):
    model = APULinea
    extra = 0
    fields = ("tipo", "descripcion", "rendimiento", "precio_referencia", "costo_unitario", "valor_unitario", "editable")
    readonly_fields = ("costo_unitario", "valor_unitario")


@admin.register(APUProyecto)
class APUProyectoAdmin(admin.ModelAdmin):
    list_display = ("proyecto_sistema", "total_costo", "total_valor_venta")
    readonly_fields = (
        "subtotal_materiales", "subtotal_herramientas", "subtotal_transporte",
        "subtotal_mano_obra", "subtotal_administracion",
        "total_costo", "total_valor_venta", "created_at", "updated_at",
    )
    inlines = [APULineaInline]
