"""
apps/ingenieria/system_defs — Definiciones backend de sistemas técnicos.

Cada archivo Python en este paquete define completamente un sistema:
  - Variables de entrada que el presupuestador debe ingresar
  - Componentes del conjunto con sus fórmulas
  - Categoría de producto por componente
  - Orden de ejecución y variables de cascada

El presupuestador NUNCA configura fórmulas ni reglas desde la interfaz.
Solo ingresa variables (ej: total_powergrip=2883) y ejecuta el despiece.
"""
