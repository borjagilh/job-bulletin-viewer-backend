# scrapers/boe_scraper.py - Scraper para el BOE

from .base_scraper import BaseScraper
from datetime import datetime, timedelta
from utils import extract_deadline_from_text
from config import Config
import re
import logging

logger = logging.getLogger(__name__)

BOE_BASE = 'https://www.boe.es'


class BOEScraper(BaseScraper):
    """Scraper para el Boletín Oficial del Estado"""

    def __init__(self):
        super().__init__(
            source_name='BOE',
            base_url=BOE_BASE
        )

    def scrape(self):
        """
        Extrae ofertas de empleo IT del BOE usando el sumario HTML diario.
        Busca en sección II-B (Oposiciones y concursos).
        """
        jobs = []

        self.session.headers.update({
            'Accept-Language': 'es-ES,es;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Referer': BOE_BASE
        })

        try:
            logger.info(f"[{self.source_name}] Iniciando scraping...")

            # Intentar los últimos 7 días para cubrir fines de semana y festivos
            sumario_soup = None
            publish_date = None
            for i in range(7):
                date = datetime.now().date() - timedelta(days=i)
                url = f"{BOE_BASE}/boe/dias/{date.year}/{date.month:02d}/{date.day:02d}/"
                response = self.make_request(url)
                if response and response.status_code == 200:
                    soup = self.parse_html(response.content)
                    # Verificar que hay contenido real (el BOE no publica todos los días)
                    if soup and soup.find(id='sec702B'):
                        sumario_soup = soup
                        publish_date = date
                        logger.info(f"[{self.source_name}] Sumario encontrado para {date}")
                        break

            if not sumario_soup or not publish_date:
                logger.warning(f"[{self.source_name}] No se encontró sumario en los últimos 7 días")
                self.log_scraping_result(0, 0)
                return jobs

            # Extraer items de sección II-B (Oposiciones y concursos)
            items_secs = []
            # También buscar en sec702A (Nombramientos) por si hay técnicos
            for sec_id in ['sec702B', 'sec702A']:
                sec_el = sumario_soup.find(id=sec_id)
                if not sec_el:
                    continue
                # Recorrer hermanos hasta la siguiente sección
                sibling = sec_el.find_next_sibling()
                while sibling and not (sibling.get('id', '').startswith('sec7') and sibling.get('id') != sec_id):
                    for li in sibling.find_all('li', class_='dispo'):
                        p = li.find('p')
                        title = p.get_text(strip=True) if p else ''
                        # Extraer ID del documento del enlace al PDF
                        pdf_link = li.find('a', href=re.compile(r'BOE-A-\d{4}-\d+'))
                        if not pdf_link:
                            continue
                        doc_id_match = re.search(r'(BOE-A-\d{4}-\d+)', pdf_link.get('href', ''))
                        if not doc_id_match:
                            continue
                        doc_id = doc_id_match.group(1)
                        # Obtener organismo del h4 más cercano anterior
                        org = self._get_parent_departamento(li)
                        items_secs.append((doc_id, title, org))
                    sibling = sibling.find_next_sibling()

            logger.info(f"[{self.source_name}] Items en sección II: {len(items_secs)}")

            for doc_id, title, org in items_secs:
                if not self.is_it_related(title, Config.IT_KEYWORDS):
                    continue
                self.delay(1)
                job = self.parse_boe_document(doc_id, publish_date, title, org)
                if job:
                    jobs.append(job)

        except Exception as e:
            logger.error(f"[{self.source_name}] Error durante scraping: {e}")

        logger.info(f"[{self.source_name}] Total ofertas IT encontradas: {len(jobs)}")
        self.log_scraping_result(len(jobs), len(jobs))
        return jobs

    def _get_parent_departamento(self, element):
        """Busca el h4 (departamento) más cercano antes del elemento."""
        for prev in element.find_all_previous(['h4', 'h3']):
            text = prev.get_text(strip=True)
            if text:
                return text
        return 'Administración General del Estado'

    def parse_boe_document(self, doc_id, publish_date, titulo_fallback='', org_fallback=''):
        """Parsea el texto HTML de un documento individual del BOE."""
        try:
            url = f"{BOE_BASE}/diario_boe/txt.php?id={doc_id}"
            response = self.make_request(url)
            if not response:
                return None

            soup = self.parse_html(response.content)
            if not soup:
                return None

            # Título: buscar en el encabezado del documento
            title = titulo_fallback
            title_tag = soup.find('h3', class_='documento-tit') or soup.find('h3')
            if title_tag:
                t = title_tag.get_text(strip=True)
                if t and len(t) > 5:
                    title = t

            # Contenido del documento
            body = soup.find('div', class_='texto') or soup.find('div', id='texto') or soup.find('article')
            full_text = body.get_text(' ', strip=True) if body else soup.get_text(' ', strip=True)

            description = full_text[:500]

            # Requisitos
            requirements = ''
            if body:
                for p in body.find_all('p'):
                    p_text = p.get_text(strip=True)
                    if any(kw in p_text.lower() for kw in ['titulaci', 'requisito', 'grupo', 'subgrupo', 'nivel']):
                        requirements = p_text[:300]
                        break
            if not requirements:
                requirements = 'Ver documento oficial en BOE'

            # Deadline
            deadline_str = extract_deadline_from_text(full_text)
            deadline = self.parse_spanish_date(deadline_str) if deadline_str else None
            if not deadline or deadline < publish_date:
                deadline = publish_date + timedelta(days=20)

            # Localización
            location = 'España'
            loc_match = re.search(
                r'\b(Madrid|Barcelona|Valencia|Valladolid|Sevilla|Zaragoza|Bilbao|'
                r'Málaga|Alicante|Murcia|Palma|Las Palmas|Santander|Pamplona|Vitoria|'
                r'Logroño|Mérida|Toledo|Guadalajara|Burgos|León|Salamanca|Segovia|Soria|'
                r'Ávila|Palencia|Zamora|Albacete|Badajoz|Cáceres|Cádiz|Córdoba|Granada|'
                r'Huelva|Jaén|Almería)\b',
                full_text, re.I
            )
            if loc_match:
                location = loc_match.group(0)

            return {
                'title': title,
                'source': self.source_name,
                'organization': org_fallback or 'Administración General del Estado',
                'location': location,
                'publish_date': publish_date,
                'deadline': deadline,
                'category': 'Administración General del Estado',
                'description': description or title,
                'requirements': requirements,
                'url': url
            }

        except Exception as e:
            logger.error(f"[{self.source_name}] Error parseando documento {doc_id}: {e}")
            return None
