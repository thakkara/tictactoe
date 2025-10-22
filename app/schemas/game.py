from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime
from enum import Enum

from app.core.game_config import MIN_GRID_SIZE, MAX_GRID_SIZE, DEFAULT_GRID_SIZE


class GameStatus(str, Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    COMPLETED = "completed"


class GameCreate(BaseModel):
    creator_id: int = Field(..., description="ID of the player creating the game")
    grid_size: int = Field(
        DEFAULT_GRID_SIZE, 
        ge=MIN_GRID_SIZE, 
        le=MAX_GRID_SIZE, 
        description=f"Grid size for the game ({MIN_GRID_SIZE}x{MIN_GRID_SIZE} to {MAX_GRID_SIZE}x{MAX_GRID_SIZE})"
    )


class JoinGame(BaseModel):
    player_id: int = Field(..., description="ID of the player joining the game")


class MoveCreate(BaseModel):
    player_id: int = Field(..., description="ID of the player making the move")
    row: int = Field(..., ge=0, description="Row index (validated against game's grid size)")
    col: int = Field(..., ge=0, description="Column index (validated against game's grid size)")


class MoveResponse(BaseModel):
    id: int
    game_id: int
    player_id: int
    row: int
    col: int
    move_number: int
    game_status: GameStatus
    winner_id: Optional[int] = None
    is_draw: bool = False

    class Config:
        orm_mode = True


class GameResponse(BaseModel):
    id: int
    status: GameStatus
    grid_size: int
    players: List[int]
    current_turn: Optional[int]
    board: List[List[Optional[int]]]
    created_at: datetime
    started_at: Optional[datetime]

    @validator("board", pre=True)
    def parse_board(cls, v):
        import json
        if isinstance(v, str):
            return json.loads(v)
        return v

    class Config:
        orm_mode = True


class GameState(BaseModel):
    id: int
    status: GameStatus
    grid_size: int
    players: List[int]
    current_turn: Optional[int]
    winner_id: Optional[int]
    board: List[List[Optional[int]]]
    moves_count: int
    created_at: datetime
    started_at: Optional[datetime]
    ended_at: Optional[datetime]

    class Config:
        orm_mode = True
