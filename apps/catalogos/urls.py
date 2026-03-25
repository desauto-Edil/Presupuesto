"""apps/catalogos/urls.py"""

from django.urls import path
from . import views

app_name = "catalogos"

urlpatterns = [
    # ── VISTA PRINCIPAL (UNIFICADA) ──────────────────────────────────────────
    path("", views.CatalogoView.as_view(), name="catalogo"),

    # Redirección de compatibilidad (maestros -> catálogo)
    path("maestros/", views.MaestrosView.as_view(), name="maestros"),

    # ── CATEGORÍAS ───────────────────────────────────────────────────────────
    path("categorias/nueva/", views.CategoriaCreateView.as_view(), name="categoria_create"),
    path("categorias/<int:pk>/editar/", views.CategoriaUpdateView.as_view(), name="categoria_update"),
    path("categorias/<int:pk>/eliminar/", views.CategoriaDeleteView.as_view(), name="categoria_delete"),

    # ── PRODUCTOS ────────────────────────────────────────────────────────────
    path("productos/", views.ProductoListView.as_view(), name="producto_list"),
    path("productos/nuevo/", views.ProductoCreateView.as_view(), name="producto_create"),
    path("productos/<int:pk>/", views.ProductoDetailView.as_view(), name="producto_detail"),
    path("productos/<int:pk>/editar/", views.ProductoUpdateView.as_view(), name="producto_update"),
    path("productos/<int:pk>/eliminar/", views.ProductoDeleteView.as_view(), name="producto_delete"),

    # ── PROVEEDORES ──────────────────────────────────────────────────────────
    path("proveedores/", views.ProveedorListView.as_view(), name="proveedor_list"),
    path("proveedores/nuevo/", views.ProveedorCreateView.as_view(), name="proveedor_create"),
    path("proveedores/<int:pk>/editar/", views.ProveedorUpdateView.as_view(), name="proveedor_update"),
    path("proveedores/<int:pk>/eliminar/", views.ProveedorDeleteView.as_view(), name="proveedor_delete"),

    # ── UNIDADES DE MEDIDA ───────────────────────────────────────────────────
    path("unidades/nueva/", views.UnidadCreateView.as_view(), name="unidad_create"),
    path("unidades/<int:pk>/editar/", views.UnidadUpdateView.as_view(), name="unidad_update"),
    path("unidades/<int:pk>/eliminar/", views.UnidadDeleteView.as_view(), name="unidad_delete"),

    # ── PRECIOS (redirección a productos) ────────────────────────────────────
    path("precios/", views.PrecioListView.as_view(), name="precio_list"),

    # ── PRODUCTOS × PROVEEDOR ────────────────────────────────────────────────
    path("productoproveedor/", views.ProductoProveedorListView.as_view(), name="productoproveedor_list"),
    path("productoproveedor/nuevo/", views.ProductoProveedorCreateView.as_view(), name="productoproveedor_create"),
    path("productoproveedor/<int:pk>/editar/", views.ProductoProveedorUpdateView.as_view(), name="productoproveedor_update"),
    path("productoproveedor/<int:pk>/eliminar/", views.ProductoProveedorDeleteView.as_view(), name="productoproveedor_delete"),
]
