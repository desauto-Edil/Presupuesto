from django.shortcuts import redirect
from django.urls import reverse

class AuthCustomMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Lista de URLs que NO requieren login (Login y Admin)
        public_urls = [
            reverse("usuarios:login"),
            "/admin/",
            "/static/",
        ]

        # Si no está logueado y la URL no es pública, redirigir al login
        if "usuario_id" not in request.session:
            if not any(request.path.startswith(url) for url in public_urls):
                return redirect("usuarios:login")

        response = self.get_response(request)
        return response