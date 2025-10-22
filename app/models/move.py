from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Move(Base):
    __tablename__ = "moves"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    row = Column(Integer, nullable=False)
    col = Column(Integer, nullable=False)
    move_number = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    game = relationship("Game", back_populates="moves")
    player = relationship("Player", back_populates="moves")

    # Constraints
    __table_args__ = (
        UniqueConstraint('game_id', 'row', 'col', name='unique_game_position'),
        # Note: row/col bounds are validated at application level based on game's grid_size
        CheckConstraint('row >= 0', name='valid_row_min'),
        CheckConstraint('col >= 0', name='valid_col_min'),
    )
