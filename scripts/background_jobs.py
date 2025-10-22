#!/usr/bin/env python3
"""
Background jobs for maintaining TicTacToe system at scale.
Run as cron jobs or scheduled tasks for optimal performance.

Usage:
    python scripts/background_jobs.py reconcile-stats
    python scripts/background_jobs.py validate-integrity  
    python scripts/background_jobs.py cleanup-cache
    python scripts/background_jobs.py backfill-stats
"""

import sys
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import sessionmaker
from app.core.database import engine
from app.services.consistency_manager import ConsistencyManager
from app.services.player_stats_manager import PlayerStatsManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('background_jobs.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def reconcile_player_stats():
    """Nightly job: Reconcile all player efficiency statistics."""
    logger.info("=== STARTING PLAYER STATS RECONCILIATION ===")
    
    with SessionLocal() as db:
        consistency_manager = ConsistencyManager(db)
        
        try:
            stats = consistency_manager.reconcile_all_player_stats(batch_size=1000)
            
            logger.info(f"Reconciliation completed successfully:")
            logger.info(f"  Total players: {stats['total_players']}")
            logger.info(f"  Updated players: {stats['updated_players']}")
            logger.info(f"  Errors: {stats['errors']}")
            logger.info(f"  Duration: {stats['duration']}")
            logger.info(f"  Batches processed: {stats['batches_processed']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Fatal error in reconciliation: {e}")
            return False


def validate_data_integrity():
    """Weekly job: Comprehensive data integrity validation."""
    logger.info("=== STARTING DATA INTEGRITY VALIDATION ===")
    
    with SessionLocal() as db:
        consistency_manager = ConsistencyManager(db)
        
        try:
            results = consistency_manager.validate_data_integrity()
            
            logger.info(f"Integrity validation completed:")
            logger.info(f"  Total issues found: {results['total_issues']}")
            
            for issue_type, issues in results['issues'].items():
                if issues:
                    logger.warning(f"  {issue_type}: {len(issues)} issues")
                    for issue in issues[:5]:  # Log first 5 issues
                        logger.warning(f"    {issue}")
                    if len(issues) > 5:
                        logger.warning(f"    ... and {len(issues) - 5} more")
                else:
                    logger.info(f"  {issue_type}: No issues found")
                    
            return results['total_issues'] == 0
            
        except Exception as e:
            logger.error(f"Error in integrity validation: {e}")
            return False


def cleanup_cache():
    """Daily job: Clean up expired cache entries."""
    logger.info("=== STARTING CACHE CLEANUP ===")
    
    with SessionLocal() as db:
        consistency_manager = ConsistencyManager(db)
        
        try:
            deleted_count = consistency_manager.cleanup_expired_cache_entries(days_old=7)
            logger.info(f"Cache cleanup completed: {deleted_count} entries removed")
            return True
            
        except Exception as e:
            logger.error(f"Error in cache cleanup: {e}")
            return False


def backfill_player_stats():
    """One-time job: Backfill efficiency stats for existing players."""
    logger.info("=== STARTING PLAYER STATS BACKFILL ===")
    
    with SessionLocal() as db:
        stats_manager = PlayerStatsManager(db)
        
        try:
            updated_count = stats_manager.batch_update_all_players(batch_size=500)
            logger.info(f"Backfill completed: {updated_count} players updated")
            return True
            
        except Exception as e:
            logger.error(f"Error in backfill: {e}")
            return False


def show_system_stats():
    """Show current system statistics."""
    logger.info("=== SYSTEM STATISTICS ===")
    
    with SessionLocal() as db:
        from sqlalchemy import func, text
        from app.models.player import Player
        from app.models.game import Game
        from app.models.move import Move
        from app.models.leaderboard_cache import LeaderboardCache
        
        try:
            # Player stats
            total_players = db.query(func.count(Player.id)).scalar()
            players_with_wins = db.query(func.count(Player.id)).filter(
                Player.total_wins > 0
            ).scalar()
            
            # Game stats
            total_games = db.query(func.count(Game.id)).scalar()
            completed_games = db.query(func.count(Game.id)).filter(
                Game.status == "completed"
            ).scalar()
            
            # Move stats
            total_moves = db.query(func.count(Move.id)).scalar()
            
            # Cache stats
            cache_entries = db.query(func.count(LeaderboardCache.cache_key)).scalar()
            active_cache = db.query(func.count(LeaderboardCache.cache_key)).filter(
                LeaderboardCache.expires_at > func.now()
            ).scalar()
            
            # Database size (SQLite specific)
            try:
                db_size_result = db.execute(text("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")).scalar()
                db_size_mb = db_size_result / (1024 * 1024) if db_size_result else 0
            except:
                db_size_mb = "Unknown"
                
            logger.info(f"Players: {total_players} total, {players_with_wins} with wins")
            logger.info(f"Games: {total_games} total, {completed_games} completed")
            logger.info(f"Moves: {total_moves} total")
            logger.info(f"Cache: {active_cache}/{cache_entries} active entries")
            logger.info(f"Database size: {db_size_mb:.2f} MB" if isinstance(db_size_mb, float) else f"Database size: {db_size_mb}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            return False


def main():
    """Main CLI entry point."""
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
        
    command = sys.argv[1]
    success = False
    
    start_time = datetime.now()
    
    if command == "reconcile-stats":
        success = reconcile_player_stats()
    elif command == "validate-integrity":
        success = validate_data_integrity()
    elif command == "cleanup-cache":
        success = cleanup_cache()
    elif command == "backfill-stats":
        success = backfill_player_stats()
    elif command == "system-stats":
        success = show_system_stats()
    else:
        logger.error(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)
        
    duration = datetime.now() - start_time
    logger.info(f"Command '{command}' completed in {duration}")
    
    if success:
        logger.info("✅ Job completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Job failed")
        sys.exit(1)


if __name__ == "__main__":
    main()