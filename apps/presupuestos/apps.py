from django.apps import AppConfig


class PresupuestosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.presupuestos"
    verbose_name = "Presupuestos"

    def ready(self):
        # Registra signals de invalidación de cache (Fase 5D).
        from . import signals  # noqa: F401
