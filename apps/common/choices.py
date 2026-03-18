"""
apps/common/choices.py — Enumeraciones compartidas entre todas las apps.

Regla: si un Choice lo usan dos o más apps distintas, vive aquí.
Si solo lo usa una app, puede vivir en esa app.
"""

from django.db import models


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
