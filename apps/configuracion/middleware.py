from django.shortcuts import redirect
from django.urls import reverse

class AuthCustomMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Lista de URLs que NO requieren login (Login y Admin)
        public_urls = [
            reverse("configuracion:login"),
            "/admin/",
            "/static/",
        ]

        # Si no está logueado y la URL no es pública, redirigir al login
        if "usuario_id" not in request.session:
            if not any(request.path.startswith(url) for url in public_urls):
                return redirect("configuracion:login")

        # ── Retroalimentar 'rol' en sesiones antiguas que no lo tengan ──────
        # Sesiones creadas antes de agregar 'rol' al login no tienen esta clave.
        # La buscamos una sola vez en BD y la guardamos para evitar consultas futuras.
        if "usuario_id" in request.session and "rol" not in request.session:
            try:
                from apps.configuracion.models import ConfiguracionSistema
                cfg = ConfiguracionSistema.objects.get(pk=request.session["usuario_id"])
                request.session["rol"] = cfg.rol
            except Exception:
                request.session["rol"] = ""

        response = self.get_response(request)
        return response