"""apps/catalogos/views.py — Vistas CRUD para catálogos maestros."""

from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from .models import UnidadMedida, CategoriaProducto, Producto, Proveedor, ProductoProveedor
from .forms import (
    UnidadMedidaForm, CategoriaProductoForm, ProductoForm,
    ProveedorForm, ProductoProveedorForm,
)
from apps.common.mixins import WithCreateFormMixin


# ── Unidades de medida ──────────────────────────────────────────────────────

class UnidadListView(ListView):
    model = UnidadMedida
    template_name = "catalogos/unidad_list.html"
    context_object_name = "unidades"
    ordering = ["codigo"]


class UnidadCreateView(CreateView):
    model = UnidadMedida
    form_class = UnidadMedidaForm
    template_name = "catalogos/unidad_form.html"
    success_url = reverse_lazy("catalogos:unidad_list")


class UnidadUpdateView(UpdateView):
    model = UnidadMedida
    form_class = UnidadMedidaForm
    template_name = "catalogos/unidad_form.html"
    success_url = reverse_lazy("catalogos:unidad_list")


class UnidadDeleteView(DeleteView):
    model = UnidadMedida
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:unidad_list")


# ── Categorías de producto ──────────────────────────────────────────────────

class CategoriaListView(ListView):
    model = CategoriaProducto
    template_name = "catalogos/categoria_list.html"
    context_object_name = "categorias"
    ordering = ["codigo"]


class CategoriaCreateView(CreateView):
    model = CategoriaProducto
    form_class = CategoriaProductoForm
    template_name = "catalogos/categoria_form.html"
    success_url = reverse_lazy("catalogos:categoria_list")


class CategoriaUpdateView(UpdateView):
    model = CategoriaProducto
    form_class = CategoriaProductoForm
    template_name = "catalogos/categoria_form.html"
    success_url = reverse_lazy("catalogos:categoria_list")


class CategoriaDeleteView(DeleteView):
    model = CategoriaProducto
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:categoria_list")


# ── Productos ───────────────────────────────────────────────────────────────

class ProductoListView(WithCreateFormMixin, ListView):
    model = Producto
    form_class = ProductoForm
    template_name = "catalogos/producto_list.html"
    context_object_name = "productos"
    ordering = ["codigo"]


class ProductoDetailView(DetailView):
    model = Producto
    template_name = "catalogos/producto_detail.html"
    context_object_name = "producto"


class ProductoCreateView(CreateView):
    model = Producto
    form_class = ProductoForm
    template_name = "catalogos/producto_form.html"
    success_url = reverse_lazy("catalogos:producto_list")


class ProductoUpdateView(UpdateView):
    model = Producto
    form_class = ProductoForm
    template_name = "catalogos/producto_form.html"
    success_url = reverse_lazy("catalogos:producto_list")


class ProductoDeleteView(DeleteView):
    model = Producto
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:producto_list")


# ── Proveedores ─────────────────────────────────────────────────────────────

class ProveedorListView(WithCreateFormMixin, ListView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = "catalogos/proveedor_list.html"
    context_object_name = "proveedores"
    ordering = ["nombre"]


class ProveedorDetailView(DetailView):
    model = Proveedor
    template_name = "catalogos/proveedor_detail.html"
    context_object_name = "proveedor"


class ProveedorCreateView(CreateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = "catalogos/proveedor_form.html"
    success_url = reverse_lazy("catalogos:proveedor_list")


class ProveedorUpdateView(UpdateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = "catalogos/proveedor_form.html"
    success_url = reverse_lazy("catalogos:proveedor_list")


class ProveedorDeleteView(DeleteView):
    model = Proveedor
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:proveedor_list")


# ── Precios producto-proveedor ───────────────────────────────────────────────

class PrecioListView(ListView):
    model = ProductoProveedor
    template_name = "catalogos/precio_list.html"
    context_object_name = "precios"
    ordering = ["producto__codigo", "proveedor__nombre"]


class PrecioCreateView(CreateView):
    model = ProductoProveedor
    form_class = ProductoProveedorForm
    template_name = "catalogos/precio_form.html"
    success_url = reverse_lazy("catalogos:precio_list")


class PrecioUpdateView(UpdateView):
    model = ProductoProveedor
    form_class = ProductoProveedorForm
    template_name = "catalogos/precio_form.html"
    success_url = reverse_lazy("catalogos:precio_list")


class PrecioDeleteView(DeleteView):
    model = ProductoProveedor
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:precio_list")
