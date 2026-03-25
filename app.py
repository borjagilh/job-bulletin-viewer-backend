# app.py - Backend Flask principal (VERSIÓN MODULAR)

from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os

# Importar módulos locales
from config import config
from models import db, JobOffer, ScrapingLog
from scrapers import get_all_scrapers
from utils import is_it_related, validate_job_data, deduplicate_jobs

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inicializar Flask
app = Flask(__name__)

# Cargar configuración
env = os.getenv('FLASK_ENV', 'development')
app.config.from_object(config[env])

# Inicializar extensiones
CORS(app)
db.init_app(app)


# ============================================================================
# FUNCIONES DE SCRAPING
# ============================================================================

def scrape_all_sources():
    """Ejecuta todos los scrapers y actualiza la base de datos"""
    logger.info("=" * 60)
    logger.info(f"INICIANDO SCRAPING PROGRAMADO: {datetime.now()}")
    logger.info("=" * 60)

    with app.app_context():
        scrapers = get_all_scrapers()
        total_jobs_found = 0
        total_jobs_added = 0

        for scraper in scrapers:
            log_entry = ScrapingLog(
                source=scraper.source_name,
                status='running',
                started_at=datetime.utcnow()
            )
            db.session.add(log_entry)
            db.session.commit()

            try:
                logger.info(f"\n--- Scraping {scraper.source_name} ---")

                # Ejecutar scraper
                jobs = scraper.scrape()
                jobs_found = len(jobs)
                jobs_added = 0

                # Procesar cada oferta encontrada
                for job_data in jobs:
                    try:
                        # Verificar si es relacionado con IT
                        full_text = f"{job_data['title']} {job_data['description']}"
                        if not is_it_related(full_text, app.config['IT_KEYWORDS']):
                            continue

                        # Validar datos
                        is_valid, error_msg = validate_job_data(job_data)
                        if not is_valid:
                            logger.warning(f"Datos inválidos: {error_msg}")
                            continue

                        # Verificar si ya existe
                        existing = JobOffer.query.filter_by(url=job_data['url']).first()
                        if existing:
                            logger.debug(f"Oferta ya existe: {job_data['title']}")
                            continue

                        # Crear nueva oferta
                        job = JobOffer.from_dict(job_data)
                        db.session.add(job)
                        jobs_added += 1

                        logger.info(f"✓ Nueva oferta: {job_data['title']}")

                    except Exception as e:
                        logger.error(f"Error procesando oferta: {e}")
                        continue

                # Commit de todas las ofertas del scraper
                db.session.commit()

                # Actualizar log
                log_entry.status = 'success'
                log_entry.jobs_found = jobs_found
                log_entry.jobs_added = jobs_added
                log_entry.completed_at = datetime.utcnow()
                db.session.commit()

                total_jobs_found += jobs_found
                total_jobs_added += jobs_added

                logger.info(f"✓ {scraper.source_name}: {jobs_found} encontradas, {jobs_added} añadidas")

            except Exception as e:
                logger.error(f"✗ Error en {scraper.source_name}: {e}")

                log_entry.status = 'error'
                log_entry.error_message = str(e)
                log_entry.completed_at = datetime.utcnow()
                db.session.commit()
                db.session.rollback()

        logger.info("=" * 60)
        logger.info(f"SCRAPING COMPLETADO: {datetime.now()}")
        logger.info(f"Total: {total_jobs_found} ofertas encontradas, {total_jobs_added} añadidas")
        logger.info("=" * 60)


# ============================================================================
# RUTAS DE LA API
# ============================================================================

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    """Obtiene todas las ofertas de empleo con filtros opcionales"""
    try:
        # Parámetros de filtrado
        source = request.args.get('source')
        category = request.args.get('category')
        search = request.args.get('search')
        active_only = request.args.get('active', 'false').lower() == 'true'

        # Query base
        query = JobOffer.query

        # Aplicar filtros
        if source and source != 'all':
            query = query.filter_by(source=source)

        if category and category != 'all':
            query = query.filter_by(category=category)

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                db.or_(
                    JobOffer.title.ilike(search_term),
                    JobOffer.description.ilike(search_term),
                    JobOffer.organization.ilike(search_term)
                )
            )

        if active_only:
            query = query.filter(JobOffer.deadline >= datetime.now().date())

        # Ordenar por fecha de publicación (más recientes primero)
        jobs = query.order_by(JobOffer.publish_date.desc()).all()

        return jsonify([job.to_dict() for job in jobs])

    except Exception as e:
        logger.error(f"Error en get_jobs: {e}")
        return jsonify({'error': 'Error al obtener ofertas'}), 500


@app.route('/api/jobs/<int:job_id>', methods=['GET'])
def get_job(job_id):
    """Obtiene los detalles de una oferta específica"""
    try:
        job = JobOffer.query.get_or_404(job_id)
        return jsonify(job.to_dict())
    except Exception as e:
        logger.error(f"Error en get_job: {e}")
        return jsonify({'error': 'Oferta no encontrada'}), 404


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Obtiene estadísticas generales del sistema"""
    try:
        total_jobs = JobOffer.query.count()

        # Ofertas por fuente
        by_source = db.session.query(
            JobOffer.source,
            db.func.count(JobOffer.id)
        ).group_by(JobOffer.source).all()

        # Ofertas activas (plazo no vencido)
        active_jobs = JobOffer.query.filter(
            JobOffer.deadline >= datetime.now().date()
        ).count()

        # Ofertas por categoría
        by_category = db.session.query(
            JobOffer.category,
            db.func.count(JobOffer.id)
        ).group_by(JobOffer.category).all()

        return jsonify({
            'total': total_jobs,
            'active': active_jobs,
            'by_source': dict(by_source),
            'by_category': dict(by_category)
        })

    except Exception as e:
        logger.error(f"Error en get_stats: {e}")
        return jsonify({'error': 'Error al obtener estadísticas'}), 500


@app.route('/api/sources', methods=['GET'])
def get_sources():
    """Obtiene lista de fuentes disponibles"""
    try:
        sources = db.session.query(JobOffer.source).distinct().all()
        return jsonify([s[0] for s in sources])
    except Exception as e:
        logger.error(f"Error en get_sources: {e}")
        return jsonify({'error': 'Error al obtener fuentes'}), 500


@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Obtiene lista de categorías disponibles"""
    try:
        categories = db.session.query(JobOffer.category).distinct().all()
        return jsonify([c[0] for c in categories])
    except Exception as e:
        logger.error(f"Error en get_categories: {e}")
        return jsonify({'error': 'Error al obtener categorías'}), 500


@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    """Endpoint manual para ejecutar scraping"""
    try:
        logger.info("Scraping manual iniciado por usuario")
        scrape_all_sources()
        return jsonify({'message': 'Scraping completado exitosamente'})
    except Exception as e:
        logger.error(f"Error en trigger_scrape: {e}")
        return jsonify({'error': 'Error al ejecutar scraping'}), 500


@app.route('/api/logs', methods=['GET'])
def get_scraping_logs():
    """Obtiene logs de scraping recientes"""
    try:
        limit = request.args.get('limit', 20, type=int)
        logs = ScrapingLog.query.order_by(
            ScrapingLog.started_at.desc()
        ).limit(limit).all()

        return jsonify([log.to_dict() for log in logs])
    except Exception as e:
        logger.error(f"Error en get_scraping_logs: {e}")
        return jsonify({'error': 'Error al obtener logs'}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })


# ============================================================================
# INICIALIZACIÓN
# ============================================================================

def init_db():
    """Inicializa la base de datos"""
    with app.app_context():
        db.create_all()

        # Insertar datos de ejemplo si la BD está vacía
        if JobOffer.query.count() == 0:
            logger.info("Base de datos vacía, insertando datos de ejemplo...")

            sample_jobs = [
                JobOffer(
                    title="Técnico/a Informático/a - Ayuntamiento de Valladolid",
                    source="BOP Valladolid",
                    organization="Ayuntamiento de Valladolid",
                    location="Valladolid",
                    publish_date=datetime.now().date(),
                    deadline=(datetime.now() + timedelta(days=30)).date(),
                    category="Administración Local",
                    description="Convocatoria para cubrir una plaza de técnico informático en el departamento de sistemas del Ayuntamiento.",
                    requirements="Titulación universitaria en Ingeniería Informática o equivalente",
                    url="https://bop.diputaciondevalladolid.es/ejemplo1"
                ),
                JobOffer(
                    title="Desarrollador/a Web - Junta de Castilla y León",
                    source="BOCYL",
                    organization="Junta de Castilla y León",
                    location="Valladolid",
                    publish_date=datetime.now().date(),
                    deadline=(datetime.now() + timedelta(days=20)).date(),
                    category="Administración Autonómica",
                    description="Proceso selectivo para incorporación de desarrollador web.",
                    requirements="Experiencia en desarrollo web, conocimientos de React, Node.js",
                    url="https://bocyl.jcyl.es/ejemplo2"
                )
            ]

            for job in sample_jobs:
                db.session.add(job)

            db.session.commit()
            logger.info(f"✓ {len(sample_jobs)} ofertas de ejemplo insertadas")


def start_scheduler():
    """Inicia el scheduler para scraping automático"""
    if not app.config['SCRAPING_ENABLED']:
        logger.info("Scraping automático deshabilitado")
        return

    scheduler = BackgroundScheduler()

    # Ejecutar scraping diariamente a la hora configurada
    scheduler.add_job(
        func=scrape_all_sources,
        trigger="cron",
        hour=app.config['SCRAPING_HOUR'],
        minute=app.config['SCRAPING_MINUTE']
    )

    scheduler.start()
    logger.info(
        f"✓ Scheduler iniciado - scraping diario a las "
        f"{app.config['SCRAPING_HOUR']:02d}:{app.config['SCRAPING_MINUTE']:02d}"
    )


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    logger.info("Iniciando aplicación...")

    init_db()
    start_scheduler()

    logger.info("=" * 60)
    logger.info("Servidor Flask iniciado")
    logger.info(f"Entorno: {env}")
    logger.info(f"Debug: {app.config['DEBUG']}")
    logger.info(f"Base de datos: {app.config['SQLALCHEMY_DATABASE_URI']}")
    logger.info("=" * 60)

    app.run(
        debug=app.config['DEBUG'],
        host='0.0.0.0',
        port=5000
    )