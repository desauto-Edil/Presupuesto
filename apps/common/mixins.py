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
        """Retorna la unidad de negocio de la sesión actual."""
        try:
            return self.request.session.get("unidad_negocio", "") or ""
        except Exception:
            return ""

    def get_queryset(self):
        qs = super().get_queryset()
        unidad = self._unidad_sesion()
        if not unidad or not self.unidad_field:
            return qs
        return qs.filter(**{self.unidad_field: unidad})


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
