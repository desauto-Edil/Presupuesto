"""apps/usuarios/urls.py"""

from django.urls import path
from . import views

app_name = "usuarios"

urlpatterns = [
    path("", views.UsuarioListView.as_view(), name="usuario_list"),
    path("nuevo/", views.UsuarioCreateView.as_view(), name="usuario_create"),
    path("<int:pk>/", views.UsuarioDetailView.as_view(), name="usuario_detail"),
    path("<int:pk>/editar/", views.UsuarioUpdateView.as_view(), name="usuario_update"),
    path("<int:pk>/eliminar/", views.UsuarioDeleteView.as_view(), name="usuario_delete"),
    path("login/", views.LoginUsuarioView.as_view(), name="login"),
    path("logout/", views.logout_usuario, name="logout"),
]
