"""
admin.py — Configuración del panel Django Admin para el sistema de presupuestos.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    UsuarioSistema, Cliente, ContactoCliente,
    Solicitud, TipoProyecto, Proyecto,
    Sistema, Subsistema, ProyectoSistema,
    UnidadMedida, CategoriaProducto, Producto,
    Proveedor, ProductoProveedor,
    ReglaCalculo, DependenciaTecnica,
    DespieceLinea,
    ConfiguracionAPU, APUProyecto, APULinea,
)


# ---------------------------------------------------------------------------
# INLINES
# ---------------------------------------------------------------------------

class ContactoClienteInline(admin.TabularInline):
    model = ContactoCliente
    extra = 1
    fields = ("nombre", "cargo", "email", "telefono", "es_principal", "activo")


class ProductoProveedorInline(admin.TabularInline):
    model = ProductoProveedor
    extra = 0
    fields = ("proveedor", "precio_unitario", "moneda", "activo")


class DependenciaTecnicaInline(admin.TabularInline):
    model = DependenciaTecnica
    extra = 0
    fields = ("producto_origen", "producto_dependiente", "obligatoria", "tipo_regla", "orden")


class ReglaCalculoInline(admin.TabularInline):
    model = ReglaCalculo
    extra = 0
    fields = ("codigo", "nombre", "producto", "variable_entrada", "coeficiente", "divisor",
              "factor_desperdicio", "formula_texto", "tipo_regla", "orden_ejecucion", "activa")


class DespieceLineaInline(admin.TabularInline):
    model = DespieceLinea
    extra = 0
    readonly_fields = ("cantidad_calculada", "precio_snapshot", "es_dependencia_automatica")
    fields = ("proyecto_sistema", "producto", "cantidad_calculada", "cantidad_ajustada",
              "precio_snapshot", "es_dependencia_automatica", "motivo_ajuste")


class APULineaInline(admin.TabularInline):
    model = APULinea
    extra = 0
    readonly_fields = ("costo_unitario", "costo_total", "valor_unitario", "valor_total")
    fields = ("tipo", "descripcion", "rendimiento", "precio_referencia",
              "iva_aplicado", "costo_unitario", "costo_total", "valor_unitario", "valor_total", "editable")


# ---------------------------------------------------------------------------
# USUARIOS
# ---------------------------------------------------------------------------

@admin.register(UsuarioSistema)
class UsuarioSistemaAdmin(admin.ModelAdmin):
    list_display  = ("nombre_completo", "email", "rol", "activo")
    list_filter   = ("rol", "activo")
    search_fields = ("nombre_completo", "email")


# ---------------------------------------------------------------------------
# CLIENTES
# ---------------------------------------------------------------------------

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display  = ("razon_social", "nit", "ciudad", "telefono_principal", "activo")
    list_filter   = ("activo", "ciudad")
    search_fields = ("razon_social", "nit")
    inlines       = [ContactoClienteInline]


@admin.register(ContactoCliente)
class ContactoClienteAdmin(admin.ModelAdmin):
    list_display  = ("nombre", "cliente", "cargo", "email", "es_principal")
    list_filter   = ("es_principal", "activo")
    search_fields = ("nombre", "cliente__razon_social")


# ---------------------------------------------------------------------------
# SOLICITUDES
# ---------------------------------------------------------------------------

@admin.register(Solicitud)
class SolicitudAdmin(admin.ModelAdmin):
    list_display   = ("consecutivo", "nombre", "cliente", "creado_por", "estado", "fecha_entrega")
    list_filter    = ("estado",)
    search_fields  = ("consecutivo", "nombre", "cliente__razon_social")
    readonly_fields = ("consecutivo", "created_at", "updated_at")
    raw_id_fields  = ("cliente", "contacto", "creado_por")

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.consecutivo:
            obj.consecutivo = Solicitud.siguiente_consecutivo()
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# PROYECTOS
# ---------------------------------------------------------------------------

@admin.register(TipoProyecto)
class TipoProyectoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "activo")


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display   = ("consecutivo", "nombre", "cliente", "tipo_proyecto", "estado",
                      "area_total_m2", "moneda", "trm")
    list_filter    = ("estado", "moneda", "tipo_proyecto")
    search_fields  = ("consecutivo", "nombre", "cliente__razon_social")
    readonly_fields = ("consecutivo", "fecha_proyecto", "created_at", "updated_at")
    raw_id_fields  = ("solicitud", "cliente", "creado_por")
    fieldsets = (
        ("Identificación", {
            "fields": ("consecutivo", "solicitud", "cliente", "creado_por", "tipo_proyecto",
                       "nombre", "descripcion", "estado")
        }),
        ("Métricas físicas", {
            "fields": ("area_total_m2", "perimetro_ml")
        }),
        ("Variables financieras", {
            "fields": ("trm", "margen_comercial_pct", "iva_pct", "aiu_pct",
                       "moneda", "aplica_exencion_iva")
        }),
        ("Seguimiento", {
            "fields": ("observaciones", "fecha_proyecto", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    inlines = [DespieceLineaInline]

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.consecutivo:
            obj.consecutivo = Proyecto.siguiente_consecutivo()
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# SISTEMAS / SUBSISTEMAS
# ---------------------------------------------------------------------------

@admin.register(Sistema)
class SistemaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "linea_negocio", "activo")
    list_filter  = ("linea_negocio", "activo")


@admin.register(Subsistema)
class SubsistemaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "sistema", "activo")
    list_filter  = ("sistema", "activo")
    inlines      = [ReglaCalculoInline, DependenciaTecnicaInline]


@admin.register(ProyectoSistema)
class ProyectoSistemaAdmin(admin.ModelAdmin):
    list_display  = ("proyecto", "sistema", "subsistema", "total_powergip", "cuadrilla_personas")
    raw_id_fields = ("proyecto",)
    readonly_fields = ("created_at", "updated_at")


# ---------------------------------------------------------------------------
# CATÁLOGO
# ---------------------------------------------------------------------------

@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "abreviatura")


@admin.register(CategoriaProducto)
class CategoriaProductoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "activa")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display   = ("codigo", "nombre", "categoria", "unidad", "origen", "activo")
    list_filter    = ("categoria", "origen", "activo")
    search_fields  = ("codigo", "nombre")
    inlines        = [ProductoProveedorInline]


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display  = ("nombre", "nit", "ciudad", "email", "activo")
    search_fields = ("nombre", "nit")


@admin.register(ProductoProveedor)
class ProductoProveedorAdmin(admin.ModelAdmin):
    list_display  = ("producto", "proveedor", "precio_unitario", "moneda", "activo")
    list_filter   = ("moneda", "activo")
    search_fields = ("producto__nombre", "proveedor__nombre")


# ---------------------------------------------------------------------------
# REGLAS Y DEPENDENCIAS
# ---------------------------------------------------------------------------

@admin.register(ReglaCalculo)
class ReglaCalculoAdmin(admin.ModelAdmin):
    list_display   = ("codigo", "nombre", "subsistema", "producto", "tipo_regla",
                      "orden_ejecucion", "activa", "version")
    list_filter    = ("tipo_regla", "activa", "subsistema")
    search_fields  = ("codigo", "nombre", "producto__nombre")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Identificación", {
            "fields": ("subsistema", "producto", "codigo", "nombre", "version", "activa")
        }),
        ("Parámetros de cálculo", {
            "fields": ("variable_entrada", "coeficiente", "divisor", "factor_desperdicio",
                       "formula_texto", "formula_python", "tipo_regla", "orden_ejecucion")
        }),
        ("Configuración", {
            "fields": ("editable_por_proyecto", "caso_prueba", "creada_por")
        }),
    )


@admin.register(DependenciaTecnica)
class DependenciaTecnicaAdmin(admin.ModelAdmin):
    list_display  = ("subsistema", "producto_origen", "producto_dependiente", "obligatoria", "tipo_regla")
    list_filter   = ("obligatoria", "tipo_regla", "subsistema")
    search_fields = ("producto_dependiente__nombre",)


# ---------------------------------------------------------------------------
# DESPIECE
# ---------------------------------------------------------------------------

@admin.register(DespieceLinea)
class DespieceLineaAdmin(admin.ModelAdmin):
    list_display   = ("proyecto", "producto", "cantidad_calculada", "cantidad_ajustada",
                      "precio_snapshot", "es_dependencia_automatica")
    list_filter    = ("es_dependencia_automatica",)
    search_fields  = ("proyecto__consecutivo", "producto__nombre")
    readonly_fields = ("cantidad_calculada", "precio_snapshot", "created_at")


# ---------------------------------------------------------------------------
# APU
# ---------------------------------------------------------------------------

@admin.register(ConfiguracionAPU)
class ConfiguracionAPUAdmin(admin.ModelAdmin):
    list_display = ("nombre", "porcentaje_ganancia", "aiu_contratista",
                    "margen_ganancia_contratista", "activa")


@admin.register(APUProyecto)
class APUProyectoAdmin(admin.ModelAdmin):
    list_display   = ("proyecto_sistema", "total_costo", "total_valor_venta",
                      "factor_venta_pct", "iva_pct", "aplica_iva")
    readonly_fields = ("subtotal_materiales", "subtotal_herramientas", "subtotal_transporte",
                       "subtotal_mano_obra", "subtotal_administracion",
                       "total_costo", "total_valor_venta",
                       "dias_trabajo", "tiempo_estimado_meses", "rendimiento_und_dia",
                       "created_at", "updated_at")
    inlines        = [APULineaInline]


@admin.register(APULinea)
class APULineaAdmin(admin.ModelAdmin):
    list_display   = ("apu", "tipo", "descripcion", "rendimiento",
                      "precio_referencia", "costo_total", "valor_total")
    list_filter    = ("tipo",)
    readonly_fields = ("costo_unitario", "costo_total", "valor_unitario", "valor_total")
