"""
ELO rating system for skill-based matchmaking.
"""
import math
import logging
from typing import Tuple, Optional
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from app.models.matchmaking import PlayerRating
from app.models.game import Game

logger = logging.getLogger(__name__)


class SkillCalculator:
    """ELO-based skill rating calculator for TicTacToe"""
    
    # Rating system constants
    DEFAULT_RATING = 1200
    DEFAULT_DEVIATION = 350.0  # High uncertainty for new players
    MIN_DEVIATION = 50.0       # Minimum uncertainty for experienced players
    MAX_RATING_CHANGE = 50     # Maximum points gained/lost per game
    
    # K-factor calculation (how much ratings change)
    K_FACTOR_NEW = 40          # New players (< 20 games)
    K_FACTOR_INTERMEDIATE = 20 # Intermediate players (20-100 games)
    K_FACTOR_VETERAN = 10      # Veteran players (100+ games)
    
    def calculate_rating_change(
        self, 
        winner_rating: int, 
        loser_rating: int,
        winner_games: int,
        loser_games: int,
        grid_size: int = 3
    ) -> Tuple[int, int]:
        """
        Calculate new ratings after a game.
        Returns (new_winner_rating, new_loser_rating)
        """
        
        # Expected scores based on current ratings
        winner_expected = self._expected_score(winner_rating, loser_rating)
        loser_expected = 1.0 - winner_expected
        
        # Actual scores (1 for win, 0 for loss)
        winner_actual = 1.0
        loser_actual = 0.0
        
        # K-factors based on experience
        winner_k = self._get_k_factor(winner_games)
        loser_k = self._get_k_factor(loser_games)
        
        # Grid size modifier (larger grids = more skill-based)
        grid_modifier = self._get_grid_size_modifier(grid_size)
        
        # Calculate rating changes
        winner_change = winner_k * grid_modifier * (winner_actual - winner_expected)
        loser_change = loser_k * grid_modifier * (loser_actual - loser_expected)
        
        # Apply maximum change limits
        winner_change = max(-self.MAX_RATING_CHANGE, min(self.MAX_RATING_CHANGE, winner_change))
        loser_change = max(-self.MAX_RATING_CHANGE, min(self.MAX_RATING_CHANGE, loser_change))
        
        new_winner_rating = int(winner_rating + winner_change)
        new_loser_rating = int(loser_rating + loser_change)
        
        # Ensure ratings don't go below 100
        new_winner_rating = max(100, new_winner_rating)
        new_loser_rating = max(100, new_loser_rating)
        
        logger.info(
            f"Rating change: Winner {winner_rating} -> {new_winner_rating} (+{winner_change:.1f}), "
            f"Loser {loser_rating} -> {new_loser_rating} ({loser_change:.1f})"
        )
        
        return new_winner_rating, new_loser_rating
    
    def _expected_score(self, rating_a: int, rating_b: int) -> float:
        """Calculate expected score for player A against player B"""
        return 1.0 / (1.0 + math.pow(10, (rating_b - rating_a) / 400.0))
    
    def _get_k_factor(self, games_played: int) -> int:
        """Get K-factor based on player experience"""
        if games_played < 20:
            return self.K_FACTOR_NEW
        elif games_played < 100:
            return self.K_FACTOR_INTERMEDIATE
        else:
            return self.K_FACTOR_VETERAN
    
    def _get_grid_size_modifier(self, grid_size: int) -> float:
        """Modify rating changes based on grid size complexity"""
        # Larger grids are more skill-based, smaller grids have more luck
        if grid_size == 3:
            return 0.8   # 3x3 has some luck factor
        elif grid_size == 4:
            return 1.0   # 4x4 is balanced
        elif grid_size >= 5:
            return 1.2   # 5x5+ is highly skill-based
        else:
            return 0.8
    
    def update_player_ratings_after_game(self, db: Session, game: Game) -> None:
        """Update both players' ratings after a completed game"""
        
        if game.status != "completed" or not game.winner_id:
            logger.warning(f"Game {game.id} is not completed or has no winner")
            return
        
        # Get player ratings
        winner_rating = self._get_or_create_rating(db, game.winner_id)
        loser_id = game.player2_id if game.winner_id == game.player1_id else game.player1_id
        loser_rating = self._get_or_create_rating(db, loser_id)
        
        # Calculate new ratings
        new_winner_rating, new_loser_rating = self.calculate_rating_change(
            winner_rating.overall_rating,
            loser_rating.overall_rating,
            winner_rating.games_played,
            loser_rating.games_played,
            game.grid_size
        )
        
        # Update winner
        self._update_rating_record(
            winner_rating, 
            new_winner_rating, 
            game.grid_size, 
            won=True
        )
        
        # Update loser  
        self._update_rating_record(
            loser_rating, 
            new_loser_rating, 
            game.grid_size, 
            won=False
        )
        
        db.commit()
        
        logger.info(
            f"Updated ratings for game {game.id}: "
            f"Winner {game.winner_id}: {new_winner_rating}, "
            f"Loser {loser_id}: {new_loser_rating}"
        )
    
    def _get_or_create_rating(self, db: Session, player_id: int) -> PlayerRating:
        """Get existing rating or create new one for player"""
        
        rating = db.query(PlayerRating).filter(
            PlayerRating.player_id == player_id
        ).first()
        
        if not rating:
            rating = PlayerRating(
                player_id=player_id,
                overall_rating=self.DEFAULT_RATING,
                grid_3x3_rating=self.DEFAULT_RATING,
                grid_4x4_rating=self.DEFAULT_RATING,
                grid_5x5_rating=self.DEFAULT_RATING,
                rating_deviation=self.DEFAULT_DEVIATION
            )
            db.add(rating)
            db.flush()  # Get ID without committing
        
        return rating
    
    def _update_rating_record(
        self, 
        rating: PlayerRating, 
        new_overall_rating: int, 
        grid_size: int, 
        won: bool
    ) -> None:
        """Update a player's rating record"""
        
        # Update overall rating
        old_rating = rating.overall_rating
        rating.overall_rating = new_overall_rating
        
        # Update grid-specific rating
        grid_rating_field = f"grid_{grid_size}x{grid_size}_rating"
        if hasattr(rating, grid_rating_field):
            old_grid_rating = getattr(rating, grid_rating_field)
            # Grid-specific ratings change similarly to overall
            rating_change = new_overall_rating - old_rating
            new_grid_rating = max(100, old_grid_rating + rating_change)
            setattr(rating, grid_rating_field, new_grid_rating)
        
        # Update games played
        rating.games_played += 1
        
        # Update rating deviation (confidence increases with more games)
        rating.rating_deviation = max(
            self.MIN_DEVIATION,
            rating.rating_deviation * 0.99  # Slowly decrease uncertainty
        )
        
        # Update peak rating
        if new_overall_rating > rating.peak_rating:
            rating.peak_rating = new_overall_rating
            rating.peak_rating_at = datetime.utcnow()
        
        # Update streaks
        if won:
            rating.current_win_streak += 1
            rating.current_loss_streak = 0
            rating.best_win_streak = max(rating.best_win_streak, rating.current_win_streak)
        else:
            rating.current_loss_streak += 1
            rating.current_win_streak = 0
        
        # Update last game timestamp
        rating.last_game_at = datetime.utcnow()
    
    def get_rating_for_grid_size(self, rating: PlayerRating, grid_size: int) -> int:
        """Get player's rating for specific grid size"""
        
        if grid_size == 3:
            return rating.grid_3x3_rating
        elif grid_size == 4:
            return rating.grid_4x4_rating
        elif grid_size == 5:
            return rating.grid_5x5_rating
        else:
            # For other grid sizes, use overall rating
            return rating.overall_rating
    
    def calculate_match_quality(
        self, 
        rating1: int, 
        rating2: int, 
        deviation1: float, 
        deviation2: float
    ) -> float:
        """
        Calculate expected match quality (0.0-1.0).
        Higher values indicate more balanced/competitive matches.
        """
        
        # Rating difference component
        rating_diff = abs(rating1 - rating2)
        rating_quality = max(0.0, 1.0 - (rating_diff / 400.0))  # 400 point diff = 0 quality
        
        # Uncertainty component (lower deviation = higher quality)
        avg_deviation = (deviation1 + deviation2) / 2
        deviation_quality = max(0.0, 1.0 - (avg_deviation / 350.0))
        
        # Combined quality (weighted average)
        overall_quality = (rating_quality * 0.7) + (deviation_quality * 0.3)
        
        return min(1.0, overall_quality)
    
    def predict_match_outcome(self, rating1: int, rating2: int) -> dict:
        """Predict match outcome probabilities"""
        
        player1_win_prob = self._expected_score(rating1, rating2)
        player2_win_prob = 1.0 - player1_win_prob
        
        # Estimate draw probability (higher for similar ratings)
        rating_diff = abs(rating1 - rating2)
        draw_prob = max(0.05, 0.3 * math.exp(-rating_diff / 200.0))
        
        # Normalize probabilities
        total = player1_win_prob + player2_win_prob + draw_prob
        
        return {
            "player1_win_probability": player1_win_prob / total,
            "player2_win_probability": player2_win_prob / total,
            "draw_probability": draw_prob / total,
            "confidence": min(1.0, rating_diff / 400.0)  # Higher diff = higher confidence
        }


# Global calculator instance
skill_calculator = SkillCalculator()