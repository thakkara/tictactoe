import json
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(20), nullable=False, default="waiting")
    current_turn = Column(Integer, ForeignKey("players.id"))
    winner_id = Column(Integer, ForeignKey("players.id"))
    board = Column(String, default='[[null,null,null],[null,null,null],[null,null,null]]')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))

    moves = relationship("Move", back_populates="game")
    game_players = relationship("GamePlayer", back_populates="game")
    winner = relationship("Player", foreign_keys=[winner_id])

    @property
    def players(self):
        return [gp.player_id for gp in self.game_players]

    def get_board(self):
        return json.loads(self.board)

    def set_board(self, board_obj):
        self.board = json.dumps(board_obj)