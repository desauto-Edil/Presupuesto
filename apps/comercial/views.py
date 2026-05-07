"""apps/comercial/views.py — Vistas del módulo comercial."""

import logging
from django.contrib import messages
from django.db.models import Count, Prefetch
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
from apps.common.mixins import WithCreateFormMixin, UnidadFilterMixin
from apps.common.choices import EstadoSolicitud

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _usuario_sistema(request):
    """Retorna el ConfiguracionSistema del request, o None si no hay sesión activa."""
    from apps.configuracion.models import ConfiguracionSistema
    if hasattr(request, "configuracion_sistema"):
        return request.configuracion_sistema
    if getattr(request, "user", None) and request.user.is_authenticated:
        return ConfiguracionSistema.objects.filter(email=request.user.email).first()
    # Fallback: autenticación por sesión personalizada
    try:
        configuracion_id = request.session.get("configuracion_id")
        if configuracion_id:
            return ConfiguracionSistema.objects.filter(pk=configuracion_id).first()
    except Exception:
        pass
    return None


def _diff_campos(original, nuevo, campos_labels: dict) -> str:
    """
    Compara los atributos de `original` y `nuevo` para los campos indicados.
    Devuelve una cadena tipo "Nombre: «A» → «B»; TRM: «4200» → «5000»".
    `campos_labels` es {field_name: label_display}.
    """
    cambios = []
    for campo, label in campos_labels.items():
        v_old = getattr(original, campo, None)
        v_new = getattr(nuevo, campo, None)
        # Para FKs, comparar PKs
        if hasattr(v_old, "pk"):
            v_old = str(v_old)
        if hasattr(v_new, "pk"):
            v_new = str(v_new)
        if str(v_old or "") != str(v_new or ""):
            cambios.append(f"{label}: «{v_old or '—'}» → «{v_new or '—'}»")
    return "; ".join(cambios) if cambios else ""


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
            configuracion=usuario,
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

        # ── Unidad del usuario en sesión ────────────────────────────────────
        unidad = self.request.session.get("unidad_negocio", "") or ""

        try:
            # Filtrar por unidad si aplica
            qs = Solicitud.objects.select_related("cliente", "creado_por")
            if unidad:
                qs = qs.filter(creado_por__unidad_negocio=unidad)

            by_estado = {
                item["estado"]: item["total"]
                for item in qs.values("estado").annotate(total=Count("id"))
            }

            ctx["total"] = qs.count()
            ctx["por_estado"] = [
                {"label": label, "value": estado, "count": by_estado.get(estado, 0)}
                for estado, label in EstadoSolicitud.choices
            ]

            # Solicitudes recientes de la unidad
            proyecto_prefetch = Prefetch(
                "proyectos",
                Proyecto.objects.filter(es_version_actual=True).only("id", "consecutivo"),
            )
            recientes_qs = list(
                qs.prefetch_related(proyecto_prefetch).order_by("-created_at")[:10]
            )
            for s in recientes_qs:
                actuales = [p for p in s.proyectos.all() if p.es_version_actual]
                s.proyecto_actual = actuales[0] if actuales else None
            ctx["recientes"] = recientes_qs

            # Conteo proyectos de la unidad
            proy_qs = Proyecto.objects.filter(es_version_actual=True)
            if unidad:
                proy_qs = proy_qs.filter(creado_por__unidad_negocio=unidad)
            ctx["total_proyectos"] = proy_qs.count()

            # Conteo despiece y APU
            try:
                from apps.presupuestos.models import ProyectoSistema, APUProyecto
                ps_qs = ProyectoSistema.objects.all()
                apu_qs = APUProyecto.objects.all()
                if unidad:
                    ps_qs = ps_qs.filter(proyecto__creado_por__unidad_negocio=unidad)
                    apu_qs = apu_qs.filter(
                        proyecto_sistema__proyecto__creado_por__unidad_negocio=unidad
                    )
                ctx["total_despieces"] = ps_qs.count()
                ctx["total_apus"] = apu_qs.count()
            except Exception as e:
                logger.warning(f"Error al contar despieces/APUs: {e}")
                ctx["total_despieces"] = 0
                ctx["total_apus"] = 0

            # ── Pendientes de sistema (filtrados por rol) ──────────────────
            rol = self.request.session.get("rol", "")
            pendientes = []
            from django.urls import reverse as _reverse

            # ── Para ASESOR_COMERCIAL y ADMINISTRADOR: solicitudes sin proyecto
            if rol in ("ASESOR_COMERCIAL", "ADMINISTRADOR", "PRESUPUESTOS"):
                sin_proyecto = qs.filter(proyectos__isnull=True).count()
                if sin_proyecto:
                    pendientes.append({
                        "titulo": f"{sin_proyecto} solicitud{'es' if sin_proyecto > 1 else ''} sin proyecto",
                        "descripcion": "Requieren creación de proyecto de presupuesto.",
                        "nivel": "aviso",
                        "url": _reverse("comercial:solicitud_list"),
                    })

            # ── Para PRESUPUESTOS: proyectos listos para iniciar despiece
            if rol == "PRESUPUESTOS":
                sin_despiece = proy_qs.filter(estado="SOLICITUD").count()
                if sin_despiece:
                    pendientes.append({
                        "titulo": f"{sin_despiece} proyecto{'s' if sin_despiece > 1 else ''} para despiece",
                        "descripcion": "Tienes proyectos asignados listos para iniciar el despiece de materiales.",
                        "nivel": "critico" if sin_despiece > 2 else "aviso",
                        "url": None,
                    })
                # Proyectos con despiece en curso (estado DESPIECE)
                en_despiece = proy_qs.filter(estado="DESPIECE").count()
                if en_despiece:
                    pendientes.append({
                        "titulo": f"{en_despiece} proyecto{'s' if en_despiece > 1 else ''} en despiece",
                        "descripcion": "Despiece en progreso. Genera el APU cuando esté listo.",
                        "nivel": "aviso",
                        "url": None,
                    })

            # ── Para ADMINISTRADOR: APUs generados pendientes de aprobación
            if rol == "ADMINISTRADOR":
                pendiente_aprobacion = proy_qs.filter(estado="APU_GENERADO").count()
                if pendiente_aprobacion:
                    pendientes.append({
                        "titulo": f"{pendiente_aprobacion} APU{'s' if pendiente_aprobacion > 1 else ''} pendiente{'s' if pendiente_aprobacion > 1 else ''} de aprobación",
                        "descripcion": "El área de Presupuestos confirmó los APUs. Requieren tu aprobación.",
                        "nivel": "critico",
                        "url": None,
                    })

            ctx["pendientes_sistema"] = pendientes
            ctx["rol_usuario"] = rol
            ctx["create_form"] = SolicitudForm()

        except Exception as e:
            logger.error(f"Error en DashboardView.get_context_data: {e}", exc_info=True)
            ctx["total"] = 0
            ctx["por_estado"] = []
            ctx["recientes"] = []
            ctx["total_proyectos"] = 0
            ctx["total_despieces"] = 0
            ctx["total_apus"] = 0
            ctx["pendientes_sistema"] = []

        return ctx


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------

class ClienteListView(UnidadFilterMixin, WithCreateFormMixin, ListView):
    model = Cliente
    form_class = ClienteConContactoForm
    template_name = "comercial/cliente_list.html"
    context_object_name = "clientes"
    ordering = ["razon_social"]
    unidad_field = "unidad_negocio"

    def get_queryset(self):
        # ADMINISTRADOR ve todos los clientes sin filtro de unidad
        rol = self.request.session.get("rol", "")
        if rol == "ADMINISTRADOR":
            return Cliente.objects.order_by("razon_social").prefetch_related("contactos")
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
        self.object = form.save(commit=False)
        # Asignar unidad de negocio desde la sesión
        unidad = self.request.session.get("unidad_negocio", "") or ""
        if unidad and not self.object.unidad_negocio:
            self.object.unidad_negocio = unidad
        self.object.save()
        form.save_m2m()
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
    template_name = "confirm_delete.html"
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
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("comercial:contacto_list")


# ---------------------------------------------------------------------------
# Solicitudes
# ---------------------------------------------------------------------------

class SolicitudListView(UnidadFilterMixin, WithCreateFormMixin, ListView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_list.html"
    context_object_name = "solicitudes"
    ordering = ["-created_at"]
    unidad_field = "creado_por__unidad_negocio"


class SolicitudDetailView(DetailView):
    model = Solicitud
    template_name = "comercial/solicitud_detail.html"
    context_object_name = "solicitud"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        solicitud = self.object
        ctx["archivos"] = solicitud.archivos.select_related("configuracion").all()

        # Proyectos / versiones vinculadas a esta solicitud
        ctx["proyectos"] = solicitud.proyectos.select_related(
            "tipo_proyecto", "creado_por"
        ).order_by("-version")
        ctx["proyecto_actual"] = solicitud.proyectos.filter(
            es_version_actual=True
        ).first()

        # Logs directos de la solicitud + logs de cualquier proyecto vinculado
        from django.db.models import Q as _Q
        proyecto_pks = list(solicitud.proyectos.values_list("pk", flat=True))
        ctx["logs"] = (
            LogSistema.objects.filter(
                _Q(modelo_afectado="Solicitud", objeto_id=solicitud.pk)
                | _Q(modelo_afectado__in=["Proyecto", "Despiece", "APU"], objeto_id__in=proyecto_pks)
            )
            .select_related("configuracion")
            .order_by("-created_at")[:100]
        )
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
        messages.success(
            self.request,
            f"Solicitud {self.object.consecutivo} creada. Ahora puede adjuntar archivos."
        )
        # Redirigir al formulario de edición para permitir adjuntar archivos
        from django.urls import reverse
        return redirect(reverse("comercial:solicitud_update", kwargs={"pk": self.object.pk}))


class SolicitudUpdateView(UpdateView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_form.html"
    success_url = reverse_lazy("comercial:solicitud_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["archivos"] = self.object.archivos.select_related("configuracion").all()
        return ctx

    def form_valid(self, form):
        self.object = form.save(commit=False)
        # Proteger campos de sistema
        original = Solicitud.objects.get(pk=self.object.pk)
        self.object.estado = original.estado
        self.object.creado_por_id = original.creado_por_id

        diff = _diff_campos(original, self.object, {
            "nombre": "Nombre",
            "consecutivo": "Consecutivo",
            "fecha_entrega": "Fecha entrega",
            "cliente": "Cliente",
            "descripcion": "Descripción",
            "observaciones": "Observaciones",
            "link_salesforce": "Link Salesforce",
        })

        self.object.save()
        form.save_m2m()
        registrar_log(
            self.request,
            accion="EDITAR_SOLICITUD",
            descripcion=(
                f"Solicitud {self.object.consecutivo} actualizada"
                + (f" — Cambios: {diff}" if diff else " (sin cambios en campos principales)")
            ),
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
        self.object.configuracion = _usuario_sistema(self.request)
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
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("comercial:tipoproyecto_list")


# ---------------------------------------------------------------------------
# Proyectos
# ---------------------------------------------------------------------------

class ProyectoListView(UnidadFilterMixin, ListView):
    model = Proyecto
    template_name = "comercial/proyecto_list.html"
    context_object_name = "proyectos"
    ordering = ["-created_at"]
    unidad_field = "creado_por__unidad_negocio"


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
        trm_cambio = original.trm != form.cleaned_data.get("trm", original.trm)

        diff = _diff_campos(original, self.object, {
            "nombre": "Nombre",
            "trm": "TRM",
            "area_total_m2": "Área (m²)",
            "perimetro_ml": "Perímetro (ml)",
            "dias_duracion": "Días",
            "num_personas": "Personas",
            "margen_comercial_pct": "Margen comercial",
            "iva_pct": "IVA",
            "aiu_pct": "AIU",
            "moneda": "Moneda",
            "tipo_proyecto": "Tipo proyecto",
        })

        self.object.consecutivo = original.consecutivo
        self.object.estado = original.estado
        self.object.creado_por_id = original.creado_por_id
        self.object.save()
        form.save_m2m()

        # Si cambió la TRM, recapturar precios de materiales en dólares en el despiece
        if trm_cambio:
            try:
                from apps.presupuestos.models import DespieceLinea
                lineas_usd = DespieceLinea.objects.filter(
                    proyecto_sistema__proyecto=self.object,
                    producto__precio_en_dolares=True,
                ).select_related("producto", "proyecto_sistema__proyecto")
                for linea in lineas_usd:
                    linea.capturar_precio()
            except Exception:
                pass

        registrar_log(
            self.request,
            accion="EDITAR_PROYECTO",
            descripcion=(
                f"Proyecto {self.object.consecutivo} actualizado"
                + (f" — Cambios: {diff}" if diff else "")
                + (" · TRM recalculó precios USD" if trm_cambio else "")
            ),
            modelo_afectado="Proyecto",
            objeto_id=self.object.pk,
        )
        messages.success(self.request, "Proyecto actualizado correctamente.")
        return HttpResponseRedirect(self.get_success_url())


class ProyectoDeleteView(DeleteView):
    model = Proyecto
    template_name = "confirm_delete.html"
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
        from django.db.models import Q as _Q
        usuario = _usuario_sistema(self.request)
        if not usuario:
            return LogSistema.objects.none()
        qs = (
            LogSistema.objects
            .filter(unidad_negocio=usuario.unidad_negocio)
            .select_related("configuracion")
            .order_by("-created_at")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                _Q(accion__icontains=q)
                | _Q(descripcion__icontains=q)
                | _Q(modelo_afectado__icontains=q)
            )
        return qs
