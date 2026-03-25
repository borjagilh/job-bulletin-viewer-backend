# scrapers/bocyl_scraper.py - Scraper para BOCYL

from .base_scraper import BaseScraper
from datetime import datetime, timedelta
from utils import extract_deadline_from_text
from config import Config
import re
import logging

logger = logging.getLogger(__name__)

BOCYL_BASE = 'https://bocyl.jcyl.es'


class BOCYLScraper(BaseScraper):
    """Scraper para el Boletín Oficial de Castilla y León"""

    def __init__(self):
        super().__init__(
            source_name='BOCYL',
            base_url=BOCYL_BASE
        )

    def scrape(self):
        """
        Extrae ofertas de empleo del BOCYL navegando el boletín diario.
        Usa boletin.do?fechaBoletin=DD/MM/YYYY para acceder al sumario.
        """
        jobs = []

        self.session.headers.update({
            'Accept-Language': 'es-ES,es;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Referer': BOCYL_BASE
        })

        try:
            logger.info(f"[{self.source_name}] Iniciando scraping...")

            # Establecer sesión con la homepage
            self.make_request(BOCYL_BASE)

            # Intentar los últimos 7 días
            for i in range(7):
                date = datetime.now().date() - timedelta(days=i)
                date_str = date.strftime('%d/%m/%Y')
                url = f"{BOCYL_BASE}/boletin.do?fechaBoletin={date_str}"

                response = self.make_request(url)
                if not response or response.status_code != 200:
                    continue

                soup = self.parse_html(response.content)
                if not soup:
                    continue

                # Verificar que hay contenido de boletín
                if not soup.find('h2', string=re.compile(r'Sumario BOCYL', re.I)):
                    # Puede que no haya boletín ese día
                    if not soup.find('h4', string=re.compile(r'Oposicion|Concurso', re.I)):
                        continue

                logger.info(f"[{self.source_name}] Boletín encontrado para {date_str}")

                # Extraer documentos de secciones de oposiciones/concursos
                new_jobs = self._extract_jobs_from_sumario(soup, date)
                jobs.extend(new_jobs)

                if new_jobs:
                    break  # Con un boletín que tiene jobs es suficiente

        except Exception as e:
            logger.error(f"[{self.source_name}] Error durante scraping: {e}")

        logger.info(f"[{self.source_name}] Total ofertas IT encontradas: {len(jobs)}")
        self.log_scraping_result(len(jobs), len(jobs))
        return jobs

    def _extract_jobs_from_sumario(self, soup, publish_date):
        """Extrae jobs del sumario HTML del BOCYL buscando en secciones de oposiciones."""
        jobs = []
        seen_urls = set()

        # Buscar todos los h4 que corresponden a "Oposiciones y Concursos"
        for h4 in soup.find_all('h4'):
            h4_text = h4.get_text(strip=True).lower()
            if 'oposicion' not in h4_text and 'concurso' not in h4_text:
                continue

            # Recorrer hermanos: h5 (org) + p (título) + ul (links)
            current_org = ''
            current_title = ''
            sibling = h4.find_next_sibling()

            while sibling and sibling.name not in ['h3', 'h4']:
                if sibling.name == 'h5':
                    current_org = sibling.get_text(strip=True)
                elif sibling.name == 'p':
                    current_title = sibling.get_text(strip=True)
                elif sibling.name == 'ul' and 'descargaBoletin' in (sibling.get('class') or []):
                    # Tenemos un grupo completo: org + título + links
                    if current_title and self.is_it_related(current_title, Config.IT_KEYWORDS):
                        # Buscar el enlace HTML (.do)
                        html_link = sibling.find('a', href=re.compile(r'\.do$|html.*\.do'))
                        if not html_link:
                            # Fallback: cualquier link
                            html_link = sibling.find('a', href=True)

                        if html_link:
                            href = html_link.get('href', '')
                            abs_url = href if href.startswith('http') else f"{BOCYL_BASE}/{href.lstrip('/')}"

                            if abs_url not in seen_urls:
                                seen_urls.add(abs_url)
                                self.delay(2)
                                job = self.parse_bocyl_announcement(
                                    abs_url, publish_date, current_title, current_org
                                )
                                if job:
                                    jobs.append(job)

                    # Reset para el siguiente documento
                    current_title = ''

                sibling = sibling.find_next_sibling()

        return jobs

    def parse_bocyl_announcement(self, announcement_url, publish_date, title_fallback='', org_fallback=''):
        """Parsea un anuncio individual del BOCYL"""
        try:
            response = self.make_request(announcement_url)
            if not response:
                return None

            content_type = response.headers.get('Content-Type', '').lower()
            if 'pdf' in content_type:
                return self._parse_pdf_announcement(
                    response.content, announcement_url, publish_date, title_fallback, org_fallback
                )

            soup = self.parse_html(response.content)
            if not soup:
                return None

            # Título: dentro de .interiores, el primer <p> después del h5 es el título
            title = title_fallback
            body_div = soup.select_one('.interiores') or soup.find('div', class_='interiores')
            if body_div:
                # Buscar el primer <p> que no sea breadcrumb y tenga texto oficial
                for p in body_div.find_all('p'):
                    p_text = p.get_text(strip=True)
                    if p_text and len(p_text) > 15 and 'Inicio' not in p_text:
                        title = p_text[:200]
                        break

            if not title or len(title) < 5:
                return None

            # Organismo
            organization = org_fallback or 'Junta de Castilla y León'
            if not organization:
                org_match = re.search(
                    r'Resoluci[oó]n de (?:la |el |los )?(.*?)(?:,|\.| por)', title, re.I
                )
                if org_match:
                    organization = org_match.group(1).strip()

            # Cuerpo del texto
            body = (
                body_div or
                soup.select_one('#contenidoSumario') or
                soup.select_one('.cuerpoDisposicion') or
                soup.select_one('#contenido') or
                soup.find('article') or
                soup.find('main')
            )
            body_text = body.get_text(' ', strip=True) if body else soup.get_text(' ', strip=True)
            description = body_text[:500]

            requirements = 'Ver boletín oficial'
            if body:
                for p in body.find_all('p'):
                    p_text = p.get_text(strip=True)
                    if any(kw in p_text.lower() for kw in ['titulaci', 'requisito', 'grupo', 'subgrupo']):
                        requirements = p_text[:300]
                        break

            deadline_str = extract_deadline_from_text(body_text)
            deadline = self.parse_spanish_date(deadline_str) if deadline_str else None
            if not deadline or deadline < publish_date:
                deadline = publish_date + timedelta(days=20)

            # Determinar categoría según organismo
            org_lower = organization.lower()
            if any(w in org_lower for w in ['ayuntamiento', 'municipio', 'concejo']):
                category = 'Administración Local'
            elif any(w in org_lower for w in ['diputaci', 'provincial']):
                category = 'Administración Provincial'
            else:
                category = 'Administración Autonómica'

            return {
                'title': title,
                'source': self.source_name,
                'organization': organization,
                'location': 'Castilla y León',
                'publish_date': publish_date,
                'deadline': deadline,
                'category': category,
                'description': description or title,
                'requirements': requirements,
                'url': announcement_url
            }

        except Exception as e:
            logger.error(f"[{self.source_name}] Error parseando anuncio {announcement_url}: {e}")
            return None

    def _parse_pdf_announcement(self, pdf_content, url, publish_date, title_fallback='', org_fallback=''):
        """Extrae datos de un PDF de anuncio BOCYL"""
        try:
            from PyPDF2 import PdfReader
            import io

            reader = PdfReader(io.BytesIO(pdf_content))
            full_text = '\n'.join(page.extract_text() or '' for page in reader.pages)
            if not full_text.strip():
                return None

            lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            title = lines[0][:200] if lines else title_fallback
            if not title or len(title) < 5:
                title = title_fallback
            if not title:
                return None

            description = ' '.join(lines[:10])[:500]
            requirements = 'Ver boletín oficial'
            for line in lines:
                if any(kw in line.lower() for kw in ['titulaci', 'requisito', 'grupo']):
                    requirements = line[:300]
                    break

            deadline_str = extract_deadline_from_text(full_text)
            deadline = self.parse_spanish_date(deadline_str) if deadline_str else None
            if not deadline or deadline < publish_date:
                deadline = publish_date + timedelta(days=20)

            org = org_fallback or 'Junta de Castilla y León'
            org_lower = org.lower()
            if any(w in org_lower for w in ['ayuntamiento', 'municipio']):
                category = 'Administración Local'
            else:
                category = 'Administración Autonómica'

            return {
                'title': title,
                'source': self.source_name,
                'organization': org,
                'location': 'Castilla y León',
                'publish_date': publish_date,
                'deadline': deadline,
                'category': category,
                'description': description,
                'requirements': requirements,
                'url': url
            }

        except Exception as e:
            logger.error(f"[{self.source_name}] Error parseando PDF BOCYL: {e}")
            return None
