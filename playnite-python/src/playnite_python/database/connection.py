"""Database connection management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from loguru import logger

from ..core.config import settings
from .models import Base

# Create engine
engine = create_engine(
    settings.database_url,
    echo=False,  # Set to True for SQL query logging
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def get_db():
    """Get database session (dependency injection for FastAPI)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
