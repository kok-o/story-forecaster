from .session import Base, engine, SessionLocal, get_db
from .models import (
    Project,
    Work,
    WorkVersion,
    Chapter,
    Scene,
    Artifact,
    Run,
    Candidate
)

def init_db():
    """Initializes all database tables."""
    Base.metadata.create_all(bind=engine)

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "init_db",
    "Project",
    "Work",
    "WorkVersion",
    "Chapter",
    "Scene",
    "Artifact",
    "Run",
    "Candidate"
]
