"""
Pydantic schemas for matchmaking API.
"""
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class MatchmakingRequest(BaseModel):
    """Request to join matchmaking queue"""
    player_id: int = Field(..., description="ID of the player joining the queue")
    grid_sizes: List[int] = Field([3], description="Acceptable grid sizes (3, 4, 5)")
    max_rating_difference: int = Field(200, ge=50, le=1000, description="Maximum rating difference")
    queue_type: str = Field("ranked", description="Queue type: ranked, casual, tournament")
    max_wait_time: int = Field(120, ge=30, le=600, description="Maximum wait time in seconds")
    
    @validator("grid_sizes")
    def validate_grid_sizes(cls, v):
        if not v or not all(3 <= size <= 10 for size in v):
            raise ValueError("Grid sizes must be between 3 and 10")
        return list(set(v))  # Remove duplicates
    
    @validator("queue_type")
    def validate_queue_type(cls, v):
        if v not in ["ranked", "casual", "tournament"]:
            raise ValueError("Queue type must be: ranked, casual, or tournament")
        return v


class MatchmakingResponse(BaseModel):
    """Response when joining matchmaking"""
    success: bool
    queue_id: Optional[int] = None
    estimated_wait_time: Optional[int] = None  # seconds
    message: str
    error_code: Optional[str] = None


class QueueStatusResponse(BaseModel):
    """Current matchmaking queue status"""
    total_searching: int
    queue_breakdown: Dict[str, Dict[str, Any]]  # queue_type -> {count, avg_wait_time}
    active_searches: int


class PlayerRatingResponse(BaseModel):
    """Player's current ratings and stats"""
    player_id: int
    overall_rating: int
    grid_3x3_rating: int
    grid_4x4_rating: int
    grid_5x5_rating: int
    games_played: int
    rating_deviation: float
    peak_rating: int
    current_win_streak: int
    current_loss_streak: int
    best_win_streak: int


class MatchHistoryResponse(BaseModel):
    """Individual match history entry"""
    match_id: int
    opponent_id: int
    game_id: Optional[int]
    rating_difference: int
    wait_time: int  # seconds
    match_quality_score: float
    game_completion_status: Optional[str]
    created_at: datetime


class LobbyPlayerResponse(BaseModel):
    """Player information in lobby"""
    player_id: int
    username: str
    rating: int
    status: str  # idle, searching, in_game
    preferences: Optional[Dict] = None
    connected_since: Optional[datetime] = None


class LobbyStatsResponse(BaseModel):
    """Current lobby statistics"""
    total_players: int
    searching_players: int
    avg_wait_time: float
    queue_breakdown: Dict[str, int]
    recent_matches: int


# WebSocket message schemas
class WebSocketMessage(BaseModel):
    """Base WebSocket message"""
    type: str
    data: Optional[Dict] = None


class LobbyUpdate(WebSocketMessage):
    """Lobby state update message"""
    type: str = "lobby_update"
    data: Dict[str, Any]


class MatchFound(WebSocketMessage):
    """Match found notification"""
    type: str = "match_found"
    data: Dict[str, Any]  # Contains game_id, opponent info, etc.


class QueueUpdate(WebSocketMessage):
    """Queue status update"""
    type: str = "queue_update"
    data: Dict[str, Any]  # Contains wait_time, position, etc.