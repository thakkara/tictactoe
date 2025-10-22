"""
Matchmaking-related database models.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from enum import Enum

from app.core.database import Base


class MatchmakingStatus(str, Enum):
    SEARCHING = "searching"
    MATCHED = "matched"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class PlayerQueue(Base):
    """Players actively searching for matches"""
    __tablename__ = "player_queue"
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    preferences = Column(Text)  # JSON: {"grid_size": [3,4,5], "max_rating_diff": 200}
    skill_rating = Column(Integer, default=1200)  # ELO rating
    queue_type = Column(String, default="ranked")  # "ranked", "casual", "tournament"
    status = Column(String, default=MatchmakingStatus.SEARCHING)
    
    # Timing
    joined_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    search_expanded_at = Column(DateTime(timezone=True))  # When search criteria expanded
    matched_at = Column(DateTime(timezone=True))
    
    # Matchmaking parameters (expand over time)
    initial_rating_range = Column(Integer, default=100)  # ±100 points initially
    current_rating_range = Column(Integer, default=100)
    max_wait_time = Column(Integer, default=60)  # seconds
    
    # Relationships
    player = relationship("Player", back_populates="queue_entries")
    
    # Indexes for efficient matching
    __table_args__ = (
        Index('idx_queue_active_search', 'status', 'queue_type', 'skill_rating'),
        Index('idx_queue_timing', 'joined_at', 'status'),
    )


class MatchmakingHistory(Base):
    """Track all matchmaking attempts for analytics"""
    __tablename__ = "matchmaking_history"
    
    id = Column(Integer, primary_key=True)
    player1_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    player2_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"))
    
    # Match quality metrics
    rating_difference = Column(Integer)
    preference_match_score = Column(Float)  # 0.0-1.0 how well preferences matched
    wait_time_player1 = Column(Integer)  # seconds
    wait_time_player2 = Column(Integer)
    
    # Outcome tracking
    match_quality_rating = Column(Integer)  # Post-game rating 1-5
    game_completion_status = Column(String)  # "completed", "abandoned", "disconnected"
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Relationships
    player1 = relationship("Player", foreign_keys=[player1_id])
    player2 = relationship("Player", foreign_keys=[player2_id])
    game = relationship("Game")


class PlayerRating(Base):
    """Player skill ratings across different game modes"""
    __tablename__ = "player_ratings"
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    
    # Different rating pools
    overall_rating = Column(Integer, default=1200)
    grid_3x3_rating = Column(Integer, default=1200)
    grid_4x4_rating = Column(Integer, default=1200)
    grid_5x5_rating = Column(Integer, default=1200)
    
    # Rating metadata
    games_played = Column(Integer, default=0)
    rating_deviation = Column(Float, default=350.0)  # Confidence in rating
    last_game_at = Column(DateTime(timezone=True))
    peak_rating = Column(Integer, default=1200)
    peak_rating_at = Column(DateTime(timezone=True))
    
    # Streak tracking
    current_win_streak = Column(Integer, default=0)
    current_loss_streak = Column(Integer, default=0)
    best_win_streak = Column(Integer, default=0)
    
    player = relationship("Player", back_populates="rating")
    
    __table_args__ = (
        Index('idx_player_rating_overall', 'overall_rating', 'rating_deviation'),
        Index('idx_player_rating_grid', 'grid_3x3_rating', 'grid_4x4_rating', 'grid_5x5_rating'),
    )