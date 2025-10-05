class GameException(Exception):
    """Base exception for game-related errors."""
    pass


class GameNotFound(GameException):
    """Raised when a game is not found."""
    pass


class GameFull(GameException):
    """Raised when trying to join a full game."""
    pass


class NotYourTurn(GameException):
    """Raised when a player tries to move out of turn."""
    pass


class CellOccupied(GameException):
    """Raised when trying to move to an occupied cell."""
    pass


class GameEnded(GameException):
    """Raised when trying to move in an ended game."""
    pass


class PlayerNotFound(GameException):
    """Raised when a player is not found."""
    pass