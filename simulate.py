"""
Simple simulation script.
"""

import requests
import random
import time
import sys


def main():
    BASE_URL = "http://localhost:8000/api/v1"
    NUM_PLAYERS = 5
    NUM_GAMES = 20

    print("=== Grid Game Simulation ===\n")

    # Create players
    print(f"\nCreating {NUM_PLAYERS} players...")
    players = []
    for i in range(NUM_PLAYERS):
        response = requests.post(
            f"{BASE_URL}/players",
            json={"username": f"player_{i}_{int(time.time())}"}
        )
        if response.status_code == 200:
            player_id = response.json()["id"]
            players.append(player_id)
            print(f"  Created player {i + 1} (ID: {player_id})")

    if len(players) < 2:
        print("X Need at least 2 players")
        sys.exit(1)

    # Play games
    print(f"\nPlaying {NUM_GAMES} games...")
    stats = {p: {"wins": 0, "losses": 0, "draws": 0} for p in players}

    for game_num in range(NUM_GAMES):
        print("In for loop")
        # Pick two random players
        p1, p2 = random.sample(players, 2)

        print(f"p1 :{p1} p2:{p2}")

        # Create game (random grid size for variety)
        grid_size = random.choice([3, 4, 5])  # Mix of different grid sizes
        response = requests.post(
            f"{BASE_URL}/games",
            json={"creator_id": p1, "grid_size": grid_size}
        )

        if response.status_code != 200:
            print(f"Failed to create game: {response.text}")
            continue
        
        game_data = response.json()
        game_id = game_data["id"]
        grid_size = game_data["grid_size"]

        print(f"create response : {game_id}")
        # Player 2 joins
        response = requests.post(
            f"{BASE_URL}/games/{game_id}/join",
            json={"player_id": p2}
        )
        print(f"join response : {response}")
        if response.status_code != 200:
            continue

        # Play the game
        current_player = p1
        other_player = p2
        board = [[None for _ in range(grid_size)] for _ in range(grid_size)]
        available_moves = [(r, c) for r in range(grid_size) for c in range(grid_size)]

        game_ended = False
        while available_moves and not game_ended:
            # Choose random move
            row, col = random.choice(available_moves)
            print(f"jmaking move  : {row} , {col}")

            # Make move
            response = requests.post(
                f"{BASE_URL}/games/{game_id}/move",
                json={"player_id": current_player, "row": row, "col": col}
            )

            print(f"making move  response: {response}")

            if response.status_code == 200:
                move_result = response.json()
                print(f"making move  response: {response.json()}")
                board[row][col] = current_player
                available_moves.remove((row, col))
                
                # Check if game ended
                if move_result["game_status"] == "completed":
                    print(f"game ended ")
                    winner_id = move_result.get("winner_id")
                    is_draw = move_result.get("is_draw")

                    if winner_id:
                        stats[winner_id]["wins"] += 1
                        loser = p2 if winner_id == p1 else p1
                        stats[loser]["losses"] += 1
                        print(f"  Game {game_num + 1} ({grid_size}x{grid_size}): Player {winner_id} won")
                    elif is_draw:
                        stats[p1]["draws"] += 1
                        stats[p2]["draws"] += 1
                        print(f"  Game {game_num + 1} ({grid_size}x{grid_size}): Draw")

                    game_ended = True
                else:
                    # Switch turns
                    current_player, other_player = other_player, current_player
            else:
                print(f"Move failed: {response.text}")
                # Remove the invalid move and continue
                available_moves.remove((row, col))
                continue

    # Display results
    print("\n=== Results ===\n")

    # Sort by wins
    sorted_players = sorted(stats.items(), key=lambda x: x[1]["wins"], reverse=True)

    print("Player Statistics:")
    for i, (player_id, player_stats) in enumerate(sorted_players[:3], 1):
        total = player_stats["wins"] + player_stats["losses"] + player_stats["draws"]
        win_rate = (player_stats["wins"] / total * 100) if total > 0 else 0
        print(f"  {i}. Player {player_id}:")
        print(f"     Wins: {player_stats['wins']}")
        print(f"     Losses: {player_stats['losses']}")
        print(f"     Draws: {player_stats['draws']}")
        print(f"     Win Rate: {win_rate:.1f}%")

    # Get API leaderboard
    print("\nAPI Leaderboard (Top 3):")
    response = requests.get(f"{BASE_URL}/leaderboard?sort_by=wins")
    if response.status_code == 200:
        leaderboard = response.json()
        for entry in leaderboard[:3]:
            print(f"  {entry['rank']}. {entry['username']}: {entry['wins']} wins")

    print("\n Simulation complete!")


if __name__ == "__main__":
    main()
