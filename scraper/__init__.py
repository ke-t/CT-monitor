"""
Paquete para scraping y parsing.
"""
from .browser import scrape_wishlist, timed_input
from .parser import parsear_cartas

__all__ = ['scrape_wishlist', 'timed_input', 'parsear_cartas']