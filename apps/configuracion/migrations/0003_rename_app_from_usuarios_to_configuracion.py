# Migration 0003 — renaming cleanup (no-op: tables already have correct names)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion', '0002_alter_usuariosistema_rol_and_more'),
    ]

    operations = [
        # Las tablas ya existen con los nombres correctos en la BD.
        # Esta migración queda como marcador vacío para no romper la cadena.
    ]
