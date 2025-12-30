"""
Stop-Loss Strategies for LightGBM Trading

Implements dynamic stop-loss strategies that use model predictions
and market volatility to manage risk.

Strategies:
- PredictionReversalStop: Exit when model prediction flips direction
- ATRTrailingStop: Volatility-adjusted trailing stop
- CompositeStop: Combine multiple strategies (exit if ANY triggers)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List
import numpy as np


@dataclass
class StopContext:
    """Context passed to stop strategies each bar."""

    position: int  # 1 (long), -1 (short), 0 (flat)
    entry_price: float
    current_price: float
    prediction: float  # LightGBM prediction (expected return)
    atr: float  # Current ATR value
    timestamp: int
    bars_in_trade: int = 0

    # Track best price for trailing stops
    best_price: float = field(default=0.0)

    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized P&L."""
        if self.position == 1:
            return self.current_price - self.entry_price
        elif self.position == -1:
            return self.entry_price - self.current_price
        return 0.0

    @property
    def unrealized_pnl_pct(self) -> float:
        """Calculate unrealized P&L as percentage."""
        if self.entry_price == 0:
            return 0.0
        return self.unrealized_pnl / self.entry_price * 100


class StopLossStrategy(ABC):
    """Base class for all stop-loss strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier for logging."""
        pass

    @abstractmethod
    def should_exit(self, ctx: StopContext) -> tuple[bool, Optional[str]]:
        """
        Check if position should be exited.

        Returns:
            (should_exit: bool, reason: str or None)
        """
        pass

    def on_entry(self, ctx: StopContext) -> None:
        """Called when a new position is opened."""
        pass

    def on_exit(self) -> None:
        """Called when position is closed."""
        pass

    def update(self, ctx: StopContext) -> None:
        """Called each bar to update internal state."""
        pass


class PredictionReversalStop(StopLossStrategy):
    """
    Exit when model prediction flips against current position.

    For long: exit if prediction < -threshold (model now bearish)
    For short: exit if prediction > threshold (model now bullish)

    This is the most responsive to model signals.
    """

    def __init__(self, threshold: float = 0.0, min_bars: int = 1):
        """
        Args:
            threshold: Minimum prediction magnitude to trigger exit.
                      0.0 = exit on any sign flip
                      0.0001 = require 0.01% predicted move against position
            min_bars: Minimum bars in trade before checking (avoid whipsaws)
        """
        self.threshold = threshold
        self.min_bars = min_bars

    @property
    def name(self) -> str:
        return "prediction_reversal"

    def should_exit(self, ctx: StopContext) -> tuple[bool, Optional[str]]:
        if ctx.position == 0:
            return False, None

        # Don't exit too early
        if ctx.bars_in_trade < self.min_bars:
            return False, None

        # Long position: exit if model now predicts DOWN
        if ctx.position == 1 and ctx.prediction < -self.threshold:
            return True, f"{self.name}_bearish"

        # Short position: exit if model now predicts UP
        if ctx.position == -1 and ctx.prediction > self.threshold:
            return True, f"{self.name}_bullish"

        return False, None


class ATRTrailingStop(StopLossStrategy):
    """
    Volatility-adjusted trailing stop using ATR.

    The stop trails the best price seen during the trade,
    maintaining a distance of N * ATR.

    As price moves in favor, stop tightens.
    As volatility increases, stop widens (gives more room).
    """

    def __init__(self, atr_multiplier: float = 2.0, min_bars: int = 2):
        """
        Args:
            atr_multiplier: Stop distance as multiple of ATR
                           2.0 = stop at 2x ATR from best price
            min_bars: Minimum bars before trailing starts
        """
        self.atr_multiplier = atr_multiplier
        self.min_bars = min_bars
        self._reset_state()

    def _reset_state(self):
        self.best_price = 0.0
        self.stop_price = 0.0

    @property
    def name(self) -> str:
        return "atr_trailing"

    def on_entry(self, ctx: StopContext) -> None:
        """Initialize tracking on new position."""
        self._reset_state()
        self.best_price = ctx.entry_price

        # Set initial stop based on entry price and ATR
        if ctx.position == 1:  # Long
            self.stop_price = ctx.entry_price - (self.atr_multiplier * ctx.atr)
        elif ctx.position == -1:  # Short
            self.stop_price = ctx.entry_price + (self.atr_multiplier * ctx.atr)

    def on_exit(self) -> None:
        """Clear state on exit."""
        self._reset_state()

    def update(self, ctx: StopContext) -> None:
        """Update trailing stop each bar."""
        if ctx.position == 0 or ctx.bars_in_trade < self.min_bars:
            return

        trail_distance = self.atr_multiplier * ctx.atr

        if ctx.position == 1:  # Long
            # Update best price if we made new high
            if ctx.current_price > self.best_price:
                self.best_price = ctx.current_price
            # Trail stop up (never down)
            new_stop = self.best_price - trail_distance
            self.stop_price = max(self.stop_price, new_stop)

        elif ctx.position == -1:  # Short
            # Update best price if we made new low
            if ctx.current_price < self.best_price:
                self.best_price = ctx.current_price
            # Trail stop down (never up)
            new_stop = self.best_price + trail_distance
            self.stop_price = min(self.stop_price, new_stop)

    def should_exit(self, ctx: StopContext) -> tuple[bool, Optional[str]]:
        if ctx.position == 0:
            return False, None

        # Update trailing stop first
        self.update(ctx)

        # Don't check until minimum bars
        if ctx.bars_in_trade < self.min_bars:
            return False, None

        # Check if price hit stop
        if ctx.position == 1 and ctx.current_price <= self.stop_price:
            pnl_pct = ctx.unrealized_pnl_pct
            return True, f"{self.name}_hit_{pnl_pct:.2f}%"

        if ctx.position == -1 and ctx.current_price >= self.stop_price:
            pnl_pct = ctx.unrealized_pnl_pct
            return True, f"{self.name}_hit_{pnl_pct:.2f}%"

        return False, None

    @property
    def current_stop(self) -> float:
        """Get current stop price for logging/debugging."""
        return self.stop_price


class MaxDrawdownStop(StopLossStrategy):
    """
    Exit if unrealized loss exceeds a threshold.

    Simple but effective risk management.
    """

    def __init__(self, max_loss_pct: float = 1.0):
        """
        Args:
            max_loss_pct: Maximum allowed loss as percentage (1.0 = 1%)
        """
        self.max_loss_pct = max_loss_pct

    @property
    def name(self) -> str:
        return "max_drawdown"

    def should_exit(self, ctx: StopContext) -> tuple[bool, Optional[str]]:
        if ctx.position == 0:
            return False, None

        if ctx.unrealized_pnl_pct < -self.max_loss_pct:
            return True, f"{self.name}_{ctx.unrealized_pnl_pct:.2f}%"

        return False, None


class TimeBasedStop(StopLossStrategy):
    """
    Exit after a maximum number of bars.

    Prevents positions from being held too long.
    """

    def __init__(self, max_bars: int = 48):
        """
        Args:
            max_bars: Maximum bars to hold position (48 = 12 hours at 15min)
        """
        self.max_bars = max_bars

    @property
    def name(self) -> str:
        return "time_based"

    def should_exit(self, ctx: StopContext) -> tuple[bool, Optional[str]]:
        if ctx.position == 0:
            return False, None

        if ctx.bars_in_trade >= self.max_bars:
            return True, f"{self.name}_{ctx.bars_in_trade}bars"

        return False, None


class CompositeStop(StopLossStrategy):
    """
    Combine multiple stop strategies.
    Exit if ANY strategy triggers.
    """

    def __init__(self, strategies: List[StopLossStrategy]):
        """
        Args:
            strategies: List of stop strategies to combine
        """
        self.strategies = strategies

    @property
    def name(self) -> str:
        names = [s.name for s in self.strategies]
        return f"composite({'+'.join(names)})"

    def on_entry(self, ctx: StopContext) -> None:
        for strategy in self.strategies:
            strategy.on_entry(ctx)

    def on_exit(self) -> None:
        for strategy in self.strategies:
            strategy.on_exit()

    def update(self, ctx: StopContext) -> None:
        for strategy in self.strategies:
            strategy.update(ctx)

    def should_exit(self, ctx: StopContext) -> tuple[bool, Optional[str]]:
        for strategy in self.strategies:
            should_exit, reason = strategy.should_exit(ctx)
            if should_exit:
                return True, reason
        return False, None


class NoStop(StopLossStrategy):
    """No stop-loss - for baseline comparison."""

    @property
    def name(self) -> str:
        return "no_stop"

    def should_exit(self, ctx: StopContext) -> tuple[bool, Optional[str]]:
        return False, None


# =============================================================================
# Factory function for easy strategy creation
# =============================================================================

def create_stop_strategy(
    strategy_type: str = "prediction_reversal",
    **kwargs
) -> StopLossStrategy:
    """
    Factory function to create stop-loss strategies.

    Args:
        strategy_type: One of:
            - "none": No stop-loss (baseline)
            - "prediction_reversal": Exit on prediction flip (DEFAULT)
            - "atr_trailing": Volatility-adjusted trailing stop
            - "max_drawdown": Exit on max loss threshold
            - "time_based": Exit after N bars
            - "both": Prediction reversal + ATR trailing (composite)
            - "all": All strategies combined
        **kwargs: Strategy-specific parameters

    Returns:
        StopLossStrategy instance

    Examples:
        >>> stop = create_stop_strategy("prediction_reversal")
        >>> stop = create_stop_strategy("atr_trailing", atr_multiplier=2.5)
        >>> stop = create_stop_strategy("both")  # Prediction + ATR
    """

    if strategy_type == "none":
        return NoStop()

    elif strategy_type == "prediction_reversal":
        return PredictionReversalStop(
            threshold=kwargs.get("threshold", 0.0),
            min_bars=kwargs.get("min_bars", 1)
        )

    elif strategy_type == "atr_trailing":
        return ATRTrailingStop(
            atr_multiplier=kwargs.get("atr_multiplier", 2.0),
            min_bars=kwargs.get("min_bars", 2)
        )

    elif strategy_type == "max_drawdown":
        return MaxDrawdownStop(
            max_loss_pct=kwargs.get("max_loss_pct", 1.0)
        )

    elif strategy_type == "time_based":
        return TimeBasedStop(
            max_bars=kwargs.get("max_bars", 48)
        )

    elif strategy_type == "both":
        # Combine prediction reversal + ATR trailing
        return CompositeStop([
            PredictionReversalStop(
                threshold=kwargs.get("threshold", 0.0),
                min_bars=kwargs.get("min_bars", 1)
            ),
            ATRTrailingStop(
                atr_multiplier=kwargs.get("atr_multiplier", 2.0),
                min_bars=kwargs.get("min_bars", 2)
            )
        ])

    elif strategy_type == "all":
        # All strategies combined
        return CompositeStop([
            PredictionReversalStop(threshold=kwargs.get("threshold", 0.0)),
            ATRTrailingStop(atr_multiplier=kwargs.get("atr_multiplier", 2.0)),
            MaxDrawdownStop(max_loss_pct=kwargs.get("max_loss_pct", 2.0)),
            TimeBasedStop(max_bars=kwargs.get("max_bars", 96))
        ])

    else:
        raise ValueError(
            f"Unknown strategy: {strategy_type}. "
            f"Choose from: none, prediction_reversal, atr_trailing, "
            f"max_drawdown, time_based, both, all"
        )


# =============================================================================
# Demo / Test
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Stop-Loss Strategy Demo")
    print("=" * 60)

    # Create test context
    ctx = StopContext(
        position=1,  # Long
        entry_price=2500.0,
        current_price=2480.0,  # Down $20
        prediction=-0.001,  # Model now bearish
        atr=25.0,  # ATR = $25
        timestamp=100,
        bars_in_trade=5
    )

    print(f"\nTest Context:")
    print(f"  Position: LONG @ ${ctx.entry_price}")
    print(f"  Current: ${ctx.current_price}")
    print(f"  Unrealized P&L: ${ctx.unrealized_pnl:.2f} ({ctx.unrealized_pnl_pct:.2f}%)")
    print(f"  Prediction: {ctx.prediction:.4f} (bearish)")
    print(f"  ATR: ${ctx.atr}")

    # Test each strategy
    strategies_to_test = [
        ("No Stop", create_stop_strategy("none")),
        ("Prediction Reversal", create_stop_strategy("prediction_reversal")),
        ("ATR Trailing (2x)", create_stop_strategy("atr_trailing", atr_multiplier=2.0)),
        ("Both Combined", create_stop_strategy("both")),
    ]

    print(f"\nResults:")
    print("-" * 50)

    for name, strategy in strategies_to_test:
        strategy.on_entry(ctx)
        should_exit, reason = strategy.should_exit(ctx)
        status = f"EXIT ({reason})" if should_exit else "HOLD"
        print(f"  {name:25s}: {status}")

    print("\n" + "=" * 60)
    print("Prediction Reversal triggered because prediction < 0 (bearish)")
    print("ATR Trailing did NOT trigger: stop at $2450, price at $2480")
    print("=" * 60)
