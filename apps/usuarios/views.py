"""apps/usuarios/views.py — Vistas CRUD para UsuarioSistema."""

from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from .models import UsuarioSistema
from .forms import UsuarioSistemaForm


class UsuarioListView(ListView):
    model = UsuarioSistema
    template_name = "usuarios/usuario_list.html"
    context_object_name = "usuarios"
    ordering = ["nombre_completo"]


class UsuarioDetailView(DetailView):
    model = UsuarioSistema
    template_name = "usuarios/usuario_detail.html"
    context_object_name = "usuario"


class UsuarioCreateView(CreateView):
    model = UsuarioSistema
    form_class = UsuarioSistemaForm
    template_name = "usuarios/usuario_form.html"
    success_url = reverse_lazy("usuarios:usuario_list")


class UsuarioUpdateView(UpdateView):
    model = UsuarioSistema
    form_class = UsuarioSistemaForm
    template_name = "usuarios/usuario_form.html"
    success_url = reverse_lazy("usuarios:usuario_list")


class UsuarioDeleteView(DeleteView):
    model = UsuarioSistema
    template_name = "usuarios/usuario_confirm_delete.html"
    success_url = reverse_lazy("usuarios:usuario_list")
