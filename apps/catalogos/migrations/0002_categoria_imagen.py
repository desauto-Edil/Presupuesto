"""Migration: Add imagen field to CategoriaProducto."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="categoriaproducto",
            name="imagen",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="categorias/",
                verbose_name="Imagen de categoría",
            ),
        ),
    ]
