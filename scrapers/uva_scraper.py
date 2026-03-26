# scrapers/uva_scraper.py - Scraper para Universidad de Valladolid

from .base_scraper import BaseScraper
from datetime import datetime, timedelta
from utils import extract_deadline_from_text
from config import Config
import re
import logging

logger = logging.getLogger(__name__)

UVA_SEDE = 'https://sede.uva.es'

# Categorías relevantes del tablón y sus slugs/totales aproximados
# URL: /tablon/{slug}/1/0/{total}
TABLON_CATEGORIES = [
    ('ptgas', 'PTGAS'),
    ('pdi', 'PDI'),
    ('investigacion', 'Investigación'),
]

# Categorías extra que pueden tener convocatorias IT
# También las categorías de la Sede electrónica de la UVa principal
UVA_EXTRA_SOURCES = [
    'https://www.uva.es/universidad/empleo-en-la-uva/',
]


class UVaScraper(BaseScraper):
    """Scraper para Universidad de Valladolid (Sede Electrónica - Tablón)"""

    def __init__(self):
        super().__init__(
            source_name='Boletín UVa',
            base_url=UVA_SEDE
        )

    def scrape(self):
        """
        Extrae ofertas de empleo IT del tablón de la Sede Electrónica de la UVa.
        Accede a las categorías PTGAS y PDI del tablón para buscar convocatorias IT.
        """
        jobs = []

        self.session.headers.update({
            'Accept-Language': 'es-ES,es;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Referer': UVA_SEDE
        })

        try:
            logger.info(f"[{self.source_name}] Iniciando scraping del tablón...")

            seen_urls = set()

            for cat_slug, cat_name in TABLON_CATEGORIES:
                # Acceder a las 3 primeras páginas de cada categoría (30 items más recientes)
                for page in range(1, 4):
                    url = f"{UVA_SEDE}/tablon/{cat_slug}/{page}/0/9999"
                    response = self.make_request(url)
                    if not response:
                        break

                    soup = self.parse_html(response.content)
                    if not soup:
                        break

                    table = soup.find('table', id='ListadoAnuncios')
                    if not table:
                        break

                    rows = table.find_all('tr')
                    items_found_this_page = 0

                    for row in rows[1:]:  # Skip header
                        cells = row.find_all('td')
                        if len(cells) < 2:
                            continue

                        title_text = cells[0].get_text(' ', strip=True)
                        date_text = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        doc_links = cells[2].find_all('a', href=True) if len(cells) > 2 else []

                        if not title_text or len(title_text) < 5:
                            continue

                        items_found_this_page += 1

                        # Filtrar por IT keywords
                        if not self.is_it_related(title_text, Config.IT_KEYWORDS):
                            continue

                        # Obtener link al documento
                        if not doc_links:
                            continue
                        doc_href = doc_links[0].get('href', '')
                        abs_url = doc_href if doc_href.startswith('http') else f"{UVA_SEDE}{doc_href}"

                        if abs_url in seen_urls:
                            continue
                        seen_urls.add(abs_url)

                        # Parsear fecha
                        publish_date = self.parse_spanish_date(date_text) or datetime.now().date()

                        self.delay(2)
                        job = self.parse_uva_announcement(abs_url, title_text, publish_date, cat_name)
                        if job:
                            jobs.append(job)

                    # Si la página tiene pocas filas, no paginar más
                    if items_found_this_page < 9:
                        break
                    self.delay(1)

        except Exception as e:
            logger.error(f"[{self.source_name}] Error durante scraping: {e}")

        logger.info(f"[{self.source_name}] Total ofertas IT encontradas: {len(jobs)}")
        self.log_scraping_result(len(jobs), len(jobs))
        return jobs

    def parse_uva_announcement(self, doc_url, title_fallback, publish_date, category_name='PTGAS'):
        """
        Parsea un documento del tablón de la UVa.
        El documento es un PDF accesible en /documento-tablon/{uuid}.
        """
        try:
            response = self.make_request(doc_url)
            if not response:
                return self._build_job(title_fallback, publish_date, doc_url, category_name)

            content_type = response.headers.get('Content-Type', '').lower()
            full_text = ''

            if 'pdf' in content_type or doc_url.endswith('.pdf'):
                try:
                    from PyPDF2 import PdfReader
                    import io
                    reader = PdfReader(io.BytesIO(response.content))
                    full_text = '\n'.join(page.extract_text() or '' for page in reader.pages)
                except Exception as pdf_e:
                    logger.warning(f"[{self.source_name}] Error leyendo PDF: {pdf_e}")
            elif 'html' in content_type:
                soup = self.parse_html(response.content)
                if soup:
                    full_text = soup.get_text(' ', strip=True)

            if not full_text.strip():
                return self._build_job(title_fallback, publish_date, doc_url, category_name)

            lines = [l.strip() for l in full_text.splitlines() if l.strip()]

            # Descripción: primeras líneas del documento
            description = ' '.join(lines[:12])[:500] or title_fallback

            # Requisitos: buscar párrafo con titulación/requisitos
            requirements = 'Ver convocatoria en sede.uva.es'
            for line in lines:
                if any(kw in line.lower() for kw in ['titulaci', 'requisito', 'grupo', 'subgrupo', 'ciclo formativo', 'grado superior']):
                    requirements = line[:300]
                    break

            # Deadline: extraer del texto del PDF
            deadline_str = extract_deadline_from_text(full_text)
            deadline = self.parse_spanish_date(deadline_str) if deadline_str else None
            if not deadline or deadline < publish_date:
                deadline = publish_date + timedelta(days=20)

            # Localización: Valladolid (con posibilidad de campus)
            location = 'Valladolid'
            campus_match = re.search(
                r'\b(Palencia|Soria|Segovia)\b', full_text[:500], re.I
            )
            if campus_match:
                location = campus_match.group(0).capitalize()

            return {
                'title': title_fallback,
                'source': self.source_name,
                'organization': 'Universidad de Valladolid',
                'location': location,
                'publish_date': publish_date,
                'deadline': deadline,
                'category': 'Universidad',
                'description': description,
                'requirements': requirements,
                'url': doc_url
            }

        except Exception as e:
            logger.error(f"[{self.source_name}] Error parseando {doc_url}: {e}")
            return self._build_job(title_fallback, publish_date, doc_url, category_name)

    def _build_job(self, title, publish_date, url, category_name='PTGAS'):
        """Construye un job básico solo con los datos del listado."""
        return {
            'title': title,
            'source': self.source_name,
            'organization': 'Universidad de Valladolid',
            'location': 'Valladolid',
            'publish_date': publish_date,
            'deadline': publish_date + timedelta(days=20),
            'category': 'Universidad',
            'description': title,
            'requirements': 'Ver convocatoria en sede.uva.es',
            'url': url
        }

    def scrape_research_jobs(self):
        """Alias para compatibilidad - delegado a scrape()."""
        return []
