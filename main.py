"""
A distributed backend for managing concurrent tictactoe.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import games, players, leaderboard
from app.core.config import settings
from app.core.database import engine, Base
from app.core.exceptions import (
    GameException, GameNotFound, GameFull,
    NotYourTurn, CellOccupied, GameEnded, PlayerNotFound
)

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

    # Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise

    # Warm up the connection pool
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Database connection pool initialized")

    yield

    # Shutdown
    logger.info("Shutting down TicTacToe API...")
    engine.dispose()
    logger.info("Database connections closed")


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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS if hasattr(settings, 'ALLOWED_ORIGINS') else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Error-Code", "X-Request-ID"]
)

# Add trusted host middleware for production
if not settings.DEBUG:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS if hasattr(settings, 'ALLOWED_HOSTS') else ["*"]
    )

# Global exception handlers
@app.exception_handler(GameNotFound)
async def game_not_found_handler(request: Request, exc: GameNotFound):
    """Handle game not found exceptions."""
    return JSONResponse(
        status_code=404,
        content={
            "detail": str(exc),
            "error_code": "GAME_NOT_FOUND",
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


@app.exception_handler(PlayerNotFound)
async def player_not_found_handler(request: Request, exc: PlayerNotFound):
    """Handle player not found exceptions."""
    return JSONResponse(
        status_code=404,
        content={
            "detail": str(exc),
            "error_code": "PLAYER_NOT_FOUND",
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


@app.exception_handler(GameFull)
async def game_full_handler(request: Request, exc: GameFull):
    """Handle game full exceptions."""
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "error_code": "GAME_FULL",
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


@app.exception_handler(NotYourTurn)
async def not_your_turn_handler(request: Request, exc: NotYourTurn):
    """Handle not your turn exceptions."""
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "error_code": "NOT_YOUR_TURN",
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


@app.exception_handler(CellOccupied)
async def cell_occupied_handler(request: Request, exc: CellOccupied):
    """Handle cell occupied exceptions."""
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "error_code": "CELL_OCCUPIED",
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


@app.exception_handler(GameEnded)
async def game_ended_handler(request: Request, exc: GameEnded):
    """Handle game ended exceptions."""
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "error_code": "GAME_ENDED",
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


@app.exception_handler(GameException)
async def game_exception_handler(request: Request, exc: GameException):
    """Handle generic game exceptions."""
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "error_code": "GAME_ERROR",
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with better formatting."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(x) for x in error["loc"][1:]),
            "message": error["msg"],
            "type": error["type"]
        })

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": errors,
            "error_code": "VALIDATION_ERROR",
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle generic HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": f"HTTP_{exc.status_code}",
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)

    # Don't expose internal errors in production
    if settings.DEBUG:
        detail = str(exc)
    else:
        detail = "An unexpected error occurred"

    return JSONResponse(
        status_code=500,
        content={
            "detail": detail,
            "error_code": "INTERNAL_ERROR",
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


# Include routers
app.include_router(games.router, prefix="/api/v1")
app.include_router(players.router, prefix="/api/v1")
app.include_router(leaderboard.router, prefix="/api/v1")

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