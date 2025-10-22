"""
A distributed backend for managing concurrent tictactoe.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import include_routers
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.startup import initialize_database, shutdown_database

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifecycle events."""
    # Startup
    logger.info("Starting Tic Tac Toe ...")
    initialize_database()

    yield

    # Shutdown
    logger.info("Shutting down TicTacToe API...")
    shutdown_database()


# Create FastAPI application
app = FastAPI(
    title="TicTacToe",
    description="""
    A distributed backend API for managing concurrent TicTacToe.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Register exception handlers
register_exception_handlers(app)


# Include routers
include_routers(app)

# CLI entry point
if __name__ == "__main__":
    import uvicorn

    # Development server configuration
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
        access_log=True
    )