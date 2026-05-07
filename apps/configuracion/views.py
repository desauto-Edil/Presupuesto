"""apps/configuracion/views.py — Vistas unificadas de Configuración."""

from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from .models import ConfiguracionSistema, UnidadNegocioInfo, UnidadPolitica, UnidadClausula, UnidadAlianza
from .forms import ConfiguracionSistemaForm
from apps.common.mixins import AdminRequiredMixin


def _form_errors(form):
    errors = []
    for field, errs in form.errors.items():
        label = form.fields[field].label if field in form.fields else field
        errors.append(f"{label}: {', '.join(errs)}")
    return " | ".join(errors) if errors else "Error al guardar el formulario."


# ── Vista principal unificada ──────────────────────────────────────────────────

class ConfiguracionView(AdminRequiredMixin, ListView):
    """Página principal de Configuración: usuarios + unidades de negocio."""
    model = ConfiguracionSistema
    template_name = "configuracion/configuracion_list.html"
    context_object_name = "configuraciones"
    ordering = ["nombre_completo"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["unidades"] = UnidadNegocioInfo.objects.prefetch_related(
            "politicas", "clausulas", "alianzas"
        ).order_by("codigo")
        return ctx


# Alias para compatibilidad con nombre anterior
ConfiguracionListView = ConfiguracionView


# ── CRUD ConfiguracionSistema (usuarios) ──────────────────────────────────────

class ConfiguracionCreateView(AdminRequiredMixin, CreateView):
    model = ConfiguracionSistema
    form_class = ConfiguracionSistemaForm
    template_name = "configuracion/configuracion_list.html"
    success_url = reverse_lazy("configuracion:configuracion")

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("configuracion:configuracion")


class ConfiguracionUpdateView(AdminRequiredMixin, UpdateView):
    model = ConfiguracionSistema
    form_class = ConfiguracionSistemaForm
    template_name = "configuracion/configuracion_list.html"
    success_url = reverse_lazy("configuracion:configuracion")

    def form_valid(self, form):
        cfg = form.save(commit=False)
        nueva_password = form.cleaned_data.get("password_hash", "").strip()
        if not nueva_password:
            cfg.password_hash = ConfiguracionSistema.objects.get(pk=cfg.pk).password_hash
        else:
            cfg.password_hash = nueva_password
        cfg.save()
        messages.success(self.request, f"Usuario {cfg.nombre_completo} actualizado.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("configuracion:configuracion")


class ConfiguracionDetailView(DetailView):
    model = ConfiguracionSistema
    template_name = "configuracion/configuracion_detail.html"
    context_object_name = "configuracion"


class ConfiguracionDeleteView(AdminRequiredMixin, DeleteView):
    model = ConfiguracionSistema
    success_url = reverse_lazy("configuracion:configuracion")


# ── CRUD UnidadNegocioInfo ────────────────────────────────────────────────────

class UnidadCreateView(AdminRequiredMixin, CreateView):
    model = UnidadNegocioInfo
    fields = ["codigo", "razon_social", "nit", "ciudad", "direccion", "telefono",
              "email", "sitio_web", "quienes_somos", "activa"]
    success_url = reverse_lazy("configuracion:configuracion")

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("configuracion:configuracion")


class UnidadUpdateView(AdminRequiredMixin, UpdateView):
    model = UnidadNegocioInfo
    fields = ["razon_social", "nit", "ciudad", "direccion", "telefono",
              "email", "sitio_web", "quienes_somos", "activa"]
    success_url = reverse_lazy("configuracion:configuracion")

    def form_valid(self, form):
        unidad = form.save()
        messages.success(self.request, f"Unidad {unidad.get_codigo_display()} actualizada.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("configuracion:configuracion")


class UnidadDeleteView(AdminRequiredMixin, DeleteView):
    model = UnidadNegocioInfo
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("configuracion:configuracion")


# ── CRUD Políticas ────────────────────────────────────────────────────────────

class PoliticaCreateView(CreateView):
    model = UnidadPolitica
    fields = ["titulo", "descripcion", "orden"]

    def form_valid(self, form):
        unidad = get_object_or_404(UnidadNegocioInfo, pk=self.kwargs["unidad_pk"])
        politica = form.save(commit=False)
        politica.unidad = unidad
        politica.save()
        messages.success(self.request, "Política agregada.")
        return redirect("configuracion:configuracion")

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("configuracion:configuracion")


class PoliticaUpdateView(UpdateView):
    model = UnidadPolitica
    fields = ["titulo", "descripcion", "orden"]
    success_url = reverse_lazy("configuracion:configuracion")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Política actualizada.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("configuracion:configuracion")


class PoliticaDeleteView(DeleteView):
    model = UnidadPolitica
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("configuracion:configuracion")


# ── CRUD Cláusulas ────────────────────────────────────────────────────────────

class ClausulaCreateView(CreateView):
    model = UnidadClausula
    fields = ["titulo", "descripcion", "orden"]

    def form_valid(self, form):
        unidad = get_object_or_404(UnidadNegocioInfo, pk=self.kwargs["unidad_pk"])
        clausula = form.save(commit=False)
        clausula.unidad = unidad
        clausula.save()
        messages.success(self.request, "Cláusula agregada.")
        return redirect("configuracion:configuracion")

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("configuracion:configuracion")


class ClausulaUpdateView(UpdateView):
    model = UnidadClausula
    fields = ["titulo", "descripcion", "orden"]
    success_url = reverse_lazy("configuracion:configuracion")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Cláusula actualizada.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("configuracion:configuracion")


class ClausulaDeleteView(DeleteView):
    model = UnidadClausula
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("configuracion:configuracion")


# ── CRUD Alianzas ─────────────────────────────────────────────────────────────

class AlianzaCreateView(AdminRequiredMixin, CreateView):
    model = UnidadAlianza
    fields = ["nombre", "descripcion", "imagen", "orden"]

    def form_valid(self, form):
        unidad = get_object_or_404(UnidadNegocioInfo, pk=self.kwargs["unidad_pk"])
        alianza = form.save(commit=False)
        alianza.unidad = unidad
        alianza.save()
        messages.success(self.request, "Alianza agregada.")
        return redirect("configuracion:configuracion")

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("configuracion:configuracion")


class AlianzaUpdateView(AdminRequiredMixin, UpdateView):
    model = UnidadAlianza
    fields = ["nombre", "descripcion", "imagen", "orden"]
    success_url = reverse_lazy("configuracion:configuracion")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Alianza actualizada.")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, _form_errors(form))
        return redirect("configuracion:configuracion")


class AlianzaDeleteView(AdminRequiredMixin, DeleteView):
    model = UnidadAlianza
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("configuracion:configuracion")


# ── Autenticación ─────────────────────────────────────────────────────────────

class LoginConfiguracionView(View):
    template_name = "configuracion/login.html"

    def get(self, request):
        if "configuracion_id" in request.session:
            return redirect("comercial:dashboard")
        return render(request, self.template_name)

    def post(self, request):
        email    = request.POST.get("email")
        password = request.POST.get("password")
        try:
            cfg = ConfiguracionSistema.objects.get(email=email, activo=True)
            if cfg.password_hash == password:
                # Guardar con ambas claves para compatibilidad con sesiones existentes
                request.session["configuracion_id"]     = cfg.id
                request.session["usuario_id"]           = cfg.id
                request.session["usuario_nombre"]       = cfg.nombre_completo
                request.session["configuracion_nombre"] = cfg.nombre_completo
                request.session["unidad_negocio"]       = cfg.unidad_negocio
                request.session["rol"]                  = cfg.rol
                return redirect("comercial:dashboard")
            else:
                messages.error(request, "Credenciales inválidas.")
        except ConfiguracionSistema.DoesNotExist:
            messages.error(request, "Usuario no encontrado.")
        return render(request, self.template_name)


def logout_configuracion(request):
    request.session.flush()
    return redirect("configuracion:login")
