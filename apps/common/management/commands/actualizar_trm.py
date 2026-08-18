"""
apps/common/management/commands/actualizar_trm.py
==================================================

Comando de gestión para actualizar la TRM diariamente.

Uso:
    python manage.py actualizar_trm

Si la actualización falla, el comando termina con exit code 1 pero NO
elimina ni sobreescribe el registro vigente anterior — la última TRM válida
permanece disponible para el sistema.

Para cron (ejemplo — ejecutar a las 8:00 AM hora Colombia):
    0 8 * * * /ruta/a/venv/bin/python /ruta/a/manage.py actualizar_trm >> /var/log/trm.log 2>&1
"""

import sys
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Obtiene la TRM vigente desde la Superintendencia Financiera y actualiza la BD."

    def handle(self, *args, **options):
        from apps.common.trm_service import actualizar_trm, TRMNoDisponibleError

        self.stdout.write("Actualizando TRM desde Superintendencia Financiera…")

        try:
            registro = actualizar_trm()
            self.stdout.write(
                self.style.SUCCESS(
                    f"TRM actualizada: {registro.valor} COP/USD (fecha {registro.fecha})"
                )
            )
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(f"Error al actualizar TRM: {exc}")
            )
            logger.error("Fallo al actualizar TRM: %s", exc, exc_info=True)
            sys.exit(1)
