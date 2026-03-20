"""apps/catalogos/views.py — Vistas CRUD para catálogos maestros."""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView,
)
from .models import UnidadMedida, CategoriaProducto, Producto, Proveedor, ProductoProveedor
from .forms import (
    UnidadMedidaForm, CategoriaProductoForm, ProductoForm,
    ProveedorForm, ProductoProveedorForm,
)
from apps.common.mixins import WithCreateFormMixin

_MAESTROS_URL = reverse_lazy("catalogos:maestros")


# ── Vista combinada: Unidades + Categorías ──────────────────────────────────

class MaestrosView(TemplateView):
    """
    Página única con los dos catálogos base:
      · Unidades de medida
      · Categorías de producto
    Ambos con modales de creación integrados.
    """
    template_name = "catalogos/maestros.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["unidades"]       = UnidadMedida.objects.all().order_by("codigo")
        ctx["categorias"]     = CategoriaProducto.objects.all().order_by("codigo")
        ctx["unidad_form"]    = UnidadMedidaForm()
        ctx["categoria_form"] = CategoriaProductoForm()
        return ctx


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
    success_url = _MAESTROS_URL


class UnidadUpdateView(UpdateView):
    model = UnidadMedida
    form_class = UnidadMedidaForm
    template_name = "catalogos/unidad_form.html"
    success_url = _MAESTROS_URL


class UnidadDeleteView(DeleteView):
    model = UnidadMedida
    template_name = "catalogos/confirm_delete.html"
    success_url = _MAESTROS_URL


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
    success_url = _MAESTROS_URL


class CategoriaUpdateView(UpdateView):
    model = CategoriaProducto
    form_class = CategoriaProductoForm
    template_name = "catalogos/categoria_form.html"
    success_url = _MAESTROS_URL


class CategoriaDeleteView(DeleteView):
    model = CategoriaProducto
    template_name = "catalogos/confirm_delete.html"
    success_url = _MAESTROS_URL


# ── Productos ───────────────────────────────────────────────────────────────

def _sincronizar_producto_proveedor(producto, proveedor, precio):
    """
    Mantiene la tabla ProductoProveedor sincronizada con el precio directo
    del Producto. Esta tabla la usa DespieceService.capturar_precio().
    Si el proveedor cambia, desactiva el registro anterior.
    """
    # Desactivar registros de otros proveedores
    ProductoProveedor.objects.filter(producto=producto).exclude(proveedor=proveedor).update(activo=False)
    # Upsert del proveedor activo
    ProductoProveedor.objects.update_or_create(
        producto=producto,
        proveedor=proveedor,
        defaults={
            "precio_unitario": precio,
            "activo": producto.activo,
        },
    )


class ProductoListView(WithCreateFormMixin, ListView):
    model = Producto
    form_class = ProductoForm
    template_name = "catalogos/producto_list.html"
    context_object_name = "productos"
    ordering = ["codigo"]

    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related("categoria", "unidad", "proveedor")
        )


class ProductoDetailView(DetailView):
    model = Producto
    template_name = "catalogos/producto_detail.html"
    context_object_name = "producto"


class ProductoCreateView(CreateView):
    model = Producto
    form_class = ProductoForm
    template_name = "catalogos/producto_form.html"
    success_url = reverse_lazy("catalogos:producto_list")

    def form_valid(self, form):
        producto = form.save(commit=False)
        # Auto-generar código si no fue provisto
        if not producto.codigo and producto.categoria_id:
            producto.codigo = Producto.generar_codigo(producto.categoria)
        producto.save()

        # Sincronizar precio con ProductoProveedor (para DespieceService)
        proveedor = form.cleaned_data.get("proveedor")
        precio    = form.cleaned_data.get("precio_actual")
        if proveedor and precio:
            _sincronizar_producto_proveedor(producto, proveedor, precio)

        return HttpResponseRedirect(self.get_success_url())


class ProductoUpdateView(UpdateView):
    model = Producto
    form_class = ProductoForm
    template_name = "catalogos/producto_form.html"
    success_url = reverse_lazy("catalogos:producto_list")

    def form_valid(self, form):
        producto = form.save()

        # Sincronizar precio con ProductoProveedor (para DespieceService)
        proveedor = form.cleaned_data.get("proveedor")
        precio    = form.cleaned_data.get("precio_actual")
        if proveedor and precio:
            _sincronizar_producto_proveedor(producto, proveedor, precio)

        return HttpResponseRedirect(self.get_success_url())


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


# ── Precios (eliminados de la UI — redirigen a producto_list) ────────────────
# ProductoProveedor sigue existiendo como tabla técnica interna.
# Los precios se gestionan desde el formulario de Producto.

class PrecioListView(ListView):
    """Redirige permanentemente al listado de productos."""
    model = ProductoProveedor
    template_name = "catalogos/precio_list.html"
    context_object_name = "precios"
    ordering = ["producto__codigo"]

    def get(self, request, *args, **kwargs):
        messages.info(request, "Los precios ahora se gestionan directamente en el catálogo de Productos.")
        return redirect("catalogos:producto_list")


class PrecioCreateView(CreateView):
    model = ProductoProveedor
    form_class = ProductoProveedorForm
    template_name = "catalogos/precio_form.html"
    success_url = reverse_lazy("catalogos:producto_list")

    def get(self, request, *args, **kwargs):
        return redirect("catalogos:producto_list")


class PrecioUpdateView(UpdateView):
    model = ProductoProveedor
    form_class = ProductoProveedorForm
    template_name = "catalogos/precio_form.html"
    success_url = reverse_lazy("catalogos:producto_list")

    def get(self, request, *args, **kwargs):
        return redirect("catalogos:producto_list")


class PrecioDeleteView(DeleteView):
    model = ProductoProveedor
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:producto_list")
