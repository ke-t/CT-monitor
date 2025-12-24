"""
Paquete para manejo de base de datos.
"""
from .handler import inicializar_bd, guardar_historial, analizar_ejemplo
from .stats_generator import generar_html_stats

__all__ = ['inicializar_bd', 'guardar_historial', 'analizar_ejemplo', 'generar_html_stats']