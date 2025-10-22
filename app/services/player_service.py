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
        """Get top 3 players by wins or efficiency using optimized caching."""
        from app.services.leaderboard_cache import LeaderboardCacheManager

        cache_manager = LeaderboardCacheManager(db)

        # Use cached leaderboard with fallback to optimized queries
        leaderboard_data = cache_manager.get_leaderboard(
            leaderboard_type=sort_by,
            limit=3,
            compute_func=lambda: self._compute_leaderboard_optimized(db, sort_by, 3)
        )

        # Add rank to results
        for i, entry in enumerate(leaderboard_data, 1):
            entry["rank"] = i

        return leaderboard_data

    def _compute_leaderboard_optimized(self, db: Session, sort_by: str, limit: int) -> List[dict]:
        """Compute leaderboard using denormalized data for maximum performance."""
        if sort_by == "wins":
            return self._get_wins_leaderboard_optimized(db, limit)
        elif sort_by == "efficiency":
            return self._get_efficiency_leaderboard_optimized(db, limit)
        else:
            raise ValueError(f"Unknown leaderboard type: {sort_by}")

    def _get_wins_leaderboard_optimized(self, db: Session, limit: int) -> List[dict]:
        """O(log n) wins leaderboard using denormalized total_wins column."""
        results = db.query(
            Player.id,
            Player.username,
            Player.total_wins
        ).filter(
            Player.total_wins > 0
        ).order_by(
            Player.total_wins.desc()
        ).limit(limit).all()

        leaderboard = []
        for player_id, username, total_wins in results:
            # Get total games for win rate calculation
            total_games = db.query(func.count(GamePlayer.game_id)).filter(
                GamePlayer.player_id == player_id
            ).scalar() or 0

            win_rate = (total_wins / total_games * 100) if total_games > 0 else 0

            leaderboard.append({
                "player_id": player_id,
                "username": username,
                "wins": total_wins,
                "total_games": total_games,
                "win_rate": round(win_rate, 2),
                "efficiency": None
            })

        return leaderboard

    def _get_efficiency_leaderboard_optimized(self, db: Session, limit: int) -> List[dict]:
        """O(log n) efficiency leaderboard using denormalized efficiency column."""
        results = db.query(
            Player.id,
            Player.username,
            Player.total_wins,
            Player.efficiency
        ).filter(
            Player.efficiency.isnot(None),
            Player.total_wins > 0
        ).order_by(
            Player.efficiency.asc()  # Lower efficiency is better
        ).limit(limit).all()

        leaderboard = []
        for player_id, username, total_wins, efficiency in results:
            leaderboard.append({
                "player_id": player_id,
                "username": username,
                "wins": total_wins,
                "total_games": total_wins,  # For efficiency, we only show wins
                "win_rate": 100.0,  # All counted games are wins
                "efficiency": round(efficiency, 2)
            })

        return leaderboard


player_service_obj = PlayerService()
