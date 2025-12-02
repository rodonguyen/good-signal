"""
Abstract base class for all technical indicators.
Ensures consistent interface across indicator implementations.
"""
from abc import ABC, abstractmethod
import pandas as pd


class BaseIndicator(ABC):
    """
    Base class for all technical indicators.
    
    All indicators must implement the calculate() method which:
    - Takes a DataFrame with OHLCV data
    - Returns the same DataFrame with additional indicator columns
    - Preserves all original columns
    """
    
    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate indicator values and add them to the DataFrame.
        
        Args:
            df: DataFrame with columns [timestamp, open, high, low, close, volume]
            
        Returns:
            DataFrame with original columns + indicator columns
            
        Example:
            BollingerBands would add: bb_upper, bb_lower, bb_middle
            RSI would add: rsi
        """
        pass
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}()"

