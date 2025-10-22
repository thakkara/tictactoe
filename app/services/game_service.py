import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.exceptions import (
    GameNotFound, GameFull, PlayerNotFound
)
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.move import Move
from app.models.player import Player
from app.services.validators import GameValidator

logger = logging.getLogger(__name__)


class GameService:
    def __init__(self):
        self.validator = GameValidator()

    def create_game(self, db: Session, creator_id: int, grid_size: int = 3) -> Game:
        # Validate grid size
        if not (3 <= grid_size <= 10):
            raise ValueError(f"Grid size must be between 3 and 10, got {grid_size}")
            
        player = db.query(Player).filter(Player.id == creator_id).first()
        if not player:
            raise PlayerNotFound(f"Player with ID {creator_id} not found")

        game = Game(status="waiting", grid_size=grid_size)
        db.add(game)
        db.flush()

        # Initialize empty board based on grid size
        game.initialize_empty_board()

        game_player = GamePlayer(
            game_id=game.id,
            player_id=creator_id,
            player_order=1
        )
        db.add(game_player)
        db.commit()
        db.refresh(game)

        logger.info(f"Game {game.id} ({grid_size}x{grid_size}) created by player {creator_id}")
        return game

    def join_game(self, db: Session, game_id: int, player_id: int) -> Game:
        game = db.query(Game).filter(
            Game.id == game_id
        ).with_for_update().first()

        if not game:
            raise GameNotFound(f"Game {game_id} not found")

        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise PlayerNotFound(f"Player with ID {player_id} not found")

        if game.status != "waiting":
            raise GameFull(f"Game {game_id} is not accepting new players")

        existing = db.query(GamePlayer).filter(
            and_(
                GamePlayer.game_id == game_id,
                GamePlayer.player_id == player_id
            )
        ).first()
        if existing:
            raise GameFull(f"Player {player_id} is already in game {game_id}")

        player_count = db.query(GamePlayer).filter(
            GamePlayer.game_id == game_id
        ).count()
        if player_count >= 2:
            raise GameFull(f"Game {game_id} is full")

        game_player = GamePlayer(
            game_id=game_id,
            player_id=player_id,
            player_order=2
        )
        db.add(game_player)

        first_player = db.query(GamePlayer).filter(
            and_(
                GamePlayer.game_id == game_id,
                GamePlayer.player_order == 1
            )
        ).first()

        game.status = "active"
        game.current_turn = first_player.player_id
        game.started_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(game)

        logger.info(f"Player {player_id} joined game {game_id}")
        return game

    def make_move(self, db: Session, game_id: int, player_id: int,
                  row: int, col: int) -> dict:
        game = db.query(Game).filter(
            Game.id == game_id
        ).with_for_update().first()

        if not game:
            raise GameNotFound(f"Game {game_id} not found")

        self.validator.validate_move(db, game, player_id, row, col)

        board = game.get_board()
        board[row][col] = player_id
        game.set_board(board)

        move_number = db.query(func.count(Move.id)).filter(
            Move.game_id == game_id
        ).scalar() + 1

        move = Move(
            game_id=game_id,
            player_id=player_id,
            row=row,
            col=col,
            move_number=move_number
        )
        db.add(move)

        if self._check_win(board, player_id):
            game.status = "completed"
            game.winner_id = player_id
            game.ended_at = datetime.now(timezone.utc)
            logger.info(f"Player {player_id} won game {game_id}")
            
            # Update player efficiency stats in real-time
            self._update_winner_stats(db, game)
            
        elif self._is_board_full(board):
            game.status = "completed"
            game.ended_at = datetime.now(timezone.utc)
            logger.info(f"Game {game_id} ended in a draw")
        else:
            next_player = db.query(GamePlayer).filter(
                and_(
                    GamePlayer.game_id == game_id,
                    GamePlayer.player_id != player_id
                )
            ).first()
            game.current_turn = next_player.player_id

        db.commit()
        db.refresh(move)

        return {
            "id": move.id,
            "game_id": game_id,
            "player_id": player_id,
            "row": row,
            "col": col,
            "move_number": move_number,
            "game_status": game.status,
            "winner_id": game.winner_id,
            "is_draw": game.status == "completed" and game.winner_id is None
        }

    def get_game_state(self, db: Session, game_id: int) -> dict:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            raise GameNotFound(f"Game {game_id} not found")

        game_players = db.query(GamePlayer).filter(
            GamePlayer.game_id == game_id
        ).order_by(GamePlayer.player_order).all()
        players = [gp.player_id for gp in game_players]

        moves_count = db.query(func.count(Move.id)).filter(
            Move.game_id == game_id
        ).scalar()

        board = game.get_board()

        return {
            "id": game.id,
            "status": game.status,
            "players": players,
            "current_turn": game.current_turn,
            "winner_id": game.winner_id,
            "board": board,
            "moves_count": moves_count,
            "created_at": game.created_at,
            "started_at": game.started_at,
            "ended_at": game.ended_at
        }

    def _check_win(self, board: List[List[int]], player_id: int) -> bool:
        """Check if player has won with configurable grid size."""
        grid_size = len(board)
        
        # Check rows
        for row in board:
            if all(cell == player_id for cell in row):
                return True
                
        # Check columns
        for col in range(grid_size):
            if all(board[row][col] == player_id for row in range(grid_size)):
                return True
                
        # Check main diagonal (top-left to bottom-right)
        if all(board[i][i] == player_id for i in range(grid_size)):
            return True
            
        # Check anti-diagonal (top-right to bottom-left)
        if all(board[i][grid_size - 1 - i] == player_id for i in range(grid_size)):
            return True
            
        return False

    def _is_board_full(self, board: List[List[int]]) -> bool:
        for row in board:
            if None in row:
                return False
        return True
        
    def _update_winner_stats(self, db: Session, game: Game) -> None:
        """Update winner's efficiency stats in real-time and invalidate caches."""
        if not game.winner_id:
            return
            
        try:
            from app.services.player_stats_manager import PlayerStatsManager
            from app.services.leaderboard_cache import LeaderboardCacheManager
            
            # Update denormalized stats
            stats_manager = PlayerStatsManager(db)
            stats_manager.on_game_completed(game)
            
            # Invalidate leaderboard caches since stats changed
            cache_manager = LeaderboardCacheManager(db)
            cache_manager.invalidate_cache("wins")
            cache_manager.invalidate_cache("efficiency")
            
            logger.info(f"Updated stats and invalidated cache for game {game.id} winner {game.winner_id}")
            
        except Exception as e:
            # Don't fail the game completion if stats update fails
            logger.error(f"Failed to update winner stats for game {game.id}: {e}")
            # Stats will be corrected by background reconciliation jobs


game_service_obj = GameService()