from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PlayerCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, description="Unique username")


class PlayerResponse(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        orm_mode = True


class PlayerStats(BaseModel):
    player_id: int
    username: str
    total_games: int
    wins: int
    losses: int
    draws: int
    win_rate: float
    total_moves: int
    efficiency: Optional[float] = Field(None, description="Average moves per win")

    class Config:
        orm_mode = True


class LeaderboardEntry(BaseModel):
    rank: int
    player_id: int
    username: str
    wins: int
    total_games: int
    win_rate: float
    efficiency: Optional[float] = None

    class Config:
        orm_mode = True