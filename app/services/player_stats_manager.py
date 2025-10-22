"""
Real-time player statistics management for scalable leaderboard system.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text, func
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.move import Move
from app.models.player import Player

logger = logging.getLogger(__name__)


class PlayerStatsManager:
    """Manages real-time updates to denormalized player statistics."""
    
    def __init__(self, db: Session):
        self.db = db
        
    def \
            on_game_completed(self, game: Game) -> None:
        """Called when a game ends - updates winner's stats immediately."""
        if not game.winner_id:
            logger.info(f"Game {game.id} ended in draw - no efficiency update needed")
            return
            
        # Get move count for the winner in this game
        winner_moves = self.db.query(func.count(Move.id)).filter(
            Move.game_id == game.id,
            Move.player_id == game.winner_id
        ).scalar()
        
        if winner_moves == 0:
            logger.warning(f"No moves found for winner {game.winner_id} in game {game.id}")
            return
            
        # Update denormalized stats atomically
        self.update_player_efficiency(game.winner_id, winner_moves)
        
        logger.info(f"Updated efficiency for player {game.winner_id}: +{winner_moves} moves")
        
    def update_player_efficiency(self, player_id: int, moves_in_win: int) -> None:
        """Atomic update of player efficiency stats using SQL."""
        try:
            # Use raw SQL for atomic updates to avoid race conditions
            result = self.db.execute(text("""
                UPDATE players 
                SET 
                    total_wins = total_wins + 1,
                    total_win_moves = total_win_moves + :moves,
                    efficiency = (total_win_moves + :moves)::float / (total_wins + 1),
                    last_efficiency_update = :update_time
                WHERE id = :player_id
                RETURNING total_wins, efficiency
            """), {
                "player_id": player_id,
                "moves": moves_in_win,
                "update_time": datetime.utcnow()
            })
            
            updated_row = result.fetchone()
            if updated_row:
                total_wins, new_efficiency = updated_row
                logger.info(
                    f"Player {player_id} stats updated: "
                    f"wins={total_wins}, efficiency={new_efficiency:.2f}"
                )
            else:
                logger.warning(f"No player found with id {player_id}")
                
        except Exception as e:
            logger.error(f"Failed to update player {player_id} efficiency: {e}")
            self.db.rollback()
            raise
            
    def recalculate_player_efficiency(self, player_id: int) -> Optional[float]:
        """Recalculate efficiency from scratch for consistency checks."""
        try:
            # Get all wins and moves for this player
            wins_data = self.db.query(
                func.count(func.distinct(Game.id)).label('total_wins'),
                func.sum(func.count(Move.id)).label('total_moves')
            ).select_from(Game).join(Move).filter(
                Game.winner_id == player_id,
                Move.player_id == player_id,
                Move.game_id == Game.id
            ).group_by(Game.id).all()
            
            if not wins_data:
                # Player has no wins
                self.db.query(Player).filter(Player.id == player_id).update({
                    'total_wins': 0,
                    'total_win_moves': 0,
                    'efficiency': None,
                    'last_efficiency_update': datetime.utcnow()
                })
                return None
                
            # Calculate stats
            total_wins = len(wins_data)
            total_moves = sum(row[1] for row in wins_data if row[1])
            efficiency = total_moves / total_wins if total_wins > 0 else None
            
            # Update player record
            self.db.query(Player).filter(Player.id == player_id).update({
                'total_wins': total_wins,
                'total_win_moves': total_moves,
                'efficiency': efficiency,
                'last_efficiency_update': datetime.utcnow()
            })
            
            logger.info(
                f"Recalculated player {player_id}: "
                f"wins={total_wins}, moves={total_moves}, efficiency={efficiency}"
            )
            
            return efficiency
            
        except Exception as e:
            logger.error(f"Failed to recalculate player {player_id} efficiency: {e}")
            raise
            
    def batch_update_all_players(self, batch_size: int = 1000) -> int:
        """Recalculate efficiency for all players in batches."""
        updated_count = 0
        offset = 0
        
        while True:
            # Get batch of player IDs
            player_ids = self.db.query(Player.id).offset(offset).limit(batch_size).all()
            
            if not player_ids:
                break
                
            for player_id, in player_ids:
                try:
                    self.recalculate_player_efficiency(player_id)
                    updated_count += 1
                except Exception as e:
                    logger.error(f"Failed to update player {player_id}: {e}")
                    
            self.db.commit()
            offset += batch_size
            
            logger.info(f"Updated batch: {len(player_ids)} players (total: {updated_count})")
            
        logger.info(f"Batch update completed: {updated_count} players updated")
        return updated_count