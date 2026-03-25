"""apps/comercial/views.py — Vistas CRUD para el módulo comercial."""

from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from .models import (
    Cliente, ContactoCliente, TipoProyecto, Solicitud,
    Proyecto, ProyectoArchivo, LogSistema,
)
from .forms import (
    ClienteForm, ClienteConContactoForm, ContactoClienteForm, TipoProyectoForm,
    SolicitudForm, ProyectoForm, ProyectoFromSolicitudForm, ProyectoArchivoForm,
)
from apps.common.mixins import WithCreateFormMixin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _usuario_sistema(request):
    """Retorna el UsuarioSistema del request, o None si no hay sesión activa."""
    from apps.usuarios.models import UsuarioSistema
    if hasattr(request, "usuario_sistema"):
        return request.usuario_sistema
    if getattr(request, "user", None) and request.user.is_authenticated:
        return UsuarioSistema.objects.filter(email=request.user.email).first()
    return None


def registrar_log(request, accion, descripcion="", modelo_afectado="", objeto_id=None):
    """
    Registra una acción en LogSistema usando la unidad del usuario en sesión.
    Silencia errores para no interrumpir el flujo principal.
    """
    try:
        usuario = _usuario_sistema(request)
        unidad = request.session.get("unidad_negocio", "")
        if usuario and unidad:
            LogSistema.objects.create(
                usuario=usuario,
                unidad_negocio=unidad,
                accion=accion,
                descripcion=descripcion,
                modelo_afectado=modelo_afectado,
                objeto_id=objeto_id,
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------

class ClienteListView(WithCreateFormMixin, ListView):
    model = Cliente
    form_class = ClienteConContactoForm
    template_name = "comercial/cliente_list.html"
    context_object_name = "clientes"
    ordering = ["razon_social"]

    def get_queryset(self):
        return super().get_queryset().prefetch_related("contactos")


class ClienteDetailView(DetailView):
    model = Cliente
    template_name = "comercial/cliente_detail.html"
    context_object_name = "cliente"


class ClienteCreateView(CreateView):
    """Crea un Cliente y su Contacto principal en una sola operación."""
    model = Cliente
    form_class = ClienteConContactoForm
    template_name = "comercial/cliente_form.html"
    success_url = reverse_lazy("comercial:cliente_list")

    def form_valid(self, form):
        self.object = form.save()
        ContactoCliente.objects.create(
            cliente=self.object,
            nombre=form.cleaned_data["contacto_nombre"],
            cargo=form.cleaned_data.get("contacto_cargo", ""),
            email=form.cleaned_data.get("contacto_email", ""),
            telefono=form.cleaned_data.get("contacto_telefono", ""),
            es_principal=True,
            activo=True,
        )
        messages.success(
            self.request,
            f"Cliente {self.object.razon_social} creado con su contacto principal.",
        )
        return HttpResponseRedirect(self.get_success_url())


class ClienteUpdateView(UpdateView):
    """Actualiza el Cliente y su contacto principal en una sola operación."""
    model = Cliente
    form_class = ClienteConContactoForm
    template_name = "comercial/cliente_form.html"
    success_url = reverse_lazy("comercial:cliente_list")

    def form_valid(self, form):
        self.object = form.save()
        cp = self.object.contacto_principal
        datos_contacto = {
            "nombre": form.cleaned_data["contacto_nombre"],
            "cargo": form.cleaned_data.get("contacto_cargo", ""),
            "email": form.cleaned_data.get("contacto_email", ""),
            "telefono": form.cleaned_data.get("contacto_telefono", ""),
        }
        if cp:
            for campo, valor in datos_contacto.items():
                setattr(cp, campo, valor)
            cp.save()
        else:
            ContactoCliente.objects.create(
                cliente=self.object,
                es_principal=True,
                activo=True,
                **datos_contacto,
            )
        messages.success(
            self.request,
            f"Cliente {self.object.razon_social} actualizado correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())


class ClienteDeleteView(DeleteView):
    model = Cliente
    template_name = "comercial/confirm_delete.html"
    success_url = reverse_lazy("comercial:cliente_list")


# ---------------------------------------------------------------------------
# Contactos de cliente
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tipos de proyecto
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Solicitudes
# ---------------------------------------------------------------------------

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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        solicitud = self.object
        # Versiones ordenadas de mayor a menor
        ctx["proyectos"] = solicitud.proyectos.select_related(
            "tipo_proyecto", "creado_por"
        ).prefetch_related("archivos").order_by("-version")
        # Logs de esta solicitud
        ctx["logs"] = LogSistema.objects.filter(
            modelo_afectado="Solicitud",
            objeto_id=solicitud.pk,
        ).select_related("usuario").order_by("-created_at")[:50]
        return ctx


class SolicitudCreateView(CreateView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_form.html"
    success_url = reverse_lazy("comercial:solicitud_list")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.creado_por = _usuario_sistema(self.request)
        self.object.save()
        form.save_m2m()
        registrar_log(
            self.request,
            accion="CREAR_SOLICITUD",
            descripcion=f"Solicitud {self.object.consecutivo} — {self.object.nombre}",
            modelo_afectado="Solicitud",
            objeto_id=self.object.pk,
        )
        return HttpResponseRedirect(self.get_success_url())


class SolicitudUpdateView(UpdateView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_form.html"
    success_url = reverse_lazy("comercial:solicitud_list")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        # Proteger campos de sistema: solo estado y creado_por
        original = Solicitud.objects.get(pk=self.object.pk)
        self.object.estado = original.estado
        self.object.creado_por_id = original.creado_por_id
        self.object.save()
        form.save_m2m()
        return HttpResponseRedirect(self.get_success_url())


class SolicitudDeleteView(View):
    """
    Las solicitudes NO se eliminan. Esta vista bloquea cualquier intento
    de borrado y redirige al detalle con un mensaje informativo.
    """

    def get(self, request, pk, *args, **kwargs):
        solicitud = get_object_or_404(Solicitud, pk=pk)
        messages.warning(
            request,
            f"La solicitud {solicitud.consecutivo} no puede eliminarse. "
            "Las solicitudes son registros permanentes del sistema.",
        )
        return redirect("comercial:solicitud_detail", pk=pk)

    def post(self, request, pk, *args, **kwargs):
        solicitud = get_object_or_404(Solicitud, pk=pk)
        messages.error(
            request,
            f"La solicitud {solicitud.consecutivo} no puede eliminarse.",
        )
        return redirect("comercial:solicitud_detail", pk=pk)


# ---------------------------------------------------------------------------
# Proyectos (versiones)
# ---------------------------------------------------------------------------

class ProyectoListView(ListView):
    model = Proyecto
    template_name = "comercial/proyecto_list.html"
    context_object_name = "proyectos"
    ordering = ["-created_at"]

    def get_queryset(self):
        return super().get_queryset().select_related(
            "cliente", "tipo_proyecto", "creado_por", "solicitud"
        )


class ProyectoDetailView(DetailView):
    model = Proyecto
    template_name = "comercial/proyecto_detail.html"
    context_object_name = "proyecto"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["archivos"] = self.object.archivos.select_related("usuario").all()
        ctx["archivo_form"] = ProyectoArchivoForm()
        # Otras versiones de la misma solicitud
        if self.object.solicitud:
            ctx["otras_versiones"] = self.object.solicitud.proyectos.exclude(
                pk=self.object.pk
            ).order_by("-version")
        return ctx


class ProyectoCreateView(CreateView):
    model = Proyecto
    form_class = ProyectoForm
    template_name = "comercial/proyecto_form.html"
    success_url = reverse_lazy("comercial:proyecto_list")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.creado_por = _usuario_sistema(self.request)
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
        original = Proyecto.objects.get(pk=self.object.pk)
        self.object.consecutivo = original.consecutivo
        self.object.estado = original.estado
        self.object.creado_por_id = original.creado_por_id
        self.object.version = original.version
        self.object.es_version_actual = original.es_version_actual
        self.object.save()
        form.save_m2m()
        return HttpResponseRedirect(self.get_success_url())


class ProyectoDeleteView(DeleteView):
    model = Proyecto
    template_name = "comercial/confirm_delete.html"
    success_url = reverse_lazy("comercial:proyecto_list")


# ---------------------------------------------------------------------------
# Crear Proyecto (nueva versión) desde Solicitud
# ---------------------------------------------------------------------------

class CrearProyectoDesdeSolicitudView(CreateView):
    """
    Crea una nueva versión de Proyecto asociada a una Solicitud.
    · Incrementa automáticamente el número de versión.
    · Marca las versiones anteriores como no actuales.
    · Registra la acción en LogSistema.
    """

    model = Proyecto
    form_class = ProyectoFromSolicitudForm
    template_name = "comercial/proyecto_desde_solicitud.html"

    def _get_solicitud(self):
        return get_object_or_404(Solicitud, pk=self.kwargs["pk"])

    def get_initial(self):
        solicitud = self._get_solicitud()
        version_actual = solicitud.version_actual
        return {
            "nombre": (version_actual.nombre if version_actual else solicitud.nombre),
            "descripcion": (version_actual.descripcion if version_actual else solicitud.descripcion),
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        solicitud = self._get_solicitud()
        ctx["solicitud"] = solicitud
        ctx["proxima_version"] = solicitud.total_versiones + 1
        return ctx

    def form_valid(self, form):
        solicitud = self._get_solicitud()

        # Calcular próxima versión
        versiones_existentes = solicitud.proyectos.order_by("-version")
        proxima_version = (versiones_existentes.first().version + 1) if versiones_existentes.exists() else 1

        # Desmarcar versión actual de las versiones anteriores
        solicitud.proyectos.filter(es_version_actual=True).update(es_version_actual=False)

        # Crear nueva versión
        self.object = form.save(commit=False)
        self.object.solicitud = solicitud
        self.object.cliente = solicitud.cliente
        self.object.creado_por = _usuario_sistema(self.request)
        self.object.version = proxima_version
        self.object.es_version_actual = True
        self.object.save()
        form.save_m2m()

        registrar_log(
            self.request,
            accion="CREAR_VERSION",
            descripcion=(
                f"Versión v{proxima_version} del proyecto {self.object.consecutivo} "
                f"para solicitud {solicitud.consecutivo}"
            ),
            modelo_afectado="Solicitud",
            objeto_id=solicitud.pk,
        )

        messages.success(
            self.request,
            f"Versión v{proxima_version} — {self.object.consecutivo} creada correctamente.",
        )
        return redirect("comercial:solicitud_detail", pk=solicitud.pk)


# ---------------------------------------------------------------------------
# Archivos de Proyecto
# ---------------------------------------------------------------------------

class ProyectoArchivoCreateView(CreateView):
    """
    Sube un archivo a una versión de proyecto.
    Redirige de vuelta al detalle de la solicitud.
    """
    model = ProyectoArchivo
    form_class = ProyectoArchivoForm
    http_method_names = ["post"]  # solo POST; el formulario está en proyecto_detail

    def _get_proyecto(self):
        return get_object_or_404(Proyecto, pk=self.kwargs["proyecto_pk"])

    def form_valid(self, form):
        proyecto = self._get_proyecto()
        self.object = form.save(commit=False)
        self.object.proyecto = proyecto
        self.object.usuario = _usuario_sistema(self.request)
        self.object.save()

        registrar_log(
            self.request,
            accion="SUBIR_ARCHIVO",
            descripcion=f"Archivo '{self.object.nombre}' subido al proyecto {proyecto.consecutivo} (v{proyecto.version})",
            modelo_afectado="Proyecto",
            objeto_id=proyecto.pk,
        )

        messages.success(self.request, f"Archivo '{self.object.nombre}' subido correctamente.")

        # Redirigir al detalle de la solicitud si existe, si no al proyecto
        if proyecto.solicitud:
            return redirect("comercial:solicitud_detail", pk=proyecto.solicitud.pk)
        return redirect("comercial:proyecto_detail", pk=proyecto.pk)

    def form_invalid(self, form):
        proyecto = self._get_proyecto()
        messages.error(self.request, "Error al subir el archivo. Verifica el formulario.")
        if proyecto.solicitud:
            return redirect("comercial:solicitud_detail", pk=proyecto.solicitud.pk)
        return redirect("comercial:proyecto_detail", pk=proyecto.pk)


class ProyectoArchivoDeleteView(View):
    """Elimina un archivo de proyecto."""

    def post(self, request, pk, *args, **kwargs):
        archivo = get_object_or_404(ProyectoArchivo, pk=pk)
        proyecto = archivo.proyecto
        nombre = archivo.nombre
        # Borrar archivo físico
        if archivo.archivo:
            archivo.archivo.delete(save=False)
        archivo.delete()

        registrar_log(
            request,
            accion="ELIMINAR_ARCHIVO",
            descripcion=f"Archivo '{nombre}' eliminado del proyecto {proyecto.consecutivo}",
            modelo_afectado="Proyecto",
            objeto_id=proyecto.pk,
        )

        messages.success(request, f"Archivo '{nombre}' eliminado.")
        if proyecto.solicitud:
            return redirect("comercial:solicitud_detail", pk=proyecto.solicitud.pk)
        return redirect("comercial:proyecto_detail", pk=proyecto.pk)


# ---------------------------------------------------------------------------
# API: contactos por cliente (AJAX)
# ---------------------------------------------------------------------------

class ContactosPorClienteView(View):
    """
    GET /comercial/api/contactos-por-cliente/<cliente_id>/
    Retorna JSON con los contactos activos del cliente.
    """

    def get(self, request, cliente_id):
        contactos = list(
            ContactoCliente.objects.filter(
                cliente_id=cliente_id, activo=True
            ).order_by("-es_principal", "nombre")
            .values("id", "nombre", "cargo", "es_principal")
        )
        return JsonResponse({"contactos": contactos})


# ---------------------------------------------------------------------------
# Logs del sistema
# ---------------------------------------------------------------------------

class LogListView(ListView):
    model = LogSistema
    template_name = "comercial/log_list.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        usuario = _usuario_sistema(self.request)
        if usuario:
            return LogSistema.objects.filter(
                unidad_negocio=usuario.unidad_negocio
            ).select_related("usuario").order_by("-created_at")
        return LogSistema.objects.none()
