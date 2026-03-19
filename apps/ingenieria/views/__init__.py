"""apps/ingenieria/views — Vistas CRUD para catálogo de ingeniería.

Solo Sistema y Subsistema tienen vistas operativas.
Reglas y Dependencias ya no tienen CRUD en la interfaz —
las recetas técnicas se definen en apps/ingenieria/system_defs/.
"""

from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from apps.ingenieria.models import Sistema, Subsistema
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

        # Mostrar definición backend si existe
        from apps.ingenieria.system_defs.registry import get_subsistema_def
        sub_def = get_subsistema_def(
            self.object.sistema.codigo,
            self.object.codigo,
        )
        ctx["sub_def"] = sub_def
        return ctx


class SubsistemaCreateView(CreateView):
    model = Subsistema
    form_class = SubsistemaForm
    template_name = "ingenieria/subsistema_form.html"
    success_url = reverse_lazy("ingenieria:subsistema_list")


class SubsistemaUpdateView(UpdateView):
    model = Subsistema
    form_class = SubsistemaForm
    template_name = "ingenieria/subsistema_form.html"
    success_url = reverse_lazy("ingenieria:subsistema_list")


class SubsistemaDeleteView(DeleteView):
    model = Subsistema
    template_name = "ingenieria/confirm_delete.html"
    success_url = reverse_lazy("ingenieria:subsistema_list")
