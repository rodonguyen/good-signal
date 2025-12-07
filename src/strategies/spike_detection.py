"""
Spike Detection Strategy using Price + Volume Z-Scores.

Strategy Logic:
- SPIKE_UP: Price z-score > threshold AND volume z-score > threshold (upward spike)
- SPIKE_DOWN: Price z-score < -threshold AND volume z-score > threshold (downward spike)
- Volume z-score direction doesn't matter (always check if > threshold)
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime
from .base import BaseStrategy
import logging

logger = logging.getLogger(__name__)


class SpikeDetectionStrategy(BaseStrategy):
    """
    Detects price spikes using separate Price and Volume Z-scores.

    Signal Conditions:
    - SPIKE_UP: price_zscore > price_threshold AND volume_zscore > volume_threshold
    - SPIKE_DOWN: price_zscore < -price_threshold AND volume_zscore > volume_threshold

    Example:
        strategy = SpikeDetectionStrategy(price_threshold=2.5, volume_threshold=1.5)
        signal = strategy.generate_signal(df)
        # Returns signal dict or None
    """

    def __init__(self, price_threshold: float = 2.5, volume_threshold: float = 1.5):
        """
        Initialize spike detection strategy.

        Args:
            price_threshold: Z-score threshold for price moves (default 2.5)
            volume_threshold: Z-score threshold for volume spikes (default 1.5)
        """
        self.price_threshold = price_threshold
        self.volume_threshold = volume_threshold

    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Detect spike on most recent completed candle (latest row).

        Args:
            df: DataFrame with columns [close, volume, price_zscore, volume_zscore, price_return, timestamp]

        Returns:
            Signal dict with structure:
            {
                'signal': 'SPIKE_UP' | 'SPIKE_DOWN',
                'price': float,
                'price_zscore': float,
                'volume_zscore': float,
                'price_return_pct': float,
                'volume': float,
                'volume_ratio': float,
                'timestamp': datetime,
                'metadata': dict
            }

            Returns None if no signal generated
        """
        # Validate input
        required_cols = ["close", "volume", "price_zscore", "volume_zscore", "price_return", "timestamp"]
        if not all(col in df.columns for col in required_cols):
            missing = [c for c in required_cols if c not in df.columns]
            logger.warning(f"Missing columns for spike detection: {missing}")
            return None

        # Need at least 2 candles (current + 1 previous)
        if len(df) < 2:
            logger.warning("Insufficient data for spike detection (need 2+ candles)")
            return None

        # Use latest row (most recent completed candle)
        latest = df.iloc[-1]

        # Extract z-scores
        price_z = latest["price_zscore"]
        volume_z = latest["volume_zscore"]

        # Skip if NaN (insufficient rolling window data)
        if pd.isna(price_z) or pd.isna(volume_z):
            logger.debug("NaN z-scores, skipping signal generation")
            return None

        # Detect SPIKE_UP: Strong positive price move + high volume
        if price_z > self.price_threshold and volume_z > self.volume_threshold:
            return self._create_signal(signal_type="SPIKE_UP", df=df, latest=latest, price_z=price_z, volume_z=volume_z)

        # Detect SPIKE_DOWN: Strong negative price move + high volume
        if price_z < -self.price_threshold and volume_z > self.volume_threshold:
            return self._create_signal(signal_type="SPIKE_DOWN", df=df, latest=latest, price_z=price_z, volume_z=volume_z)

        # No spike detected
        logger.info(f"No spike: price_z={price_z:.2f}, volume_z={volume_z:.2f}")
        return None

    def _create_signal(self, signal_type: str, df: pd.DataFrame, latest: pd.Series, price_z: float, volume_z: float) -> Dict[str, Any]:
        """Helper to construct signal dictionary."""

        # Calculate volume ratio (current vs rolling average)
        window = 20  # Match indicator window
        avg_volume = df["volume"].tail(window).mean()
        volume_ratio = latest["volume"] / avg_volume if avg_volume > 0 else 0

        # Calculate price return percentage
        price_return_pct = latest["price_return"] * 100

        # Determine signal strength
        confirmation = "STRONG" if (abs(price_z) > 3.0 and volume_z > 2.0) else "MODERATE"

        signal_data = {
            "signal": signal_type,
            "price": float(latest["close"]),
            "price_zscore": float(price_z),
            "volume_zscore": float(volume_z),
            "price_return_pct": float(price_return_pct),
            "volume": float(latest["volume"]),
            "volume_ratio": float(volume_ratio),
            "timestamp": latest["timestamp"],
            "metadata": {
                "price_threshold": self.price_threshold,
                "volume_threshold": self.volume_threshold,
                "avg_volume": float(avg_volume),
                "combined_score": float(abs(price_z) + volume_z),
                "confirmation": confirmation,
            },
        }

        logger.info(f"{signal_type} detected: price_z={price_z:.2f}, " f"volume_z={volume_z:.2f}, strength={confirmation}")

        return signal_data

    def format_signal_message(self, symbol: str, signal_data: Dict[str, Any]) -> str:
        """
        Format spike signal for Discord notification.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            signal_data: Signal dict from generate_signal()

        Returns:
            Formatted message string for Discord
        """
        signal_type = signal_data["signal"]
        emoji = "🔺" if signal_type == "SPIKE_UP" else "🔻"

        # Clean symbol for display
        display_symbol = symbol.replace(":USDT", "").replace("USDT", "")

        message = f"{emoji} **{signal_type} DETECTED** {emoji}\n\n"
        message += f"**Symbol:** {display_symbol}\n"
        message += f"**Price:** ${signal_data['price']:,.2f}\n"
        message += f"**Price Change:** {signal_data['price_return_pct']:+.2f}%\n\n"

        message += f"**Z-Scores:**\n"
        message += f"• Price Z-Score: {signal_data['price_zscore']:.2f} "
        message += f"({'above' if signal_data['price_zscore'] > 0 else 'below'} threshold: {signal_data['metadata']['price_threshold']})\n"
        message += f"• Volume Z-Score: {signal_data['volume_zscore']:.2f} "
        message += f"(threshold: {signal_data['metadata']['volume_threshold']})\n\n"

        message += f"**Volume Analysis:**\n"
        message += f"• Current Volume: {signal_data['volume']:,.0f}\n"
        message += f"• Average Volume: {signal_data['metadata']['avg_volume']:,.0f}\n"
        message += f"• Volume Ratio: {signal_data['volume_ratio']:.2f}x average\n\n"

        message += f"**Signal Strength:** {signal_data['metadata']['confirmation']}\n"
        message += f"**Combined Score:** {signal_data['metadata']['combined_score']:.2f}\n\n"

        message += f"**Timestamp:** {signal_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S UTC')}\n"

        return message

    def __repr__(self) -> str:
        return f"SpikeDetectionStrategy(price_threshold={self.price_threshold}, volume_threshold={self.volume_threshold})"
