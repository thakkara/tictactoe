"""
Game-related API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import (
    GameNotFound, GameFull, NotYourTurn,
    CellOccupied, GameEnded, PlayerNotFound
)
from app.schemas import game as game_schemas
from app.services.game_service import game_service_obj

router = APIRouter(
    prefix="/games",
    tags=["games"],
    responses={404: {"description": "Game not found"}}
)


@router.post("", response_model=game_schemas.GameResponse)
def create_game(
        game: game_schemas.GameCreate,
        db: Session = Depends(get_db)
):
    """
    Create a new game session.

    The creator automatically becomes the first player.
    The game starts in 'waiting' status until a second player joins.
    """
    try:
        return game_service_obj.create_game(db, game.creator_id)
    except PlayerNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create game")


@router.post("/{game_id}/join", response_model=game_schemas.GameResponse)
def join_game(
        game_id: int,
        player: game_schemas.JoinGame,
        db: Session = Depends(get_db)
):
    """
    Join an existing game session as the second player.

    Once the second player joins:
    - Game status changes to 'active'
    - First player (creator) gets the first turn
    """
    try:
        return game_service_obj.join_game(db, game_id, player.player_id)
    except GameNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except GameFull as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PlayerNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to join game")


@router.post("/{game_id}/move", response_model=game_schemas.MoveResponse)
def make_move(
        game_id: int,
        move: game_schemas.MoveCreate,
        db: Session = Depends(get_db)
):
    """
    Make a move in the game.

    Validates:
    - Game exists and is active
    - It's the player's turn
    - The cell is empty
    - Player is part of the game

    Returns the move result including:
    - Move details
    - Updated game status
    - Winner (if game ended)
    - Draw status (if applicable)
    """
    try:
        res = game_service_obj.make_move(
            db, game_id, move.player_id, move.row, move.col
        )
        return res
    except GameNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotYourTurn as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": "NOT_YOUR_TURN"}
        )
    except CellOccupied as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": "CELL_OCCUPIED"}
        )
    except GameEnded as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": "GAME_ENDED"}
        )
    except PlayerNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to make move")


@router.get("/{game_id}", response_model=game_schemas.GameState)
def get_game_state(
        game_id: int,
        db: Session = Depends(get_db)
):
    """
    Get the current state of a game.

    Returns:
    - Current board state
    - Game status
    - Players
    - Current turn (if active)
    - Winner (if completed)
    - Move count
    """
    try:
        return game_service_obj.get_game_state(db, game_id)
    except GameNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get game state")
