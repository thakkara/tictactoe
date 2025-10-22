from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Denormalized efficiency stats for performance
    total_wins = Column(Integer, default=0, nullable=False, index=True)
    total_win_moves = Column(Integer, default=0, nullable=False)
    efficiency = Column(Float, index=True)  # average moves per win
    last_efficiency_update = Column(DateTime(timezone=True))

    # Relationships
    moves = relationship("Move", back_populates="player")
    game_players = relationship("GamePlayer", back_populates="player")
    won_games = relationship("Game", foreign_keys="Game.winner_id")