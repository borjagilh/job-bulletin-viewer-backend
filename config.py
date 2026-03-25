# config.py - Configuración centralizada del backend

import os


class Config:
    """Configuración base de la aplicación"""

    # Base de datos
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///jobs.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'True') == 'True'

    # API
    API_PREFIX = '/api'

    # Scraping
    SCRAPING_ENABLED = os.getenv('SCRAPING_ENABLED', 'True') == 'True'
    SCRAPING_HOUR = int(os.getenv('SCRAPING_HOUR', '8'))  # Hora del día para scraping automático
    SCRAPING_MINUTE = int(os.getenv('SCRAPING_MINUTE', '0'))

    # Request settings
    REQUEST_TIMEOUT = 30  # segundos
    REQUEST_DELAY = 2  # segundos entre requests

    # Palabras clave IT
    IT_KEYWORDS = [
        'informátic', 'programad', 'desarrollad', 'software', 'sistemas',
        'tecnología', 'tecnolog', 'ciberseguridad', 'redes', 'datos',
        'web', 'aplicaciones', 'TIC', 'digital', 'analista',
        'administrador de sistemas', 'devops', 'ingenier', 'cloud',
        'base de datos', 'inteligencia artificial', 'machine learning',
        'desarrollo', 'backend', 'frontend', 'fullstack'
    ]


class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True


class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://user:pass@localhost/jobsdb')


# Seleccionar configuración según entorno
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}