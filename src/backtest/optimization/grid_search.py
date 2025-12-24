"""
Parameter grid generation for walk-forward optimization.
"""

from typing import Iterator


def generate_parameter_grid(
    breakout_range: tuple[float, float, float],  # (start, end, step)
    stop_range: tuple[float, float, float],  # (start, end, step)
) -> list[dict[str, float]]:
    """
    Generate all parameter combinations for grid search.

    Args:
        breakout_range: Tuple of (start, end, step) for breakout_multiplier
        stop_range: Tuple of (start, end, step) for stop_multiplier

    Returns:
        List of parameter dictionaries, each with 'breakout_multiplier' and 'stop_multiplier'

    Example:
        >>> grid = generate_parameter_grid((0.24, 0.60, 0.02), (0.16, 0.50, 0.02))
        >>> len(grid)
        342
        >>> grid[0]
        {'breakout_multiplier': 0.24, 'stop_multiplier': 0.16}
    """
    breakout_start, breakout_end, breakout_step = breakout_range
    stop_start, stop_end, stop_step = stop_range

    grid = []
    breakout_val = breakout_start
    while breakout_val <= breakout_end + 1e-9:  # Add small epsilon for float comparison
        stop_val = stop_start
        while stop_val <= stop_end + 1e-9:
            grid.append({
                "breakout_multiplier": round(breakout_val, 2),
                "stop_multiplier": round(stop_val, 2),
            })
            stop_val += stop_step
        breakout_val += breakout_step

    return grid


def iterate_parameter_grid(
    breakout_range: tuple[float, float, float],
    stop_range: tuple[float, float, float],
) -> Iterator[dict[str, float]]:
    """
    Iterator version of generate_parameter_grid for memory efficiency.

    Args:
        breakout_range: Tuple of (start, end, step) for breakout_multiplier
        stop_range: Tuple of (start, end, step) for stop_multiplier

    Yields:
        Parameter dictionaries with 'breakout_multiplier' and 'stop_multiplier'
    """
    breakout_start, breakout_end, breakout_step = breakout_range
    stop_start, stop_end, stop_step = stop_range

    breakout_val = breakout_start
    while breakout_val <= breakout_end + 1e-9:
        stop_val = stop_start
        while stop_val <= stop_end + 1e-9:
            yield {
                "breakout_multiplier": round(breakout_val, 2),
                "stop_multiplier": round(stop_val, 2),
            }
            stop_val += stop_step
        breakout_val += breakout_step

