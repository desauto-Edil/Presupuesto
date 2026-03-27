"""apps/usuarios/views.py — Vistas CRUD para UsuarioSistema."""

from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from .models import UsuarioSistema
from .forms import UsuarioSistemaForm


def _form_errors(form):
    """Convierte los errores del form en un string legible para messages."""
    errors = []
    for field, errs in form.errors.items():
        label = form.fields[field].label if field in form.fields else field
        errors.append(f"{label}: {', '.join(errs)}")
    return " | ".join(errors) if errors else "Error al guardar el formulario."


class UsuarioListView(ListView):
    model = UsuarioSistema
    template_name = "usuarios/usuario_list.html"
    context_object_name = "usuarios"
    ordering = ["nombre_completo"]

class UsuarioCreateView(CreateView):
    model = UsuarioSistema
    form_class = UsuarioSistemaForm
    template_name = "usuarios/usuario_list.html"
    success_url = reverse_lazy("usuarios:usuario_list")

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("usuarios:usuario_list")


class UsuarioUpdateView(UpdateView):
    model = UsuarioSistema
    form_class = UsuarioSistemaForm
    template_name = "usuarios/usuario_list.html"
    success_url = reverse_lazy("usuarios:usuario_list")

    def form_valid(self, form):
        usuario = form.save(commit=False)
        nueva_password = form.cleaned_data.get("password_hash", "").strip()
        if not nueva_password:
            # Conservar la contraseña existente sin tocarla
            usuario.password_hash = UsuarioSistema.objects.get(pk=usuario.pk).password_hash
        else:
            usuario.password_hash = nueva_password
        usuario.save()
        messages.success(self.request, f"Usuario {usuario.nombre_completo} actualizado.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("usuarios:usuario_list")


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
            return redirect("comercial:dashboard")
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
                
                return redirect("comercial:dashboard") # Redirigir al inicio real
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

