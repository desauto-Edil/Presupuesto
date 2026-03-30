from django.contrib import admin
from .models import UnidadMedida, CategoriaProducto, Producto, Proveedor, ProductoProveedor


@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "abreviatura")
    search_fields = ("codigo", "nombre")


@admin.register(CategoriaProducto)
class CategoriaProductoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "activa")
    list_filter = ("activa",)
    search_fields = ("codigo", "nombre")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display  = ("codigo", "nombre", "categoria", "proveedor", "precio_actual",
                     "fecha_actualizacion_precio", "activo")
    list_filter   = ("categoria", "origen", "activo", "proveedor")
    search_fields = ("codigo", "nombre", "marca")
    ordering = ("-fecha_actualizacion_precio",)
    readonly_fields = ("codigo", "fecha_actualizacion_precio", "created_at", "updated_at")

    fieldsets = (
        ("Identificación", {
            "fields": ("codigo", "nombre", "categoria", "unidad", "origen", "activo"),
        }),
        ("Proveedor y precio", {
            "fields": ("proveedor", "precio_actual", "fecha_actualizacion_precio"),
            "description": "El precio se sincroniza automáticamente con la tabla interna de precios.",
        }),
        ("Datos técnicos", {
            "fields": ("marca", "linea", "rendimiento"),
            "classes": ("collapse",),
        }),
        ("Auditoría", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nit", "nombre", "ciudad", "activo")
    list_filter = ("activo",)
    search_fields = ("nit", "nombre")
    readonly_fields = ("created_at", "updated_at")


# ProductoProveedor: tabla técnica interna, solo visible en admin para diagnóstico
@admin.register(ProductoProveedor)
class ProductoProveedorAdmin(admin.ModelAdmin):
    list_display = ("producto", "proveedor", "precio_unitario", "moneda", "activo", "updated_at")
    list_filter = ("moneda", "activo")
    search_fields = ("producto__nombre", "proveedor__nombre")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-updated_at",)
