# utils.py - Funciones de utilidad

from datetime import datetime
import re
import logging

logger = logging.getLogger(__name__)


def is_it_related(text, keywords):
    """
    Verifica si un texto contiene palabras clave relacionadas con IT.

    Args:
        text (str): Texto a analizar
        keywords (list): Lista de palabras clave

    Returns:
        bool: True si contiene palabras clave IT
    """
    if not text:
        return False

    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords)


def clean_text(text):
    """
    Limpia texto eliminando espacios extras, saltos de línea, etc.

    Args:
        text (str): Texto a limpiar

    Returns:
        str: Texto limpio
    """
    if not text:
        return ""

    # Eliminar espacios múltiples
    text = re.sub(r'\s+', ' ', text)

    # Eliminar espacios al inicio y final
    text = text.strip()

    return text


def extract_email(text):
    """
    Extrae dirección de email de un texto.

    Args:
        text (str): Texto que contiene email

    Returns:
        str or None: Email encontrado o None
    """
    if not text:
        return None

    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    match = re.search(email_pattern, text)

    return match.group(0) if match else None


def extract_deadline_from_text(text):
    """
    Intenta extraer fecha límite de un texto usando patrones comunes.

    Args:
        text (str): Texto que puede contener fecha

    Returns:
        str or None: Fecha extraída en formato string
    """
    if not text:
        return None

    # Patrones comunes de plazos
    patterns = [
        r'plazo.{0,20}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'hasta.{0,20}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'antes.{0,20}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def categorize_job(organization_name):
    """
    Determina la categoría de la oferta basándose en el organismo.

    Args:
        organization_name (str): Nombre del organismo

    Returns:
        str: Categoría de la oferta
    """
    org_lower = organization_name.lower()

    if any(word in org_lower for word in ['ministerio', 'estado', 'gobierno de españa']):
        return 'Administración General del Estado'

    elif any(word in org_lower for word in ['junta', 'comunidad', 'autonómica']):
        return 'Administración Autonómica'

    elif any(word in org_lower for word in ['diputación', 'diputacion', 'provincial']):
        return 'Administración Provincial'

    elif any(word in org_lower for word in ['ayuntamiento', 'municipio', 'concejo']):
        return 'Administración Local'

    elif any(word in org_lower for word in ['universidad', 'uva', 'campus']):
        return 'Universidad'

    else:
        return 'Otras Administraciones'


def format_job_summary(job):
    """
    Crea un resumen legible de una oferta de empleo.

    Args:
        job (dict): Diccionario con datos de la oferta

    Returns:
        str: Resumen formateado
    """
    summary = f"""
    Título: {job.get('title', 'N/A')}
    Organismo: {job.get('organization', 'N/A')}
    Ubicación: {job.get('location', 'N/A')}
    Plazo: {job.get('deadline', 'N/A')}
    URL: {job.get('url', 'N/A')}
    """
    return summary.strip()


def validate_job_data(job_data):
    """
    Valida que los datos de una oferta sean correctos.

    Args:
        job_data (dict): Datos de la oferta

    Returns:
        tuple: (es_valido, mensaje_error)
    """
    required_fields = [
        'title', 'source', 'organization', 'location',
        'publish_date', 'deadline', 'category',
        'description', 'requirements', 'url'
    ]

    # Verificar campos requeridos
    for field in required_fields:
        if field not in job_data or not job_data[field]:
            return False, f"Campo requerido faltante: {field}"

    # Verificar que title no esté vacío
    if len(job_data['title'].strip()) < 5:
        return False, "El título es demasiado corto"

    # Verificar URL
    if not job_data['url'].startswith('http'):
        return False, "URL inválida"

    # Verificar fechas
    try:
        if job_data['deadline'] < job_data['publish_date']:
            return False, "La fecha límite no puede ser anterior a la fecha de publicación"
    except:
        return False, "Formato de fechas inválido"

    return True, "OK"


def deduplicate_jobs(jobs):
    """
    Elimina ofertas duplicadas basándose en la URL.

    Args:
        jobs (list): Lista de ofertas

    Returns:
        list: Lista sin duplicados
    """
    seen_urls = set()
    unique_jobs = []

    for job in jobs:
        url = job.get('url')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)

    return unique_jobs