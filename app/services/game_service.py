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

    def create_game(self, db: Session, creator_id: int) -> Game:
        player = db.query(Player).filter(Player.id == creator_id).first()
        if not player:
            raise PlayerNotFound(f"Player with ID {creator_id} not found")

        game = Game(status="waiting")
        db.add(game)
        db.flush()

        game_player = GamePlayer(
            game_id=game.id,
            player_id=creator_id,
            player_order=1
        )
        db.add(game_player)
        db.commit()
        db.refresh(game)

        logger.info(f"Game {game.id} created by player {creator_id}")
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

        board = game.get_board() if game.board else [[None] * 3 for _ in range(3)]
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

        board = game.get_board() if game.board else [[None] * 3 for _ in range(3)]

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
        for row in board:
            if all(cell == player_id for cell in row):
                return True
        for col in range(3):
            if all(board[row][col] == player_id for row in range(3)):
                return True
        if all(board[i][i] == player_id for i in range(3)):
            return True
        if all(board[i][2 - i] == player_id for i in range(3)):
            return True
        return False

    def _is_board_full(self, board: List[List[int]]) -> bool:
        for row in board:
            if None in row:
                return False
        return True


game_service_obj = GameService()