"""apps/ingenieria/views — Vistas CRUD para ingeniería."""

from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from apps.ingenieria.models import Sistema, Subsistema, ReglaCalculo, DependenciaTecnica
from apps.ingenieria.forms import SistemaForm, SubsistemaForm, ReglaCalculoForm, DependenciaTecnicaForm


# ── Sistemas ─────────────────────────────────────────────────────────────────

class SistemaListView(ListView):
    model = Sistema
    template_name = "ingenieria/sistema_list.html"
    context_object_name = "sistemas"
    ordering = ["codigo"]


class SistemaDetailView(DetailView):
    model = Sistema
    template_name = "ingenieria/sistema_detail.html"
    context_object_name = "sistema"


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

class SubsistemaListView(ListView):
    model = Subsistema
    template_name = "ingenieria/subsistema_list.html"
    context_object_name = "subsistemas"
    ordering = ["sistema__codigo", "codigo"]


class SubsistemaDetailView(DetailView):
    model = Subsistema
    template_name = "ingenieria/subsistema_detail.html"
    context_object_name = "subsistema"


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


# ── Reglas de cálculo ─────────────────────────────────────────────────────────

class ReglaListView(ListView):
    model = ReglaCalculo
    template_name = "ingenieria/regla_list.html"
    context_object_name = "reglas"
    ordering = ["subsistema__codigo", "orden_ejecucion"]


class ReglaDetailView(DetailView):
    model = ReglaCalculo
    template_name = "ingenieria/regla_detail.html"
    context_object_name = "regla"


class ReglaCreateView(CreateView):
    model = ReglaCalculo
    form_class = ReglaCalculoForm
    template_name = "ingenieria/regla_form.html"
    success_url = reverse_lazy("ingenieria:regla_list")


class ReglaUpdateView(UpdateView):
    model = ReglaCalculo
    form_class = ReglaCalculoForm
    template_name = "ingenieria/regla_form.html"
    success_url = reverse_lazy("ingenieria:regla_list")


class ReglaDeleteView(DeleteView):
    model = ReglaCalculo
    template_name = "ingenieria/confirm_delete.html"
    success_url = reverse_lazy("ingenieria:regla_list")


# ── Dependencias técnicas ──────────────────────────────────────────────────────

class DependenciaListView(ListView):
    model = DependenciaTecnica
    template_name = "ingenieria/dependencia_list.html"
    context_object_name = "dependencias"
    ordering = ["subsistema__codigo", "orden"]


class DependenciaCreateView(CreateView):
    model = DependenciaTecnica
    form_class = DependenciaTecnicaForm
    template_name = "ingenieria/dependencia_form.html"
    success_url = reverse_lazy("ingenieria:dependencia_list")


class DependenciaUpdateView(UpdateView):
    model = DependenciaTecnica
    form_class = DependenciaTecnicaForm
    template_name = "ingenieria/dependencia_form.html"
    success_url = reverse_lazy("ingenieria:dependencia_list")


class DependenciaDeleteView(DeleteView):
    model = DependenciaTecnica
    template_name = "ingenieria/confirm_delete.html"
    success_url = reverse_lazy("ingenieria:dependencia_list")
