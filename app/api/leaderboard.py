"""
Leaderboard API endpoints.
"""
from enum import Enum
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas import player as player_schemas
from app.services.player_service import player_service_obj


class SortBy(str, Enum):
    WINS = "wins"
    EFFICIENCY = "efficiency"


router = APIRouter(
    prefix="/leaderboard",
    tags=["leaderboard"]
)


@router.get("", response_model=List[player_schemas.LeaderboardEntry])
def get_leaderboard(
        sort_by: SortBy = Query(SortBy.WINS, description="Ranking criteria"),
        db: Session = Depends(get_db)
):
    """
    Get the leaderboard showing top players.

    Ranking options:
    - wins: Most total wins
    - efficiency: Lowest average moves per win (requires at least 1 win)

    """
    try:
        return player_service_obj.get_leaderboard(
            db,
            sort_by=sort_by.value,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get leaderboard: {str(e)}"
        )