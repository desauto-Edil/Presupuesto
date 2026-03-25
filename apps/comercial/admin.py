from django.contrib import admin
from .models import (
    Cliente, ContactoCliente, TipoProyecto, Solicitud,
    Proyecto, ProyectoArchivo, LogSistema,
)


class ContactoClienteInline(admin.TabularInline):
    model = ContactoCliente
    extra = 1
    fields = ("nombre", "cargo", "email", "telefono", "es_principal", "activo")


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nit", "razon_social", "activo")
    list_filter = ("activo",)
    search_fields = ("nit", "razon_social")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ContactoClienteInline]


@admin.register(TipoProyecto)
class TipoProyectoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "activo")
    list_filter = ("activo",)


@admin.register(Solicitud)
class SolicitudAdmin(admin.ModelAdmin):
    list_display = ("consecutivo", "cliente", "nombre", "estado", "creado_por", "created_at")
    list_filter = ("estado",)
    search_fields = ("consecutivo", "nombre", "cliente__razon_social")

    # consecutivo es ahora editable (ingresado por el usuario desde Selford)
    readonly_fields = ("estado", "creado_por", "created_at", "updated_at")

    fieldsets = (
        ("Datos de Selford", {
            "fields": ("consecutivo", "link_selford"),
            "description": "Consecutivo y link provienen del sistema Selford.",
        }),
        ("Datos de la solicitud", {
            "fields": ("cliente", "contacto", "nombre", "descripcion", "fecha_entrega", "observaciones"),
        }),
        ("Sistema (solo lectura)", {
            "fields": ("estado", "creado_por", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


class ProyectoArchivoInline(admin.TabularInline):
    model = ProyectoArchivo
    extra = 0
    fields = ("nombre", "archivo", "usuario", "fecha_subida")
    readonly_fields = ("fecha_subida",)


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = (
        "consecutivo", "version", "es_version_actual",
        "cliente", "nombre", "estado", "creado_por", "created_at",
    )
    list_filter = ("estado", "tipo_proyecto", "es_version_actual")
    search_fields = ("consecutivo", "nombre", "cliente__razon_social")
    readonly_fields = (
        "consecutivo", "estado", "creado_por", "version",
        "es_version_actual", "fecha_proyecto", "created_at", "updated_at",
    )
    inlines = [ProyectoArchivoInline]

    fieldsets = (
        ("Sistema (solo lectura)", {
            "fields": (
                "consecutivo", "version", "es_version_actual",
                "estado", "creado_por", "fecha_proyecto", "created_at", "updated_at",
            ),
            "description": "Campos controlados exclusivamente por el sistema.",
        }),
        ("Datos del proyecto", {
            "fields": (
                "solicitud", "cliente", "tipo_proyecto",
                "nombre", "descripcion", "area_total_m2", "perimetro_ml",
            ),
        }),
        ("Variables financieras", {
            "fields": ("trm", "margen_comercial_pct", "iva_pct", "aiu_pct", "moneda", "aplica_exencion_iva"),
        }),
        ("Observaciones", {
            "fields": ("observaciones", "motivo_devolucion"),
        }),
    )


@admin.register(ProyectoArchivo)
class ProyectoArchivoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "proyecto", "usuario", "fecha_subida")
    list_filter = ("fecha_subida",)
    search_fields = ("nombre", "proyecto__consecutivo")
    readonly_fields = ("fecha_subida",)


@admin.register(LogSistema)
class LogSistemaAdmin(admin.ModelAdmin):
    list_display = ("created_at", "unidad_negocio", "accion", "usuario", "modelo_afectado", "objeto_id")
    list_filter = ("unidad_negocio", "accion", "modelo_afectado")
    search_fields = ("accion", "descripcion", "usuario__nombre_completo")
    readonly_fields = ("created_at", "unidad_negocio", "usuario", "accion", "descripcion", "modelo_afectado", "objeto_id")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
