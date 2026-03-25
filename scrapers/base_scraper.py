
# scrapers/base_scraper.py - Clase base para todos los scrapers

import requests
import time
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Clase base abstracta para todos los scrapers"""

    def __init__(self, source_name, base_url):
        self.source_name = source_name
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    @abstractmethod
    def scrape(self):
        """
        Método abstracto que debe implementar cada scraper.
        Debe retornar una lista de diccionarios con las ofertas encontradas.

        Formato de cada oferta:
        {
            'title': str,
            'source': str,
            'organization': str,
            'location': str,
            'publish_date': date,
            'deadline': date,
            'category': str,
            'description': str,
            'requirements': str,
            'url': str
        }
        """
        pass

    def make_request(self, url, method='GET', **kwargs):
        """Realiza una petición HTTP con manejo de errores"""
        try:
            logger.info(f"[{self.source_name}] Requesting: {url}")

            if method.upper() == 'GET':
                response = self.session.get(url, timeout=30, **kwargs)
            elif method.upper() == 'POST':
                response = self.session.post(url, timeout=30, **kwargs)
            else:
                raise ValueError(f"Método HTTP no soportado: {method}")

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.source_name}] Error en request a {url}: {e}")
            return None

    def parse_html(self, html_content):
        """Parsea contenido HTML con BeautifulSoup"""
        try:
            return BeautifulSoup(html_content, 'lxml')
        except Exception as e:
            logger.error(f"[{self.source_name}] Error parseando HTML: {e}")
            return None

    def is_it_related(self, text, keywords):
        """Verifica si el texto contiene palabras clave de IT"""
        if not text:
            return False

        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in keywords)

    def parse_spanish_date(self, date_str):
        """
        Intenta parsear fechas en diferentes formatos españoles.
        Retorna un objeto date o None si falla.
        """
        if not date_str:
            return None

        # Formatos comunes en boletines oficiales españoles
        formats = [
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%d.%m.%Y',
            '%Y-%m-%d',
            '%d de %B de %Y',
            '%d de %b de %Y'
        ]

        # Mapeo de meses en español
        months_es = {
            'enero': 'January', 'febrero': 'February', 'marzo': 'March',
            'abril': 'April', 'mayo': 'May', 'junio': 'June',
            'julio': 'July', 'agosto': 'August', 'septiembre': 'September',
            'octubre': 'October', 'noviembre': 'November', 'diciembre': 'December'
        }

        # Reemplazar nombres de meses en español por inglés
        date_str_clean = date_str.strip()
        for es, en in months_es.items():
            date_str_clean = date_str_clean.replace(es, en)

        # Intentar parsear con cada formato
        for fmt in formats:
            try:
                return datetime.strptime(date_str_clean, fmt).date()
            except ValueError:
                continue

        logger.warning(f"[{self.source_name}] No se pudo parsear fecha: {date_str}")
        return None

    def extract_text(self, element, selector=None, default=''):
        """Extrae texto de un elemento HTML de forma segura"""
        try:
            if selector:
                found = element.select_one(selector)
                return found.get_text(strip=True) if found else default
            return element.get_text(strip=True) if element else default
        except Exception as e:
            logger.error(f"[{self.source_name}] Error extrayendo texto: {e}")
            return default

    def delay(self, seconds=2):
        """Añade un delay entre requests para ser respetuoso"""
        time.sleep(seconds)

    def log_scraping_result(self, jobs_found, jobs_valid):
        """Registra el resultado del scraping"""
        logger.info(
            f"[{self.source_name}] Scraping completado: "
            f"{jobs_found} ofertas encontradas, "
            f"{jobs_valid} relacionadas con IT"
        )