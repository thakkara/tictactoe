from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.exceptions import (
    NotYourTurn, CellOccupied, GameEnded, PlayerNotFound
)
from app.models.game import Game
from app.models.game_player import GamePlayer


class GameValidator:
    """Validates game moves and state transitions."""

    def validate_move(self, db: Session, game: Game, player_id: int,
                      row: int, col: int) -> None:
        """Validate a move is legal for any grid size."""
        # Check if game is active
        if game.status != "active":
            if game.status == "completed":
                raise GameEnded(f"Game {game.id} has already ended")
            else:
                raise GameEnded(f"Game {game.id} is not active")

        # Check if player is in the game
        player_in_game = db.query(GamePlayer).filter(
            and_(
                GamePlayer.game_id == game.id,
                GamePlayer.player_id == player_id
            )
        ).first()

        if not player_in_game:
            raise PlayerNotFound(f"Player {player_id} is not in game {game.id}")

        # Check if it's the player's turn
        if game.current_turn != player_id:
            raise NotYourTurn(f"It's not player {player_id}'s turn")

        # Validate position bounds for dynamic grid size
        if not game.is_valid_position(row, col):
            raise ValueError(f"Position ({row}, {col}) is invalid for {game.grid_size}x{game.grid_size} grid")

        # Check if cell is already occupied
        board = game.get_board()
        if board[row][col] is not None:
            raise CellOccupied(f"Cell ({row}, {col}) is already occupied")
