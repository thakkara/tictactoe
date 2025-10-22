"""
Configuration constants for the TicTacToe game engine.
"""

# Grid size limits
MIN_GRID_SIZE = 3
MAX_GRID_SIZE = 10
DEFAULT_GRID_SIZE = 3

# Game rules
def get_min_moves_to_win(grid_size: int) -> int:
    """Get minimum number of moves needed to win for a given grid size."""
    return grid_size

def get_max_moves_for_draw(grid_size: int) -> int:
    """Get maximum number of moves before a draw for a given grid size."""
    return grid_size * grid_size

def is_valid_grid_size(grid_size: int) -> bool:
    """Check if a grid size is valid."""
    return MIN_GRID_SIZE <= grid_size <= MAX_GRID_SIZE

def get_efficiency_normalization_factor(grid_size: int) -> float:
    """
    Get normalization factor for efficiency across different grid sizes.
    This allows fair comparison between players on different grid sizes.
    """
    # Efficiency is normalized by the minimum possible moves to win
    return float(grid_size) / DEFAULT_GRID_SIZE

def normalize_efficiency_for_leaderboard(efficiency: float, grid_size: int) -> float:
    """
    Normalize efficiency score for cross-grid-size leaderboard comparison.
    Lower normalized score = better efficiency.
    """
    return efficiency * get_efficiency_normalization_factor(grid_size)