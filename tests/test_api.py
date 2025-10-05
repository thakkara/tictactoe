import pytest

from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.move import Move
from app.models.player import Player

@pytest.fixture(autouse=True)
def db_cleanup(db_session):  # use the correct session fixture name
    for model in [Move, Game, Player, GamePlayer]:
        db_session.query(model).delete()
    db_session.commit()

class TestGameAPI:

    def test_create_player(self, client):
        response = client.post("api/v1/players", json={"username": "testuser"})
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert "id" in data

    def test_create_game(self, client):
        player = client.post("api/v1/players", json={"username": "player1"}).json()
        response = client.post("api/v1/games", json={"creator_id": player["id"]})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "waiting"
        assert player["id"] in data["players"]

    def test_join_game(self, client):
        p1 = client.post("api/v1/players", json={"username": "player1"}).json()
        p2 = client.post("api/v1/players", json={"username": "player2"}).json()
        game = client.post("api/v1/games", json={"creator_id": p1["id"]}).json()
        response = client.post(f"api/v1/games/{game['id']}/join", json={"player_id": p2["id"]})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        assert len(data["players"]) == 2

    def test_make_move(self, client):
        p1 = client.post("api/v1/players", json={"username": "player1"}).json()
        p2 = client.post("api/v1/players", json={"username": "player2"}).json()
        game = client.post("api/v1/games", json={"creator_id": p1["id"]}).json()
        client.post(f"api/v1/games/{game['id']}/join", json={"player_id": p2["id"]})
        response = client.post(
            f"api/v1/games/{game['id']}/move",
            json={"player_id": p1["id"], "row": 0, "col": 0}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["row"] == 0
        assert data["col"] == 0
        assert data["move_number"] == 1

    def test_invalid_move_not_turn(self, client):
        p1 = client.post("api/v1/players", json={"username": "player1"}).json()
        p2 = client.post("api/v1/players", json={"username": "player2"}).json()
        game = client.post("api/v1/games", json={"creator_id": p1["id"]}).json()
        player2_id = p2["id"]
        client.post(f"api/v1/games/{game['id']}/join", json={"player_id": player2_id})
        response = client.post(
            f"api/v1/games/{game['id']}/move",
            json={"player_id": player2_id, "row": 0, "col": 0}
        )
        assert response.status_code == 400
        assert f"It's not player {player2_id}'s turn" in response.json()["detail"]

    def test_game_win_detection(self, client):
        p1 = client.post("api/v1/players", json={"username": "player1"}).json()
        p2 = client.post("api/v1/players", json={"username": "player2"}).json()
        game = client.post("api/v1/games", json={"creator_id": p1["id"]}).json()
        client.post(f"api/v1/games/{game['id']}/join", json={"player_id": p2["id"]})
        moves = [
            (p1["id"], 0, 0),
            (p2["id"], 1, 0),
            (p1["id"], 0, 1),
            (p2["id"], 1, 1),
            (p1["id"], 0, 2),
        ]
        for i, (player_id, row, col) in enumerate(moves):
            response = client.post(
                f"api/v1/games/{game['id']}/move",
                json={"player_id": player_id, "row": row, "col": col}
            )
            data = response.json()
            if i == len(moves) - 1:
                assert data["game_status"] == "completed"
                assert data["winner_id"] == p1["id"]
                assert data["is_draw"] is False

    def test_leaderboard(self, client):
        p1 = client.post("api/v1/players", json={"username": "player0"}).json()
        p2 = client.post("api/v1/players", json={"username": "player1"}).json()
        for _ in range(3):
            game = client.post("api/v1/games", json={"creator_id": p1["id"]}).json()
            client.post(f"api/v1/games/{game['id']}/join", json={"player_id": p2["id"]})
            moves = [
                (p1["id"], 0, 0),
                (p2["id"], 1, 0),
                (p1["id"], 0, 1),
                (p2["id"], 1, 1),
                (p1["id"], 0, 2),
            ]
            for player_id, row, col in moves:
                client.post(
                    f"api/v1/games/{game['id']}/move",
                    json={"player_id": player_id, "row": row, "col": col}
                )
        response = client.get("api/v1/leaderboard?sort_by=wins")
        assert response.status_code == 200
        data = response.json()
        assert data[0]["username"] == "player0"
        assert data[0]["wins"] >= 3


    def test_leaderboard_by_efficiency(self, client):
        p1 = client.post("api/v1/players", json={"username": "efficient1"}).json()
        p2 = client.post("api/v1/players", json={"username": "efficient2"}).json()
        # p1 wins 2 games quickly, p2 wins 1 game
        for _ in range(2):
            game = client.post("api/v1/games", json={"creator_id": p1["id"]}).json()
            client.post(f"api/v1/games/{game['id']}/join", json={"player_id": p2["id"]})
            moves = [
                (p1["id"], 0, 0),
                (p2["id"], 1, 0),
                (p1["id"], 0, 1),
                (p2["id"], 1, 1),
                (p1["id"], 0, 2),
            ]
            for player_id, row, col in moves:
                client.post(
                    f"api/v1/games/{game['id']}/move",
                    json={"player_id": player_id, "row": row, "col": col}
                )
        # p2 wins 1 game
        game = client.post("api/v1/games", json={"creator_id": p2["id"]}).json()
        client.post(f"api/v1/games/{game['id']}/join", json={"player_id": p1["id"]})
        moves = [
            (p2["id"], 0, 0),
            (p1["id"], 1, 0),
            (p2["id"], 0, 1),
            (p1["id"], 1, 1),
            (p2["id"], 0, 2),
        ]
        for player_id, row, col in moves:
            client.post(
                f"api/v1/games/{game['id']}/move",
                json={"player_id": player_id, "row": row, "col": col}
            )
        response = client.get("api/v1/leaderboard?sort_by=efficiency")
        assert response.status_code == 200
        data = response.json()
        assert data[0]["username"] in ["efficient1", "efficient2"]
        assert data[0]["efficiency"] is not None
        assert data[0]["wins"] >= 1