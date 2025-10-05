from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime
from enum import Enum


class GameStatus(str, Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    COMPLETED = "completed"


class GameCreate(BaseModel):
    creator_id: int = Field(..., description="ID of the player creating the game")


class JoinGame(BaseModel):
    player_id: int = Field(..., description="ID of the player joining the game")


class MoveCreate(BaseModel):
    player_id: int = Field(..., description="ID of the player making the move")
    row: int = Field(..., ge=0, le=2, description="Row index (0-2)")
    col: int = Field(..., ge=0, le=2, description="Column index (0-2)")


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
