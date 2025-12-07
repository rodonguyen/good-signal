"""
Abstract base class for all trading strategies.
Ensures consistent signal generation interface.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import pandas as pd


class BaseStrategy(ABC):
    """
    Base class for all trading strategies.

    All strategies must implement generate_signal() which:
    - Analyzes DataFrame with OHLCV + indicator data
    - Returns signal dict or None
    - Includes all metadata needed for logging/notification
    """

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal based on data and indicators.

        Args:
            df: DataFrame with OHLCV + calculated indicators

        Returns:
            Signal dictionary with structure:
            {
                'signal': 'BUY' | 'SELL',
                'price': float,           # Current close price
                'threshold': float,       # Calculated trigger threshold
                'bb_upper': float,        # Current BB upper band
                'bb_lower': float,        # Current BB lower band
                'bb_middle': float,       # Current BB middle (SMA)
                'metadata': dict          # Strategy-specific data
            }

            Returns None if no signal generated

        Example:
            {
                'signal': 'BUY',
                'price': 45123.50,
                'threshold': 45200.00,
                'bb_upper': 46000.00,
                'bb_lower': 44500.00,
                'bb_middle': 45250.00,
                'metadata': {'slope': -76.5, 'distance': 76.5}
            }
        """
        pass

    def format_signal_message(self, symbol: str, signal_data: Dict[str, Any]) -> str:
        """
        Format trading signal into a readable message string.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            signal_data: Signal dict from generate_signal()

        Returns:
            Formatted message string ready for notification

        Default implementation provides basic formatting.
        Subclasses should override for strategy-specific formatting.
        """
        signal_type = signal_data["signal"]
        price = signal_data["price"]
        threshold = signal_data["threshold"]

        message = f"{signal_type} Signal for {symbol}\nPrice: {price:.2f}\nThreshold: {threshold:.2f}"
        return message

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}()"
