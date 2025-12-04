"""
Bollinger Band Trendline Breakout Strategy.

Strategy Logic:
- Calculate trendline from BB values at t-2 and t-1
- Extrapolate to current time t
- Generate BUY signal if price breaks above upper trendline (breakout up)
- Generate SELL signal if price breaks below lower trendline (breakout down)
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime
from .base import BaseStrategy
import logging

logger = logging.getLogger(__name__)


class BBTrendlineStrategy(BaseStrategy):
    """
    Bollinger Band Trendline Breakout Strategy.

    Entry Signals:
    - BUY: Close price breaks above extrapolated upper BB trendline (breakout up)
    - SELL: Close price breaks below extrapolated lower BB trendline (breakout down)

    Trendline Calculation:
    - Upper: slope = (BB_upper[t-1] - BB_upper[t-2]) / 1
    - Threshold_upper = BB_upper[t-1] + slope
    - Lower: slope = (BB_lower[t-1] - BB_lower[t-2]) / 1
    - Threshold_lower = BB_lower[t-1] + slope

    Example:
        If BB_upper at t-2 = 46000, t-1 = 46100 (rising)
        slope = +100
        threshold = 46100 + 100 = 46200
        If current price = 46250 > 46200 → BUY signal (breakout up)
    """

    def __init__(self):
        """Initialize strategy (no parameters needed for now)."""
        pass

    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal based on BB trendline breakout.

        Args:
            df: DataFrame with columns [close, bb_upper, bb_lower, bb_middle, timestamp]

        Returns:
            Signal dict or None if no signal

        Signal Structure:
            {
                'signal': 'BUY' | 'SELL',
                'price': float,
                'threshold': float,
                'bb_upper': float,
                'bb_lower': float,
                'bb_middle': float,
                'timestamp': datetime,
                'metadata': {
                    'slope': float,
                    'distance_to_threshold': float,
                    'bb_width': float
                }
            }
        """
        # Validate input
        required_cols = ["close", "bb_upper", "bb_lower", "bb_middle", "timestamp"]
        if not all(col in df.columns for col in required_cols):
            logger.error(f"Missing required columns. Need: {required_cols}")
            return None

        if len(df) < 3:
            logger.warning("Need at least 3 rows for trendline calculation")
            return None

        # Get last 3 rows (t-2, t-1, t)
        t_minus_2 = df.iloc[-3]
        t_minus_1 = df.iloc[-2]
        t_current = df.iloc[-1]

        # Check for NaN values
        if pd.isna(
            [
                t_minus_2["bb_lower"],
                t_minus_1["bb_lower"],
                t_minus_2["bb_upper"],
                t_minus_1["bb_upper"],
            ]
        ).any():
            logger.warning("NaN values in Bollinger Bands, skipping signal")
            return None

        current_price = float(t_current["close"])

        # === UPPER BAND TRENDLINE (BUY SIGNAL - Breakout Up) ===
        upper_slope = float(t_minus_1["bb_upper"] - t_minus_2["bb_upper"])
        upper_threshold = float(t_minus_1["bb_upper"] + upper_slope)

        # Check for BUY signal (price breaks above upper trendline)
        if current_price > upper_threshold:
            distance = current_price - upper_threshold
            bb_width = float(t_current["bb_upper"] - t_current["bb_lower"])

            signal_data = {
                "signal": "BUY",
                "price": current_price,
                "threshold": upper_threshold,
                "bb_upper": float(t_current["bb_upper"]),
                "bb_lower": float(t_current["bb_lower"]),
                "bb_middle": float(t_current["bb_middle"]),
                "timestamp": t_current["timestamp"],
                "metadata": {
                    "slope": upper_slope,
                    "distance_to_threshold": distance,
                    "bb_width": bb_width,
                    "penetration_pct": (distance / upper_threshold) * 100,
                },
            }

            logger.info(
                f"BUY signal generated (breakout up): price={current_price:.2f}, "
                f"threshold={upper_threshold:.2f}, distance={distance:.2f}"
            )

            return signal_data

        # === LOWER BAND TRENDLINE (SELL SIGNAL - Breakout Down) ===
        lower_slope = float(t_minus_1["bb_lower"] - t_minus_2["bb_lower"])
        lower_threshold = float(t_minus_1["bb_lower"] + lower_slope)

        # Check for SELL signal (price breaks below lower trendline)
        if current_price < lower_threshold:
            distance = lower_threshold - current_price
            bb_width = float(t_current["bb_upper"] - t_current["bb_lower"])

            signal_data = {
                "signal": "SELL",
                "price": current_price,
                "threshold": lower_threshold,
                "bb_upper": float(t_current["bb_upper"]),
                "bb_lower": float(t_current["bb_lower"]),
                "bb_middle": float(t_current["bb_middle"]),
                "timestamp": t_current["timestamp"],
                "metadata": {
                    "slope": lower_slope,
                    "distance_to_threshold": distance,
                    "bb_width": bb_width,
                    "penetration_pct": (distance / lower_threshold) * 100,
                },
            }

            logger.info(
                f"SELL signal generated (breakout down): price={current_price:.2f}, "
                f"threshold={lower_threshold:.2f}, distance={distance:.2f}"
            )

            return signal_data

        # No signal
        logger.debug(
            f"No signal: price={current_price:.2f}, "
            f"lower_threshold={lower_threshold:.2f}, "
            f"upper_threshold={upper_threshold:.2f}"
        )
        return None

    def __repr__(self) -> str:
        return "BBTrendlineStrategy()"
