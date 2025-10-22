"""
Background consistency jobs for maintaining data integrity at scale.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.move import Move
from app.models.player import Player
from app.models.game_player import GamePlayer
from app.services.player_stats_manager import PlayerStatsManager

logger = logging.getLogger(__name__)


class ConsistencyManager:
    """Manages background jobs for data consistency and integrity."""
    
    def __init__(self, db: Session):
        self.db = db
        self.stats_manager = PlayerStatsManager(db)
        
    def reconcile_all_player_stats(self, batch_size: int = 1000) -> Dict[str, Any]:
        """
        Nightly job to reconcile all player statistics.
        Recalculates denormalized efficiency data from source tables.
        """
        logger.info("Starting full player stats reconciliation")
        
        stats = {
            "total_players": 0,
            "updated_players": 0,
            "errors": 0,
            "start_time": datetime.now(),
            "batches_processed": 0
        }
        
        try:
            # Get total player count for progress tracking
            total_players = self.db.query(func.count(Player.id)).scalar()
            stats["total_players"] = total_players
            
            logger.info(f"Reconciling {total_players} players in batches of {batch_size}")
            
            offset = 0
            while True:
                # Process players in batches to manage memory
                player_ids = self.db.query(Player.id).offset(offset).limit(batch_size).all()
                
                if not player_ids:
                    break
                    
                batch_updated = 0
                batch_errors = 0
                
                for player_id, in player_ids:
                    try:
                        old_efficiency = self._get_current_efficiency(player_id)
                        new_efficiency = self.stats_manager.recalculate_player_efficiency(player_id)
                        
                        if old_efficiency != new_efficiency:
                            batch_updated += 1
                            logger.debug(f"Updated player {player_id}: {old_efficiency} -> {new_efficiency}")
                            
                    except Exception as e:
                        batch_errors += 1
                        logger.error(f"Error reconciling player {player_id}: {e}")
                        
                # Commit batch
                try:
                    self.db.commit()
                    stats["updated_players"] += batch_updated
                    stats["errors"] += batch_errors
                    stats["batches_processed"] += 1
                    
                    logger.info(
                        f"Batch {stats['batches_processed']}: "
                        f"updated {batch_updated}, errors {batch_errors} "
                        f"(total: {stats['updated_players']}/{total_players})"
                    )
                    
                except Exception as e:
                    logger.error(f"Error committing batch: {e}")
                    self.db.rollback()
                    stats["errors"] += len(player_ids)
                    
                offset += batch_size
                
        except Exception as e:
            logger.error(f"Fatal error in reconciliation: {e}")
            stats["errors"] += 1
            
        finally:
            stats["end_time"] = datetime.now()
            stats["duration"] = stats["end_time"] - stats["start_time"]
            
        logger.info(
            f"Reconciliation completed: "
            f"{stats['updated_players']} updated, "
            f"{stats['errors']} errors, "
            f"duration: {stats['duration']}"
        )
        
        return stats
        
    def _get_current_efficiency(self, player_id: int) -> float:
        """Get current efficiency value for a player."""
        result = self.db.query(Player.efficiency).filter(Player.id == player_id).scalar()
        return result
        
    def validate_data_integrity(self) -> Dict[str, Any]:
        """Run comprehensive data integrity checks."""
        logger.info("Starting data integrity validation")
        
        issues = {
            "orphaned_moves": self._check_orphaned_moves(),
            "invalid_game_states": self._check_invalid_game_states(),
            "efficiency_mismatches": self._check_efficiency_mismatches(),
            "missing_game_players": self._check_missing_game_players()
        }
        
        total_issues = sum(len(issue_list) for issue_list in issues.values())
        
        logger.info(f"Data integrity check completed: {total_issues} total issues found")
        
        return {
            "timestamp": datetime.now(),
            "total_issues": total_issues,
            "issues": issues
        }
        
    def _check_orphaned_moves(self) -> list:
        """Find moves that reference non-existent games or players."""
        orphaned = self.db.query(
            Move.id, Move.game_id, Move.player_id
        ).outerjoin(Game, Move.game_id == Game.id).outerjoin(
            Player, Move.player_id == Player.id
        ).filter(
            (Game.id.is_(None)) | (Player.id.is_(None))
        ).all()
        
        issues = [
            {"move_id": move_id, "game_id": game_id, "player_id": player_id}
            for move_id, game_id, player_id in orphaned
        ]
        
        if issues:
            logger.warning(f"Found {len(issues)} orphaned moves")
            
        return issues
        
    def _check_invalid_game_states(self) -> list:
        """Find games with inconsistent state."""
        # Games marked as completed but no winner and not a draw
        invalid_games = self.db.query(Game.id, Game.status).filter(
            Game.status == "completed",
            Game.winner_id.is_(None)
        ).all()
        
        issues = []
        for game_id, status in invalid_games:
            # Check if game should have a winner (not a draw)
            move_count = self.db.query(func.count(Move.id)).filter(
                Move.game_id == game_id
            ).scalar()
            
            if move_count < 9:  # Not a full board (draw)
                issues.append({
                    "game_id": game_id,
                    "issue": "completed_game_no_winner",
                    "move_count": move_count
                })
                
        if issues:
            logger.warning(f"Found {len(issues)} games with invalid state")
            
        return issues
        
    def _check_efficiency_mismatches(self, sample_size: int = 100) -> list:
        """Check for mismatches between denormalized and calculated efficiency."""
        # Sample players with efficiency data
        players_with_efficiency = self.db.query(
            Player.id, Player.efficiency, Player.total_wins
        ).filter(
            Player.efficiency.isnot(None),
            Player.total_wins > 0
        ).limit(sample_size).all()
        
        mismatches = []
        
        for player_id, stored_efficiency, stored_wins in players_with_efficiency:
            # Calculate actual efficiency
            actual_stats = self._calculate_actual_efficiency(player_id)
            
            if actual_stats:
                actual_efficiency = actual_stats["efficiency"]
                actual_wins = actual_stats["wins"]
                
                # Check for significant differences (>0.1 or different win counts)
                if (abs(stored_efficiency - actual_efficiency) > 0.1 or 
                    stored_wins != actual_wins):
                    mismatches.append({
                        "player_id": player_id,
                        "stored_efficiency": stored_efficiency,
                        "actual_efficiency": actual_efficiency,
                        "stored_wins": stored_wins,
                        "actual_wins": actual_wins
                    })
                    
        if mismatches:
            logger.warning(f"Found {len(mismatches)} efficiency mismatches")
            
        return mismatches
        
    def _calculate_actual_efficiency(self, player_id: int) -> dict:
        """Calculate actual efficiency from moves and games tables."""
        # Get wins and total moves for this player
        wins_data = self.db.query(
            Game.id,
            func.count(Move.id).label("move_count")
        ).join(Move).filter(
            Game.winner_id == player_id,
            Move.player_id == player_id,
            Move.game_id == Game.id
        ).group_by(Game.id).all()
        
        if not wins_data:
            return None
            
        total_wins = len(wins_data)
        total_moves = sum(row.move_count for row in wins_data)
        efficiency = total_moves / total_wins if total_wins > 0 else None
        
        return {
            "wins": total_wins,
            "total_moves": total_moves,
            "efficiency": efficiency
        }
        
    def _check_missing_game_players(self) -> list:
        """Find games without proper game_player records."""
        # Games that have moves but missing game_player records
        games_with_moves = self.db.query(
            Move.game_id,
            func.count(func.distinct(Move.player_id)).label("unique_players")
        ).group_by(Move.game_id).subquery()
        
        games_with_players = self.db.query(
            GamePlayer.game_id,
            func.count(GamePlayer.player_id).label("registered_players")
        ).group_by(GamePlayer.game_id).subquery()
        
        # Find mismatches
        mismatches = self.db.query(
            games_with_moves.c.game_id,
            games_with_moves.c.unique_players,
            func.coalesce(games_with_players.c.registered_players, 0).label("registered")
        ).outerjoin(
            games_with_players,
            games_with_moves.c.game_id == games_with_players.c.game_id
        ).filter(
            games_with_moves.c.unique_players != func.coalesce(games_with_players.c.registered_players, 0)
        ).all()
        
        issues = [
            {
                "game_id": game_id,
                "players_with_moves": unique_players,
                "registered_players": registered
            }
            for game_id, unique_players, registered in mismatches
        ]
        
        if issues:
            logger.warning(f"Found {len(issues)} games with missing game_player records")
            
        return issues
        
    def cleanup_expired_cache_entries(self, days_old: int = 7) -> int:
        """Clean up old cache entries to prevent table bloat."""
        from app.models.leaderboard_cache import LeaderboardCache
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        deleted_count = self.db.query(LeaderboardCache).filter(
            LeaderboardCache.expires_at < cutoff_date
        ).delete()
        
        self.db.commit()
        
        logger.info(f"Cleaned up {deleted_count} expired cache entries")
        return deleted_count