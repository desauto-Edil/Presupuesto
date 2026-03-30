"""apps/catalogos/views.py — Vistas CRUD para catálogos maestros."""

from django.contrib import messages
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, DetailView, RedirectView
)
from django.urls import reverse_lazy
from django.db.models import Count, Prefetch

from .models import CategoriaProducto, Producto, UnidadMedida, ProductoProveedor, Proveedor
from .forms  import CategoriaForm, ProductoForm, UnidadMedidaForm, ProveedorForm


# ─────────────────────────────────────────────────────────────────
# VISTA PRINCIPAL UNIFICADA  →  /catalogos/
# ─────────────────────────────────────────────────────────────────
class CatalogoView(ListView):
    """
    Muestra en una sola pantalla:
      - Unidades de medida (panel colapsable)
      - Categorías como cards con sus productos anidados
    """
    template_name = "catalogos/catalogos.html"
    context_object_name = "categorias"

    def get_queryset(self):
        return (
            CategoriaProducto.objects
            .prefetch_related(
                Prefetch(
                    "productos",
                    queryset=Producto.objects
                        .select_related("proveedor", "unidad")
                        .filter(activo=True)
                        .order_by("nombre"),
                )
            )
            .annotate(cantidad_productos=Count("productos"))
            .order_by("nombre")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs  = self.get_queryset()

        ctx["unidades"] = UnidadMedida.objects.order_by("nombre")
        ctx["total_categorias"] = qs.count()
        ctx["categorias_activas"]= qs.filter(activa=True).count()
        ctx["total_productos"] = Producto.objects.filter(activo=True).count()

        # Formularios para los modales de creación
        ctx["modal_categoria_form"] = CategoriaForm()
        ctx["modal_producto_form"] = ProductoForm()
        ctx["modal_unidad_form"] = UnidadMedidaForm()

        return ctx


# Alias de compatibilidad
class MaestrosView(RedirectView):
    permanent = False
    pattern_name = "catalogos:catalogo"


# ─────────────────────────────────────────────────────────────────
# CATEGORÍAS
# ─────────────────────────────────────────────────────────────────
class CategoriaCreateView(CreateView):
    model = CategoriaProducto
    form_class = CategoriaForm
    template_name = "catalogos/categoria_form.html"
    success_url = reverse_lazy("catalogos:catalogo")

    def form_valid(self, form):
        messages.success(self.request, "Categoría creada correctamente.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Corrige los errores del formulario.")
        return super().form_invalid(form)


class CategoriaUpdateView(UpdateView):
    model = CategoriaProducto
    form_class = CategoriaForm
    template_name = "catalogos/categoria_form.html"
    success_url = reverse_lazy("catalogos:catalogo")

    def form_valid(self, form):
        messages.success(self.request, "Categoría actualizada correctamente.")
        return super().form_valid(form)


class CategoriaDeleteView(DeleteView):
    model = CategoriaProducto
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:catalogo")


# ─────────────────────────────────────────────────────────────────
# PRODUCTOS
# ─────────────────────────────────────────────────────────────────
class ProductoListView(ListView):
    """
    Vista de tabla filtrable por categoría
    (accesible desde botón 'Ver todos' dentro de una tarjeta)
    """
    model = Producto
    template_name = "catalogos/producto_list.html"
    context_object_name = "productos"

    def get_queryset(self):
        qs = Producto.objects.select_related("categoria", "proveedor", "unidad")
        cat_pk = self.request.GET.get("categoria")
        if cat_pk:
            qs = qs.filter(categoria__pk=cat_pk)
        return qs.order_by("categoria__nombre", "nombre")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["create_form"] = ProductoForm()
        return ctx


class ProductoCreateView(CreateView):
    model = Producto
    form_class = ProductoForm
    template_name = "catalogos/producto_form.html"
    success_url = reverse_lazy("catalogos:producto_list")

    def get_initial(self):
        initial = super().get_initial()
        cat_pk = self.request.GET.get("categoria")
        if cat_pk:
            initial["categoria"] = cat_pk
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        ProductoProveedor.objects.update_or_create(
            producto=self.object,
            proveedor=self.object.proveedor,
            defaults={
                "precio_unitario": self.object.precio_actual,
                "moneda": self.object.moneda,
                "activo": True,
            }
        )
        messages.success(self.request, "Producto y precio registrados correctamente.")
        return response


class ProductoUpdateView(UpdateView):
    model = Producto
    form_class = ProductoForm
    template_name = "catalogos/producto_form.html"
    success_url = reverse_lazy("catalogos:catalogo")

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.object.proveedor:
            ProductoProveedor.objects.update_or_create(
                producto=self.object,
                proveedor=self.object.proveedor,
                defaults={
                    "precio_unitario": self.object.precio_actual,
                    "moneda": self.object.moneda,
                    "activo": True,
                }
            )
        messages.success(self.request, "Producto actualizado correctamente.")
        return response


class ProductoDeleteView(DeleteView):
    model = Producto
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:catalogo")


class ProductoDetailView(DetailView):
    model = Producto
    template_name = "catalogos/producto_detail.html"
    context_object_name = "producto"


# ─────────────────────────────────────────────────────────────────
# UNIDADES DE MEDIDA
# ─────────────────────────────────────────────────────────────────
class UnidadCreateView(CreateView):
    model = UnidadMedida
    form_class = UnidadMedidaForm
    template_name = "catalogos/unidad_form.html"
    success_url = reverse_lazy("catalogos:catalogo")


class UnidadUpdateView(UpdateView):
    model = UnidadMedida
    form_class = UnidadMedidaForm
    template_name = "catalogos/unidad_form.html"
    success_url = reverse_lazy("catalogos:catalogo")


class UnidadDeleteView(DeleteView):
    model = UnidadMedida
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:catalogo")


# ─────────────────────────────────────────────────────────────────
# PROVEEDORES
# ─────────────────────────────────────────────────────────────────
class ProveedorListView(ListView):
    model = Proveedor
    template_name = "catalogos/proveedor_list.html"
    context_object_name = "proveedores"
    ordering = ["nombre"]


class ProveedorCreateView(CreateView):
    model = Proveedor
    template_name = "catalogos/proveedor_form.html"
    fields = "__all__"
    success_url = reverse_lazy("catalogos:proveedor_list")


class ProveedorUpdateView(UpdateView):
    model = Proveedor
    template_name = "catalogos/proveedor_form.html"
    fields = "__all__"
    success_url = reverse_lazy("catalogos:proveedor_list")


class ProveedorDeleteView(DeleteView):
    model = Proveedor
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:proveedor_list")


# ─────────────────────────────────────────────────────────────────
# PRODUCTOS × PROVEEDOR (precios)
# ─────────────────────────────────────────────────────────────────
class PrecioListView(RedirectView):
    permanent = False
    pattern_name = "catalogos:producto_list"


class ProductoProveedorListView(ListView):
    model = ProductoProveedor
    template_name = "catalogos/productoproveedor_list.html"
    context_object_name = "productos_proveedor"
    ordering = ["producto__nombre"]


class ProductoProveedorCreateView(CreateView):
    model = ProductoProveedor
    template_name = "catalogos/productoproveedor_form.html"
    fields = "__all__"
    success_url = reverse_lazy("catalogos:productoproveedor_list")


class ProductoProveedorUpdateView(UpdateView):
    model = ProductoProveedor
    template_name = "catalogos/productoproveedor_form.html"
    fields = "__all__"
    success_url = reverse_lazy("catalogos:productoproveedor_list")


class ProductoProveedorDeleteView(DeleteView):
    model = ProductoProveedor
    template_name = "catalogos/confirm_delete.html"
    success_url = reverse_lazy("catalogos:productoproveedor_list")
