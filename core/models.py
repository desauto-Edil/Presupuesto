"""
models.py — Modelos de datos

Jerarquía:
  Cliente → Solicitud → Proyecto → ProyectoSistema
    (Sistema/Subsistema) → DespieceLinea → APULinea
"""

from django.db import models
from django.utils import timezone
import re


# ---------------------------------------------------------------------------
# ENUMERACIONES
# ---------------------------------------------------------------------------

class RolSistema(models.TextChoices):
    ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
    PRESUPUESTOS = "PRESUPUESTOS", "Presupuestos"
    COMPRAS = "COMPRAS", "Compras"
    ASESOR_COMERCIAL = "ASESOR_COMERCIAL", "Asesor comercial"
    SOLO_LECTURA = "SOLO_LECTURA", "Solo lectura"


class EstadoSolicitud(models.TextChoices):
    BORRADOR = "BORRADOR", "Borrador"
    EN_GESTION = "EN_GESTION", "En gestión"
    APROBADA = "APROBADA", "Aprobada"
    RECHAZADA = "RECHAZADA", "Rechazada"
    CERRADA = "CERRADA", "Cerrada"


class EstadoProyecto(models.TextChoices):
    BORRADOR = "BORRADOR", "Borrador"
    SOLICITUD = "SOLICITUD", "Solicitud"
    DESPIECE = "DESPIECE", "Despiece"
    EN_REVISION_COMPRAS = "EN_REVISION_COMPRAS", "En revisión de precios (Compras)"
    DESPIECE_VALIDADO = "DESPIECE_VALIDADO", "Despiece validado"
    APU = "APU", "APU en proceso"
    APU_GENERADO = "APU_GENERADO", "APU enviado a revisión"
    COTIZADO = "COTIZADO", "Cotizado"
    APROBADO = "APROBADO", "Aprobado"
    CERRADO = "CERRADO", "Cerrado"
    ANULADO = "ANULADO", "Anulado"


class LineaNegocio(models.TextChoices):
    CUBIERTAS = "CUBIERTAS", "Cubiertas"
    FACHADAS = "FACHADAS", "Fachadas"
    OTROS = "OTROS", "Otros"


class OrigenProducto(models.TextChoices):
    NACIONAL = "NACIONAL", "Nacional"
    IMPORTADO = "IMPORTADO", "Importado"


class TipoRegla(models.TextChoices):
    FIJA = "FIJA", "Fija"
    VARIABLE_SISTEMA = "VARIABLE_SISTEMA", "Variable sistema"
    VARIABLE_PROYECTO = "VARIABLE_PROYECTO", "Variable proyecto"
    EDITABLE_USUARIO = "EDITABLE_USUARIO", "Editable usuario"
    DERIVADA = "DERIVADA", "Derivada de otro producto"


class Moneda(models.TextChoices):
    COP = "COP", "COP"
    USD = "USD", "USD"
    EUR = "EUR", "EUR"


class TipoAPU(models.TextChoices):
    MATERIALES = "MATERIALES", "Materiales"
    HERRAMIENTAS_EQUIPOS = "HERRAMIENTAS_EQUIPOS", "Herramientas y equipos"
    TRANSPORTE = "TRANSPORTE", "Transporte"
    MANO_DE_OBRA = "MANO_DE_OBRA", "Mano de obra"
    ADMINISTRACION = "ADMINISTRACION", "Administración"


# ---------------------------------------------------------------------------
# USUARIOS
# ---------------------------------------------------------------------------

class UsuarioSistema(models.Model):
    email = models.EmailField(unique=True)
    nombre_completo = models.CharField(max_length=200)
    password_hash = models.TextField()
    rol = models.CharField(
        max_length=30, 
        choices=RolSistema.choices, 
        default=RolSistema.SOLO_LECTURA)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "usuarios"

    def __str__(self):
        return f"{self.nombre_completo} ({self.rol})"


# ---------------------------------------------------------------------------
# CLIENTES
# ---------------------------------------------------------------------------

class Cliente(models.Model):
    nit = models.CharField(max_length=50, unique=True)
    razon_social = models.CharField(max_length=300)
    ciudad = models.CharField(max_length=100, blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)
    telefono_principal = models.CharField(max_length=30, blank=True, null=True)
    email_principal = models.EmailField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clientes"

    def __str__(self):
        return f"{self.razon_social} ({self.nit})"

    @property
    def contacto_principal(self):
        return self.contactos.filter(es_principal=True, activo=True).first()


class ContactoCliente(models.Model):
    cliente = models.ForeignKey(
        Cliente, 
        on_delete=models.CASCADE, 
        related_name="contactos"
    )
    nombre = models.CharField(max_length=200)
    cargo = models.CharField(max_length=120, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    telefono = models.CharField(max_length=30, blank=True, null=True)
    es_principal = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contactos_cliente"

    def __str__(self):
        return f"{self.nombre} — {self.cliente.razon_social}"


# ---------------------------------------------------------------------------
# SOLICITUDES
# ---------------------------------------------------------------------------

class Solicitud(models.Model):
    consecutivo = models.CharField(max_length=30, unique=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="solicitudes")
    contacto = models.ForeignKey(
        ContactoCliente, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="solicitudes"
    )
    creado_por = models.ForeignKey(
        UsuarioSistema, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="solicitudes_creadas"
    )
    nombre = models.CharField(max_length=300)
    descripcion = models.TextField(blank=True, null=True)
    fecha_entrega = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=EstadoSolicitud.choices, default=EstadoSolicitud.EN_GESTION)
    observaciones = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "solicitudes"

    def __str__(self):
        return f"{self.consecutivo} — {self.nombre}"

    def save(self, *args, **kwargs):
        """Auto-asigna el contacto principal si no fue especificado."""
        if not self.contacto_id and self.cliente_id:
            self.contacto = self.cliente.contacto_principal
        super().save(*args, **kwargs)

    @classmethod
    def siguiente_consecutivo(cls):
        """Genera el siguiente consecutivo SLD-YYYY-NNNN."""
        year = timezone.now().year
        prefix = f"SLD-{year}-"
        last = cls.objects.filter(consecutivo__startswith=prefix).order_by("-consecutivo").first()
        if last:
            num = int(last.consecutivo.split("-")[-1]) + 1
        else:
            num = 1
        return f"{prefix}{num:04d}"


# ---------------------------------------------------------------------------
# PROYECTOS
# ---------------------------------------------------------------------------

class TipoProyecto(models.Model):
    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "tipos_proyecto"

    def __str__(self):
        return self.nombre


class Proyecto(models.Model):
    consecutivo = models.CharField(
        max_length=30, 
        unique=True)
    solicitud = models.ForeignKey(
        Solicitud, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="proyectos"
    )
    cliente = models.ForeignKey(
        Cliente, 
        on_delete=models.PROTECT, 
        related_name="proyectos")
    creado_por = models.ForeignKey(
        UsuarioSistema, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="proyectos_creados"
    )
    tipo_proyecto = models.ForeignKey(
        TipoProyecto, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="proyectos"
    )
    nombre = models.CharField(max_length=300)
    descripcion = models.TextField(
        blank=True, 
        null=True)
    fecha_proyecto = models.DateField(auto_now_add=True)
    area_total_m2 = models.DecimalField(
        max_digits=14, 
        decimal_places=4, 
        blank=True, 
        null=True)
    perimetro_ml = models.DecimalField(
        max_digits=14, 
        decimal_places=4, 
        blank=True, 
        null=True)
    # Variables finan(predeterminadas, editables)
    trm = models.DecimalField(max_digits=14, 
                              decimal_places=4, 
                              default=4200)
    margen_comercial_pct = models.DecimalField(max_digits=8, 
                                               decimal_places=4, 
                                               default=20)
    iva_pct = models.DecimalField(max_digits=8, 
                                  decimal_places=4, 
                                  default=19)
    aiu_pct = models.DecimalField(max_digits=8, 
                                  decimal_places=4, 
                                  default=0)
    moneda = models.CharField(max_length=3, 
                              choices=Moneda.choices, 
                              default=Moneda.COP)
    aplica_exencion_iva = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True, null=True)
    estado = models.CharField(max_length=25,
                              choices=EstadoProyecto.choices,
                              default=EstadoProyecto.SOLICITUD)
    motivo_devolucion = models.TextField(
        blank=True, null=True,
        help_text="Motivo de rechazo o devolución por parte del Administrador o Compras"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "proyectos"

    def __str__(self):
        return f"{self.consecutivo} — {self.nombre}"

    @classmethod
    def siguiente_consecutivo(cls):
        year = timezone.now().year
        prefix = f"PRY-{year}-"
        last = cls.objects.filter(consecutivo__startswith=prefix).order_by("-consecutivo").first()
        if last:
            num = int(last.consecutivo.split("-")[-1]) + 1
        else:
            num = 1
        return f"{prefix}{num:04d}"

    def avanzar_a_despiece(self):
        if self.estado == EstadoProyecto.SOLICITUD:
            self.estado = EstadoProyecto.DESPIECE
            self.save(update_fields=["estado", "updated_at"])

    def avanzar_a_revision_compras(self):
        """Presupuestos envía a Compras porque los precios requieren actualización."""
        if self.estado == EstadoProyecto.DESPIECE:
            self.estado = EstadoProyecto.EN_REVISION_COMPRAS
            self.save(update_fields=["estado", "updated_at"])

    def volver_de_compras(self):
        """Compras confirma precios actualizados; regresa a Despiece para re-validar."""
        if self.estado == EstadoProyecto.EN_REVISION_COMPRAS:
            self.estado = EstadoProyecto.DESPIECE
            self.motivo_devolucion = None
            self.save(update_fields=["estado", "motivo_devolucion", "updated_at"])

    def avanzar_a_despiece_validado(self):
        """Presupuestos valida que todos los precios estén actualizados."""
        if self.estado in (EstadoProyecto.DESPIECE, EstadoProyecto.EN_REVISION_COMPRAS):
            self.estado = EstadoProyecto.DESPIECE_VALIDADO
            self.save(update_fields=["estado", "updated_at"])

    def avanzar_a_apu(self):
        """Solo desde DESPIECE_VALIDADO se puede iniciar el APU."""
        if self.estado == EstadoProyecto.DESPIECE_VALIDADO:
            self.estado = EstadoProyecto.APU
            self.save(update_fields=["estado", "updated_at"])

    def avanzar_a_apu_generado(self):
        """Presupuestos envía el APU completo a revisión del Administrador."""
        if self.estado == EstadoProyecto.APU:
            self.estado = EstadoProyecto.APU_GENERADO
            self.save(update_fields=["estado", "updated_at"])

    def aprobar_cotizacion(self):
        """Administrador aprueba el cálculo final y habilita la cotización."""
        if self.estado == EstadoProyecto.APU_GENERADO:
            self.estado = EstadoProyecto.COTIZADO
            self.motivo_devolucion = None
            self.save(update_fields=["estado", "motivo_devolucion", "updated_at"])

    def rechazar_apu(self, motivo: str = ""):
        """Administrador devuelve el APU para ajuste; regresa al estado APU."""
        if self.estado == EstadoProyecto.APU_GENERADO:
            self.estado = EstadoProyecto.APU
            self.motivo_devolucion = motivo
            self.save(update_fields=["estado", "motivo_devolucion", "updated_at"])

    def avanzar_a_cotizado(self):
        """Asesor confirma que la cotización fue enviada al cliente."""
        if self.estado == EstadoProyecto.COTIZADO:
            self.estado = EstadoProyecto.APROBADO
            self.save(update_fields=["estado", "updated_at"])


# ---------------------------------------------------------------------------
# CATÁLOGO: SISTEMAS, SUBSISTEMAS, PRODUCTOS
# ---------------------------------------------------------------------------

class Sistema(models.Model):
    codigo        = models.CharField(max_length=50, unique=True)
    nombre        = models.CharField(max_length=200)
    linea_negocio = models.CharField(max_length=20, 
                                     choices=LineaNegocio.choices)
    descripcion   = models.TextField(blank=True, null=True)
    activo        = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sistemas"

    def __str__(self):
        return self.nombre


class Subsistema(models.Model):
    sistema    = models.ForeignKey(Sistema, 
                                   on_delete=models.CASCADE, 
                                   related_name="subsistemas")
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subsistemas"

    def __str__(self):
        return f"{self.sistema.nombre} › {self.nombre}"


class UnidadMedida(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=50)
    abreviatura = models.CharField(max_length=15)

    class Meta:
        db_table = "unidades_medida"

    def __str__(self):
        return self.abreviatura


class CategoriaProducto(models.Model):
    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "categorias_producto"

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=300)
    categoria = models.ForeignKey(CategoriaProducto, 
                                  on_delete=models.PROTECT, 
                                  related_name="productos")
    unidad = models.ForeignKey(UnidadMedida, 
                               on_delete=models.PROTECT, 
                               related_name="productos")
    origen = models.CharField(max_length=15, 
                              choices=OrigenProducto.choices, 
                              default=OrigenProducto.NACIONAL)
    marca = models.CharField(max_length=150, 
                             blank=True, null=True)
    linea = models.CharField(max_length=150, 
                             blank=True, null=True)
    rendimiento = models.DecimalField(max_digits=14, 
                                      decimal_places=6, 
                                      blank=True, null=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "productos"

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"


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
        db_table = "proveedores"

    def __str__(self):
        return self.nombre


class ProductoProveedor(models.Model):
    producto = models.ForeignKey(Producto, 
                                       on_delete=models.CASCADE,
                                       related_name="proveedores_producto")
    proveedor = models.ForeignKey(Proveedor, 
                                       on_delete=models.CASCADE, 
                                       related_name="productos_proveedor")
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=6)
    moneda = models.CharField(max_length=3, choices=Moneda.choices, 
                                      default=Moneda.COP)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "productos_proveedor"
        unique_together = ("producto", "proveedor")

    def __str__(self):
        return f"{self.producto.nombre} — {self.proveedor.nombre}"


# ---------------------------------------------------------------------------
# REGLAS DE CÁLCULO Y DEPENDENCIAS
# ---------------------------------------------------------------------------

class ReglaCalculo(models.Model):
    """
    Define cómo se calcula la cantidad de un producto dentro de un subsistema.

    Fórmulas soportadas (campo formula_texto):
      - Constante:   "8"  →  cantidad = 8 * variable_entrada * factor_desperdicio
      - Coeficiente: "coef * var / div"  (parseo simbólico)
      - Expresión:   cualquier expresión Python-safe con variables del contexto

    Variables de contexto disponibles en la evaluación:
      Total_PowerGrip, area_m2, perimetro_ml, <nombre_producto_dependiente>
    """
    subsistema           = models.ForeignKey(Subsistema, on_delete=models.CASCADE, 
                                             related_name="reglas")
    producto             = models.ForeignKey(Producto, on_delete=models.CASCADE, 
                                             related_name="reglas_calculo")
    codigo               = models.CharField(max_length=60)
    nombre               = models.CharField(max_length=200)
    variable_entrada     = models.CharField(max_length=80, blank=True, null=True,
                                            help_text="Nombre de la variable de contexto usada como base (ej: Total_PowerGrip)")
    coeficiente          = models.DecimalField(max_digits=18, decimal_places=6, 
                                               blank=True, null=True)
    divisor              = models.DecimalField(max_digits=18, decimal_places=6, 
                                               blank=True, null=True)
    factor_desperdicio   = models.DecimalField(max_digits=12, decimal_places=6, 
                                               default=1.01)
    formula_texto        = models.TextField(
                               help_text="Expresión legible. Ej: (8 × Total_PowerGrip) * 101%")
    formula_python       = models.TextField(
                               blank=True, null=True,
                               help_text="Expresión Python evaluable. Usa variables del contexto.")
    tipo_regla           = models.CharField(max_length=30, choices=TipoRegla.choices, 
                                            default=TipoRegla.FIJA)
    orden_ejecucion      = models.IntegerField(default=1)
    editable_por_proyecto = models.BooleanField(default=False)
    version              = models.IntegerField(default=1)
    activa               = models.BooleanField(default=True)
    caso_prueba          = models.TextField(blank=True, null=True)
    creada_por           = models.ForeignKey(
        UsuarioSistema, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="reglas_creadas"
    )
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reglas_calculo"
        unique_together = ("subsistema", "codigo", "version")
        ordering = ["orden_ejecucion"]

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"

    def evaluar(self, contexto: dict) -> float:
        """
        Evalúa la regla con el contexto dado y retorna la cantidad calculada.
        El contexto debe incluir al menos la variable de entrada principal.
        """
        import math

        # Construir expresión Python si no está explícita
        expr = self.formula_python or self._formula_auto()
        if not expr:
            raise ValueError(f"Regla {self.codigo}: no tiene fórmula evaluable.")

        # Normalizar separadores decimales de la expresión
        safe_ctx = {k: float(v) for k, v in contexto.items() if v is not None}
        safe_ctx["math"] = math

        try:
            resultado = eval(expr, {"__builtins__": {}}, safe_ctx)  # noqa: S307
        except Exception as exc:
            raise ValueError(f"Regla {self.codigo}: error al evaluar '{expr}': {exc}") from exc

        return float(resultado)

    def _formula_auto(self):
        """Genera expresión Python automáticamente desde coeficiente/divisor/variable."""
        if not self.variable_entrada:
            return None
        var = self.variable_entrada
        coef = float(self.coeficiente) if self.coeficiente else 1.0
        div = float(self.divisor) if self.divisor else 1.0
        desp = float(self.factor_desperdicio)
        return f"({coef} * {var} / {div}) * {desp}"


class DependenciaTecnica(models.Model):
    """
    Relación obligatoria/condicional entre un producto seleccionado
    y los productos que se deben agregar automáticamente al despiece.
    """
    subsistema = models.ForeignKey(Subsistema, on_delete=models.CASCADE, related_name="dependencias")
    producto_origen = models.ForeignKey(
        Producto, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="dependencias_origen",
        help_text="Si es NULL la dependencia aplica a todo el subsistema"
    )
    producto_dependiente = models.ForeignKey(
        Producto, on_delete=models.CASCADE, related_name="dependencias_dependiente"
    )
    variable_entrada = models.CharField(max_length=80, blank=True, null=True)
    condicion_texto = models.TextField(blank=True, null=True)
    obligatoria = models.BooleanField(default=True)
    orden = models.IntegerField(default=1)
    tipo_regla = models.CharField(max_length=30, 
                                  choices=TipoRegla.choices, 
                                  default=TipoRegla.FIJA)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dependencias_tecnicas"
        ordering = ["orden"]

    def __str__(self):
        origen = self.producto_origen.nombre if self.producto_origen else "(subsistema)"
        return f"{origen} → {self.producto_dependiente.nombre}"


# ---------------------------------------------------------------------------
# PROYECTO ↔ SISTEMA / SUBSISTEMA
# ---------------------------------------------------------------------------

class ProyectoSistema(models.Model):
    """
    Vincula un proyecto con un sistema y un subsistema seleccionado.
    Aquí se almacenan las variables de entrada dinámicas (ej: Total_PowerGrip).
    """
    proyecto = models.ForeignKey(Proyecto, 
                                 on_delete=models.CASCADE, 
                                 related_name="proyecto_sistemas")
    sistema = models.ForeignKey(Sistema, 
                                on_delete=models.PROTECT, 
                                related_name="proyecto_sistemas")
    subsistema = models.ForeignKey(
        Subsistema, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="proyecto_sistemas"
    )
    orden = models.IntegerField(default=1)
    # Variables de entrada dinámicas del despiece
    total_powergip = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True,
        help_text="Cantidad base de PowerGrip ingresada por el usuario"
    )
    cuadrilla_personas = models.IntegerField(
        blank=True, null=True,
        help_text="Número de personas en la cuadrilla de instalación"
    )
    variables_extra  = models.JSONField(
        default=dict, blank=True,
        help_text="Variables adicionales editables por proyecto en formato JSON"
    )
    observaciones = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
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
        Retorna lista de líneas creadas.
        """
        if not self.subsistema:
            return []

        deps = DependenciaTecnica.objects.filter(
            subsistema=self.subsistema,
            obligatoria=True
        ).select_related("producto_dependiente")

        creadas = []
        for dep in deps:
            linea, nueva = DespieceLinea.objects.get_or_create(
                proyecto=self.proyecto,
                proyecto_sistema=self,
                producto=dep.producto_dependiente,
                defaults={
                    "cantidad_calculada": 0,
                    "es_dependencia_automatica": True,
                }
            )
            if nueva:
                creadas.append(linea)
        return creadas


# ---------------------------------------------------------------------------
# DESPIECE
# ---------------------------------------------------------------------------

class DespieceLinea(models.Model):
    """
    Línea de despiece: un producto con su cantidad calculada/ajustada
    para un proyecto y un proyecto_sistema específico.
    """
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, 
                                 related_name="despiece_lineas")
    proyecto_sistema = models.ForeignKey(
        ProyectoSistema, on_delete=models.CASCADE,
        blank=True, null=True, related_name="despiece_lineas"
    )
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, 
                                 related_name="despiece_lineas")
    regla = models.ForeignKey(
        ReglaCalculo, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="despiece_lineas"
    )
    cantidad_calculada = models.DecimalField(max_digits=18, 
                                             decimal_places=6)
    cantidad_ajustada = models.DecimalField(max_digits=18, 
                                            decimal_places=6, 
                                            blank=True, null=True)
    motivo_ajuste = models.TextField(blank=True, null=True)
    precio_snapshot  = models.DecimalField(max_digits=18, 
                                           decimal_places=6, 
                                           blank=True, 
                                           null=True, 
                                           help_text="Precio unitario al momento de calcular el despiece")
    es_dependencia_automatica = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "despiece_lineas"

    def __str__(self):
        return f"{self.proyecto.consecutivo} / {self.producto.nombre}"

    @property
    def cantidad_final(self):
        return self.cantidad_ajustada if self.cantidad_ajustada is not None else self.cantidad_calculada

    def capturar_precio(self):
        """Toma snapshot del mejor precio activo del producto."""
        pp = self.producto.proveedores_producto.filter(activo=True).order_by("precio_unitario").first()
        if pp:
            self.precio_snapshot = pp.precio_unitario
            self.save(update_fields=["precio_snapshot", "updated_at"])


# ---------------------------------------------------------------------------
# APU (Análisis de Precios Unitarios)
# ---------------------------------------------------------------------------

class ConfiguracionAPU(models.Model):
    """
    Valores predeterminados del APU, configurables por Administrador.
    Solo debe existir un registro activo.
    """
    nombre = models.CharField(max_length=100, default="Configuración global")
    porcentaje_ganancia = models.DecimalField(max_digits=8, 
                                              decimal_places=4, 
                                              default=20)
    aiu_contratista = models.DecimalField(max_digits=8, 
                                          decimal_places=4, 
                                          default=30)
    desperdicio  = models.DecimalField(max_digits=8, 
                                       decimal_places=4, 
                                       default=3)
    margen_ganancia_contratista = models.DecimalField(max_digits=8, 
                                                      decimal_places=4, 
                                                      default=30)
    activa = models.BooleanField(default=True)
    modificado_por = models.ForeignKey(
        UsuarioSistema, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="configs_apu"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
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
    Cabecera del APU para un ProyectoSistema. Almacena las variables
    de entrada del cálculo de mano de obra y los totales por categoría.
    """
    proyecto_sistema = models.OneToOneField(ProyectoSistema, on_delete=models.CASCADE, related_name="apu")
    # Variables de entrada (Nivel 4)
    factor_venta_pct = models.DecimalField(max_digits=8, decimal_places=4, default=20,
                                                    help_text="% margen sobre costo unitario → valor unitario")
    iva_pct = models.DecimalField(max_digits=8, decimal_places=4, default=19)
    aplica_iva = models.BooleanField(default=True)
    aiu_contratista_pct = models.DecimalField(max_digits=8, 
                                              decimal_places=4, 
                                              default=30)
    margen_contratista_pct = models.DecimalField(max_digits=8, 
                                                 decimal_places=4, 
                                                 default=30)
    # Parámetros de mano de obra
    dias_trabajo = models.DecimalField(max_digits=10, decimal_places=4, 
                                       blank=True, null=True)
    tiempo_estimado_meses = models.DecimalField(max_digits=10, 
                                                decimal_places=4, 
                                                blank=True, null=True)
    rendimiento_und_dia = models.DecimalField(max_digits=14, decimal_places=6, 
                                              blank=True, null=True)
    # Totales calculados (se actualizan al recalcular)
    subtotal_materiales = models.DecimalField(max_digits=18, decimal_places=4, 
                                              default=0)
    subtotal_herramientas = models.DecimalField(max_digits=18, decimal_places=4, 
                                                default=0)
    subtotal_transporte = models.DecimalField(max_digits=18, decimal_places=4, 
                                              default=0)
    subtotal_mano_obra = models.DecimalField(max_digits=18, decimal_places=4, 
                                             default=0)
    subtotal_administracion = models.DecimalField(max_digits=18, decimal_places=4, 
                                                  default=0)
    total_costo = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_valor_venta = models.DecimalField(max_digits=18, decimal_places=4, 
                                            default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
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
                valor=Sum("valor_total")
            )
            totales[tipo] = {"costo": float(agg["costo"] or 0), 
                             "valor": float(agg["valor"] or 0)}

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
            "total_costo", "total_valor_venta", "updated_at"
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
    Aplica la fórmula:
      costo_unitario = (cantidad_despiece / rendimiento) * precio_referencia * IVA_factor
      costo_total    = rendimiento_apu * costo_unitario
      valor_unitario = costo_unitario * (1 + factor_venta/100)
      valor_total    = rendimiento_apu * valor_unitario
    """
    apu = models.ForeignKey(APUProyecto, on_delete=models.CASCADE, related_name="lineas")
    tipo = models.CharField(max_length=30, choices=TipoAPU.choices)
    descripcion = models.CharField(max_length=300)
    despiece_linea = models.ForeignKey(
        DespieceLinea, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="apu_lineas",
        help_text="Referencia al ítem de despiece origen (solo materiales)"
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
