"""
apps/presupuestos/signals.py — Invalidación de cache de presupuestos (Fase 5D).

Escucha post_save / post_delete sobre ConfiguracionAPU y limpia la clave
cache-aside del singleton de configuración activa.

Los signals de APULinea (recalcular APU) viven en apps/presupuestos/models/apu.py
y NO se tocan en esta fase.

Registro: apps/presupuestos/apps.py → PresupuestosConfig.ready() importa este
módulo.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.common.cache import invalidate_config_apu_cache
from apps.presupuestos.models import ConfiguracionAPU


@receiver(post_save, sender=ConfiguracionAPU)
def _configapu_post_save(sender, instance, **kwargs):
    invalidate_config_apu_cache()


@receiver(post_delete, sender=ConfiguracionAPU)
def _configapu_post_delete(sender, instance, **kwargs):
    invalidate_config_apu_cache()
