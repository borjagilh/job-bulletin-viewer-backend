# scrapers/__init__.py - Inicialización del módulo de scrapers

from .base_scraper import BaseScraper
from .boe_scraper import BOEScraper
from .bocyl_scraper import BOCYLScraper
from .bop_scraper import BOPValladolidScraper
from .uva_scraper import UVaScraper

__all__ = [
    'BaseScraper',
    'BOEScraper',
    'BOCYLScraper',
    'BOPValladolidScraper',
    'UVaScraper'
]

def get_all_scrapers():
    """Retorna una lista con instancias de todos los scrapers disponibles"""
    return [
        BOEScraper(),
        BOCYLScraper(),
        BOPValladolidScraper(),
        UVaScraper()
    ]