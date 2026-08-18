"""
apps/common/trm_service.py
===========================

Servicio canónico de TRM (Tasa Representativa del Mercado).

Interfaz pública
----------------
    obtener_trm_vigente()   -> Decimal
    obtener_trm_registro()  -> TRMVigente
    actualizar_trm()        -> TRMVigente   (para el management command)

El resto del sistema NO debe llamar nada más de este módulo.

Fuente
------
Datos Abiertos Colombia (datos.gov.co) — API Socrata, dataset de TRM publicado
por la Superintendencia Financiera:
    https://www.datos.gov.co/resource/32sa-8pi3.json

Fallback
--------
1. Intentar obtener desde cache.
2. Si no hay en cache: buscar el registro TRMVigente más reciente con vigente=True.
3. Si no existe ninguno: lanzar TRMNoDisponibleError (nunca usar un valor inventado).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Excepción pública
# ---------------------------------------------------------------------------

class TRMNoDisponibleError(Exception):
    """
    Se lanza cuando no hay ninguna TRM válida disponible en el sistema.
    Indica que el management command `actualizar_trm` nunca se ha ejecutado
    exitosamente, o que la BD está vacía.
    """


# ---------------------------------------------------------------------------
# Constantes de cache
# ---------------------------------------------------------------------------

_CACHE_KEY = "common:trm_vigente:registro_pk"
_TTL = 60 * 60 * 20   # 20 horas — margen para la actualización diaria


# ---------------------------------------------------------------------------
# Interfaz pública
# ---------------------------------------------------------------------------

def obtener_trm_vigente() -> Decimal:
    """
    Devuelve el valor Decimal de la TRM actualmente vigente.

    Raises:
        TRMNoDisponibleError: si nunca se ha almacenado una TRM válida en BD.
    """
    return obtener_trm_registro().valor


def obtener_trm_registro():
    """
    Devuelve el objeto TRMVigente actualmente activo.

    Primero intenta desde cache (pk del registro). Si el cache está vacío o
    el registro ya no existe, consulta la BD y recarga el cache.

    Raises:
        TRMNoDisponibleError: si no existe ningún registro vigente en BD.
    """
    from django.core.cache import cache
    from apps.configuracion.models import TRMVigente

    # ── Intentar desde cache ────────────────────────────────────────────────
    pk_cached = cache.get(_CACHE_KEY)
    if pk_cached is not None:
        try:
            registro = TRMVigente.objects.get(pk=pk_cached, vigente=True)
            return registro
        except TRMVigente.DoesNotExist:
            # Invalidar cache obsoleto y caer a BD
            cache.delete(_CACHE_KEY)

    # ── Consultar BD ────────────────────────────────────────────────────────
    registro = (
        TRMVigente.objects
        .filter(vigente=True)
        .order_by("-fecha", "-created_at")
        .first()
    )

    if registro is None:
        raise TRMNoDisponibleError(
            "No hay ninguna TRM disponible en el sistema. "
            "Ejecute `python manage.py actualizar_trm` para obtener la TRM inicial."
        )

    # Poblar cache
    cache.set(_CACHE_KEY, registro.pk, _TTL)
    return registro


def invalidar_cache_trm() -> None:
    """Invalida el cache de TRM. Llamar después de actualizar el registro vigente."""
    from django.core.cache import cache
    cache.delete(_CACHE_KEY)


# ---------------------------------------------------------------------------
# Actualización (llamada desde el management command)
# ---------------------------------------------------------------------------

def actualizar_trm() -> "TRMVigente":
    """
    Obtiene la TRM oficial de la Superintendencia Financiera y actualiza la BD.

    Flujo:
    1. Fetch SOAP → nuevo valor + fecha.
    2. Marcar registro(s) anteriores con vigente=False.
    3. Crear nuevo TRMVigente con vigente=True.
    4. Invalidar cache.
    5. Devolver el registro creado.

    Raises:
        Exception: si el fetch falla completamente (el caller debe decidir si
                   propagar o solo loguear).
    """
    from django.db import transaction
    from apps.configuracion.models import TRMVigente

    valor, fecha = _fetch_trm_superfinanciera()

    with transaction.atomic():
        # Marcar anteriores como no vigentes
        TRMVigente.objects.filter(vigente=True).update(vigente=False)
        # Crear nuevo registro
        nuevo = TRMVigente.objects.create(
            valor=valor,
            fecha=fecha,
            vigente=True,
            fuente="Superintendencia Financiera de Colombia",
        )

    invalidar_cache_trm()
    logger.info("TRM actualizada: %s (fecha %s)", valor, fecha)
    return nuevo


# ---------------------------------------------------------------------------
# Fetcher interno — Superintendencia Financiera SOAP
# ---------------------------------------------------------------------------

def _fetch_trm_superfinanciera() -> tuple[Decimal, "datetime.date"]:
    """
    Obtiene la TRM vigente desde la API de Datos Abiertos Colombia (datos.gov.co),
    dataset publicado por la Superintendencia Financiera (dataset ID: 32sa-8pi3).

    API Socrata — GET JSON:
        https://www.datos.gov.co/resource/32sa-8pi3.json
        ?$limit=1&$order=vigenciadesde DESC

    Retorna:
        (valor: Decimal, fecha: datetime.date)

    Raises:
        Exception: ante cualquier fallo de red, parseo o dato inválido.
    """
    import datetime
    import json
    import urllib.request
    from urllib.parse import urlencode

    params = urlencode({
        "$limit": "1",
        "$order": "vigenciadesde DESC",
    })
    url = f"https://www.datos.gov.co/resource/32sa-8pi3.json?{params}"

    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )

    timeout_secs = 15
    with urllib.request.urlopen(req, timeout=timeout_secs) as resp:
        data = json.loads(resp.read())

    if not data:
        raise ValueError(
            "datos.gov.co no devolvió ningún registro de TRM. "
            "Verifique el dataset 32sa-8pi3 en https://www.datos.gov.co"
        )

    registro = data[0]

    # ── Valor ──────────────────────────────────────────────────────────────────
    try:
        valor = Decimal(str(registro["valor"]).strip())
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise ValueError(f"Campo 'valor' TRM inválido en respuesta: {registro!r}") from exc

    if valor <= 0:
        raise ValueError(f"TRM recibida es inválida (≤ 0): {valor}")

    # ── Fecha ──────────────────────────────────────────────────────────────────
    # 'vigenciadesde' llega como "YYYY-MM-DDT00:00:00.000"
    try:
        fecha_str = str(registro.get("vigenciadesde", "")).strip()[:10]
        fecha = datetime.date.fromisoformat(fecha_str)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Campo 'vigenciadesde' TRM inválido: {registro.get('vigenciadesde')!r}"
        ) from exc

    return valor, fecha
