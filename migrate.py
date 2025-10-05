"""
Database migration script to set up the initial schema.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://localhost/gridgame"
)

def run_migrations():
    """Run database migrations."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Create tables
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status VARCHAR NOT NULL DEFAULT 'waiting',
                current_turn INTEGER,
                winner_id INTEGER REFERENCES players(id),
                board TEXT DEFAULT '[[null,null,null],[null,null,null],[null,null,null]]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                ended_at TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS game_players (
                game_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                player_order INTEGER NOT NULL,
                PRIMARY KEY (game_id, player_id),
                FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
                FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
                player_id INTEGER REFERENCES players(id) ON DELETE CASCADE,
                row INTEGER NOT NULL CHECK (row BETWEEN 0 AND 2),
                col INTEGER NOT NULL CHECK (col BETWEEN 0 AND 2),
                move_number INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (game_id, row, col)
            )
        """))

        # Create indexes for performance (SQLite-compatible)
        for index_name, sql in [
            ("idx_moves_game_player", "CREATE INDEX idx_moves_game_player ON moves (game_id, player_id);"),
            ("idx_game_players_player", "CREATE INDEX idx_game_players_player ON game_players (player_id);"),
            ("idx_games_winner", "CREATE INDEX idx_games_winner ON games (winner_id) WHERE winner_id IS NOT NULL;")
        ]:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND name=:name"),
                {"name": index_name}
            )
            if not result.fetchone():
                conn.execute(text(sql))

        conn.commit()

    print("Database migrations completed successfully.")


if __name__ == "__main__":
    print("Starting database migration...")

    # Run migrations
    run_migrations()

    print("Migration complete!")
