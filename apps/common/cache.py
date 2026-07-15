"""
apps/common/cache.py — Helpers Cache-Aside para AndinaCost.

Patrón: Cache-Aside.
    - Lectura: cache → si miss, leer DB y guardar en cache.
    - Escritura: invalidar la clave (no escribir directamente al cache).

Convención de namespaces:
    "<dominio>:<recurso>[:<id>]"
    p. ej. "catalogos:unidades", "catalogos:categorias", "ingenieria:receta:42".

ESTADO: módulo base. Aún NO está cableado al resto del proyecto.
La adopción se hará en una fase posterior del refactor; aquí solo dejamos la
plantilla canónica para que todos los servicios futuros usen el mismo patrón.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from django.core.cache import cache


# ---------------------------------------------------------------------------
# TTLs por dominio (segundos). Centralizados para no dispersar números mágicos.
# ---------------------------------------------------------------------------
TTL_UNIDADES = 60 * 60 * 24      # 1 día — catálogo cuasi-inmutable
TTL_CATEGORIAS = 60 * 60         # 1 hora
TTL_CONFIG_APU = 60 * 60         # 1 hora — singleton
TTL_RECETA_SUBSISTEMA = 60 * 10  # 10 minutos
TTL_CATALOGO_APU = 60 * 30       # 30 minutos
TTL_DEFAULT = 60 * 5             # 5 minutos


# ---------------------------------------------------------------------------
# Helper genérico cache-aside
# ---------------------------------------------------------------------------
def cache_aside(key: str, loader: Callable[[], Any], ttl: int = TTL_DEFAULT) -> Any:
    """Devuelve cache[key]; si miss, ejecuta loader() y lo guarda."""
    value = cache.get(key)
    if value is not None:
        return value
    value = loader()
    if value is not None:
        cache.set(key, value, ttl)
    return value


def invalidate(keys: Iterable[str]) -> None:
    """Invalida una o varias claves de cache."""
    for k in keys:
        cache.delete(k)


# ---------------------------------------------------------------------------
# Catálogos — Unidades de medida
# ---------------------------------------------------------------------------
KEY_UNIDADES = "catalogos:unidades"


def get_cached_unidades() -> list[dict]:
    """Listado serializable de UnidadMedida activas."""
    def _load() -> list[dict]:
        from apps.catalogos.models import UnidadMedida
        return list(
            UnidadMedida.objects.order_by("nombre")
            .values("id", "codigo", "nombre", "abreviatura")
        )
    return cache_aside(KEY_UNIDADES, _load, TTL_UNIDADES)


def invalidate_unidades_cache() -> None:
    invalidate([KEY_UNIDADES])


# ---------------------------------------------------------------------------
# Catálogos — Categorías de producto
# ---------------------------------------------------------------------------
KEY_CATEGORIAS = "catalogos:categorias"


def get_cached_categorias() -> list[dict]:
    """Listado serializable de CategoriaProducto activas."""
    def _load() -> list[dict]:
        from apps.catalogos.models import CategoriaProducto
        qs = CategoriaProducto.objects.all()
        # filtrar activas si existe el campo
        if hasattr(CategoriaProducto, "activa"):
            qs = qs.filter(activa=True)
        return list(qs.order_by("nombre").values("id", "codigo", "nombre"))
    return cache_aside(KEY_CATEGORIAS, _load, TTL_CATEGORIAS)


def invalidate_categorias_cache() -> None:
    invalidate([KEY_CATEGORIAS])


# ---------------------------------------------------------------------------
# Presupuestos — Configuración APU (singleton)
# ---------------------------------------------------------------------------
KEY_CONFIG_APU = "presupuestos:config_apu:activa"


def get_cached_config_apu_id() -> Optional[int]:
    """ID de la ConfiguracionAPU activa (no la instancia para no acoplar al ORM)."""
    def _load() -> Optional[int]:
        from apps.presupuestos.models import ConfiguracionAPU
        cfg = ConfiguracionAPU.activa_o_default()
        return cfg.id if cfg else None
    return cache_aside(KEY_CONFIG_APU, _load, TTL_CONFIG_APU)


def invalidate_config_apu_cache() -> None:
    invalidate([KEY_CONFIG_APU])


# ---------------------------------------------------------------------------
# Ingeniería — Receta técnica por subsistema
# ---------------------------------------------------------------------------
def key_receta_subsistema(subsistema_id: int) -> str:
    return f"ingenieria:receta:{subsistema_id}"


def invalidate_receta_subsistema(subsistema_id: int) -> None:
    invalidate([key_receta_subsistema(subsistema_id)])
