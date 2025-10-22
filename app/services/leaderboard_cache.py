"""
Multi-tier caching system for scalable leaderboard performance.
"""
import json
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import List, Dict, Any, Optional, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.leaderboard_cache import LeaderboardCache
from app.models.player import Player

logger = logging.getLogger(__name__)


class LeaderboardCacheManager:
    """
    Multi-tier caching system:
    L1: In-memory LRU cache (fastest, limited size)
    L2: Database cache table (persistent, medium speed)
    L3: Direct query (slowest, always fresh)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self._memory_cache = {}
        self._cache_ttl = {}
        
    def get_leaderboard(
        self, 
        leaderboard_type: str, 
        limit: int = 3,
        compute_func: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard with multi-tier caching.
        
        Args:
            leaderboard_type: 'wins' or 'efficiency'
            limit: Number of top players to return
            compute_func: Function to compute fresh data if cache miss
        """
        cache_key = f"{leaderboard_type}_{limit}"
        
        # L1: Check in-memory cache first
        data = self._get_from_memory_cache(cache_key)
        if data is not None:
            logger.debug(f"L1 cache hit for {cache_key}")
            return data
            
        # L2: Check database cache
        data = self._get_from_database_cache(cache_key)
        if data is not None:
            logger.debug(f"L2 cache hit for {cache_key}")
            # Store in L1 for next time
            self._store_in_memory_cache(cache_key, data, ttl_minutes=2)
            return data
            
        # L3: Cache miss - compute fresh data
        logger.debug(f"Cache miss for {cache_key} - computing fresh data")
        
        if compute_func:
            fresh_data = compute_func()
        else:
            fresh_data = self._compute_default_leaderboard(leaderboard_type, limit)
            
        # Store in both cache levels
        self._store_in_database_cache(cache_key, fresh_data, ttl_minutes=10)
        self._store_in_memory_cache(cache_key, fresh_data, ttl_minutes=2)
        
        return fresh_data
        
    def _get_from_memory_cache(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """Get data from L1 in-memory cache."""
        if cache_key not in self._memory_cache:
            return None
            
        # Check if expired
        if (cache_key in self._cache_ttl and 
            self._cache_ttl[cache_key] < datetime.now()):
            del self._memory_cache[cache_key]
            del self._cache_ttl[cache_key]
            return None
            
        return self._memory_cache[cache_key]
        
    def _store_in_memory_cache(
        self, 
        cache_key: str, 
        data: List[Dict[str, Any]], 
        ttl_minutes: int = 2
    ) -> None:
        """Store data in L1 in-memory cache."""
        self._memory_cache[cache_key] = data
        self._cache_ttl[cache_key] = datetime.now() + timedelta(minutes=ttl_minutes)
        
        # Simple LRU: keep only last 20 entries
        if len(self._memory_cache) > 20:
            oldest_key = min(self._cache_ttl.keys(), key=self._cache_ttl.get)
            del self._memory_cache[oldest_key]
            del self._cache_ttl[oldest_key]
            
    def _get_from_database_cache(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """Get data from L2 database cache."""
        try:
            cached_entry = self.db.query(LeaderboardCache).filter(
                LeaderboardCache.cache_key == cache_key,
                LeaderboardCache.expires_at > func.now()
            ).first()
            
            if cached_entry:
                return json.loads(cached_entry.data)
                
        except Exception as e:
            logger.error(f"Error reading from database cache: {e}")
            
        return None
        
    def _store_in_database_cache(
        self, 
        cache_key: str, 
        data: List[Dict[str, Any]], 
        ttl_minutes: int = 10
    ) -> None:
        """Store data in L2 database cache."""
        try:
            expires_at = datetime.now() + timedelta(minutes=ttl_minutes)
            
            # Upsert cache entry
            existing = self.db.query(LeaderboardCache).filter(
                LeaderboardCache.cache_key == cache_key
            ).first()
            
            if existing:
                existing.data = json.dumps(data)
                existing.expires_at = expires_at
            else:
                cache_entry = LeaderboardCache(
                    cache_key=cache_key,
                    data=json.dumps(data),
                    expires_at=expires_at
                )
                self.db.add(cache_entry)
                
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error storing to database cache: {e}")
            self.db.rollback()
            
    def _compute_default_leaderboard(
        self, 
        leaderboard_type: str, 
        limit: int
    ) -> List[Dict[str, Any]]:
        """Compute fresh leaderboard data using optimized queries."""
        if leaderboard_type == "wins":
            return self._compute_wins_leaderboard(limit)
        elif leaderboard_type == "efficiency":
            return self._compute_efficiency_leaderboard(limit)
        else:
            raise ValueError(f"Unknown leaderboard type: {leaderboard_type}")
            
    def _compute_wins_leaderboard(self, limit: int) -> List[Dict[str, Any]]:
        """Optimized wins leaderboard using denormalized data."""
        results = self.db.query(
            Player.id,
            Player.username,
            Player.total_wins
        ).filter(
            Player.total_wins > 0
        ).order_by(
            Player.total_wins.desc()
        ).limit(limit).all()
        
        return [
            {
                "id": player_id,
                "username": username,
                "wins": total_wins,
                "total_games": self._get_total_games(player_id)
            }
            for player_id, username, total_wins in results
        ]
        
    def _compute_efficiency_leaderboard(self, limit: int) -> List[Dict[str, Any]]:
        """Optimized efficiency leaderboard using denormalized data."""
        results = self.db.query(
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
        
        return [
            {
                "id": player_id,
                "username": username,
                "wins": total_wins,
                "efficiency": round(efficiency, 2)
            }
            for player_id, username, total_wins, efficiency in results
        ]
        
    def _get_total_games(self, player_id: int) -> int:
        """Get total games played by a player."""
        from app.models.game_player import GamePlayer
        return self.db.query(func.count(GamePlayer.game_id)).filter(
            GamePlayer.player_id == player_id
        ).scalar() or 0
        
    def invalidate_cache(self, leaderboard_type: Optional[str] = None) -> None:
        """Invalidate cache entries."""
        if leaderboard_type:
            # Invalidate specific leaderboard type
            pattern = f"{leaderboard_type}_"
            keys_to_remove = [k for k in self._memory_cache.keys() if k.startswith(pattern)]
            
            for key in keys_to_remove:
                self._memory_cache.pop(key, None)
                self._cache_ttl.pop(key, None)
                
            # Invalidate database cache
            try:
                self.db.query(LeaderboardCache).filter(
                    LeaderboardCache.cache_key.like(f"{leaderboard_type}_%")
                ).delete(synchronize_session=False)
                self.db.commit()
            except Exception as e:
                logger.error(f"Error invalidating database cache: {e}")
                self.db.rollback()
        else:
            # Invalidate all caches
            self._memory_cache.clear()
            self._cache_ttl.clear()
            
            try:
                self.db.query(LeaderboardCache).delete()
                self.db.commit()
            except Exception as e:
                logger.error(f"Error clearing database cache: {e}")
                self.db.rollback()
                
        logger.info(f"Cache invalidated for type: {leaderboard_type or 'all'}")
        
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        return {
            "memory_cache_size": len(self._memory_cache),
            "memory_cache_keys": list(self._memory_cache.keys()),
            "database_cache_size": self.db.query(func.count(LeaderboardCache.cache_key)).scalar(),
            "active_db_entries": self.db.query(func.count(LeaderboardCache.cache_key)).filter(
                LeaderboardCache.expires_at > func.now()
            ).scalar()
        }