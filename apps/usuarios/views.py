"""apps/usuarios/views.py — Vistas CRUD para UsuarioSistema."""

from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from .models import UsuarioSistema
from .forms import UsuarioSistemaForm


class UsuarioListView(ListView):
    model = UsuarioSistema
    template_name = "usuarios/usuario_list.html"
    context_object_name = "usuarios"
    ordering = ["nombre_completo"]

class UsuarioCreateView(CreateView):
    model = UsuarioSistema
    form_class = UsuarioSistemaForm
    # Usaremos un template que SOLO tiene el contenido del form
    template_name = "usuarios/partials/usuario_form_inner.html"
    success_url = reverse_lazy("usuarios:usuario_list")
    
class UsuarioUpdateView(UpdateView):
    model = UsuarioSistema
    form_class = UsuarioSistemaForm
    template_name = "usuarios/partials/usuario_form_inner.html"
    success_url = reverse_lazy("usuarios:usuario_list")


class UsuarioDetailView(DetailView):
    model = UsuarioSistema
    template_name = "usuarios/usuario_detail.html"
    context_object_name = "usuario"


class UsuarioDeleteView(DeleteView):
    model = UsuarioSistema
    # El borrado ahora lo maneja el modal global, pero dejamos la URL lista
    success_url = reverse_lazy("usuarios:usuario_list")


class LoginUsuarioView(View):
    template_name = "usuarios/login.html"

    def get(self, request):
        if "usuario_id" in request.session:
            return redirect("comercial:proyecto_list")
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get("email")
        password = request.POST.get("password")

        try:
            usuario = UsuarioSistema.objects.get(email=email, activo=True)
            if usuario.password_hash == password:
                # Iniciar Sesión Manual
                request.session["usuario_id"] = usuario.id
                request.session["usuario_nombre"] = usuario.nombre_completo
                request.session["unidad_negocio"] = usuario.unidad_negocio
                
                return redirect("comercial:proyecto_list") # Redirigir al inicio real
            else:
                messages.error(request, "Credenciales inválidas.")
        except UsuarioSistema.DoesNotExist:
            messages.error(request, "Usuario no encontrado.")
            
        return render(request, self.template_name)


def dispatch(self, request, *args, **kwargs):
    if "usuario_id" not in request.session:
        return redirect("usuarios:login")
    return super().dispatch(request, *args, **kwargs)

def logout_usuario(request):
    request.session.flush() 
    return redirect("usuarios:login")

