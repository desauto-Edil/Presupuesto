"""
ensure_default_admin — Crea (idempotente) el administrador inicial del sistema.

Lee credenciales desde variables de entorno. Nunca persiste contraseña plana.
Nunca imprime la contraseña.

Variables requeridas:
    ANDINACOST_ADMIN_EMAIL
    ANDINACOST_ADMIN_PASSWORD

Variables opcionales:
    ANDINACOST_ADMIN_NAME      (default: "Administrador del sistema")
    ANDINACOST_ADMIN_UNIDAD    (default: "EDILANDINA" — unidad corporativa
                                del administrador global; no limita su
                                alcance, sólo da identidad visual).
"""

import os
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from django.db import transaction

from apps.configuracion.models import ConfiguracionSistema
from apps.common.choices import RolSistema, UnidadNegocio


PASSWORDS_DEBILES = {
    "admin", "admin123", "administrator", "password", "password123",
    "123456", "12345678", "qwerty", "letmein",
    "change-me-secure-password",
}
LONGITUD_MINIMA = 10


class Command(BaseCommand):
    help = "Asegura la existencia de un administrador inicial usando variables de entorno."

    def handle(self, *args, **options):
        email = (os.environ.get("ANDINACOST_ADMIN_EMAIL") or "").strip().lower()
        password = os.environ.get("ANDINACOST_ADMIN_PASSWORD") or ""
        nombre = (os.environ.get("ANDINACOST_ADMIN_NAME") or "Administrador del sistema").strip()
        unidad = (os.environ.get("ANDINACOST_ADMIN_UNIDAD") or UnidadNegocio.EDILANDINA).strip().upper()

        if not email or not password:
            self.stderr.write(self.style.ERROR(
                "Faltan variables de entorno requeridas: "
                "ANDINACOST_ADMIN_EMAIL y ANDINACOST_ADMIN_PASSWORD."
            ))
            return

        # Validación básica de seguridad de contraseña
        if len(password) < LONGITUD_MINIMA:
            self.stderr.write(self.style.ERROR(
                f"La contraseña no cumple la longitud mínima ({LONGITUD_MINIMA} caracteres)."
            ))
            return
        if password.strip().lower() in PASSWORDS_DEBILES:
            self.stderr.write(self.style.ERROR(
                "La contraseña está en la lista de valores débiles. Use una contraseña más segura."
            ))
            return

        # Validar unidad de negocio
        unidades_validas = {u.value for u in UnidadNegocio}
        if unidad not in unidades_validas:
            self.stderr.write(self.style.ERROR(
                f"Unidad de negocio inválida: {unidad}. Válidas: {', '.join(sorted(unidades_validas))}."
            ))
            return

        with transaction.atomic():
            existente = ConfiguracionSistema.objects.filter(email__iexact=email).first()
            if existente is not None:
                # Idempotente conservador: nunca sobrescribir contraseña, rol ni nombre.
                # Fase 12.3 ext: si el usuario ya es ADMINISTRADOR y su unidad
                # difiere de la pedida (típicamente EDILANDINA), reasignar
                # solamente la unidad. Esto da identidad visual gris/negro/blanco
                # al administrador global sin alterar credenciales.
                if existente.rol == RolSistema.ADMINISTRADOR:
                    if existente.unidad_negocio != unidad:
                        existente.unidad_negocio = unidad
                        existente.save(update_fields=["unidad_negocio", "updated_at"])
                        self.stdout.write(self.style.SUCCESS(
                            f"Administrador global asociado a {unidad}."
                        ))
                    else:
                        self.stdout.write(self.style.WARNING("Administrador inicial ya existe."))
                else:
                    # El email pertenece a un usuario no-ADMINISTRADOR. No tocar.
                    self.stdout.write(self.style.WARNING(
                        "Ya existe un usuario con ese email pero no es ADMINISTRADOR. "
                        "No se realiza ningún cambio."
                    ))
                return

            ConfiguracionSistema.objects.create(
                email=email,
                nombre_completo=nombre,
                password_hash=make_password(password),
                unidad_negocio=unidad,
                rol=RolSistema.ADMINISTRADOR,
                activo=True,
            )

        # Limpiar referencia local a la contraseña en claro
        password = None  # noqa: F841
        self.stdout.write(self.style.SUCCESS("Administrador inicial creado."))
