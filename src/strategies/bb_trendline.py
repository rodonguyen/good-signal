"""
Bollinger Band Trendline Breakout Strategy.

Strategy Logic:
- Calculate trendline from BB values at t-3 and t-2
- Extrapolate to t-1 position
- Generate BUY signal if t-1's close price breaks above upper trendline (breakout up)
- Generate SELL signal if t-1's close price breaks below lower trendline (breakout down)
- Uses completed candle (t-1) for signal generation when new candle (t) appears
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime
from .base import BaseStrategy
from src.utils.datetime_utils import to_local_timezone
import logging

logger = logging.getLogger(__name__)


class BBTrendlineStrategy(BaseStrategy):
    """
    Bollinger Band Trendline Breakout Strategy.

    Entry Signals:
    - BUY: t-1's close price breaks above extrapolated upper BB trendline (breakout up)
    - SELL: t-1's close price breaks below extrapolated lower BB trendline (breakout down)

    Trendline Calculation:
    - Upper: slope = (BB_upper[t-2] - BB_upper[t-3]) / 1
    - Threshold_upper = BB_upper[t-2] + slope (extrapolated to t-1)
    - Lower: slope = (BB_lower[t-2] - BB_lower[t-3]) / 1
    - Threshold_lower = BB_lower[t-2] + slope (extrapolated to t-1)

    Example:
        If BB_upper at t-3 = 46000, t-2 = 46100 (rising)
        slope = +100
        threshold = 46100 + 100 = 46200 (at t-1 position)
        If t-1's close price = 46250 > 46200 → BUY signal (breakout up)
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
                'open_timestamp': datetime,
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

        if len(df) < 4:
            logger.warning("⚠️Need at least 4 rows for trendline calculation (t-3, t-2, t-1, t)")
            return None

        # Get last 4 rows (t-3, t-2, t-1, t)
        # t-3 and t-2 are used for trendline calculation
        # t-1 is the completed candle we check for signal
        # t is the current/new candle
        t_minus_3 = df.iloc[-4]
        t_minus_2 = df.iloc[-3]
        t_minus_1 = df.iloc[-2]
        t_current = df.iloc[-1]

        # Check for NaN values
        if pd.isna(
            [
                t_minus_3["bb_lower"],
                t_minus_2["bb_lower"],
                t_minus_3["bb_upper"],
                t_minus_2["bb_upper"],
                t_minus_1["close"],
            ]
        ).any():
            logger.warning("⚠️NaN values in Bollinger Bands or close price, skipping signal")
            return None

        # Use t-1's completed close price for signal comparison
        t_minus_1_price = float(t_minus_1["close"])

        # === UPPER BAND TRENDLINE (BUY SIGNAL - Breakout Up) ===
        # Calculate slope from t-3 to t-2
        upper_slope = float(t_minus_2["bb_upper"] - t_minus_3["bb_upper"])
        # Extrapolate to t-1 position: threshold = BB_upper[t-2] + slope
        upper_threshold = float(t_minus_2["bb_upper"] + upper_slope)

        # Check for BUY signal (t-1's close price breaks above upper trendline)
        if t_minus_1_price > upper_threshold:
            distance = t_minus_1_price - upper_threshold
            bb_width = float(t_minus_1["bb_upper"] - t_minus_1["bb_lower"])

            signal_data = {
                "signal": "BUY",
                "price": t_minus_1_price,
                "threshold": upper_threshold,
                "bb_upper": float(t_minus_1["bb_upper"]),
                "bb_lower": float(t_minus_1["bb_lower"]),
                "bb_middle": float(t_minus_1["bb_middle"]),
                "open_timestamp": t_minus_1["timestamp"],
                "metadata": {
                    "bb_t_minus_1": float(t_minus_2["bb_upper"]),
                    "bb_t_minus_2": float(t_minus_3["bb_upper"]),
                    "slope": upper_slope,
                    "distance_to_threshold": distance,
                    "penetration_pct": (distance / upper_threshold) * 100,
                },
            }

            logger.info(
                f"BUY signal generated (breakout up): price={t_minus_1_price:.2f}, " f"threshold={upper_threshold:.2f}, distance={distance:.2f}"
            )

            return signal_data

        # === LOWER BAND TRENDLINE (SELL SIGNAL - Breakout Down) ===
        # Calculate slope from t-3 to t-2
        lower_slope = float(t_minus_2["bb_lower"] - t_minus_3["bb_lower"])
        # Extrapolate to t-1 position: threshold = BB_lower[t-2] + slope
        lower_threshold = float(t_minus_2["bb_lower"] + lower_slope)

        # Check for SELL signal (t-1's close price breaks below lower trendline)
        if t_minus_1_price < lower_threshold:
            distance = lower_threshold - t_minus_1_price
            bb_width = float(t_minus_1["bb_upper"] - t_minus_1["bb_lower"])

            signal_data = {
                "signal": "SELL",
                "price": t_minus_1_price,
                "threshold": lower_threshold,
                "bb_upper": float(t_minus_1["bb_upper"]),
                "bb_lower": float(t_minus_1["bb_lower"]),
                "bb_middle": float(t_minus_1["bb_middle"]),
                "open_timestamp": t_minus_1["timestamp"],
                "metadata": {
                    "bb_t_minus_3": float(t_minus_3["bb_lower"]),
                    "bb_t_minus_2": float(t_minus_2["bb_lower"]),
                    "slope": lower_slope,
                    "distance_to_threshold": distance,
                    "bb_width": bb_width,
                    "penetration_pct": (distance / lower_threshold) * 100,
                },
            }

            logger.info(
                f"SELL signal generated (breakout down): price={t_minus_1_price:.2f}, " f"threshold={lower_threshold:.2f}, distance={distance:.2f}"
            )

            return signal_data

        # No signal
        logger.debug(f"No signal: price={t_minus_1_price:.2f}, " f"lower_threshold={lower_threshold:.2f}, " f"upper_threshold={upper_threshold:.2f}")
        return None

    def format_signal_message(self, symbol: str, signal_data: Dict[str, Any]) -> str:
        """
        Format trading signal into readable Discord message.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            signal_data: Signal dict from generate_signal()

        Returns:
            Formatted message string
        """
        # Clean symbol for display (remove :USDT suffix if present)
        display_symbol = symbol.replace(":USDT", "")

        # Extract data
        signal_type = signal_data["signal"]
        price = signal_data["price"]
        threshold = signal_data["threshold"]
        bb_upper = signal_data["bb_upper"]
        bb_lower = signal_data["bb_lower"]
        bb_middle = signal_data["bb_middle"]
        open_timestamp = signal_data["open_timestamp"]

        # Convert open_timestamp to local timezone
        local_open_timestamp = to_local_timezone(open_timestamp)

        # Get current timestamp
        current_timestamp = to_local_timezone(datetime.utcnow())

        # Extract metadata
        metadata = signal_data.get("metadata", {})
        slope = metadata.get("slope", 0)
        distance = metadata.get("distance_to_threshold", 0)
        penetration_pct = metadata.get("penetration_pct", 0)
        bb_t_minus_3 = metadata.get("bb_t_minus_3", 0)
        bb_t_minus_2 = metadata.get("bb_t_minus_2", 0)

        # Determine band label based on signal type
        band_label = "Upper Band" if signal_type == "BUY" else "Lower Band"
        emoji = "🟢" if signal_type == "BUY" else "🔴"

        # Build message
        message = f"""
{emoji} **{signal_type} SIGNAL** {emoji}

**Symbol:** {display_symbol}
**Price:** ${price:,.2f}
**Threshold:** ${threshold:,.2f}
**Distance:** ${distance:,.2f} ({abs(distance/price)*100:.2f}%)

**Bollinger Bands:**
• Upper: ${bb_upper:,.2f}
• Middle: ${bb_middle:,.2f}
• Lower: ${bb_lower:,.2f}

**Trendline:**
• {band_label} (t-3): ${bb_t_minus_3:,.2f}
• {band_label} (t-2): ${bb_t_minus_2:,.2f}
• Threshold: {(price+slope):,.2f} ({slope:+.2f})
• Penetration: {penetration_pct:.2f}%

**Open Time:** {local_open_timestamp.strftime('%Y-%m-%d %H:%M:%S')}
**Timestamp:** {current_timestamp.strftime('%Y-%m-%d %H:%M:%S')}
"""

        return message.strip()

    def __repr__(self) -> str:
        return "BBTrendlineStrategy()"
