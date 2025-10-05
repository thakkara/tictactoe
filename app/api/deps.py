"""
Dependency injection for API endpoints.
"""
from typing import Generator

from app.core.database import SessionLocal


def get_db() -> Generator:
    """
    Database dependency that ensures proper session cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()





