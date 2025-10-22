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
    grid_size = Column(Integer, nullable=False, default=3, index=True)  # 3x3, 4x4, 5x5, etc.
    board = Column(String, default=None)  # Dynamic board generation
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
        """Get the game board as a 2D list, creating empty board if needed."""
        if self.board:
            return json.loads(self.board)
        else:
            # Generate empty board based on grid_size
            return [[None for _ in range(self.grid_size)] for _ in range(self.grid_size)]

    def set_board(self, board_obj):
        """Set the game board from a 2D list."""
        self.board = json.dumps(board_obj)
        
    def initialize_empty_board(self):
        """Initialize an empty board based on grid_size."""
        empty_board = [[None for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        self.set_board(empty_board)
        return empty_board
        
    def is_valid_position(self, row: int, col: int) -> bool:
        """Check if a position is valid for this game's grid size."""
        return 0 <= row < self.grid_size and 0 <= col < self.grid_size
        
    def get_total_cells(self) -> int:
        """Get total number of cells in the grid."""
        return self.grid_size * self.grid_size