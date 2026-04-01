"""apps/ingenieria/views — Vistas CRUD para catálogo de ingeniería.

Solo Sistema y Subsistema tienen vistas operativas.
Reglas y Dependencias ya no tienen CRUD en la interfaz —
las recetas técnicas se definen en apps/ingenieria/system_defs/.
"""

from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from apps.ingenieria.models import Sistema, Subsistema, ComponenteSubsistema, VariableSubsistema
from apps.ingenieria.forms import SistemaForm, SubsistemaForm
from apps.common.mixins import WithCreateFormMixin


# ── Sistemas ──────────────────────────────────────────────────────────────────

class SistemaListView(WithCreateFormMixin, ListView):
    model = Sistema
    form_class = SistemaForm
    template_name = "ingenieria/sistema_list.html"
    context_object_name = "sistemas"
    ordering = ["codigo"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["subsistemas"] = (
            Subsistema.objects
            .select_related("sistema")
            .order_by("sistema__codigo", "codigo")
        )
        ctx["create_subsistema_form"] = SubsistemaForm()
        return ctx


class SistemaDetailView(DetailView):
    model = Sistema
    template_name = "ingenieria/sistema_detail.html"
    context_object_name = "sistema"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["subsistemas"] = self.object.subsistemas.filter(activo=True).order_by("codigo")

        # Mostrar definición backend si existe
        from apps.ingenieria.system_defs.registry import get_sistema_def, sistema_tiene_def
        ctx["tiene_def_backend"] = sistema_tiene_def(self.object.codigo)
        ctx["subsistemas_def"] = get_sistema_def(self.object.codigo)
        return ctx


class SistemaCreateView(CreateView):
    model = Sistema
    form_class = SistemaForm
    template_name = "ingenieria/sistema_form.html"
    success_url = reverse_lazy("ingenieria:sistema_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        # Crear subsistemas inline si se enviaron
        codigos  = self.request.POST.getlist("sub_codigo[]")
        nombres  = self.request.POST.getlist("sub_nombre[]")
        descrips = self.request.POST.getlist("sub_descripcion[]")
        for codigo, nombre, descripcion in zip(codigos, nombres, descrips):
            codigo  = codigo.strip()
            nombre  = nombre.strip()
            if codigo and nombre:
                Subsistema.objects.get_or_create(
                    sistema=self.object,
                    codigo=codigo,
                    defaults={"nombre": nombre, "descripcion": descripcion.strip(), "activo": True},
                )
        return response


class SistemaUpdateView(UpdateView):
    model = Sistema
    form_class = SistemaForm
    template_name = "ingenieria/sistema_form.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


class SistemaDeleteView(DeleteView):
    model = Sistema
    template_name = "ingenieria/confirm_delete.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


# ── Subsistemas ───────────────────────────────────────────────────────────────

class SubsistemaListView(WithCreateFormMixin, ListView):
    model = Subsistema
    form_class = SubsistemaForm
    template_name = "ingenieria/subsistema_list.html"
    context_object_name = "subsistemas"
    ordering = ["sistema__codigo", "codigo"]


class SubsistemaDetailView(DetailView):
    model = Subsistema
    template_name = "ingenieria/subsistema_detail.html"
    context_object_name = "subsistema"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # DB componentes y variables (prioridad)
        ctx["componentes_db"] = list(
            ComponenteSubsistema.objects.filter(subsistema=self.object)
            .select_related("categoria")
            .order_by("orden")
        )
        ctx["variables_db"] = list(
            VariableSubsistema.objects.filter(subsistema=self.object).order_by("orden")
        )

        # Registro Python (fallback / comparación)
        from apps.ingenieria.system_defs.registry import get_subsistema_def
        ctx["sub_def"] = get_subsistema_def(self.object.sistema.codigo, self.object.codigo)
        return ctx


def _guardar_componentes_variables(subsistema, post):
    """
    Procesa arrays de variables y componentes enviados desde el form del subsistema.
    Reemplaza todos los existentes con los nuevos valores enviados.
    """
    from apps.catalogos.models import CategoriaProducto

    # ── Variables ─────────────────────────────────────────────────────────────
    var_variables  = post.getlist("var_variable[]")
    var_labels     = post.getlist("var_label[]")
    var_unidades   = post.getlist("var_unidad[]")
    var_defaults   = post.getlist("var_default[]")

    VariableSubsistema.objects.filter(subsistema=subsistema).delete()
    for idx, (variable, label) in enumerate(zip(var_variables, var_labels)):
        variable = variable.strip()
        label    = label.strip()
        if variable and label:
            try:
                default = float(var_defaults[idx]) if idx < len(var_defaults) and var_defaults[idx].strip() else 0
            except ValueError:
                default = 0
            VariableSubsistema.objects.create(
                subsistema=subsistema,
                variable=variable,
                label=label,
                unidad=var_unidades[idx].strip() if idx < len(var_unidades) else "",
                valor_default=default,
                orden=idx + 1,
            )

    # ── Componentes ──────────────────────────────────────────────────────────
    comp_codigos     = post.getlist("comp_codigo[]")
    comp_nombres     = post.getlist("comp_nombre[]")
    comp_categorias  = post.getlist("comp_categoria[]")
    comp_formulas    = post.getlist("comp_formula[]")
    comp_v_salidas   = post.getlist("comp_variable_salida[]")
    comp_unidades    = post.getlist("comp_unidad[]")
    comp_ref_apu     = post.getlist("comp_variable_referencia_apu[]")
    comp_unidad_apu  = post.getlist("comp_unidad_apu[]")

    ComponenteSubsistema.objects.filter(subsistema=subsistema).delete()
    for idx, (codigo, nombre, formula) in enumerate(zip(comp_codigos, comp_nombres, comp_formulas)):
        codigo  = codigo.strip()
        nombre  = nombre.strip()
        formula = formula.strip()
        if codigo and nombre and formula:
            cat_pk = comp_categorias[idx].strip() if idx < len(comp_categorias) else ""
            categoria = None
            if cat_pk:
                try:
                    categoria = CategoriaProducto.objects.get(pk=int(cat_pk))
                except (CategoriaProducto.DoesNotExist, ValueError):
                    pass
            ComponenteSubsistema.objects.create(
                subsistema=subsistema,
                codigo=codigo,
                nombre=nombre,
                categoria=categoria,
                formula_texto=formula,
                variable_salida=comp_v_salidas[idx].strip() if idx < len(comp_v_salidas) else "",
                unidad=comp_unidades[idx].strip() if idx < len(comp_unidades) else "",
                variable_referencia_apu=comp_ref_apu[idx].strip() if idx < len(comp_ref_apu) else "",
                unidad_apu=comp_unidad_apu[idx].strip() if idx < len(comp_unidad_apu) else "",
                orden=idx + 1,
            )


class SubsistemaCreateView(CreateView):
    model = Subsistema
    form_class = SubsistemaForm
    template_name = "ingenieria/subsistema_form.html"
    success_url = reverse_lazy("ingenieria:sistema_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.catalogos.models import CategoriaProducto
        ctx["categorias_producto"] = CategoriaProducto.objects.filter(activa=True).order_by("nombre")
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        _guardar_componentes_variables(self.object, self.request.POST)
        return response


class SubsistemaUpdateView(UpdateView):
    model = Subsistema
    form_class = SubsistemaForm
    template_name = "ingenieria/subsistema_form.html"
    success_url = reverse_lazy("ingenieria:sistema_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.catalogos.models import CategoriaProducto
        ctx["categorias_producto"] = CategoriaProducto.objects.filter(activa=True).order_by("nombre")
        ctx["variables_existentes"] = list(
            VariableSubsistema.objects.filter(subsistema=self.object).order_by("orden").values()
        )
        ctx["componentes_existentes"] = list(
            ComponenteSubsistema.objects.filter(subsistema=self.object)
            .select_related("categoria")
            .order_by("orden")
            .values("id", "codigo", "nombre", "categoria_id", "formula_texto",
                    "variable_salida", "unidad", "variable_referencia_apu", "unidad_apu", "orden")
        )
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        _guardar_componentes_variables(self.object, self.request.POST)
        return response


class SubsistemaDeleteView(DeleteView):
    model = Subsistema
    template_name = "ingenieria/confirm_delete.html"
    success_url = reverse_lazy("ingenieria:subsistema_list")
