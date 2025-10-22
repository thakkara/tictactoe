"""
Router registration for the TicTacToe API.
"""
from fastapi import FastAPI

from app.api import games, players, leaderboard


def include_routers(app: FastAPI) -> None:
    """Include all API routers with the FastAPI application."""
    app.include_router(games.router, prefix="/api/v1", tags=["games"])
    app.include_router(players.router, prefix="/api/v1", tags=["players"])
    app.include_router(leaderboard.router, prefix="/api/v1", tags=["leaderboard"])