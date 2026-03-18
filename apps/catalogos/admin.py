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


class ProductoProveedorInline(admin.TabularInline):
    model = ProductoProveedor
    extra = 1
    fields = ("proveedor", "precio_unitario", "moneda", "activo")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "categoria", "unidad", "origen", "activo")
    list_filter = ("categoria", "origen", "activo")
    search_fields = ("codigo", "nombre", "marca")
    readonly_fields = ("codigo", "created_at", "updated_at")
    inlines = [ProductoProveedorInline]


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nit", "nombre", "ciudad", "activo")
    list_filter = ("activo",)
    search_fields = ("nit", "nombre")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProductoProveedor)
class ProductoProveedorAdmin(admin.ModelAdmin):
    list_display = ("producto", "proveedor", "precio_unitario", "moneda", "activo")
    list_filter = ("moneda", "activo")
    readonly_fields = ("created_at", "updated_at")
