"""apps/comercial/views.py — Vistas del módulo comercial."""

import logging
from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.db.models import ProtectedError
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views import View
from apps.common.apu_lock import objeto_bloqueado_por_apu, MENSAJE_BLOQUEO
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView,
)
from .models import Cliente, ContactoCliente, TipoProyecto, Solicitud, SolicitudArchivo, Proyecto, LogSistema
from .forms import (
    ClienteConContactoForm, ContactoClienteForm,
    TipoProyectoForm, SolicitudForm, SolicitudArchivoForm,
    ProyectoForm, ProyectoFromSolicitudForm,
)
from apps.common.mixins import (
    WithCreateFormMixin, UnidadFilterMixin, UnidadObjectAccessMixin,
    AdminRequiredMixin, AdminGerenteRequiredMixin, GestionComercialMixin,
    RolRequeridoMixin, ROLES_GESTION_COMERCIAL,
)
from apps.common.choices import EstadoSolicitud
from apps.common.auth import puede_gestionar_unidad as _puede_gestionar_unidad

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
    # Fallback: autenticación por sesión personalizada del proyecto
    try:
        # Fase 12.2 — la clave real seteada por el login es "usuario_id".
        # Mantenemos "configuracion_id" como fallback histórico.
        usuario_id = request.session.get("usuario_id") or request.session.get("configuracion_id")
        if usuario_id:
            return ConfiguracionSistema.objects.filter(pk=usuario_id).first()
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
        # Fase 12.3 ext: ADMINISTRADOR ve global (unidad efectiva = "").
        from apps.common.auth import unidad_efectiva as _unidad_efectiva
        unidad = _unidad_efectiva(self.request)

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
            ctx["create_form"] = SolicitudForm(unidad_negocio=unidad)

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


class ClienteDetailView(UnidadObjectAccessMixin, DetailView):
    model = Cliente
    template_name = "comercial/cliente_list.html"
    context_object_name = "cliente"


class ClienteCreateView(GestionComercialMixin, CreateView):
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


class ClienteUpdateView(GestionComercialMixin, UpdateView):
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


class ClienteDeleteView(AdminGerenteRequiredMixin, DeleteView):
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


class ContactoCreateView(GestionComercialMixin, CreateView):
    model = ContactoCliente
    form_class = ContactoClienteForm
    template_name = "comercial/contacto_form.html"
    success_url = reverse_lazy("comercial:contacto_list")


class ContactoUpdateView(GestionComercialMixin, UpdateView):
    model = ContactoCliente
    form_class = ContactoClienteForm
    template_name = "comercial/contacto_form.html"
    success_url = reverse_lazy("comercial:contacto_list")


class ContactoDeleteView(AdminGerenteRequiredMixin, DeleteView):
    model = ContactoCliente
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("comercial:contacto_list")


# ---------------------------------------------------------------------------
# Solicitudes
# ---------------------------------------------------------------------------

class SolicitudListView(GestionComercialMixin, UnidadFilterMixin, WithCreateFormMixin, ListView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_list.html"
    context_object_name = "solicitudes"
    ordering = ["-created_at"]
    unidad_field = "creado_por__unidad_negocio"
    paginate_by = 50

    def get_queryset(self):
        from django.db.models import Q as _Q
        qs = super().get_queryset().select_related("cliente", "creado_por")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                _Q(consecutivo__icontains=q)
                | _Q(nombre__icontains=q)
                | _Q(cliente__razon_social__icontains=q)
            )
        estado = self.request.GET.get("estado", "").strip()
        if estado:
            qs = qs.filter(estado=estado)
        responsable = self.request.GET.get("responsable", "").strip()
        if responsable:
            qs = qs.filter(creado_por__pk=responsable)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.configuracion.models import ConfiguracionSistema
        ctx["q"] = self.request.GET.get("q", "")
        ctx["estado_filtro"] = self.request.GET.get("estado", "")
        ctx["responsable_filtro"] = self.request.GET.get("responsable", "")
        ctx["estados"] = EstadoSolicitud.choices
        ctx["responsables"] = (
            ConfiguracionSistema.objects
            .filter(solicitudes_creadas__isnull=False)
            .distinct()
            .order_by("nombre_completo")
        )
        # Sobrescribir create_form con filtro de unidad de negocio
        unidad = self.request.session.get("unidad_negocio", "") or ""
        ctx["create_form"] = SolicitudForm(unidad_negocio=unidad)

        # ── Panel master-detail: cargar detalle de la solicitud seleccionada
        # vía ?sel=<pk>. Respeta los gates de unidad de SolicitudDetailView —
        # si el usuario no puede gestionar la unidad del objeto, el panel
        # derecho queda vacío sin filtrar la lista.
        sel_raw = self.request.GET.get("sel", "")
        sel_pk = int(sel_raw) if sel_raw.isdigit() else None
        ctx["sel_pk"] = sel_pk
        ctx["solicitud_sel"] = None
        if sel_pk:
            sel = Solicitud.objects.select_related(
                "cliente", "creado_por", "contacto"
            ).filter(pk=sel_pk).first()
            if sel is not None:
                # Unidad efectiva del objeto: usa la del modelo y, si está vacía,
                # cae al creador — consistente con el filtro por
                # `creado_por__unidad_negocio` que aplica UnidadFilterMixin a la
                # lista. Sin este fallback, una solicitud visible en la lista
                # podía rechazarse al seleccionarla.
                unidad_obj = (getattr(sel, "unidad_negocio", "") or "") or (
                    getattr(sel.creado_por, "unidad_negocio", "") if sel.creado_por_id else ""
                )
                # Bypass del creador: si el usuario actual creó la solicitud,
                # puede verla (igual que UnidadObjectAccessMixin).
                from apps.common.auth import get_usuario_actual
                usuario_actual = get_usuario_actual(self.request)
                es_creador = (
                    usuario_actual is not None
                    and sel.creado_por_id == usuario_actual.pk
                )
                if es_creador or _puede_gestionar_unidad(self.request, unidad_obj):
                    ctx["solicitud_sel"] = sel
                    ctx.update(build_solicitud_detail_context(self.request, sel))
        return ctx


def build_solicitud_detail_context(request, solicitud):
    """
    Construye el contexto del detalle de una Solicitud para ser usado tanto por
    `SolicitudDetailView` (URL directa) como por `SolicitudListView` cuando hay
    `?sel=<pk>` (panel master-detail). No duplica lógica.

    Devuelve un dict listo para mezclar en el contexto del template.
    """
    from apps.ingenieria.models import DespieceMaestro
    from apps.presupuestos.models import (
        ProyectoSistema, APUProyecto, APUDespieceIncluido,
    )
    from apps.presupuestos.models import APUProyecto as _APU
    from django.db.models import Q as _Q
    from apps.common.auth import puede_devolver_solicitud

    ctx = {"solicitud": solicitud}
    ctx["archivos"] = solicitud.archivos.select_related("configuracion").all()

    proyectos_qs = list(
        solicitud.proyectos.select_related("tipo_proyecto", "creado_por").order_by("-version")
    )
    proyectos_data = []
    for p in proyectos_qs:
        despieces_raw = list(
            DespieceMaestro.objects.filter(proyecto=p)
            .select_related("subsistema", "subsistema__sistema")
            .order_by("-updated_at")
        )
        apus_map = {}
        despieces_sin_apu = []
        for dm in despieces_raw:
            apu = None
            try:
                # Match preciso: la relación APUDespieceIncluido es la fuente
                # de verdad de "qué despiece está en qué APU". Antes se usaba
                # matching por (proyecto, sistema, subsistema), lo que agrupaba
                # erróneamente a TODOS los despieces de un mismo subsistema en
                # el primer APU del subsistema — bloqueando la generación de
                # APUs adicionales desde otros despieces.
                inc = (
                    APUDespieceIncluido.objects
                    .filter(despiece_maestro=dm, activo=True)
                    .select_related("apu", "apu__aprobado_por")
                    .first()
                )
                if inc and inc.apu:
                    apu = inc.apu
                else:
                    # Fallback legacy: datos antiguos sin APUDespieceIncluido.
                    # Solo asigna si hay UN APU para ese subsistema; si hay 0,
                    # va a "sin APU"; si hay 1, lo asocia (compatibilidad).
                    ps = ProyectoSistema.objects.filter(
                        proyecto=p,
                        sistema=dm.subsistema.sistema,
                        subsistema=dm.subsistema,
                    ).first()
                    if ps:
                        existing_apus = list(
                            APUProyecto.objects
                            .filter(proyecto_sistema=ps)
                            .select_related("aprobado_por")
                        )
                        if len(existing_apus) == 1 and not APUDespieceIncluido.objects.filter(apu=existing_apus[0]).exists():
                            apu = existing_apus[0]
            except Exception:
                apu = None
            if apu:
                bucket = apus_map.setdefault(apu.pk, {"apu": apu, "despieces": []})
                bucket["despieces"].append(dm)
            else:
                despieces_sin_apu.append(dm)
        apus_data = list(apus_map.values())
        # Consolidación disponible si el proyecto tiene 2+ despieces guardados
        # o 2+ APUs ya generados. Cubre los dos escenarios típicos: usuario que
        # todavía no genera APUs pero quiere ver el flujo, y usuario con APUs
        # listos para unir.
        despieces_guardados_count = sum(
            1 for dm in despieces_raw if dm.esta_guardado
        )
        proyectos_data.append({
            "proy": p,
            "apus_data": apus_data,
            "despieces_sin_apu": despieces_sin_apu,
            "puede_consolidar": (
                despieces_guardados_count >= 2 or len(apus_data) >= 2
            ),
        })
    ctx["proyectos"] = proyectos_qs
    ctx["proyectos_data"] = proyectos_data
    ctx["proyecto_actual"] = next((p for p in proyectos_qs if p.es_version_actual), None)

    proyecto_pks_resumen = [p.pk for p in proyectos_qs]
    apus_qs = _APU.objects.filter(
        Q(proyecto_sistema__proyecto_id__in=proyecto_pks_resumen) |
        Q(proyecto_id__in=proyecto_pks_resumen)
    )
    ctx["apu_resumen"] = {
        "total": apus_qs.count(),
        "individuales": apus_qs.filter(
            tipo_apu=_APU.TipoAPUConsolidacion.INDIVIDUAL).count(),
        "consolidados": apus_qs.filter(
            tipo_apu=_APU.TipoAPUConsolidacion.CONSOLIDADO).count(),
        "aprobados": apus_qs.exclude(
            modalidad_aiu_seleccionada__isnull=True).exclude(
            modalidad_aiu_seleccionada="").count(),
        "en_revision": apus_qs.filter(
            modalidad_aiu_seleccionada__isnull=True,
            fecha_envio_revision__isnull=False).count(),
    }

    proyecto_pks = [p.pk for p in proyectos_qs]
    ctx["logs"] = (
        LogSistema.objects.filter(
            _Q(modelo_afectado="Solicitud", objeto_id=solicitud.pk)
            | _Q(modelo_afectado__in=["Proyecto", "Despiece", "APU"], objeto_id__in=proyecto_pks)
        )
        .select_related("configuracion")
        .order_by("-created_at")[:100]
    )
    _proyecto_initial = {"nombre": solicitud.nombre, "descripcion": solicitud.descripcion}
    try:
        from apps.common.trm_service import obtener_trm_vigente
        _proyecto_initial["trm"] = obtener_trm_vigente()
    except Exception:
        pass  # TRM no disponible; el usuario la ingresa manualmente en el modal
    ctx["proyecto_form"] = ProyectoFromSolicitudForm(initial=_proyecto_initial)
    ultima = solicitud.proyectos.order_by("-version").first()
    ctx["proxima_version"] = (ultima.version + 1) if ultima else 1
    ctx["puede_devolver"] = puede_devolver_solicitud(request, solicitud)
    return ctx


class SolicitudDetailView(View):
    """
    Redirige la URL legacy /solicitudes/<pk>/ al panel master-detail
    /solicitudes/?sel=<pk>. Conserva bookmarks y enlaces internos sin
    duplicar pantallas. Los gates de unidad los aplica el panel.
    """
    def get(self, request, pk, *args, **kwargs):
        from django.urls import reverse
        url = reverse("comercial:solicitud_list") + f"?sel={pk}"
        return redirect(url)


class SolicitudCreateView(GestionComercialMixin, CreateView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["unidad_negocio"] = self.request.session.get("unidad_negocio", "") or ""
        return kwargs

    def form_valid(self, form):
        # El archivo adjunto es OPCIONAL: la solicitud se crea con o sin archivos.
        archivos = self.request.FILES.getlist("archivos")
        self.object = form.save(commit=False)
        self.object.creado_por = _usuario_sistema(self.request)
        self.object.save()
        form.save_m2m()
        usuario = _usuario_sistema(self.request)
        for archivo in archivos:
            SolicitudArchivo.objects.create(
                solicitud=self.object,
                archivo=archivo,
                nombre=archivo.name,
                configuracion=usuario,
            )
        registrar_log(
            self.request,
            accion="CREAR_SOLICITUD",
            descripcion=(
                f"Solicitud {self.object.consecutivo} — {self.object.nombre} "
                f"({len(archivos)} archivo(s) adjunto(s))"
            ),
            modelo_afectado="Solicitud",
            objeto_id=self.object.pk,
        )
        if archivos:
            msg = f"Solicitud {self.object.consecutivo} creada con {len(archivos)} archivo(s)."
        else:
            msg = f"Solicitud {self.object.consecutivo} creada (sin archivos adjuntos)."
        messages.success(self.request, msg)
        return redirect("comercial:solicitud_detail", pk=self.object.pk)


class SolicitudUpdateView(GestionComercialMixin, UpdateView):
    model = Solicitud
    form_class = SolicitudForm
    template_name = "comercial/solicitud_form.html"

    def dispatch(self, request, *args, **kwargs):
        # Solo lectura si algún APU de la solicitud ya fue aprobado.
        self.object = self.get_object()
        if objeto_bloqueado_por_apu(self.object):
            messages.error(request, MENSAJE_BLOQUEO)
            return redirect("comercial:solicitud_detail", pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["unidad_negocio"] = self.request.session.get("unidad_negocio", "") or ""
        return kwargs

    def get_success_url(self):
        return reverse_lazy("comercial:solicitud_detail", kwargs={"pk": self.object.pk})

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


class SolicitudDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        from apps.common.auth import es_admin, get_usuario_actual
        solicitud = get_object_or_404(Solicitud, pk=pk)
        consecutivo = solicitud.consecutivo
        # Bloqueo de solo lectura: si hay un APU aprobado, solo el admin global
        # puede eliminar (escape hatch). El resto queda bloqueado.
        if objeto_bloqueado_por_apu(solicitud) and not es_admin(request):
            messages.error(request, MENSAJE_BLOQUEO)
            return redirect("comercial:solicitud_detail", pk=solicitud.pk)
        try:
            if es_admin(request):
                # Servicio explícito: elimina proyectos → APUs → cotizaciones
                # → consolidados en orden controlado. Sin introspección.
                from apps.comercial.services.admin_eliminacion import (
                    eliminar_solicitud_admin,
                )
                eliminar_solicitud_admin(solicitud, usuario=get_usuario_actual(request))
            else:
                solicitud.delete()
        except ProtectedError:
            messages.error(
                request,
                f"La solicitud {consecutivo} no puede eliminarse porque tiene "
                "proyectos, APUs o cotizaciones asociadas. Para conservar la "
                "trazabilidad, puede archivarla.",
            )
            return redirect("comercial:solicitud_detail", pk=pk)
        except Exception as exc:
            logger.exception("[SolicitudDeleteView] Error eliminando %s", consecutivo)
            messages.error(
                request,
                f"No se pudo eliminar la solicitud {consecutivo}: {exc}",
            )
            return redirect("comercial:solicitud_detail", pk=pk)
        registrar_log(
            request,
            accion="ELIMINAR_SOLICITUD",
            descripcion=f"Solicitud {consecutivo} eliminada",
            modelo_afectado="Solicitud",
            objeto_id=pk,
        )
        messages.success(request, f"Solicitud {consecutivo} eliminada.")
        return redirect("comercial:solicitud_list")


class SolicitudDevolverView(View):
    """
    POST /comercial/solicitudes/<pk>/devolver/

    Devuelve la solicitud para ajustes internos del presupuesto.
    No es un rechazo comercial: el cliente no aparece en este flujo.
    """

    def post(self, request, pk, *args, **kwargs):
        from apps.common.auth import puede_devolver_solicitud
        solicitud = get_object_or_404(Solicitud, pk=pk)

        # Fase 12.2 — Gate de permisos
        if not puede_devolver_solicitud(request, solicitud):
            registrar_log(
                request, accion="APROBACION_DENEGADA",
                descripcion=f"Intento no autorizado de devolver Solicitud {solicitud.pk}.",
                modelo_afectado="Solicitud", objeto_id=pk,
            )
            messages.error(
                request,
                "No tiene permiso para devolver esta solicitud. Solo el "
                "aprobador asignado puede realizar esta acción.",
            )
            return redirect("comercial:solicitud_detail", pk=pk)

        motivo = (request.POST.get("motivo") or "").strip()
        if not motivo:
            messages.error(
                request,
                "Debe indicar un motivo para devolver la solicitud.",
            )
            return redirect("comercial:solicitud_detail", pk=pk)

        solicitud.estado = EstadoSolicitud.DEVUELTA
        solicitud.motivo_devolucion = motivo
        solicitud.save(update_fields=["estado", "motivo_devolucion", "updated_at"])
        registrar_log(
            request,
            accion="DEVOLVER_SOLICITUD",
            descripcion=(
                f"Solicitud {solicitud.consecutivo} devuelta para ajustes. "
                f"Motivo: {motivo}"
            ),
            modelo_afectado="Solicitud",
            objeto_id=pk,
        )
        messages.success(request, "Solicitud devuelta para ajustes.")
        return redirect("comercial:solicitud_detail", pk=pk)


class SolicitudArchivarView(AdminGerenteRequiredMixin, View):
    """POST: archiva (estado=CERRADA) una solicitud preservando trazabilidad."""

    def post(self, request, pk, *args, **kwargs):
        solicitud = get_object_or_404(Solicitud, pk=pk)
        if solicitud.estado == EstadoSolicitud.CERRADA:
            messages.info(request, f"La solicitud {solicitud.consecutivo} ya estaba archivada.")
            return redirect("comercial:solicitud_detail", pk=pk)
        solicitud.estado = EstadoSolicitud.CERRADA
        solicitud.save(update_fields=["estado", "updated_at"])
        registrar_log(
            request,
            accion="ARCHIVAR_SOLICITUD",
            descripcion=f"Solicitud {solicitud.consecutivo} archivada (CERRADA)",
            modelo_afectado="Solicitud",
            objeto_id=pk,
        )
        messages.success(request, f"Solicitud {solicitud.consecutivo} archivada.")
        return redirect("comercial:solicitud_detail", pk=pk)


# ---------------------------------------------------------------------------
# Archivos de Solicitud
# ---------------------------------------------------------------------------

class SolicitudArchivoCreateView(GestionComercialMixin, CreateView):
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


class SolicitudArchivoDeleteView(GestionComercialMixin, View):
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


class TipoProyectoCreateView(AdminRequiredMixin, CreateView):
    model = TipoProyecto
    form_class = TipoProyectoForm
    template_name = "comercial/tipoproyecto_form.html"
    success_url = reverse_lazy("comercial:tipoproyecto_list")


class TipoProyectoUpdateView(AdminRequiredMixin, UpdateView):
    model = TipoProyecto
    form_class = TipoProyectoForm
    template_name = "comercial/tipoproyecto_form.html"
    success_url = reverse_lazy("comercial:tipoproyecto_list")


class TipoProyectoDeleteView(AdminRequiredMixin, DeleteView):
    model = TipoProyecto
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("comercial:tipoproyecto_list")


# ---------------------------------------------------------------------------
# Proyectos
# ---------------------------------------------------------------------------

class ProyectoListView(View):
    """Redirige a solicitudes — los proyectos viven dentro de solicitudes."""
    def get(self, request, *args, **kwargs):
        return redirect("comercial:solicitud_list")


class ProyectoDetailView(UnidadObjectAccessMixin, DetailView):
    model = Proyecto
    template_name = "comercial/proyecto_detail.html"
    context_object_name = "proyecto"

    def get_unidad_del_objeto(self, obj):
        # Proyecto se asocia por creado_por.unidad_negocio
        creado_por = getattr(obj, "creado_por", None)
        if creado_por is not None:
            return getattr(creado_por, "unidad_negocio", "") or ""
        return ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = self.object

        # ── Despieces Maestro asociados al proyecto ────────────────────────────
        try:
            from apps.ingenieria.models import DespieceMaestro
            from apps.presupuestos.models import (
                ProyectoSistema, APUProyecto, APUDespieceIncluido,
            )
            despieces_raw = list(
                proyecto.despieces_maestro
                .select_related("subsistema", "subsistema__sistema")
                .order_by("-updated_at")
            )
            # Agrupar por APU usando APUDespieceIncluido (fuente de verdad).
            # Antes se usaba matching (proyecto, sistema, subsistema), que
            # asignaba erróneamente todos los despieces de un subsistema al
            # primer APU del subsistema, bloqueando el botón "Gen. APU" del
            # segundo despiece.
            apus_map = {}        # apu.pk -> {"apu": apu, "despieces": [dm,...]}
            despieces_sin_apu = []
            for dm in despieces_raw:
                apu = None
                try:
                    inc = (
                        APUDespieceIncluido.objects
                        .filter(despiece_maestro=dm, activo=True)
                        .select_related("apu", "apu__aprobado_por")
                        .first()
                    )
                    if inc and inc.apu:
                        apu = inc.apu
                    else:
                        # Fallback legacy: dato antiguo sin APUDespieceIncluido.
                        ps_legacy = ProyectoSistema.objects.filter(
                            proyecto=proyecto,
                            sistema=dm.subsistema.sistema,
                            subsistema=dm.subsistema,
                        ).first()
                        if ps_legacy:
                            existing_apus = list(
                                APUProyecto.objects
                                .filter(proyecto_sistema=ps_legacy)
                                .select_related("aprobado_por")
                            )
                            if len(existing_apus) == 1 and not APUDespieceIncluido.objects.filter(apu=existing_apus[0]).exists():
                                apu = existing_apus[0]
                except Exception:
                    apu = None
                if apu:
                    bucket = apus_map.setdefault(apu.pk, {"apu": apu, "despieces": []})
                    bucket["despieces"].append(dm)
                else:
                    despieces_sin_apu.append(dm)
            ctx["apus_data"] = list(apus_map.values())
            ctx["despieces_sin_apu"] = despieces_sin_apu
            ctx["total_despieces"] = len(despieces_raw)
            # Fase 11.5 — APUs consolidados del proyecto (opcionales)
            ctx["apus_consolidados"] = list(
                APUProyecto.objects
                .filter(proyecto=proyecto,
                        tipo_apu=APUProyecto.TipoAPUConsolidacion.CONSOLIDADO)
                .prefetch_related("origenes_consolidado__apu_origen")
                .order_by("-created_at")
            )
            despieces_guardados_count = sum(
                1 for dm in despieces_raw if dm.esta_guardado
            )
            ctx["puede_consolidar"] = (
                despieces_guardados_count >= 2 or len(apus_map) >= 2
            )
            # APUs guardados para el presupuesto del proyecto
            try:
                ctx["n_apus_guardados"] = APUProyecto.objects.filter(
                    proyecto_sistema__proyecto=proyecto,
                    cantidad_base_apu__isnull=False,
                    archivado=False,
                ).count()
            except Exception:
                ctx["n_apus_guardados"] = 0
        except Exception:
            ctx["apus_data"] = []
            ctx["despieces_sin_apu"] = []
            ctx["total_despieces"] = 0
            ctx["apus_consolidados"] = []
            ctx["puede_consolidar"] = False

        # ── Otras versiones de la misma solicitud ─────────────────────────────
        if proyecto.solicitud_id:
            ctx["otras_versiones"] = (
                proyecto.solicitud.proyectos
                .exclude(pk=proyecto.pk)
                .order_by("-version")
            )
        else:
            ctx["otras_versiones"] = Proyecto.objects.none()
        return ctx


class ProyectoCreateView(GestionComercialMixin, CreateView):
    model = Proyecto
    form_class = ProyectoForm
    template_name = "comercial/proyecto_form.html"

    def get_initial(self):
        initial = super().get_initial()
        try:
            from apps.common.trm_service import obtener_trm_vigente
            initial["trm"] = obtener_trm_vigente()
        except Exception:
            pass  # TRM no disponible; el usuario debe ingresar el valor manualmente
        return initial

    def get_success_url(self):
        if self.object.solicitud_id:
            return reverse_lazy("comercial:solicitud_detail", kwargs={"pk": self.object.solicitud_id})
        return reverse_lazy("comercial:proyecto_detail", kwargs={"pk": self.object.pk})

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


class ProyectoUpdateView(GestionComercialMixin, UpdateView):
    model = Proyecto
    form_class = ProyectoForm
    template_name = "comercial/proyecto_form.html"

    def get_success_url(self):
        if self.object.solicitud_id:
            return reverse_lazy("comercial:solicitud_detail", kwargs={"pk": self.object.solicitud_id})
        return reverse_lazy("comercial:proyecto_detail", kwargs={"pk": self.object.pk})

    def dispatch(self, request, *args, **kwargs):
        # Solo lectura si el proyecto tiene un APU aprobado.
        self.object = self.get_object()
        if objeto_bloqueado_por_apu(self.object):
            messages.error(request, MENSAJE_BLOQUEO)
            return redirect("comercial:proyecto_detail", pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        self.object = form.save(commit=False)
        original = Proyecto.objects.get(pk=self.object.pk)
        trm_cambio = original.trm != form.cleaned_data.get("trm", original.trm)

        diff = _diff_campos(original, self.object, {
            "nombre": "Nombre",
            "trm": "TRM",
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


class ProyectoDeleteView(AdminRequiredMixin, DeleteView):
    model = Proyecto
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("comercial:solicitud_list")

    def post(self, request, *args, **kwargs):
        from apps.common.auth import es_admin, get_usuario_actual
        self.object = self.get_object()
        consecutivo = self.object.consecutivo
        pk = self.object.pk
        # Bloqueo de solo lectura: con APU aprobado, solo el admin global elimina.
        if objeto_bloqueado_por_apu(self.object) and not es_admin(request):
            messages.error(request, MENSAJE_BLOQUEO)
            return redirect("comercial:proyecto_detail", pk=pk)
        try:
            if es_admin(request):
                from apps.comercial.services.admin_eliminacion import (
                    eliminar_proyecto_admin,
                )
                eliminar_proyecto_admin(self.object, usuario=get_usuario_actual(request))
            else:
                self.object.delete()
        except ProtectedError:
            messages.error(
                request,
                f"El proyecto {consecutivo} no puede eliminarse "
                "porque tiene despieces, APUs o cotizaciones asociadas. "
                "Puede anularlo para conservar la trazabilidad.",
            )
            return redirect("comercial:proyecto_detail", pk=pk)
        except Exception as exc:
            logger.exception("[ProyectoDeleteView] Error eliminando %s", consecutivo)
            messages.error(
                request,
                f"No se pudo eliminar el proyecto {consecutivo}: {exc}",
            )
            return redirect("comercial:proyecto_detail", pk=pk)
        messages.success(request, f"Proyecto {consecutivo} eliminado.")
        return redirect(self.success_url)


class ProyectoAnularView(AdminGerenteRequiredMixin, View):
    """POST: anula (estado=ANULADO) un proyecto preservando trazabilidad."""

    def post(self, request, pk, *args, **kwargs):
        from apps.common.choices import EstadoProyecto
        proyecto = get_object_or_404(Proyecto, pk=pk)
        if proyecto.estado == EstadoProyecto.ANULADO:
            messages.info(request, f"El proyecto {proyecto.consecutivo} ya estaba anulado.")
            return redirect("comercial:proyecto_detail", pk=pk)
        proyecto.estado = EstadoProyecto.ANULADO
        proyecto.save(update_fields=["estado", "updated_at"])
        registrar_log(
            request,
            accion="ANULAR_PROYECTO",
            descripcion=f"Proyecto {proyecto.consecutivo} v{proyecto.version} anulado",
            modelo_afectado="Proyecto",
            objeto_id=pk,
        )
        messages.success(request, f"Proyecto {proyecto.consecutivo} anulado.")
        return redirect("comercial:proyecto_detail", pk=pk)


class CrearProyectoDesdeSolicitudView(GestionComercialMixin, CreateView):
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
        initial = {"nombre": solicitud.nombre, "descripcion": solicitud.descripcion}
        try:
            from apps.common.trm_service import obtener_trm_vigente
            initial["trm"] = obtener_trm_vigente()
        except Exception:
            pass  # TRM no disponible; el usuario debe ingresar el valor manualmente
        return initial

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
# Clonar proyecto como nueva versión
# ---------------------------------------------------------------------------

class ClonarProyectoComoVersionView(GestionComercialMixin, View):
    """
    POST /comercial/proyectos/<pk>/clonar/
    Clona el proyecto indicado como nueva versión dentro de la misma solicitud.
    Redirige al detalle del nuevo proyecto.
    """
    def post(self, request, pk, *args, **kwargs):
        proyecto_base = get_object_or_404(Proyecto, pk=pk)
        if not proyecto_base.solicitud_id:
            messages.error(request, "Este proyecto no está vinculado a una solicitud y no puede clonarse como versión.")
            return redirect("comercial:proyecto_detail", pk=pk)
        from apps.presupuestos.services.proyecto_service import clonar_proyecto_como_version
        usuario = _usuario_sistema(request)
        nuevo = clonar_proyecto_como_version(proyecto_base, usuario)
        messages.success(
            request,
            f"Versión {nuevo.consecutivo} v{nuevo.version} creada como copia de v{proyecto_base.version}.",
        )
        return redirect("comercial:proyecto_detail", pk=nuevo.pk)


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


