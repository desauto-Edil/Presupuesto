"""
apps/presupuestos/models/despiece.py — Ejecución del despiece por proyecto.

ProyectoSistema: vincula un proyecto con el sistema/subsistema elegido
                  y almacena las variables de entrada del cálculo.
DespieceLinea:   resultado de aplicar las reglas del subsistema al proyecto.
                  Puede tener producto ya resuelto o estar pendiente de
                  selección

Dependencias cruzadas:
  - comercial.Proyecto
  - ingenieria.Sistema, Subsistema, ReglaCalculo, DependenciaTecnica
  - catalogos.Producto, CategoriaProducto
"""

from django.db import models


class ProyectoSistema(models.Model):
    """
    Instancia de ejecución de un subsistema para un proyecto concreto.
    Almacena las variables de entrada dinámicas (Total_PowerGrip, cuadrilla, etc.)
    """
    proyecto = models.ForeignKey(
        "comercial.Proyecto", on_delete=models.CASCADE, related_name="proyecto_sistemas"
    )
    sistema = models.ForeignKey(
        "ingenieria.Sistema", on_delete=models.PROTECT, related_name="proyecto_sistemas"
    )
    subsistema = models.ForeignKey(
        "ingenieria.Subsistema", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="proyecto_sistemas",
    )
    orden = models.IntegerField(default=1)
    total_powergip = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True,
        help_text="Cantidad base de PowerGrip ingresada por el usuario",
    )
    cuadrilla_personas = models.IntegerField(
        blank=True, null=True,
        help_text="Número de personas en la cuadrilla de instalación",
    )
    variables_extra = models.JSONField(
        default=dict, blank=True,
        help_text="Variables adicionales editables por proyecto en formato JSON",
    )
    observaciones = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "proyecto_sistemas"
        unique_together = ("proyecto", "sistema", "subsistema")

    def __str__(self):
        sub = self.subsistema.nombre if self.subsistema else "—"
        return f"{self.proyecto.consecutivo} / {self.sistema.nombre} / {sub}"

    def get_contexto(self) -> dict:
        """Construye el diccionario de variables para evaluar reglas."""
        ctx = {
            "Total_PowerGrip": float(self.total_powergip or 0),
            "area_m2": float(self.proyecto.area_total_m2 or 0),
            "perimetro_ml": float(self.proyecto.perimetro_ml or 0),
            "cuadrilla": float(self.cuadrilla_personas or 0),
        }
        ctx.update({k: float(v) for k, v in (self.variables_extra or {}).items()})
        return ctx

    def inyectar_dependencias(self):
        """
        Crea DespieceLinea para todas las dependencias obligatorias
        del subsistema seleccionado (si no existen ya).

        Soporta dos modos:
          - Dependencia con producto_dependiente → línea con producto resuelto.
          - Dependencia con categoria_producto   → línea pendiente de selección.

        Retorna lista de líneas creadas.
        """
        from apps.ingenieria.models import DependenciaTecnica

        if not self.subsistema:
            return []

        deps = DependenciaTecnica.objects.filter(
            subsistema=self.subsistema, obligatoria=True
        ).select_related("producto_dependiente", "categoria_producto")

        creadas = []
        for dep in deps:
            if dep.producto_dependiente_id:
                linea, nueva = DespieceLinea.objects.get_or_create(
                    proyecto=self.proyecto,
                    proyecto_sistema=self,
                    producto=dep.producto_dependiente,
                    defaults={
                        "cantidad_calculada":      0,
                        "es_dependencia_automatica": True,
                        "dependencia_tecnica":     dep,
                    },
                )
            elif dep.categoria_producto_id:
                linea, nueva = DespieceLinea.objects.get_or_create(
                    proyecto=self.proyecto,
                    proyecto_sistema=self,
                    dependencia_tecnica=dep,
                    defaults={
                        "cantidad_calculada":      0,
                        "es_dependencia_automatica": True,
                        "categoria_producto":      dep.categoria_producto,
                    },
                )
            else:
                continue

            if nueva:
                creadas.append(linea)
        return creadas


class DespieceLinea(models.Model):
    """
    Línea de despiece: un componente con su cantidad calculada/ajustada
    para un proyecto y sistema específico.

    Estado del producto:
      - producto resuelto:  producto_id is not None  → tiene precio, listo para APU
      - pendiente selección: producto_id is None AND categoria_producto_id is not None
    """
    proyecto = models.ForeignKey(
        "comercial.Proyecto", on_delete=models.CASCADE, related_name="despiece_lineas"
    )
    proyecto_sistema = models.ForeignKey(
        ProyectoSistema, on_delete=models.CASCADE,
        blank=True, null=True, related_name="despiece_lineas",
    )
    producto = models.ForeignKey(
        "catalogos.Producto", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="despiece_lineas",
        help_text="Producto resuelto; NULL si aún está pendiente de selección",
    )
    categoria_producto = models.ForeignKey(
        "catalogos.CategoriaProducto", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="despiece_lineas",
        help_text="Categoría cuando el producto aún no ha sido seleccionado",
    )
    dependencia_tecnica = models.ForeignKey(
        "ingenieria.DependenciaTecnica", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="despiece_lineas",
        help_text="Dependencia que originó esta línea (para líneas automáticas de categoría)",
    )
    regla = models.ForeignKey(
        "ingenieria.ReglaCalculo", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="despiece_lineas",
    )
    cantidad_calculada = models.DecimalField(max_digits=18, decimal_places=6)
    cantidad_ajustada = models.DecimalField(max_digits=18, decimal_places=6, blank=True, null=True)
    motivo_ajuste = models.TextField(blank=True, null=True)
    precio_snapshot = models.DecimalField(
        max_digits=18, decimal_places=6, blank=True, null=True,
        help_text="Precio unitario al momento de calcular el despiece",
    )
    es_dependencia_automatica = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "despiece_lineas"

    def __str__(self):
        nombre = (
            self.producto.nombre if self.producto
            else f"[{self.categoria_producto}]" if self.categoria_producto
            else "—"
        )
        return f"{self.proyecto.consecutivo} / {nombre}"

    @property
    def cantidad_final(self):
        return self.cantidad_ajustada if self.cantidad_ajustada is not None else self.cantidad_calculada

    @property
    def pendiente_seleccion(self):
        """True si esta línea tiene categoría pero aún no tiene producto concreto asignado."""
        return self.producto_id is None and self.categoria_producto_id is not None

    def capturar_precio(self):
        """Toma snapshot del mejor precio activo del producto (solo si el producto está resuelto)."""
        if not self.producto_id:
            return
        pp = self.producto.proveedores_producto.filter(activo=True).order_by("precio_unitario").first()
        if pp:
            self.precio_snapshot = pp.precio_unitario
            self.save(update_fields=["precio_snapshot", "updated_at"])
