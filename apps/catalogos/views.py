"""apps/catalogos/views.py — Vistas CRUD para catálogos maestros."""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, DetailView, RedirectView
)
from django.urls import reverse_lazy
from django.db.models import Count, Prefetch

from .models import CategoriaProducto, Producto, UnidadMedida, ProductoProveedor, Proveedor
from .forms  import CategoriaForm, ProductoForm, UnidadMedidaForm, ProveedorForm
from apps.common.mixins import (
    GestionCatalogoCategoriasMixin,
    GestionCatalogosProductosMixin,
    GestionCatalogoProveedoresMixin,
)


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

        # Proveedores (tab unificado)
        proveedores_qs = Proveedor.objects.order_by("nombre")
        ctx["proveedores"]          = proveedores_qs
        ctx["proveedores_activos"]  = proveedores_qs.filter(activo=True).count()
        ctx["proveedores_inactivos"]= proveedores_qs.filter(activo=False).count()

        # Formularios para los modales de creación
        ctx["modal_categoria_form"] = CategoriaForm()
        ctx["modal_producto_form"] = ProductoForm()
        ctx["modal_unidad_form"] = UnidadMedidaForm()
        ctx["modal_proveedor_form"] = ProveedorForm(initial={"activo": True})

        return ctx


# Alias de compatibilidad
class MaestrosView(RedirectView):
    permanent = False
    pattern_name = "catalogos:catalogo"


# ─────────────────────────────────────────────────────────────────
# CATEGORÍAS
# ─────────────────────────────────────────────────────────────────
class CategoriaCreateView(GestionCatalogoCategoriasMixin, CreateView):
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


class CategoriaUpdateView(GestionCatalogoCategoriasMixin, UpdateView):
    model = CategoriaProducto
    form_class = CategoriaForm
    template_name = "catalogos/categoria_form.html"
    success_url = reverse_lazy("catalogos:catalogo")

    def form_valid(self, form):
        messages.success(self.request, "Categoría actualizada correctamente.")
        return super().form_valid(form)


class CategoriaDeleteView(GestionCatalogoCategoriasMixin, DeleteView):
    model = CategoriaProducto
    template_name = "confirm_delete.html"
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
        ctx["categorias"] = CategoriaProducto.objects.order_by("nombre")
        return ctx


class ProductoCreateView(GestionCatalogosProductosMixin, CreateView):
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
        producto = form.save(commit=False)
        if not producto.codigo:
            producto.codigo = Producto.generar_codigo(producto.categoria)
        producto.save()
        form.save_m2m()
        self.object = producto
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
        return HttpResponseRedirect(self.get_success_url())


class ProductoUpdateView(GestionCatalogosProductosMixin, UpdateView):
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


class ProductoDeleteView(GestionCatalogosProductosMixin, DeleteView):
    model = Producto
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("catalogos:catalogo")


class ProductoDetailView(DetailView):
    model = Producto
    template_name = "catalogos/producto_detail.html"
    context_object_name = "producto"


# ─────────────────────────────────────────────────────────────────
# UNIDADES DE MEDIDA
# ─────────────────────────────────────────────────────────────────
class UnidadCreateView(GestionCatalogoCategoriasMixin, CreateView):
    model = UnidadMedida
    form_class = UnidadMedidaForm
    template_name = "catalogos/unidad_form.html"
    success_url = reverse_lazy("catalogos:catalogo")


class UnidadUpdateView(GestionCatalogoCategoriasMixin, UpdateView):
    model = UnidadMedida
    form_class = UnidadMedidaForm
    template_name = "catalogos/unidad_form.html"
    success_url = reverse_lazy("catalogos:catalogo")


class UnidadDeleteView(GestionCatalogoCategoriasMixin, DeleteView):
    model = UnidadMedida
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("catalogos:catalogo")


# ─────────────────────────────────────────────────────────────────
# PROVEEDORES
# ─────────────────────────────────────────────────────────────────
class ProveedorListView(ListView):
    model = Proveedor
    template_name = "catalogos/proveedor_list.html"
    context_object_name = "proveedores"
    ordering = ["nombre"]


class ProveedorCreateView(GestionCatalogoProveedoresMixin, CreateView):
    model = Proveedor
    form_class = ProveedorForm
    success_url = reverse_lazy("catalogos:catalogo")


class ProveedorUpdateView(GestionCatalogoProveedoresMixin, UpdateView):
    model = Proveedor
    form_class = ProveedorForm
    success_url = reverse_lazy("catalogos:catalogo")


class ProveedorDeleteView(GestionCatalogoProveedoresMixin, DeleteView):
    model = Proveedor
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("catalogos:catalogo")


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


class ProductoProveedorCreateView(GestionCatalogosProductosMixin, CreateView):
    model = ProductoProveedor
    template_name = "catalogos/productoproveedor_form.html"
    fields = "__all__"
    success_url = reverse_lazy("catalogos:productoproveedor_list")


class ProductoProveedorUpdateView(GestionCatalogosProductosMixin, UpdateView):
    model = ProductoProveedor
    template_name = "catalogos/productoproveedor_form.html"
    fields = "__all__"
    success_url = reverse_lazy("catalogos:productoproveedor_list")


class ProductoProveedorDeleteView(GestionCatalogosProductosMixin, DeleteView):
    model = ProductoProveedor
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("catalogos:productoproveedor_list")
