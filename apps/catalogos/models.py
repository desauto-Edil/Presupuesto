"""
apps/catalogos/models.py — Catálogo maestro reutilizable.
  - Unidades de medida
  - Categorías de producto
  - Productos (con proveedor y precio integrados)
  - Proveedores
  - ProductoProveedor (tabla técnica usada por DespieceService)

Dependencias: solo apps.common (choices).
"""

from django.db import models
from django.utils import timezone
from apps.common.choices import OrigenProducto, Moneda


# ---------------------------------------------------------------------------
# UNIDADES DE MEDIDA
# ---------------------------------------------------------------------------

class UnidadMedida(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=50)
    abreviatura = models.CharField(max_length=15)

    class Meta:
        app_label = "catalogos"
        db_table = "unidades_medida"

    def __str__(self):
        return self.abreviatura


# ---------------------------------------------------------------------------
# CATEGORÍAS DE PRODUCTO
# ---------------------------------------------------------------------------

class CategoriaProducto(models.Model):
    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    imagen = models.ImageField(
        upload_to="categorias/",
        blank=True,
        null=True,
        verbose_name="Imagen de categoría",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        app_label = "catalogos"
        db_table = "categorias_producto"

    def __str__(self):
        return self.nombre


# ---------------------------------------------------------------------------
# PRODUCTOS
# ---------------------------------------------------------------------------

class Producto(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=300)
    categoria = models.ForeignKey(
        CategoriaProducto, on_delete=models.PROTECT, related_name="productos"
    )
    unidad = models.ForeignKey(
        UnidadMedida, on_delete=models.PROTECT, related_name="productos"
    )
    # ── Proveedor, precio y moneda ────────────────────────────────────────────
    proveedor = models.ForeignKey(
        "Proveedor", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="productos_principales",
    )
    precio_actual = models.DecimalField(
        max_digits=18, decimal_places=6, 
        default=0)
   
    moneda = models.CharField(
        max_length=3, choices=Moneda.choices, default=Moneda.COP,
        verbose_name="Moneda",
    )
    fecha_actualizacion_precio = models.DateTimeField(
        auto_now=True
        )
    # ─────────────────────────────────────────────────────────────────────────
    origen = models.CharField(
        max_length=15, choices=OrigenProducto.choices, default=OrigenProducto.NACIONAL
    )
    marca = models.CharField(max_length=150, blank=True, null=True)
    linea = models.CharField(max_length=150, blank=True, null=True)
    rendimiento = models.DecimalField(max_digits=14, decimal_places=6, blank=True, null=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "catalogos"
        db_table  = "productos"

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"

    def save(self, *args, **kwargs):
        """
        Auto-detecta cambio de precio y actualiza fecha_actualizacion_precio.
        NO hace sync a ProductoProveedor aquí para evitar dependencias circulares
        en el modelo — la sincronización ocurre en la vista (form_valid).
        """
        if self.precio_actual is not None:
            precio_cambio = True
            if self.pk:
                try:
                    anterior = Producto.objects.get(pk=self.pk)
                    precio_cambio = (anterior.precio_actual != self.precio_actual)
                except Producto.DoesNotExist:
                    pass
            if precio_cambio:
                self.fecha_actualizacion_precio = timezone.now()
        super().save(*args, **kwargs)

    @classmethod
    def generar_codigo(cls, categoria) -> str:
        """
        Genera el siguiente código único para un producto según su categoría.
        Formato: {CATEGORIA_CODIGO}-{NNNN}  →  Ej: FIJ-0001, CUB-0023
        """
        prefix = f"{categoria.codigo.upper()}-"
        existing = cls.objects.filter(codigo__startswith=prefix).values_list("codigo", flat=True)
        max_num = 0
        for codigo in existing:
            suffix = codigo[len(prefix):]
            try:
                num = int(suffix)
                if num > max_num:
                    max_num = num
            except (ValueError, TypeError):
                pass
        return f"{prefix}{max_num + 1:04d}"


# ---------------------------------------------------------------------------
# PROVEEDORES
# ---------------------------------------------------------------------------

class Proveedor(models.Model):
    nit = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=300)
    ciudad = models.CharField(max_length=100, blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)
    telefono = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "catalogos"
        db_table  = "proveedores"

    def __str__(self):
        return self.nombre


# ---------------------------------------------------------------------------
# PRODUCTO ↔ PROVEEDOR (precio)
# ---------------------------------------------------------------------------

class ProductoProveedor(models.Model):
    producto = models.ForeignKey(
        Producto, on_delete=models.CASCADE, related_name="proveedores_producto"
    )
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.CASCADE, related_name="productos_proveedor"
    )
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=6)
    moneda = models.CharField(max_length=3, choices=Moneda.choices, default=Moneda.COP)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "catalogos"
        db_table = "productos_proveedor"
        unique_together = ("producto", "proveedor")

    def __str__(self):
        return f"{self.producto.nombre} — {self.proveedor.nombre}"
    