# scrapers/bop_scraper.py - Scraper para BOP Valladolid

from .base_scraper import BaseScraper
from datetime import datetime, timedelta
from utils import extract_deadline_from_text
from config import Config
import re
import logging

logger = logging.getLogger(__name__)

BOP_BASE = 'https://bop.sede.diputaciondevalladolid.es'
LISTING_URL = f'{BOP_BASE}/ultimobop'

MESES_ES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
    5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
    9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
}


class BOPValladolidScraper(BaseScraper):
    """Scraper para el BOP de la Provincia de Valladolid"""

    def __init__(self):
        super().__init__(
            source_name='BOP Valladolid',
            base_url=BOP_BASE
        )

    def scrape(self):
        """
        Extrae ofertas de empleo IT del BOP de Valladolid.
        - Usa /ultimobop para obtener el boletín actual (HTML estático con todos los anuncios).
        - Para cada anuncio IT-related, parsea el PDF para extraer datos completos.
        """
        jobs = []

        self.session.headers.update({
            'Accept-Language': 'es-ES,es;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Referer': BOP_BASE
        })

        try:
            logger.info(f"[{self.source_name}] Iniciando scraping desde {LISTING_URL}")

            response = self.make_request(LISTING_URL)
            if not response:
                logger.warning(f"[{self.source_name}] No se pudo acceder al BOP")
                self.log_scraping_result(0, 0)
                return jobs

            soup = self.parse_html(response.content)
            if not soup:
                self.log_scraping_result(0, 0)
                return jobs

            # Extraer la fecha del boletín (h2 con la fecha)
            publish_date = datetime.now().date()
            h2 = soup.find('h2')
            if h2:
                date_parsed = self.parse_spanish_date(h2.get_text(strip=True))
                if date_parsed:
                    publish_date = date_parsed

            logger.info(f"[{self.source_name}] Boletín del {publish_date}")

            # Recoger anuncios únicos: cada <li> con links a BOPVA-*.pdf
            seen_urls = set()
            anuncios = []  # (title, org, pdf_url, section_name)
            current_section = 'III.-ADMINISTRACIÓN LOCAL'

            for el in soup.find_all(['p', 'li']):
                # Actualizar sección actual si es un título de sección
                if el.name == 'p' and 'titulo_secc_boletin' in (el.get('class') or []):
                    current_section = el.get_text(strip=True)
                    continue

                if el.name != 'li':
                    continue

                links = el.find_all('a', href=lambda h: h and 'BOPVA' in h and h.endswith('.pdf'))
                if not links:
                    continue

                pdf_url = links[0].get('href', '')
                if pdf_url in seen_urls:
                    continue
                seen_urls.add(pdf_url)

                title = links[0].get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                # Extraer organismo: texto del li antes del link
                full_text = el.get_text(' ', strip=True)
                org = full_text[:full_text.find(title)].strip() if title in full_text else ''
                # Limpiar sección del texto del org
                for sec in ['I.-ADMINISTRACIÓN DEL ESTADO', 'II.-ADMINISTRACIÓN AUTONÓMICA',
                            'III.-ADMINISTRACIÓN LOCAL', 'IV.-ADMINISTRACIÓN DE JUSTICIA']:
                    org = org.replace(sec, '').strip()
                org = org.strip() or 'Diputación Provincial de Valladolid'

                anuncios.append((title, org, pdf_url, current_section))

            logger.info(f"[{self.source_name}] Anuncios encontrados: {len(anuncios)}")

            for title, org, pdf_url, section in anuncios:
                if not self.is_it_related(title, Config.IT_KEYWORDS):
                    continue

                self.delay(2)
                job = self.parse_bop_bulletin(pdf_url, title, org, publish_date, section)
                if job:
                    jobs.append(job)

        except Exception as e:
            logger.error(f"[{self.source_name}] Error durante scraping: {e}")

        logger.info(f"[{self.source_name}] Total ofertas IT encontradas: {len(jobs)}")
        self.log_scraping_result(len(jobs), len(jobs))
        return jobs

    def parse_bop_bulletin(self, pdf_url, title_fallback, org_fallback, publish_date, section=''):
        """Parsea el PDF de un anuncio del BOP para extraer datos completos."""
        try:
            response = self.make_request(pdf_url)
            if not response:
                return self._build_job_from_listing(
                    title_fallback, org_fallback, publish_date, pdf_url, section
                )

            content_type = response.headers.get('Content-Type', '').lower()
            full_text = ''

            if 'pdf' in content_type or pdf_url.endswith('.pdf'):
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
                return self._build_job_from_listing(
                    title_fallback, org_fallback, publish_date, pdf_url, section
                )

            lines = [l.strip() for l in full_text.splitlines() if l.strip()]

            # Título: usar el de la página de listado (más limpio que el del PDF)
            title = title_fallback

            # Organismo
            organization = org_fallback
            org_match = re.search(
                r'(Ayuntamiento|Diputaci[oó]n|Mancomunidad|Junta Vecinal|'
                r'Concejo|Entidad Local)\s+(?:de\s+)?([\wÁÉÍÓÚáéíóúñÑ\s]+?)(?:\.|,|\n)',
                full_text[:500], re.I
            )
            if org_match:
                organization = f"{org_match.group(1)} de {org_match.group(2).strip()}"

            # Categoría según organismo
            org_lower = organization.lower()
            if any(w in org_lower for w in ['ayuntamiento', 'junta vecinal', 'entidad local menor', 'concejo']):
                category = 'Administración Local'
            elif any(w in org_lower for w in ['diputaci', 'provinc']):
                category = 'Administración Provincial'
            else:
                category = 'Administración Local'

            # Localización
            location = 'Valladolid'
            loc_match = re.search(
                r'(?:Ayuntamiento|Mancomunidad|Junta Vecinal|Concejo|Entidad Local)\s+de\s+'
                r'([\wÁÉÍÓÚáéíóúñÑ\s]+?)(?:\.|,|\n)',
                full_text[:400], re.I
            )
            if loc_match:
                location = loc_match.group(1).strip()

            description = ' '.join(lines[:10])[:500] or title

            requirements = 'Ver BOP Valladolid'
            for line in lines:
                if any(kw in line.lower() for kw in ['titulaci', 'requisito', 'grupo', 'ciclo formativo']):
                    requirements = line[:300]
                    break

            deadline_str = extract_deadline_from_text(full_text)
            deadline = self.parse_spanish_date(deadline_str) if deadline_str else None
            if not deadline or deadline < publish_date:
                deadline = publish_date + timedelta(days=20)

            return {
                'title': title,
                'source': self.source_name,
                'organization': organization,
                'location': location,
                'publish_date': publish_date,
                'deadline': deadline,
                'category': category,
                'description': description,
                'requirements': requirements,
                'url': pdf_url
            }

        except Exception as e:
            logger.error(f"[{self.source_name}] Error parseando {pdf_url}: {e}")
            return self._build_job_from_listing(
                title_fallback, org_fallback, publish_date, pdf_url, section
            )

    def _build_job_from_listing(self, title, org, publish_date, url, section=''):
        """Construye un job básico solo con los datos del listado (sin detalle)."""
        org_lower = org.lower()
        if any(w in org_lower for w in ['ayuntamiento', 'junta vecinal', 'entidad local']):
            category = 'Administración Local'
        else:
            category = 'Administración Provincial'

        return {
            'title': title,
            'source': self.source_name,
            'organization': org or 'Diputación Provincial de Valladolid',
            'location': 'Valladolid',
            'publish_date': publish_date,
            'deadline': publish_date + timedelta(days=20),
            'category': category,
            'description': title,
            'requirements': 'Ver BOP Valladolid',
            'url': url
        }
