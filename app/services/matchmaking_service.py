"""
Core matchmaking service for TicTacToe players.
"""
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, text

from app.models.matchmaking import PlayerQueue, MatchmakingHistory, PlayerRating, MatchmakingStatus
from app.models.player import Player
from app.models.game import Game
from app.services.game_service import game_service_obj
from app.services.skill_calculator import SkillCalculator

logger = logging.getLogger(__name__)


@dataclass
class MatchmakingPreferences:
    """Player preferences for matchmaking"""
    grid_sizes: List[int] = None  # [3, 4, 5] - acceptable grid sizes
    max_rating_difference: int = 200  # Maximum skill difference
    preferred_queue_type: str = "ranked"  # "ranked", "casual", "tournament"
    max_wait_time: int = 120  # Maximum wait time in seconds
    
    def to_json(self) -> str:
        return json.dumps({
            "grid_sizes": self.grid_sizes or [3],
            "max_rating_difference": self.max_rating_difference,
            "preferred_queue_type": self.preferred_queue_type,
            "max_wait_time": self.max_wait_time
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> 'MatchmakingPreferences':
        data = json.loads(json_str)
        return cls(
            grid_sizes=data.get("grid_sizes", [3]),
            max_rating_difference=data.get("max_rating_difference", 200),
            preferred_queue_type=data.get("preferred_queue_type", "ranked"),
            max_wait_time=data.get("max_wait_time", 120)
        )


@dataclass
class MatchResult:
    """Result of a matchmaking attempt"""
    success: bool
    player1_id: int
    player2_id: int
    game_id: Optional[int] = None
    match_quality_score: float = 0.0
    wait_time: float = 0.0
    error_message: Optional[str] = None


class MatchmakingService:
    """Core matchmaking logic and queue management"""
    
    def __init__(self):
        self.skill_calculator = SkillCalculator()
        self.active_searches: Dict[int, asyncio.Task] = {}  # player_id -> search task
        
    async def join_matchmaking(
        self, 
        db: Session, 
        player_id: int, 
        preferences: MatchmakingPreferences
    ) -> PlayerQueue:
        """Add player to matchmaking queue"""
        
        # Check if player is already in queue
        existing_queue = db.query(PlayerQueue).filter(
            PlayerQueue.player_id == player_id,
            PlayerQueue.status == MatchmakingStatus.SEARCHING
        ).first()
        
        if existing_queue:
            logger.info(f"Player {player_id} already in queue")
            return existing_queue
        
        # Get player's current rating
        rating = self._get_player_rating(db, player_id)
        
        # Create queue entry
        queue_entry = PlayerQueue(
            player_id=player_id,
            preferences=preferences.to_json(),
            skill_rating=rating.overall_rating,
            queue_type=preferences.preferred_queue_type,
            initial_rating_range=preferences.max_rating_difference,
            current_rating_range=preferences.max_rating_difference,
            max_wait_time=preferences.max_wait_time
        )
        
        db.add(queue_entry)
        db.commit()
        
        # Start async search for this player
        search_task = asyncio.create_task(
            self._continuous_matchmaking_search(db, queue_entry.id)
        )
        self.active_searches[player_id] = search_task
        
        logger.info(f"Player {player_id} joined matchmaking queue with rating {rating.overall_rating}")
        return queue_entry
    
    async def leave_matchmaking(self, db: Session, player_id: int) -> bool:
        """Remove player from matchmaking queue"""
        
        # Cancel active search
        if player_id in self.active_searches:
            self.active_searches[player_id].cancel()
            del self.active_searches[player_id]
        
        # Update queue status
        updated_rows = db.query(PlayerQueue).filter(
            PlayerQueue.player_id == player_id,
            PlayerQueue.status == MatchmakingStatus.SEARCHING
        ).update({
            "status": MatchmakingStatus.CANCELLED,
            "matched_at": datetime.utcnow()
        })
        
        db.commit()
        logger.info(f"Player {player_id} left matchmaking queue")
        return updated_rows > 0
    
    async def _continuous_matchmaking_search(self, db: Session, queue_entry_id: int):
        """Continuously search for matches for a player"""
        
        try:
            while True:
                queue_entry = db.query(PlayerQueue).filter(
                    PlayerQueue.id == queue_entry_id
                ).first()
                
                if not queue_entry or queue_entry.status != MatchmakingStatus.SEARCHING:
                    break
                
                # Try to find a match
                match_result = await self._find_match(db, queue_entry)
                
                if match_result.success:
                    logger.info(f"Match found for player {queue_entry.player_id}")
                    break
                
                # Expand search criteria if been waiting too long
                await self._maybe_expand_search_criteria(db, queue_entry)
                
                # Check for timeout
                wait_time = (datetime.utcnow() - queue_entry.joined_at).total_seconds()
                if wait_time > queue_entry.max_wait_time:
                    await self._handle_matchmaking_timeout(db, queue_entry)
                    break
                
                # Wait before next search attempt
                await asyncio.sleep(2)  # Search every 2 seconds
                
        except asyncio.CancelledError:
            logger.info(f"Matchmaking search cancelled for queue entry {queue_entry_id}")
        except Exception as e:
            logger.error(f"Error in matchmaking search for {queue_entry_id}: {e}")
    
    async def _find_match(self, db: Session, queue_entry: PlayerQueue) -> MatchResult:
        """Find a match for the given player"""
        
        preferences = MatchmakingPreferences.from_json(queue_entry.preferences)
        
        # Find potential opponents
        potential_opponents = db.query(PlayerQueue).filter(
            and_(
                PlayerQueue.id != queue_entry.id,
                PlayerQueue.status == MatchmakingStatus.SEARCHING,
                PlayerQueue.queue_type == queue_entry.queue_type,
                PlayerQueue.skill_rating.between(
                    queue_entry.skill_rating - queue_entry.current_rating_range,
                    queue_entry.skill_rating + queue_entry.current_rating_range
                )
            )
        ).order_by(
            func.abs(PlayerQueue.skill_rating - queue_entry.skill_rating)
        ).limit(10).all()
        
        if not potential_opponents:
            return MatchResult(
                success=False,
                player1_id=queue_entry.player_id,
                player2_id=0,
                error_message="No suitable opponents found"
            )
        
        # Find best match based on preferences
        best_opponent = self._select_best_opponent(
            queue_entry, potential_opponents, preferences
        )
        
        if not best_opponent:
            return MatchResult(
                success=False,
                player1_id=queue_entry.player_id,
                player2_id=0,
                error_message="No compatible opponent preferences"
            )
        
        # Create the match
        return await self._create_match(db, queue_entry, best_opponent, preferences)
    
    def _select_best_opponent(
        self, 
        player_queue: PlayerQueue, 
        potential_opponents: List[PlayerQueue],
        preferences: MatchmakingPreferences
    ) -> Optional[PlayerQueue]:
        """Select the best opponent based on preferences and compatibility"""
        
        scored_opponents = []
        
        for opponent in potential_opponents:
            opponent_prefs = MatchmakingPreferences.from_json(opponent.preferences)
            
            # Calculate compatibility score
            score = self._calculate_match_compatibility(
                preferences, opponent_prefs, 
                player_queue.skill_rating, opponent.skill_rating
            )
            
            if score > 0.3:  # Minimum compatibility threshold
                scored_opponents.append((opponent, score))
        
        if not scored_opponents:
            return None
        
        # Return opponent with highest compatibility score
        scored_opponents.sort(key=lambda x: x[1], reverse=True)
        return scored_opponents[0][0]
    
    def _calculate_match_compatibility(
        self,
        prefs1: MatchmakingPreferences,
        prefs2: MatchmakingPreferences,
        rating1: int,
        rating2: int
    ) -> float:
        """Calculate how compatible two players are for a match (0.0-1.0)"""
        
        score = 0.0
        
        # Grid size compatibility (40% weight)
        common_grid_sizes = set(prefs1.grid_sizes) & set(prefs2.grid_sizes)
        if common_grid_sizes:
            score += 0.4
        
        # Rating compatibility (35% weight)
        rating_diff = abs(rating1 - rating2)
        max_acceptable_diff = min(prefs1.max_rating_difference, prefs2.max_rating_difference)
        if rating_diff <= max_acceptable_diff:
            # Closer ratings get higher score
            rating_score = 1.0 - (rating_diff / max_acceptable_diff)
            score += 0.35 * rating_score
        
        # Queue type compatibility (15% weight)
        if prefs1.preferred_queue_type == prefs2.preferred_queue_type:
            score += 0.15
        
        # Wait time compatibility (10% weight) - prefer players with similar wait tolerance
        wait_time_diff = abs(prefs1.max_wait_time - prefs2.max_wait_time)
        if wait_time_diff <= 60:  # Within 1 minute
            score += 0.1
        
        return score
    
    async def _create_match(
        self, 
        db: Session, 
        player1_queue: PlayerQueue, 
        player2_queue: PlayerQueue,
        preferences: MatchmakingPreferences
    ) -> MatchResult:
        """Create a game between two matched players"""
        
        try:
            # Choose grid size (prefer smaller for faster games)
            player1_prefs = MatchmakingPreferences.from_json(player1_queue.preferences)
            player2_prefs = MatchmakingPreferences.from_json(player2_queue.preferences)
            
            common_grid_sizes = set(player1_prefs.grid_sizes) & set(player2_prefs.grid_sizes)
            grid_size = min(common_grid_sizes) if common_grid_sizes else 3
            
            # Create game
            game = game_service_obj.create_game(db, player1_queue.player_id, grid_size)
            
            # Player 2 joins automatically
            game = game_service_obj.join_game(db, game.id, player2_queue.player_id)
            
            # Update queue entries
            for queue_entry in [player1_queue, player2_queue]:
                queue_entry.status = MatchmakingStatus.MATCHED
                queue_entry.matched_at = datetime.utcnow()
            
            # Record matchmaking history
            wait_time_1 = (datetime.utcnow() - player1_queue.joined_at).total_seconds()
            wait_time_2 = (datetime.utcnow() - player2_queue.joined_at).total_seconds()
            
            history = MatchmakingHistory(
                player1_id=player1_queue.player_id,
                player2_id=player2_queue.player_id,
                game_id=game.id,
                rating_difference=abs(player1_queue.skill_rating - player2_queue.skill_rating),
                wait_time_player1=int(wait_time_1),
                wait_time_player2=int(wait_time_2),
                preference_match_score=self._calculate_match_compatibility(
                    player1_prefs, player2_prefs,
                    player1_queue.skill_rating, player2_queue.skill_rating
                )
            )
            
            db.add(history)
            db.commit()
            
            # Remove from active searches
            for player_id in [player1_queue.player_id, player2_queue.player_id]:
                if player_id in self.active_searches:
                    self.active_searches[player_id].cancel()
                    del self.active_searches[player_id]
            
            logger.info(
                f"Match created: Game {game.id} between players "
                f"{player1_queue.player_id} and {player2_queue.player_id}"
            )
            
            return MatchResult(
                success=True,
                player1_id=player1_queue.player_id,
                player2_id=player2_queue.player_id,
                game_id=game.id,
                match_quality_score=history.preference_match_score,
                wait_time=max(wait_time_1, wait_time_2)
            )
            
        except Exception as e:
            logger.error(f"Failed to create match: {e}")
            return MatchResult(
                success=False,
                player1_id=player1_queue.player_id,
                player2_id=player2_queue.player_id,
                error_message=str(e)
            )
    
    async def _maybe_expand_search_criteria(self, db: Session, queue_entry: PlayerQueue):
        """Expand search criteria for players who have been waiting too long"""
        
        wait_time = (datetime.utcnow() - queue_entry.joined_at).total_seconds()
        
        # Expand every 30 seconds, up to 3x initial range
        if wait_time >= 30 and queue_entry.current_rating_range < queue_entry.initial_rating_range * 3:
            if not queue_entry.search_expanded_at or \
               (datetime.utcnow() - queue_entry.search_expanded_at).total_seconds() >= 30:
                
                queue_entry.current_rating_range = min(
                    queue_entry.current_rating_range + 50,
                    queue_entry.initial_rating_range * 3
                )
                queue_entry.search_expanded_at = datetime.utcnow()
                db.commit()
                
                logger.info(
                    f"Expanded search range for player {queue_entry.player_id} "
                    f"to ±{queue_entry.current_rating_range} rating points"
                )
    
    async def _handle_matchmaking_timeout(self, db: Session, queue_entry: PlayerQueue):
        """Handle players who have waited too long"""
        
        queue_entry.status = MatchmakingStatus.TIMEOUT
        queue_entry.matched_at = datetime.utcnow()
        db.commit()
        
        # Remove from active searches
        if queue_entry.player_id in self.active_searches:
            del self.active_searches[queue_entry.player_id]
        
        logger.info(f"Matchmaking timeout for player {queue_entry.player_id}")
    
    def _get_player_rating(self, db: Session, player_id: int) -> PlayerRating:
        """Get or create player rating record"""
        
        rating = db.query(PlayerRating).filter(
            PlayerRating.player_id == player_id
        ).first()
        
        if not rating:
            rating = PlayerRating(player_id=player_id)
            db.add(rating)
            db.commit()
        
        return rating
    
    def get_queue_status(self, db: Session) -> Dict[str, Any]:
        """Get current matchmaking queue statistics"""
        
        queue_stats = db.query(
            PlayerQueue.queue_type,
            func.count(PlayerQueue.id).label('count'),
            func.avg(func.extract('epoch', datetime.utcnow() - PlayerQueue.joined_at)).label('avg_wait_time')
        ).filter(
            PlayerQueue.status == MatchmakingStatus.SEARCHING
        ).group_by(PlayerQueue.queue_type).all()
        
        return {
            "total_searching": sum(stat.count for stat in queue_stats),
            "queue_breakdown": {
                stat.queue_type: {
                    "count": stat.count,
                    "avg_wait_time": float(stat.avg_wait_time or 0)
                }
                for stat in queue_stats
            },
            "active_searches": len(self.active_searches)
        }


# Global service instance
matchmaking_service = MatchmakingService()