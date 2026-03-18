"""
apps/presupuestos/models/apu.py — Análisis de Precios Unitarios (APU).

ConfiguracionAPU: valores predeterminados globales del APU.
APUProyecto:      cabecera del APU para un ProyectoSistema.
APULinea:         ítem individual de costo dentro del APU.

Fórmula central (Nivel 4):
  costo_unitario = precio_referencia * IVA_factor
  costo_total    = rendimiento * costo_unitario
  valor_unitario = costo_unitario * (1 + factor_venta/100)
  valor_total    = rendimiento * valor_unitario
"""

from django.db import models
from apps.common.choices import TipoAPU


class ConfiguracionAPU(models.Model):
    """
    Valores predeterminados del APU, configurables por Administrador.
    Solo debe existir un registro activo.
    """
    nombre = models.CharField(max_length=100, default="Configuración global")
    porcentaje_ganancia = models.DecimalField(max_digits=8, decimal_places=4, default=20)
    aiu_contratista = models.DecimalField(max_digits=8, decimal_places=4, default=30)
    desperdicio = models.DecimalField(max_digits=8, decimal_places=4, default=3)
    margen_ganancia_contratista = models.DecimalField(max_digits=8, decimal_places=4, default=30)
    activa = models.BooleanField(default=True)
    modificado_por = models.ForeignKey(
        "usuarios.UsuarioSistema", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="configs_apu",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "configuracion_apu"

    def __str__(self):
        return self.nombre

    @classmethod
    def activa_o_default(cls):
        cfg = cls.objects.filter(activa=True).first()
        if not cfg:
            cfg = cls.objects.create()
        return cfg


class APUProyecto(models.Model):
    """
    Cabecera del APU para un ProyectoSistema.
    Almacena las variables de entrada del cálculo de mano de obra y los totales.
    """
    proyecto_sistema = models.OneToOneField(
        "presupuestos.ProyectoSistema", on_delete=models.CASCADE, related_name="apu"
    )
    factor_venta_pct = models.DecimalField(max_digits=8, decimal_places=4, default=20,
                                           help_text="% margen sobre costo unitario → valor unitario")
    iva_pct = models.DecimalField(max_digits=8, decimal_places=4, default=19)
    aplica_iva = models.BooleanField(default=True)
    aiu_contratista_pct = models.DecimalField(max_digits=8, decimal_places=4, default=30)
    margen_contratista_pct = models.DecimalField(max_digits=8, decimal_places=4, default=30)

    # Parámetros de mano de obra
    dias_trabajo = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    tiempo_estimado_meses = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    rendimiento_und_dia = models.DecimalField(max_digits=14, decimal_places=6, blank=True, null=True)

    # Totales calculados (se actualizan al recalcular)
    subtotal_materiales = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    subtotal_herramientas = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    subtotal_transporte = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    subtotal_mano_obra = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    subtotal_administracion = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_costo = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_valor_venta = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "apu_proyectos"

    def __str__(self):
        return f"APU {self.proyecto_sistema}"

    def recalcular(self):
        """Recalcula todos los subtotales a partir de las APULineas."""
        from django.db.models import Sum
        totales = {}
        for tipo in TipoAPU.values:
            agg = self.lineas.filter(tipo=tipo).aggregate(
                costo=Sum("costo_total"),
                valor=Sum("valor_total"),
            )
            totales[tipo] = {
                "costo": float(agg["costo"] or 0),
                "valor": float(agg["valor"] or 0),
            }

        self.subtotal_materiales = totales[TipoAPU.MATERIALES]["costo"]
        self.subtotal_herramientas = totales[TipoAPU.HERRAMIENTAS_EQUIPOS]["costo"]
        self.subtotal_transporte = totales[TipoAPU.TRANSPORTE]["costo"]
        self.subtotal_mano_obra = totales[TipoAPU.MANO_DE_OBRA]["costo"]
        self.subtotal_administracion = totales[TipoAPU.ADMINISTRACION]["costo"]
        self.total_costo = (
            self.subtotal_materiales + self.subtotal_herramientas
            + self.subtotal_transporte + self.subtotal_mano_obra
            + self.subtotal_administracion
        )
        self.total_valor_venta = sum(v["valor"] for v in totales.values())
        self.save(update_fields=[
            "subtotal_materiales", "subtotal_herramientas", "subtotal_transporte",
            "subtotal_mano_obra", "subtotal_administracion",
            "total_costo", "total_valor_venta", "updated_at",
        ])

    def calcular_tiempo(self):
        """Calcula días y tiempo estimado desde Total_PowerGrip y cuadrilla."""
        ps = self.proyecto_sistema
        total_pg = float(ps.total_powergip or 0)
        personas = float(ps.cuadrilla_personas or 1)
        if total_pg > 0 and personas > 0:
            self.dias_trabajo = total_pg / (personas * 40)
            self.tiempo_estimado_meses = 0.0333 * float(self.dias_trabajo)
            self.rendimiento_und_dia = total_pg / float(self.dias_trabajo) if self.dias_trabajo else 0
            self.save(update_fields=["dias_trabajo", "tiempo_estimado_meses", "rendimiento_und_dia", "updated_at"])


class APULinea(models.Model):
    """
    Línea individual del APU: un ítem de costo dentro de una categoría.
    """
    apu = models.ForeignKey(APUProyecto, on_delete=models.CASCADE, related_name="lineas")
    tipo = models.CharField(max_length=30, choices=TipoAPU.choices)
    descripcion = models.CharField(max_length=300)
    despiece_linea = models.ForeignKey(
        "presupuestos.DespieceLinea", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="apu_lineas",
        help_text="Referencia al ítem de despiece origen (solo materiales)",
    )
    rendimiento = models.DecimalField(max_digits=14, decimal_places=6, default=1,
                                      help_text="Cantidad de producto que rinde por unidad de APU")
    precio_referencia = models.DecimalField(max_digits=18, decimal_places=6, default=0,
                                            help_text="Precio unitario del insumo/recurso")
    iva_aplicado = models.BooleanField(default=True)

    # Calculados automáticamente
    costo_unitario = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    costo_total = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    valor_unitario = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    valor_total = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    editable = models.BooleanField(default=False,
                                   help_text="Si True, el usuario puede modificar precio_referencia/rendimiento")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "presupuestos"
        db_table = "apu_lineas"
        ordering = ["tipo", "descripcion"]

    def __str__(self):
        return f"{self.tipo} / {self.descripcion}"

    def calcular(self):
        """
        Recalcula costo_unitario, costo_total, valor_unitario, valor_total
        usando los parámetros del APUProyecto padre.
        """
        apu = self.apu
        iva_factor = (1 + float(apu.iva_pct) / 100) if (self.iva_aplicado and apu.aplica_iva) else 1.0
        factor_venta = 1 + float(apu.factor_venta_pct) / 100
        rend = float(self.rendimiento) or 1.0
        precio = float(self.precio_referencia)

        self.costo_unitario = precio * iva_factor
        self.costo_total = rend * float(self.costo_unitario)
        self.valor_unitario = float(self.costo_unitario) * factor_venta
        self.valor_total = rend * float(self.valor_unitario)
        self.save(update_fields=["costo_unitario", "costo_total", "valor_unitario", "valor_total", "updated_at"])
