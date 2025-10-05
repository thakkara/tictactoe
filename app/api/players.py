"""
Player-related API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import PlayerNotFound
from app.schemas import player as player_schemas
from app.services.player_service import player_service_obj

router = APIRouter(
    prefix="/players",
    tags=["players"],
    responses={404: {"description": "Player not found"}}
)


@router.post("", response_model=player_schemas.PlayerResponse)
def create_player(
        player: player_schemas.PlayerCreate,
        db: Session = Depends(get_db)
):
    """
    Create a new player.

    Username must be unique. If username already exists,
    returns the existing player instead of creating a duplicate.
    """
    try:
        print(f"in create player {player}")
        return player_service_obj.create_player(db, player.username)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Failed to create player")


@router.get("/{player_id}/stats", response_model=player_schemas.PlayerStats)
def get_player_stats(
        player_id: int,
        db: Session = Depends(get_db)
):
    """
    Get comprehensive statistics for a player.

    Returns:
    - Total games played
    - Wins, losses, draws
    - Win rate percentage
    - Total moves made
    - Efficiency (average moves per win)
    """
    try:
        return player_service_obj.get_player_stats(db, player_id)
    except PlayerNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get player stats")
