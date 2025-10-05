# TicTacToe Game

A distributed backend API for managing concurrent tictactoe. Built with FastAPI and designed for scalability, featuring turn-based gameplay, real-time win detection, and comprehensive player statistics.

## Quick Start

```bash
# 1. Clone the repository
git clone <repository-url>
cd tictactoe

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup environment
echo "DATABASE_URL=sqlite:///./gridgame.db" > .env
echo "SECRET_KEY=your-secret-key" >> .env

# 4. Create database
python migrate.py

# 5. Run the server
uvicorn main:app --reload
```

**That's it!** The API is running at http://localhost:8000

-  **API Documentation**: http://localhost:8000/docs

## Features

### Core Game Mechanics
- **3×3 Grid Gameplay**: Players mark cells with their unique ID
- **Turn-Based System**: Strict turn enforcement with validation
- **Win Detection**: Automatic detection of rows, columns, and diagonals
- **Draw Detection**: Game ends when board is full with no winner
- **Concurrent Games**: Multiple isolated game sessions
- **Leaderboards**: Top players by wins or efficiency


## API Overview

### Game Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/games` | Create new game |
| POST | `/api/v1/games/{id}/join` | Join existing game |
| POST | `/api/v1/games/{id}/move` | Make a move |
| GET | `/api/v1/games/{id}` | Get game state |

### Player Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/players` | Create player |
| GET | `/api/v1/players/{id}/stats` | Get player statistics |
| GET | `/api/v1/leaderboard` | Get top 3 players |

##  How to Play

### 1. Create Players
```bash
curl -X POST http://localhost:8000/api/v1/players \
  -H "Content-Type: application/json" \
  -d '{"username": "alice"}'
```

### 2. Create Game
```bash
curl -X POST http://localhost:8000/api/v1/games \
  -H "Content-Type: application/json" \
  -d '{"creator_id": 1}'
```

### 3. Join Game
```bash
curl -X POST http://localhost:8000/api/v1/games/1/join \
  -H "Content-Type: application/json" \
  -d '{"player_id": 2}'
```

### 4. Make Moves
```bash
curl -X POST http://localhost:8000/api/v1/games/1/move \
  -H "Content-Type: application/json" \
  -d '{"player_id": 1, "row": 0, "col": 0}'
```

##  Testing

### Run Tests
```bash
pytest tests/test_api.py
```

### Run Simulation
```bash
# Quick simulation
python simple_simulate.py

# Advanced simulation
uvicorn main:app --reload
python simulate.py
```

##  Installation Options

### SQLite
```bash
pip install -r requirements.txt
echo "DATABASE_URL=sqlite:///./gridgame.db" > .env
python migrate.py
```

## 📊 Game Rules

1. **Starting**: First player to create the game goes first
2. **Turns**: Players alternate placing their ID on empty cells
3. **Winning**: Complete a row, column, or diagonal with your ID
4. **Drawing**: All cells filled with no winner
5. **Invalid Moves**: 
   - Not your turn → `NOT_YOUR_TURN` error
   - Cell occupied → `CELL_OCCUPIED` error
   - Game ended → `GAME_ENDED` error

## 🏆 Leaderboard

### Efficiency Metric
- **Definition**: Average moves needed to win
- **Calculation**: Total moves in wins ÷ Number of wins
- **Example**: Won 3 games with 5, 4, 6 moves = 5.0 efficiency

### Ranking Modes
1. **By Wins**: Most total victories
2. **By Efficiency**: Fewest moves per win (min 1 win required)

### Get Leaderboard
```bash
# Top 3 by wins
curl http://localhost:8000/api/v1/leaderboard?sort_by=wins

# Top 3 by efficiency
curl http://localhost:8000/api/v1/leaderboard?sort_by=efficiency
```
