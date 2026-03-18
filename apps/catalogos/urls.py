"""apps/catalogos/urls.py"""

from django.urls import path
from . import views

app_name = "catalogos"

urlpatterns = [
    # Unidades de medida
    path("unidades/", views.UnidadListView.as_view(), name="unidad_list"),
    path("unidades/nueva/", views.UnidadCreateView.as_view(), name="unidad_create"),
    path("unidades/<int:pk>/editar/", views.UnidadUpdateView.as_view(), name="unidad_update"),
    path("unidades/<int:pk>/eliminar/", views.UnidadDeleteView.as_view(), name="unidad_delete"),

    # Categorías
    path("categorias/", views.CategoriaListView.as_view(), name="categoria_list"),
    path("categorias/nueva/", views.CategoriaCreateView.as_view(), name="categoria_create"),
    path("categorias/<int:pk>/editar/", views.CategoriaUpdateView.as_view(), name="categoria_update"),
    path("categorias/<int:pk>/eliminar/", views.CategoriaDeleteView.as_view(), name="categoria_delete"),

    # Productos
    path("productos/", views.ProductoListView.as_view(), name="producto_list"),
    path("productos/nuevo/", views.ProductoCreateView.as_view(), name="producto_create"),
    path("productos/<int:pk>/", views.ProductoDetailView.as_view(), name="producto_detail"),
    path("productos/<int:pk>/editar/", views.ProductoUpdateView.as_view(), name="producto_update"),
    path("productos/<int:pk>/eliminar/", views.ProductoDeleteView.as_view(), name="producto_delete"),

    # Proveedores
    path("proveedores/", views.ProveedorListView.as_view(), name="proveedor_list"),
    path("proveedores/nuevo/", views.ProveedorCreateView.as_view(), name="proveedor_create"),
    path("proveedores/<int:pk>/", views.ProveedorDetailView.as_view(), name="proveedor_detail"),
    path("proveedores/<int:pk>/editar/", views.ProveedorUpdateView.as_view(), name="proveedor_update"),
    path("proveedores/<int:pk>/eliminar/", views.ProveedorDeleteView.as_view(), name="proveedor_delete"),

    # Precios producto-proveedor
    path("precios/", views.PrecioListView.as_view(), name="precio_list"),
    path("precios/nuevo/", views.PrecioCreateView.as_view(), name="precio_create"),
    path("precios/<int:pk>/editar/", views.PrecioUpdateView.as_view(), name="precio_update"),
    path("precios/<int:pk>/eliminar/", views.PrecioDeleteView.as_view(), name="precio_delete"),
]
