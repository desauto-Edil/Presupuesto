"""apps/common/mixins.py — Mixins reutilizables para vistas Django."""

from django.contrib import messages
from django.shortcuts import redirect


# ---------------------------------------------------------------------------
# Conjuntos de roles (fuente de verdad centralizada)
# Modificar AQUÍ cuando cambien las reglas de acceso — no dispersar en vistas.
# ---------------------------------------------------------------------------

ROLES_ADMIN               = {"ADMINISTRADOR"}
ROLES_ADMIN_GERENTE       = {"ADMINISTRADOR", "GERENTE"}
ROLES_GESTION_COMERCIAL   = {"ADMINISTRADOR", "GERENTE", "PRESUPUESTOS", "ASESOR_COMERCIAL"}
ROLES_PRESUPUESTOS        = {"ADMINISTRADOR", "GERENTE", "PRESUPUESTOS"}
ROLES_CATALOGO_PRODUCTOS  = {"ADMINISTRADOR", "PRESUPUESTOS", "COMPRAS"}
ROLES_CATALOGO_CATEGORIAS = {"ADMINISTRADOR", "PRESUPUESTOS"}
ROLES_CATALOGO_PROVEEDORES= {"ADMINISTRADOR", "PRESUPUESTOS", "ASESOR_COMERCIAL"}
ROLES_INGENIERIA          = {"ADMINISTRADOR", "PRESUPUESTOS"}
ROLES_DESCARGA_PDF        = {"ADMINISTRADOR", "GERENTE", "PRESUPUESTOS", "ASESOR_COMERCIAL"}


# ---------------------------------------------------------------------------
# Mixin base: control por rol
# ---------------------------------------------------------------------------

class RolRequeridoMixin:
    """
    Mixin base para proteger vistas por rol de sesión.

    Declara `roles_permitidos` (set de strings) en la subclase.
    Bloquea en dispatch() antes de cualquier lógica de negocio.

    Uso:
        class MiView(RolRequeridoMixin, CreateView):
            roles_permitidos = ROLES_GESTION_COMERCIAL
    """
    roles_permitidos: set = set()
    redirect_url_name: str = "comercial:dashboard"
    mensaje_denegacion: str = "No tiene permisos para realizar esta acción."

    def dispatch(self, request, *args, **kwargs):
        rol = request.session.get("rol", "")
        if not rol or rol not in self.roles_permitidos:
            messages.error(request, self.mensaje_denegacion)
            return redirect(self.redirect_url_name)
        return super().dispatch(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Mixins concretos listos para usar en vistas
# ---------------------------------------------------------------------------

class AdminRequiredMixin(RolRequeridoMixin):
    """Solo ADMINISTRADOR global."""
    roles_permitidos = ROLES_ADMIN
    mensaje_denegacion = "Solo el Administrador global puede acceder a esta sección."


class AdminGerenteRequiredMixin(RolRequeridoMixin):
    """ADMINISTRADOR o GERENTE."""
    roles_permitidos = ROLES_ADMIN_GERENTE
    mensaje_denegacion = "Esta acción requiere rol de Administrador o Gerente."


class GestionComercialMixin(RolRequeridoMixin):
    """ADMINISTRADOR, GERENTE, PRESUPUESTOS o ASESOR_COMERCIAL."""
    roles_permitidos = ROLES_GESTION_COMERCIAL
    mensaje_denegacion = "Su perfil no permite crear o editar registros comerciales."


class GestionPresupuestosMixin(RolRequeridoMixin):
    """ADMINISTRADOR, GERENTE o PRESUPUESTOS."""
    roles_permitidos = ROLES_PRESUPUESTOS
    mensaje_denegacion = "Su perfil no permite acceder al módulo de presupuestos."


class GestionCatalogosProductosMixin(RolRequeridoMixin):
    """ADMINISTRADOR, PRESUPUESTOS o COMPRAS."""
    roles_permitidos = ROLES_CATALOGO_PRODUCTOS
    mensaje_denegacion = "Su perfil no permite modificar el catálogo de productos."


class GestionCatalogoCategoriasMixin(RolRequeridoMixin):
    """ADMINISTRADOR o PRESUPUESTOS."""
    roles_permitidos = ROLES_CATALOGO_CATEGORIAS
    mensaje_denegacion = "Su perfil no permite modificar categorías o unidades de medida."


class GestionCatalogoProveedoresMixin(RolRequeridoMixin):
    """ADMINISTRADOR, PRESUPUESTOS o ASESOR_COMERCIAL."""
    roles_permitidos = ROLES_CATALOGO_PROVEEDORES
    mensaje_denegacion = "Su perfil no permite modificar proveedores."


class GestionIngenieriaMixin(RolRequeridoMixin):
    """ADMINISTRADOR o PRESUPUESTOS — sistemas, subsistemas, calculador."""
    roles_permitidos = ROLES_INGENIERIA
    mensaje_denegacion = "Su perfil no permite modificar la configuración de ingeniería."


class DescargaPDFMixin(RolRequeridoMixin):
    """ADMINISTRADOR, GERENTE, PRESUPUESTOS o ASESOR_COMERCIAL."""
    roles_permitidos = ROLES_DESCARGA_PDF
    mensaje_denegacion = "Su perfil no tiene acceso a los documentos PDF."


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
