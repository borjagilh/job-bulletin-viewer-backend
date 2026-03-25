# scrapers/uva_scraper.py - Scraper para Universidad de Valladolid

from .base_scraper import BaseScraper
from datetime import datetime, timedelta
from utils import extract_deadline_from_text
from config import Config
import re
import logging

logger = logging.getLogger(__name__)

UVA_BASE = 'https://www.uva.es'

EMPLOYMENT_URLS = [
    f"{UVA_BASE}/export/sites/uva/6.vidauniversitaria/6.01.ofertaempleo/",
    f"{UVA_BASE}/export/sites/uva/7.comunidaduniversitaria/7.09.tablondeanuncios/",
]


class UVaScraper(BaseScraper):
    """Scraper para Universidad de Valladolid"""

    def __init__(self):
        super().__init__(
            source_name='Boletín UVa',
            base_url=UVA_BASE
        )

    def scrape(self):
        """Extrae ofertas de empleo IT de las páginas de empleo de la UVa."""
        jobs = []

        self.session.headers.update({
            'Accept-Language': 'es-ES,es;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Referer': self.base_url
        })

        try:
            logger.info(f"[{self.source_name}] Iniciando scraping...")

            seen_urls = set()

            for listing_url in EMPLOYMENT_URLS:
                response = self.make_request(listing_url)
                if not response:
                    continue

                soup = self.parse_html(response.content)
                if not soup:
                    continue

                # Buscar todos los enlaces en la página
                links = soup.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)

                    if not text or len(text) < 5:
                        continue

                    # Solo seguir links internos que parezcan convocatorias
                    if not (href.startswith('/') or href.startswith(UVA_BASE)):
                        continue

                    # Filtrar por keywords IT
                    if not self.is_it_related(text, Config.IT_KEYWORDS):
                        continue

                    # Construir URL absoluta
                    if href.startswith('/'):
                        abs_url = f"{UVA_BASE}{href}"
                    else:
                        abs_url = href

                    if abs_url in seen_urls:
                        continue
                    seen_urls.add(abs_url)

                    # Intentar extraer fecha del contexto del listing (span/li adyacente)
                    listing_date_str = None
                    parent = link.parent
                    if parent:
                        parent_text = parent.get_text()
                        date_match = re.search(
                            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', parent_text
                        )
                        if date_match:
                            listing_date_str = date_match.group(1)

                    self.delay(2)
                    job = self.parse_uva_announcement(abs_url, listing_date_str)
                    if job:
                        jobs.append(job)

        except Exception as e:
            logger.error(f"[{self.source_name}] Error durante scraping: {e}")

        logger.info(f"[{self.source_name}] Total ofertas IT encontradas: {len(jobs)}")
        self.log_scraping_result(len(jobs), len(jobs))
        return jobs

    def parse_uva_announcement(self, announcement_url, listing_date_str=None):
        """Parsea un anuncio de la UVa"""
        try:
            response = self.make_request(announcement_url)
            if not response:
                return None

            soup = self.parse_html(response.content)
            if not soup:
                return None

            # Título: buscar h1, luego h2
            title = ''
            for tag in ['h1', 'h2']:
                t = soup.find(tag)
                if t:
                    title = t.get_text(strip=True)
                    if title:
                        break

            if not title or len(title) < 5:
                return None

            # Fecha de publicación: buscar <th> con 'publicaci' y su <td> adyacente
            publish_date = None
            th_pub = soup.find('th', string=re.compile(r'publicaci', re.I))
            if th_pub:
                td = th_pub.find_next_sibling('td')
                if td:
                    publish_date = self.parse_spanish_date(td.get_text(strip=True))

            # Fallback: fecha del listing o del texto
            if not publish_date and listing_date_str:
                publish_date = self.parse_spanish_date(listing_date_str)
            if not publish_date:
                publish_date = datetime.now().date()

            # Deadline: buscar <th> con 'plazo' y su <td>
            deadline = None
            th_plazo = soup.find('th', string=re.compile(r'plazo', re.I))
            if th_plazo:
                td = th_plazo.find_next_sibling('td')
                if td:
                    deadline = self.parse_spanish_date(td.get_text(strip=True))

            # Fallback deadline desde texto de la página
            if not deadline:
                full_text = soup.get_text()
                deadline_str = extract_deadline_from_text(full_text)
                if deadline_str:
                    deadline = self.parse_spanish_date(deadline_str)

            if not deadline or deadline < publish_date:
                deadline = publish_date + timedelta(days=20)

            # Localización: Valladolid por defecto, buscar campus
            location = 'Valladolid'
            full_text = soup.get_text()
            campus_match = re.search(
                r'\b(Palencia|Soria|Segovia|Valladolid)\b', full_text, re.I
            )
            if campus_match:
                location = campus_match.group(0).capitalize()

            # Descripción
            description = ''
            desc_div = soup.select_one('.descripcion, .contenido-principal, #contenido, main')
            if desc_div:
                description = desc_div.get_text(strip=True)[:500]
            if not description:
                description = title

            # Requisitos
            requirements = ''
            req_div = soup.select_one('.requisitos')
            if req_div:
                requirements = req_div.get_text(strip=True)[:300]
            if not requirements:
                # Buscar párrafo con palabras clave de requisitos
                for p in soup.find_all('p'):
                    p_text = p.get_text(strip=True)
                    if any(kw in p_text.lower() for kw in ['titulaci', 'requisito', 'grupo', 'ciclo formativo']):
                        requirements = p_text[:300]
                        break
            if not requirements:
                requirements = 'Ver convocatoria oficial'

            return {
                'title': title,
                'source': self.source_name,
                'organization': 'Universidad de Valladolid',
                'location': location,
                'publish_date': publish_date,
                'deadline': deadline,
                'category': 'Universidad',
                'description': description,
                'requirements': requirements,
                'url': announcement_url
            }

        except Exception as e:
            logger.error(f"[{self.source_name}] Error parseando anuncio {announcement_url}: {e}")
            return None

    def scrape_research_jobs(self):
        """Convocatorias de investigación (delegado a scrape() principal)"""
        return []
