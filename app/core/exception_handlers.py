"""
Exception handlers for the TicTacToe API.
"""
import logging
from fastapi import Request, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.exceptions import (
    GameException, GameNotFound, GameFull,
    NotYourTurn, CellOccupied, GameEnded, PlayerNotFound
)

logger = logging.getLogger(__name__)


def create_error_response(status_code: int, detail: str, error_code: str, request: Request) -> JSONResponse:
    """Create a standardized error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "error_code": error_code,
            "request_id": getattr(request.state, 'request_id', None)
        }
    )


async def game_not_found_handler(request: Request, exc: GameNotFound) -> JSONResponse:
    """Handle game not found exceptions."""
    return create_error_response(404, str(exc), "GAME_NOT_FOUND", request)


async def player_not_found_handler(request: Request, exc: PlayerNotFound) -> JSONResponse:
    """Handle player not found exceptions."""
    return create_error_response(404, str(exc), "PLAYER_NOT_FOUND", request)


async def game_full_handler(request: Request, exc: GameFull) -> JSONResponse:
    """Handle game full exceptions."""
    return create_error_response(400, str(exc), "GAME_FULL", request)


async def not_your_turn_handler(request: Request, exc: NotYourTurn) -> JSONResponse:
    """Handle not your turn exceptions."""
    return create_error_response(400, str(exc), "NOT_YOUR_TURN", request)


async def cell_occupied_handler(request: Request, exc: CellOccupied) -> JSONResponse:
    """Handle cell occupied exceptions."""
    return create_error_response(400, str(exc), "CELL_OCCUPIED", request)


async def game_ended_handler(request: Request, exc: GameEnded) -> JSONResponse:
    """Handle game ended exceptions."""
    return create_error_response(400, str(exc), "GAME_ENDED", request)


async def game_exception_handler(request: Request, exc: GameException) -> JSONResponse:
    """Handle generic game exceptions."""
    return create_error_response(400, str(exc), "GAME_ERROR", request)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
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


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle generic HTTP exceptions."""
    return create_error_response(exc.status_code, exc.detail, f"HTTP_{exc.status_code}", request)


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)

    # Don't expose internal errors in production
    if settings.DEBUG:
        detail = str(exc)
    else:
        detail = "An unexpected error occurred"

    return create_error_response(500, detail, "INTERNAL_ERROR", request)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI app."""
    app.add_exception_handler(GameNotFound, game_not_found_handler)
    app.add_exception_handler(PlayerNotFound, player_not_found_handler)
    app.add_exception_handler(GameFull, game_full_handler)
    app.add_exception_handler(NotYourTurn, not_your_turn_handler)
    app.add_exception_handler(CellOccupied, cell_occupied_handler)
    app.add_exception_handler(GameEnded, game_ended_handler)
    app.add_exception_handler(GameException, game_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)