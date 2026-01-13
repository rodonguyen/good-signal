"""
Dynamic Stop-Loss Strategies for Bayesian Trading

Uses Strategy Pattern for easy modification, extension, and replacement.
All strategies use signals from the Bayesian model rather than fixed parameters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
import numpy as np


@dataclass
class StopContext:
    """Context passed to stop-loss strategies each bar."""

    position: int  # 1 (long), -1 (short), 0 (flat)
    entry_price: float
    current_price: float
    delta_p: float  # Combined prediction
    dp1: float  # S1 (180-bar) prediction
    dp2: float  # S2 (360-bar) prediction
    dp3: float  # S3 (720-bar) prediction
    timestamp: any  # Current bar timestamp
    bars_in_trade: int = 0  # Bars since entry


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

        Args:
            ctx: StopContext with current market state and predictions

        Returns:
            (should_exit: bool, reason: str or None)
        """
        pass

    def on_entry(self, ctx: StopContext) -> None:
        """Called when a new position is opened. Override if needed."""
        pass

    def on_exit(self) -> None:
        """Called when position is closed. Override to reset state."""
        pass


class PredictionReversalStop(StopLossStrategy):
    """
    Strategy 1: Exit when model prediction flips direction.

    Uses the model's own signal - if it predicted UP to enter long,
    exit when it now predicts DOWN (and vice versa for shorts).
    """

    def __init__(self, threshold: float = 0.04):
        """
        Args:
            threshold: Minimum prediction magnitude to trigger exit.
                       Use same as entry threshold for symmetry,
                       or lower for faster exits.
        """
        self.threshold = threshold

    @property
    def name(self) -> str:
        return "prediction_reversal"

    def should_exit(self, ctx: StopContext) -> tuple[bool, Optional[str]]:
        if ctx.position == 0:
            return False, None

        # Long position: exit if model now predicts DOWN
        if ctx.position == 1 and ctx.delta_p < -self.threshold:
            return True, f"{self.name}_bearish"

        # Short position: exit if model now predicts UP
        if ctx.position == -1 and ctx.delta_p > self.threshold:
            return True, f"{self.name}_bullish"

        return False, None


class TimeframeDisagreementStop(StopLossStrategy):
    """
    Strategy 2: Exit when short-term (S1) and long-term (S3) both turn against position.

    S1 (180-bar) has highest predictive power (score 0.0982).
    S3 (720-bar) captures longer-term trend.
    When both agree against position = high confidence reversal.
    """

    @property
    def name(self) -> str:
        return "timeframe_disagreement"

    def should_exit(self, ctx: StopContext) -> tuple[bool, Optional[str]]:
        if ctx.position == 0:
            return False, None

        # Long position: exit if both S1 and S3 are bearish
        if ctx.position == 1 and ctx.dp1 < 0 and ctx.dp3 < 0:
            return True, f"{self.name}_both_bearish"

        # Short position: exit if both S1 and S3 are bullish
        if ctx.position == -1 and ctx.dp1 > 0 and ctx.dp3 > 0:
            return True, f"{self.name}_both_bullish"

        return False, None


class PredictionMomentumStop(StopLossStrategy):
    """
    Strategy 4: Exit when prediction momentum fades significantly.

    Tracks prediction strength over time. If the model's conviction
    drops substantially from its peak, exit to lock in gains or cut losses.
    """

    def __init__(self, lookback: int = 10, fade_threshold: float = 0.5, min_bars: int = 5):
        """
        Args:
            lookback: Number of bars to track prediction history
            fade_threshold: Exit if recent avg drops below this fraction of peak
                           (0.5 = exit when prediction fades to 50% of peak)
            min_bars: Minimum bars in trade before checking momentum
        """
        self.lookback = lookback
        self.fade_threshold = fade_threshold
        self.min_bars = min_bars
        self._reset_state()

    def _reset_state(self):
        self.prediction_history: List[float] = []
        self.peak_prediction: float = 0.0

    @property
    def name(self) -> str:
        return "prediction_momentum"

    def on_entry(self, ctx: StopContext) -> None:
        """Reset tracking on new position."""
        self._reset_state()
        self.prediction_history.append(abs(ctx.delta_p))
        self.peak_prediction = abs(ctx.delta_p)

    def on_exit(self) -> None:
        """Clear state on exit."""
        self._reset_state()

    def should_exit(self, ctx: StopContext) -> tuple[bool, Optional[str]]:
        if ctx.position == 0:
            return False, None

        # Track prediction magnitude (direction-agnostic strength)
        current_strength = abs(ctx.delta_p)
        self.prediction_history.append(current_strength)

        # Keep only recent history
        if len(self.prediction_history) > self.lookback:
            self.prediction_history = self.prediction_history[-self.lookback :]

        # Update peak
        if current_strength > self.peak_prediction:
            self.peak_prediction = current_strength

        # Don't check until minimum bars elapsed
        if ctx.bars_in_trade < self.min_bars:
            return False, None

        # Avoid division by zero
        if self.peak_prediction == 0:
            return False, None

        # Check if prediction momentum has faded
        recent_avg = np.mean(self.prediction_history[-5:]) if len(self.prediction_history) >= 5 else current_strength
        fade_ratio = recent_avg / self.peak_prediction

        if fade_ratio < self.fade_threshold:
            return True, f"{self.name}_faded_{fade_ratio:.2f}"

        return False, None


class CompositeStop(StopLossStrategy):
    """
    Combine multiple stop strategies.
    Exit if ANY strategy triggers.
    """

    def __init__(self, strategies: List[StopLossStrategy]):
        """
        Args:
            strategies: List of stop strategies to combine.
                       Checked in order, first trigger wins.
        """
        self.strategies = strategies

    @property
    def name(self) -> str:
        return "composite"

    def on_entry(self, ctx: StopContext) -> None:
        """Propagate entry event to all strategies."""
        for strategy in self.strategies:
            strategy.on_entry(ctx)

    def on_exit(self) -> None:
        """Propagate exit event to all strategies."""
        for strategy in self.strategies:
            strategy.on_exit()

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


def create_stop_strategy(strategy_type: str = "timeframe_disagreement", **kwargs) -> StopLossStrategy:
    """
    Factory function to create stop-loss strategies.

    Args:
        strategy_type: One of:
            - "none": No stop-loss (baseline)
            - "prediction_reversal": Exit on prediction flip
            - "timeframe_disagreement": Exit when S1 and S3 both against position
            - "prediction_momentum": Exit when prediction strength fades
            - "composite": Combine multiple strategies
        **kwargs: Strategy-specific parameters

    Returns:
        StopLossStrategy instance

    Examples:
        >>> stop = create_stop_strategy("timeframe_disagreement")
        >>> stop = create_stop_strategy("prediction_reversal", threshold=0.08)
        >>> stop = create_stop_strategy("composite", strategies=[
        ...     PredictionReversalStop(threshold=0.05),
        ...     TimeframeDisagreementStop()
        ... ])
    """
    strategies = {
        "none": NoStop,
        "prediction_reversal": PredictionReversalStop,
        "timeframe_disagreement": TimeframeDisagreementStop,
        "prediction_momentum": PredictionMomentumStop,
        "composite": CompositeStop,
    }

    if strategy_type not in strategies:
        raise ValueError(f"Unknown strategy: {strategy_type}. Choose from: {list(strategies.keys())}")

    return strategies[strategy_type](**kwargs)


# =============================================================================
# Example usage and testing
# =============================================================================

if __name__ == "__main__":
    # Demo: Create and test strategies
    print("=" * 60)
    print("Stop-Loss Strategy Demo")
    print("=" * 60)

    # Create test context (simulating a long position)
    ctx = StopContext(
        position=1,
        entry_price=3500.0,
        current_price=3480.0,
        delta_p=0.02,  # Still slightly bullish
        dp1=-0.01,  # S1 turned bearish
        dp2=0.03,  # S2 still bullish
        dp3=-0.02,  # S3 turned bearish
        timestamp="2025-01-01 12:00:00",
        bars_in_trade=15,
    )

    print(f"\nTest Context:")
    print(f"  Position: LONG @ {ctx.entry_price}")
    print(f"  Current: {ctx.current_price}")
    print(f"  delta_p: {ctx.delta_p:.4f}")
    print(f"  dp1 (S1): {ctx.dp1:.4f}, dp2 (S2): {ctx.dp2:.4f}, dp3 (S3): {ctx.dp3:.4f}")

    # Test each strategy
    strategies_to_test = [
        ("No Stop", create_stop_strategy("none")),
        ("Prediction Reversal", create_stop_strategy("prediction_reversal", threshold=0.05)),
        ("Timeframe Disagreement", create_stop_strategy("timeframe_disagreement")),
        ("Prediction Momentum", create_stop_strategy("prediction_momentum")),
    ]

    print(f"\nResults:")
    print("-" * 40)

    for name, strategy in strategies_to_test:
        # Simulate entry for stateful strategies
        strategy.on_entry(ctx)

        should_exit, reason = strategy.should_exit(ctx)
        status = f"EXIT ({reason})" if should_exit else "HOLD"
        print(f"  {name:25s}: {status}")

    print("\n" + "=" * 60)
    print("In this scenario:")
    print("  - dp1 < 0 AND dp3 < 0 → TimeframeDisagreement triggers EXIT")
    print("  - delta_p > -threshold → PredictionReversal does NOT trigger")
    print("=" * 60)
