"""
apps/catalogos/signals.py — Invalidación de cache de catálogos (Fase 5D).

Escuchan post_save / post_delete sobre UnidadMedida y CategoriaProducto y
limpian las claves cache-aside correspondientes en apps/common/cache.py.

No se cachean Producto, Proveedor ni ProductoProveedor (precios) — política
diferida para una fase posterior con TTL más conservador.

Registro: apps/catalogos/apps.py → CatalogosConfig.ready() importa este módulo.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.catalogos.models import CategoriaProducto, UnidadMedida
from apps.common.cache import (
    invalidate_categorias_cache,
    invalidate_unidades_cache,
)


@receiver(post_save, sender=UnidadMedida)
def _unidad_post_save(sender, instance, **kwargs):
    invalidate_unidades_cache()


@receiver(post_delete, sender=UnidadMedida)
def _unidad_post_delete(sender, instance, **kwargs):
    invalidate_unidades_cache()


@receiver(post_save, sender=CategoriaProducto)
def _categoria_post_save(sender, instance, **kwargs):
    invalidate_categorias_cache()


@receiver(post_delete, sender=CategoriaProducto)
def _categoria_post_delete(sender, instance, **kwargs):
    invalidate_categorias_cache()
