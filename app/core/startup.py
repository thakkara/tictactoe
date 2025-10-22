"""
Application startup and shutdown logic for the TicTacToe API.
"""
import logging
from sqlalchemy import text

from app.core.database import engine, Base

logger = logging.getLogger(__name__)


def initialize_database() -> None:
    """Initialize database tables and warm up connection pool."""
    try:
        # Create database tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
        
        # Warm up the connection pool
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection pool initialized")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def shutdown_database() -> None:
    """Clean up database connections."""
    try:
        engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during database shutdown: {e}")
        # Don't re-raise during shutdown