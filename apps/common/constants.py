"""
apps/common/constants.py — Constantes de sistema compartidas.
"""

# Formatos de consecutivos
FORMATO_CONSECUTIVO_SOLICITUD = "SLD-{year}-{num:04d}"
FORMATO_CONSECUTIVO_PROYECTO = "PRY-{year}-{num:04d}"
FORMATO_CODIGO_PRODUCTO = "{cat_codigo}-{num:04d}"

# Defaults financieros
# DEFAULT_TRM eliminado: nunca usar un valor inventado como fallback de TRM.
# Usar apps.common.trm_service.obtener_trm_vigente() que lanza TRMNoDisponibleError
# si no hay registro válido en BD.
DEFAULT_MARGEN_PCT = 130
DEFAULT_IVA_PCT = 19
DEFAULT_AIU_PCT = 130
DEFAULT_MONEDA = "COP"

# Defaults APU
DEFAULT_FACTOR_VENTA_PCT = 20
DEFAULT_AIU_CONTRATISTA_PCT = 30
DEFAULT_MARGEN_CONTRATISTA_PCT = 30
DEFAULT_DESPERDICIO_PCT = 3
