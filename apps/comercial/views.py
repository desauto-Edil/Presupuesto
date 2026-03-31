"""apps/comercial/views.py — Vistas del módulo comercial."""

from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView,
)
from .models import Cliente, ContactoCliente, TipoProyecto, Solicitud, SolicitudArchivo, Proyecto, LogSistema
from .forms import (
    ClienteConContactoForm, ContactoClienteForm,
    TipoProyectoForm, SolicitudForm, SolicitudArchivoForm,
    ProyectoForm, ProyectoFromSolicitudForm,
)
from apps.common.mixins import WithCreateFormMixin
from apps.common.choices import EstadoSolicitud


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
    # Fallback: autenticación por sesión personalizada
    try:
        usuario_id = request.session.get("usuario_id")
        if usuario_id:
            return UsuarioSistema.objects.filter(pk=usuario_id).first()
    except Exception:
        pass
    return None


def registrar_log(request, accion, descripcion="", modelo_afectado="", objeto_id=None):
    """Registra una acción en LogSistema. Silencia errores para no interrumpir el flujo."""
    try:
        usuario = _usuario_sistema(request)
        if not usuario:
            return
        unidad = ""
        try:
            unidad = request.session.get("unidad_negocio", "") or ""
        except Exception:
            pass
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
# Dashboard
# ---------------------------------------------------------------------------

class DashboardView(TemplateView):
    template_name = "comercial/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = Solicitud.objects.select_related("cliente", "creado_por")

        # Conteo solicitudes por estado
        by_estado = {
            item["estado"]: item["total"]
            for item in qs.values("estado").annotate(total=Count("id"))
        }

        ctx["total"] = qs.count()
        ctx["por_estado"] = [
            {
                "label": label,
                "value": estado,
                "count": by_estado.get(estado, 0),
            }
            for estado, label in EstadoSolicitud.choices
        ]

        # Solicitudes recientes — añadir proyecto_actual por anotación
        recientes_qs = list(qs.order_by("-created_at")[:10])
        for s in recientes_qs:
            s.proyecto_actual = s.proyectos.filter(es_version_actual=True).first()
        ctx["recientes"] = recientes_qs

        # Conteo proyectos (solo versiones actuales)
        ctx["total_proyectos"] = Proyecto.objects.filter(es_version_actual=True).count()

        # Conteo despiece y APU (presupuestos)
        try:
            from apps.presupuestos.models import ProyectoSistema, APUProyecto
            ctx["total_despieces"] = ProyectoSistema.objects.count()
            ctx["total_apus"] = APUProyecto.objects.count()
        except Exception:
            ctx["total_despieces"] = 0
            ctx["total_apus"] = 0

        return ctx


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
    template_name = "comercial/cliente_list.html"
    context_object_name = "cliente"


class ClienteCreateView(CreateView):
    """Crea un Cliente y su Contacto principal en una sola operación."""
    model = Cliente
    form_class = ClienteConContactoForm
    template_name = "comercial/cliente_list.html"
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
        registrar_log(
            self.request,
            accion="CREAR_CLIENTE",
            descripcion=f"Cliente {self.object.razon_social} creado",
            modelo_afectado="Cliente",
            objeto_id=self.object.pk,
        )
        messages.success(
            self.request,
            f"Cliente {self.object.razon_social} creado correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                label = form.fields[field].label if field in form.fields else field
                messages.error(self.request, f"{label}: {error}")
        return redirect("comercial:cliente_list")


class ClienteUpdateView(UpdateView):
    """Actualiza el Cliente y su contacto principal en una sola operación."""
    model = Cliente
    form_class = ClienteConContactoForm
    template_name = "comercial/cliente_list.html"
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
        registrar_log(
            self.request,
            accion="EDITAR_CLIENTE",
            descripcion=f"Cliente {self.object.razon_social} actualizado",
            modelo_afectado="Cliente",
            objeto_id=self.object.pk,
        )
        messages.success(
            self.request,
            f"Cliente {self.object.razon_social} actualizado correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                label = form.fields[field].label if field in form.fields else field
                messages.error(self.request, f"{label}: {error}")
        return redirect("comercial:cliente_list")


class ClienteDeleteView(DeleteView):
    model = Cliente
    template_name = "comercial/confirm_delete.html"
    success_url = reverse_lazy("comercial:cliente_list")

    def form_valid(self, form):
        registrar_log(
            self.request,
            accion="ELIMINAR_CLIENTE",
            descripcion=f"Cliente {self.object.razon_social} eliminado",
            modelo_afectado="Cliente",
            objeto_id=self.object.pk,
        )
        return super().form_valid(form)


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
        ctx["archivos"] = solicitud.archivos.select_related("usuario").all()
        ctx["archivo_form"] = SolicitudArchivoForm()

        # Proyectos / versiones vinculadas a esta solicitud
        ctx["proyectos"] = solicitud.proyectos.select_related(
            "tipo_proyecto", "creado_por"
        ).order_by("-version")
        ctx["proyecto_actual"] = solicitud.proyectos.filter(
            es_version_actual=True
        ).first()

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
        messages.success(self.request, f"Solicitud {self.object.consecutivo} creada.")
        return HttpResponseRedirect(self.get_success_url())


class SolicitudUpdateView(UpdateView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_form.html"
    success_url = reverse_lazy("comercial:solicitud_list")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        # Proteger campos de sistema
        original = Solicitud.objects.get(pk=self.object.pk)
        self.object.estado = original.estado
        self.object.creado_por_id = original.creado_por_id
        self.object.save()
        form.save_m2m()
        registrar_log(
            self.request,
            accion="EDITAR_SOLICITUD",
            descripcion=f"Solicitud {self.object.consecutivo} actualizada",
            modelo_afectado="Solicitud",
            objeto_id=self.object.pk,
        )
        messages.success(self.request, "Solicitud actualizada correctamente.")
        return HttpResponseRedirect(self.get_success_url())


class SolicitudDeleteView(View):
    def post(self, request, pk, *args, **kwargs):
        solicitud = get_object_or_404(Solicitud, pk=pk)
        consecutivo = solicitud.consecutivo
        registrar_log(
            request,
            accion="ELIMINAR_SOLICITUD",
            descripcion=f"Solicitud {consecutivo} eliminada",
            modelo_afectado="Solicitud",
            objeto_id=pk,
        )
        solicitud.delete()
        messages.success(request, f"Solicitud {consecutivo} eliminada.")
        return redirect("comercial:solicitud_list")


# ---------------------------------------------------------------------------
# Archivos de Solicitud
# ---------------------------------------------------------------------------

class SolicitudArchivoCreateView(CreateView):
    """Sube un archivo adjunto a una Solicitud."""
    model = SolicitudArchivo
    form_class = SolicitudArchivoForm
    http_method_names = ["post"]

    def _get_solicitud(self):
        return get_object_or_404(Solicitud, pk=self.kwargs["solicitud_pk"])

    def form_valid(self, form):
        solicitud = self._get_solicitud()
        self.object = form.save(commit=False)
        self.object.solicitud = solicitud
        self.object.usuario = _usuario_sistema(self.request)
        self.object.save()
        registrar_log(
            self.request,
            accion="SUBIR_ARCHIVO",
            descripcion=f"Archivo '{self.object.nombre}' subido a {solicitud.consecutivo}",
            modelo_afectado="Solicitud",
            objeto_id=solicitud.pk,
        )
        messages.success(self.request, f"Archivo '{self.object.nombre}' subido correctamente.")
        return redirect("comercial:solicitud_detail", pk=solicitud.pk)

    def form_invalid(self, form):
        solicitud = self._get_solicitud()
        messages.error(self.request, "Error al subir el archivo. Verifica los datos.")
        return redirect("comercial:solicitud_detail", pk=solicitud.pk)


class SolicitudArchivoDeleteView(View):
    """Elimina un archivo de solicitud."""

    def post(self, request, pk, *args, **kwargs):
        archivo = get_object_or_404(SolicitudArchivo, pk=pk)
        solicitud = archivo.solicitud
        nombre = archivo.nombre
        if archivo.archivo:
            archivo.archivo.delete(save=False)
        archivo.delete()
        registrar_log(
            request,
            accion="ELIMINAR_ARCHIVO",
            descripcion=f"Archivo '{nombre}' eliminado de {solicitud.consecutivo}",
            modelo_afectado="Solicitud",
            objeto_id=solicitud.pk,
        )
        messages.success(request, f"Archivo '{nombre}' eliminado.")
        return redirect("comercial:solicitud_detail", pk=solicitud.pk)


# ---------------------------------------------------------------------------
# Tipos de Proyecto
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
# Proyectos
# ---------------------------------------------------------------------------

class ProyectoListView(ListView):
    model = Proyecto
    template_name = "comercial/proyecto_list.html"
    context_object_name = "proyectos"
    ordering = ["-created_at"]


class ProyectoDetailView(DetailView):
    model = Proyecto
    template_name = "comercial/proyecto_detail.html"
    context_object_name = "proyecto"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # ProyectoSistemas (despieces) de este proyecto
        try:
            from apps.presupuestos.models import ProyectoSistema
            ctx["proyecto_sistemas"] = (
                self.object.proyecto_sistemas
                .select_related("sistema", "subsistema")
                .prefetch_related("despiece_lineas")
                .order_by("sistema__nombre")
            )
        except Exception:
            ctx["proyecto_sistemas"] = []
        # Otras versiones de la misma solicitud
        if self.object.solicitud_id:
            ctx["otras_versiones"] = (
                self.object.solicitud.proyectos
                .exclude(pk=self.object.pk)
                .order_by("-version")
            )
        else:
            ctx["otras_versiones"] = Proyecto.objects.none()
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
        registrar_log(
            self.request,
            accion="CREAR_PROYECTO",
            descripcion=f"Proyecto {self.object.consecutivo} — {self.object.nombre} creado",
            modelo_afectado="Proyecto",
            objeto_id=self.object.pk,
        )
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
        self.object.save()
        form.save_m2m()
        registrar_log(
            self.request,
            accion="EDITAR_PROYECTO",
            descripcion=f"Proyecto {self.object.consecutivo} — {self.object.nombre} actualizado",
            modelo_afectado="Proyecto",
            objeto_id=self.object.pk,
        )
        messages.success(self.request, "Proyecto actualizado correctamente.")
        return HttpResponseRedirect(self.get_success_url())


class ProyectoDeleteView(DeleteView):
    model = Proyecto
    template_name = "comercial/confirm_delete.html"
    success_url = reverse_lazy("comercial:proyecto_list")


class CrearProyectoDesdeSolicitudView(CreateView):
    """
    Crea una nueva versión de Proyecto para una Solicitud.
    Permite múltiples versiones; el modelo auto-gestiona el número y la versión actual.
    """
    model = Proyecto
    form_class = ProyectoFromSolicitudForm
    template_name = "comercial/proyecto_desde_solicitud.html"

    def _get_solicitud(self):
        return get_object_or_404(Solicitud, pk=self.kwargs["pk"])

    def get_initial(self):
        solicitud = self._get_solicitud()
        return {"nombre": solicitud.nombre, "descripcion": solicitud.descripcion}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        solicitud = self._get_solicitud()
        ctx["solicitud"] = solicitud
        # Versiones existentes para mostrar historial
        ctx["versiones_existentes"] = solicitud.proyectos.order_by("-version")
        # Próxima versión
        ultima = solicitud.proyectos.order_by("-version").first()
        ctx["proxima_version"] = (ultima.version + 1) if ultima else 1
        return ctx

    def form_valid(self, form):
        solicitud = self._get_solicitud()
        self.object = form.save(commit=False)
        self.object.solicitud = solicitud
        self.object.cliente = solicitud.cliente
        self.object.creado_por = _usuario_sistema(self.request)
        # version y es_version_actual se asignan en Proyecto.save()
        self.object.save()
        form.save_m2m()
        registrar_log(
            self.request,
            accion="CREAR_PROYECTO",
            descripcion=(
                f"Proyecto {self.object.consecutivo} v{self.object.version} "
                f"creado desde {solicitud.consecutivo}"
            ),
            modelo_afectado="Proyecto",
            objeto_id=self.object.pk,
        )
        messages.success(
            self.request,
            f"Proyecto {self.object.consecutivo} (v{self.object.version}) creado correctamente.",
        )
        return redirect("comercial:proyecto_detail", pk=self.object.pk)


# ---------------------------------------------------------------------------
# API interna: contactos por cliente (AJAX)
# ---------------------------------------------------------------------------

class ContactosPorClienteView(View):
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
