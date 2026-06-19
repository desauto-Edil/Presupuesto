from django.apps import AppConfig


class CatalogosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalogos"
    verbose_name = "Catálogos"

    def ready(self):
        # Registra signals de invalidación de cache (Fase 5D).
        from . import signals  # noqa: F401
