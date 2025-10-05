import logging
from typing import List

from sqlalchemy import func, and_, desc
from sqlalchemy.orm import Session

from app.core.exceptions import PlayerNotFound
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.move import Move
from app.models.player import Player

logger = logging.getLogger(__name__)


class PlayerService:

    def create_player(self, db: Session, username: str) -> Player:
        """Create a new player."""
        # Check if username already exists
        existing = db.query(Player).filter(Player.username == username).first()
        if existing:
            return existing  # Return existing player instead of error

        player = Player(username=username)
        db.add(player)
        db.commit()
        db.refresh(player)

        logger.info(f"Created player {player.id} with username '{username}'")
        return player

    def get_player_stats(self, db: Session, player_id: int) -> dict:
        """Get comprehensive statistics for a player."""
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise PlayerNotFound(f"Player {player_id} not found")

        # Get game counts
        total_games = db.query(func.count(GamePlayer.game_id)).filter(
            GamePlayer.player_id == player_id
        ).join(Game).filter(
            Game.status == "completed"
        ).scalar() or 0

        wins = db.query(func.count(Game.id)).filter(
            Game.winner_id == player_id
        ).scalar() or 0

        # Games that ended without this player winning
        losses = db.query(func.count(GamePlayer.game_id)).filter(
            GamePlayer.player_id == player_id
        ).join(Game).filter(
            and_(
                Game.status == "completed",
                Game.winner_id != player_id,
                Game.winner_id.isnot(None)
            )
        ).scalar() or 0

        draws = total_games - wins - losses

        # Calculate win rate
        win_rate = (wins / total_games * 100) if total_games > 0 else 0.0

        # Get total moves
        total_moves = db.query(func.count(Move.id)).filter(
            Move.player_id == player_id
        ).scalar() or 0

        # Calculate efficiency (average moves per win)
        if wins > 0:
            moves_in_wins = db.query(func.sum(
                func.count(Move.id)
            )).filter(
                Move.player_id == player_id
            ).join(Game).filter(
                Game.winner_id == player_id
            ).group_by(Game.id).all()

            total_winning_moves = sum(count[0] for count in moves_in_wins) if moves_in_wins else 0
            efficiency = total_winning_moves / wins if wins > 0 else None
        else:
            efficiency = None

        return {
            "player_id": player_id,
            "username": player.username,
            "total_games": total_games,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_rate": round(win_rate, 2),
            "total_moves": total_moves,
            "efficiency": round(efficiency, 2) if efficiency else None
        }

    def get_leaderboard(self, db: Session, sort_by: str = "wins") -> List[dict]:
        """Get top 3 players by wins or efficiency."""
        if sort_by == "wins":
            # Subquery for wins
            wins_subq = db.query(
                Game.winner_id.label("player_id"),
                func.count(Game.id).label("wins")
            ).filter(
                Game.winner_id.isnot(None)
            ).group_by(Game.winner_id).subquery()

            # Subquery for total games
            games_subq = db.query(
                GamePlayer.player_id,
                func.count(GamePlayer.game_id).label("total_games")
            ).join(Game).filter(
                Game.status == "completed"
            ).group_by(GamePlayer.player_id).subquery()

            # Main query
            query = db.query(
                Player.id,
                Player.username,
                func.coalesce(wins_subq.c.wins, 0).label("wins"),
                func.coalesce(games_subq.c.total_games, 0).label("total_games")
            ).outerjoin(
                wins_subq, Player.id == wins_subq.c.player_id
            ).outerjoin(
                games_subq, Player.id == games_subq.c.player_id
            ).filter(
                func.coalesce(wins_subq.c.wins, 0) > 0
            ).order_by(
                desc("wins")
            ).limit(3)

        else:  # sort by efficiency
            # Complex query to calculate efficiency
            # Get moves per winning game for each player
            efficiency_subq = db.query(
                Move.player_id,
                func.count(Move.id).label("move_count"),
                Game.id.label("game_id")
            ).join(Game).filter(
                Game.winner_id == Move.player_id
            ).group_by(Move.player_id, Game.id).subquery()

            # Average moves per win
            avg_moves = db.query(
                efficiency_subq.c.player_id,
                func.avg(efficiency_subq.c.move_count).label("efficiency"),
                func.count(efficiency_subq.c.game_id).label("wins")
            ).group_by(efficiency_subq.c.player_id).subquery()

            query = db.query(
                Player.id,
                Player.username,
                avg_moves.c.wins,
                avg_moves.c.efficiency
            ).join(
                avg_moves, Player.id == avg_moves.c.player_id
            ).order_by(
                avg_moves.c.efficiency
            ).limit(3)

        results = query.all()

        leaderboard = []
        for i, row in enumerate(results, 1):
            if sort_by == "wins":
                win_rate = (row.wins / row.total_games * 100) if row.total_games > 0 else 0
                entry = {
                    "rank": i,
                    "player_id": row.id,
                    "username": row.username,
                    "wins": row.wins,
                    "total_games": row.total_games,
                    "win_rate": round(win_rate, 2),
                    "efficiency": None
                }
            else:
                entry = {
                    "rank": i,
                    "player_id": row.id,
                    "username": row.username,
                    "wins": row.wins,
                    "total_games": row.wins,  # For efficiency, we only count wins
                    "win_rate": 100.0,  # All are wins
                    "efficiency": round(float(row.efficiency), 2)
                }
            leaderboard.append(entry)

        return leaderboard


player_service_obj = PlayerService()
