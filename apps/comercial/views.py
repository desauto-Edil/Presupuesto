"""apps/comercial/views.py — Vistas CRUD para el módulo comercial."""

from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from .models import Cliente, ContactoCliente, TipoProyecto, Solicitud, Proyecto
from .forms import ClienteForm, ContactoClienteForm, TipoProyectoForm, SolicitudForm, ProyectoForm
from apps.common.mixins import WithCreateFormMixin


def _usuario_sistema(request):
    """Retorna el UsuarioSistema del request, o None si no hay sesión activa."""
    from apps.usuarios.models import UsuarioSistema
    if hasattr(request, "usuario_sistema"):
        return request.usuario_sistema
    if getattr(request, "user", None) and request.user.is_authenticated:
        return UsuarioSistema.objects.filter(email=request.user.email).first()
    return None


# ── Clientes ────────────────────────────────────────────────────────────────

class ClienteListView(WithCreateFormMixin, ListView):
    model = Cliente
    form_class = ClienteForm
    template_name = "comercial/cliente_list.html"
    context_object_name = "clientes"
    ordering = ["razon_social"]


class ClienteDetailView(DetailView):
    model = Cliente
    template_name = "comercial/cliente_detail.html"
    context_object_name = "cliente"


class ClienteCreateView(CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "comercial/cliente_form.html"
    success_url = reverse_lazy("comercial:cliente_list")


class ClienteUpdateView(UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = "comercial/cliente_form.html"
    success_url = reverse_lazy("comercial:cliente_list")


class ClienteDeleteView(DeleteView):
    model = Cliente
    template_name = "comercial/confirm_delete.html"
    success_url = reverse_lazy("comercial:cliente_list")


# ── Contactos de cliente ─────────────────────────────────────────────────────

class ContactoListView(ListView):
    model = ContactoCliente
    template_name = "comercial/contacto_list.html"
    context_object_name = "contactos"
    ordering = ["cliente__razon_social", "nombre"]


class ContactoCreateView(CreateView):
    model = ContactoCliente
    form_class = ContactoClienteForm
    template_name = "comercial/contacto_form.html"
    success_url = reverse_lazy("comercial:contacto_list")


class ContactoUpdateView(UpdateView):
    model = ContactoCliente
    form_class = ContactoClienteForm
    template_name = "comercial/contacto_form.html"
    success_url = reverse_lazy("comercial:contacto_list")


class ContactoDeleteView(DeleteView):
    model = ContactoCliente
    template_name = "comercial/confirm_delete.html"
    success_url = reverse_lazy("comercial:contacto_list")


# ── Tipos de proyecto ────────────────────────────────────────────────────────

class TipoProyectoListView(ListView):
    model = TipoProyecto
    template_name = "comercial/tipoproyecto_list.html"
    context_object_name = "tipos"
    ordering = ["nombre"]


class TipoProyectoCreateView(CreateView):
    model = TipoProyecto
    form_class = TipoProyectoForm
    template_name = "comercial/tipoproyecto_form.html"
    success_url = reverse_lazy("comercial:tipoproyecto_list")


class TipoProyectoUpdateView(UpdateView):
    model = TipoProyecto
    form_class = TipoProyectoForm
    template_name = "comercial/tipoproyecto_form.html"
    success_url = reverse_lazy("comercial:tipoproyecto_list")


class TipoProyectoDeleteView(DeleteView):
    model = TipoProyecto
    template_name = "comercial/confirm_delete.html"
    success_url = reverse_lazy("comercial:tipoproyecto_list")


# ── Solicitudes ──────────────────────────────────────────────────────────────

class SolicitudListView(WithCreateFormMixin, ListView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_list.html"
    context_object_name = "solicitudes"
    ordering = ["-created_at"]


class SolicitudDetailView(DetailView):
    model = Solicitud
    template_name = "comercial/solicitud_detail.html"
    context_object_name = "solicitud"


class SolicitudCreateView(CreateView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_form.html"
    success_url = reverse_lazy("comercial:solicitud_list")

    def form_valid(self, form):
        """
        Asigna campos del sistema antes de persistir:
          · consecutivo  → model.save() lo genera automáticamente.
          · estado       → default EN_GESTION (definido en el modelo).
          · creado_por   → se resuelve aquí desde el request; nunca del form.
        """
        self.object = form.save(commit=False)
        self.object.creado_por = _usuario_sistema(self.request)
        self.object.save()
        form.save_m2m()
        return HttpResponseRedirect(self.get_success_url())


class SolicitudUpdateView(UpdateView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_form.html"
    success_url = reverse_lazy("comercial:solicitud_list")

    def form_valid(self, form):

        self.object = form.save(commit=False)
        original = Solicitud.objects.get(pk=self.object.pk)
        self.object.consecutivo = original.consecutivo
        self.object.estado = original.estado
        self.object.creado_por_id = original.creado_por_id
        self.object.save()
        form.save_m2m()
        return HttpResponseRedirect(self.get_success_url())


class SolicitudDeleteView(DeleteView):
    model = Solicitud
    template_name = "comercial/confirm_delete.html"
    success_url = reverse_lazy("comercial:solicitud_list")


# ── Proyectos ────────────────────────────────────────────────────────────────

class ProyectoListView(ListView):
    model = Proyecto
    template_name = "comercial/proyecto_list.html"
    context_object_name = "proyectos"
    ordering = ["-created_at"]


class ProyectoDetailView(DetailView):
    model = Proyecto
    template_name = "comercial/proyecto_detail.html"
    context_object_name = "proyecto"


class ProyectoCreateView(CreateView):
    model = Proyecto
    form_class = ProyectoForm
    template_name = "comercial/proyecto_form.html"
    success_url = reverse_lazy("comercial:proyecto_list")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.creado_por = _usuario_sistema(self.request)
        # consecutivo y estado: gestionados en model.save() y default del modelo
        self.object.save()
        form.save_m2m()
        return HttpResponseRedirect(self.get_success_url())


class ProyectoUpdateView(UpdateView):
    model = Proyecto
    form_class = ProyectoForm
    template_name = "comercial/proyecto_form.html"
    success_url = reverse_lazy("comercial:proyecto_list")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        # Protección: restaurar campos del sistema desde la BD
        original = Proyecto.objects.get(pk=self.object.pk)
        self.object.consecutivo = original.consecutivo
        self.object.estado = original.estado
        self.object.creado_por_id = original.creado_por_id
        self.object.save()
        form.save_m2m()
        return HttpResponseRedirect(self.get_success_url())


class ProyectoDeleteView(DeleteView):
    model = Proyecto
    template_name = "comercial/confirm_delete.html"
    success_url = reverse_lazy("comercial:proyecto_list")
