"""apps/common/mixins.py — Mixins reutilizables para vistas Django."""

from django.contrib import messages
from django.shortcuts import redirect


# ---------------------------------------------------------------------------
# Mixin: acceso exclusivo para rol ADMINISTRADOR
# ---------------------------------------------------------------------------

class AdminRequiredMixin:
    """
    Requiere que el usuario en sesión tenga rol ADMINISTRADOR.
    Redirige al dashboard con mensaje de error si no cumple.
    """
    def dispatch(self, request, *args, **kwargs):
        rol = request.session.get("rol", "")
        if rol != "ADMINISTRADOR":
            messages.error(
                request,
                "Solo el rol Administrador puede acceder a esta sección."
            )
            return redirect("comercial:dashboard")
        return super().dispatch(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Mixin: aislamiento por unidad de negocio
# ---------------------------------------------------------------------------

class UnidadFilterMixin:
    """
    Filtra el queryset de cualquier vista para mostrar solo los registros
    de la unidad de negocio del usuario en sesión.

    Soporta tres patrones de campo:
      1. unidad_negocio  — campo directo en el modelo (Cliente, LogSistema, etc.)
      2. creado_por__unidad_negocio — FK a ConfiguracionSistema (Solicitud, Proyecto)
      3. Sin campo — no filtra (fallback seguro)

    Además expone `_unidad_sesion()` para usarlo en get_context_data().
    """

    # Subclases pueden sobreescribir para elegir el lookup:
    unidad_field = None  # Ej: "unidad_negocio" o "creado_por__unidad_negocio"

    def _unidad_sesion(self):
        """Retorna la unidad de negocio efectiva (Fase 12.3 ext).
        ADMINISTRADOR → "" (global). Resto → session["unidad_negocio"].
        """
        # Import diferido para evitar ciclos.
        from apps.common.auth import unidad_efectiva
        try:
            return unidad_efectiva(self.request)
        except Exception:
            return ""

    def get_queryset(self):
        qs = super().get_queryset()
        # ADMINISTRADOR ve todo, sin filtro por unidad.
        from apps.common.auth import puede_ver_todas_las_unidades
        try:
            if puede_ver_todas_las_unidades(self.request):
                return qs
        except Exception:
            pass
        unidad = self._unidad_sesion()
        if not unidad or not self.unidad_field:
            return qs
        return qs.filter(**{self.unidad_field: unidad})


class UnidadObjectAccessMixin:
    """
    Para vistas de DETALLE: rechaza accesos a objetos de otra unidad cuando
    el usuario no es ADMINISTRADOR. Aplica tras `get_object`.

    Subclases definen `get_unidad_del_objeto(obj) -> str`. Devolver "" indica
    que el objeto no está atado a una unidad específica.
    """

    redirect_url_name = "comercial:dashboard"
    mensaje_denegacion = "No tiene permiso para acceder a información de otra unidad."

    def get_unidad_del_objeto(self, obj):
        # Implementación por defecto: intenta atributos comunes.
        unidad = getattr(obj, "unidad_negocio", None)
        if unidad:
            return unidad
        creado_por = getattr(obj, "creado_por", None)
        if creado_por is not None:
            return getattr(creado_por, "unidad_negocio", "") or ""
        return ""

    def dispatch(self, request, *args, **kwargs):
        # Resolver objeto antes de chequear permisos
        try:
            self.object = self.get_object()
        except Exception:
            # Si no se puede resolver, deja que la vista falle naturalmente
            return super().dispatch(request, *args, **kwargs)

        from apps.common.auth import puede_gestionar_unidad, get_usuario_actual

        # Bypass — el creador del objeto siempre puede acceder a lo suyo.
        usuario = get_usuario_actual(request)
        creado_por_id = getattr(self.object, "creado_por_id", None)
        if usuario is not None and creado_por_id is not None and usuario.pk == creado_por_id:
            return super().dispatch(request, *args, **kwargs)

        unidad_obj = self.get_unidad_del_objeto(self.object)
        if not puede_gestionar_unidad(request, unidad_obj):
            messages.error(request, self.mensaje_denegacion)
            return redirect(self.redirect_url_name)
        return super().dispatch(request, *args, **kwargs)


class WithCreateFormMixin:
    """
    Inyecta `create_form` (instancia vacía) en el contexto de una ListView.
    Permite renderizar el formulario de alta directamente en la misma página
    (modal de creación) sin necesitar una vista ni URL separadas.

    Uso:
        class ClienteListView(WithCreateFormMixin, ListView):
            form_class = ClienteForm
            ...
    """
    form_class = None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.form_class:
            ctx["create_form"] = self.form_class()
        return ctx
