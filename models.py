# models.py - Modelos de base de datos

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class JobOffer(db.Model):
    """Modelo para ofertas de empleo"""

    __tablename__ = 'job_offers'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False, index=True)
    source = db.Column(db.String(100), nullable=False, index=True)
    organization = db.Column(db.String(300), nullable=False)
    location = db.Column(db.String(200), nullable=False, index=True)
    publish_date = db.Column(db.Date, nullable=False, index=True)
    deadline = db.Column(db.Date, nullable=False, index=True)
    category = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text, nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<JobOffer {self.title}>'

    def to_dict(self):
        """Convierte el modelo a diccionario para JSON"""
        return {
            'id': self.id,
            'title': self.title,
            'source': self.source,
            'organization': self.organization,
            'location': self.location,
            'publishDate': self.publish_date.isoformat(),
            'deadline': self.deadline.isoformat(),
            'category': self.category,
            'description': self.description,
            'requirements': self.requirements,
            'url': self.url,
            'createdAt': self.created_at.isoformat() if self.created_at else None
        }

    @staticmethod
    def from_dict(data):
        """Crea un objeto JobOffer desde un diccionario"""
        return JobOffer(
            title=data.get('title'),
            source=data.get('source'),
            organization=data.get('organization'),
            location=data.get('location'),
            publish_date=data.get('publish_date'),
            deadline=data.get('deadline'),
            category=data.get('category'),
            description=data.get('description'),
            requirements=data.get('requirements'),
            url=data.get('url')
        )


class ScrapingLog(db.Model):
    """Modelo para logs de scraping"""

    __tablename__ = 'scraping_logs'

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False)  # success, error, partial
    jobs_found = db.Column(db.Integer, default=0)
    jobs_added = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<ScrapingLog {self.source} - {self.status}>'

    def to_dict(self):
        return {
            'id': self.id,
            'source': self.source,
            'status': self.status,
            'jobsFound': self.jobs_found,
            'jobsAdded': self.jobs_added,
            'errorMessage': self.error_message,
            'startedAt': self.started_at.isoformat() if self.started_at else None,
            'completedAt': self.completed_at.isoformat() if self.completed_at else None
        }