"""Filter utilities for market condition filters."""

import pandas as pd
import numpy as np
from typing import Optional


def calculate_narrow_day(
    daily_bars: pd.DataFrame,
    threshold: float = 0.5,
    lookback_period: int = 20
) -> pd.Series:
    """Calculate narrow day filter.
    
    A narrow day is when the previous day's range is less than threshold × average range.
    This indicates low volatility and potential for breakout.
    
    Args:
        daily_bars: DataFrame with daily bars (columns: day, high, low, close, etc.)
        threshold: Threshold multiplier (default: 0.5 = 50% of average)
        lookback_period: Period for calculating average range
        
    Returns:
        Boolean Series indicating narrow days
    """
    # Calculate daily range
    daily_bars = daily_bars.copy()
    daily_bars['range'] = daily_bars['high'] - daily_bars['low']
    
    # Calculate average range over lookback period
    daily_bars['avg_range'] = daily_bars['range'].rolling(
        window=lookback_period, min_periods=1
    ).mean()
    
    # Previous day's range
    prev_range = daily_bars['range'].shift(1)
    avg_range = daily_bars['avg_range'].shift(1)
    
    # Narrow day: previous day range < threshold × average range
    narrow_day = prev_range < (threshold * avg_range)
    
    return narrow_day.fillna(False)


def calculate_volatility_contraction(
    daily_bars: pd.DataFrame,
    short_period: int = 5,
    long_period: int = 14
) -> pd.Series:
    """Calculate volatility contraction filter.
    
    Volatility contraction occurs when recent ATR is less than longer-term ATR.
    This suggests a potential breakout is building.
    
    Args:
        daily_bars: DataFrame with daily bars (must have 'atr' column)
        short_period: Short-term ATR period (default: 5)
        long_period: Long-term ATR period (default: 14)
        
    Returns:
        Boolean Series indicating volatility contraction days
    """
    if 'atr' not in daily_bars.columns:
        raise ValueError("daily_bars must have 'atr' column")
    
    daily_bars = daily_bars.copy()
    
    # Calculate short-term and long-term ATR averages
    short_atr = daily_bars['atr'].rolling(window=short_period, min_periods=1).mean()
    long_atr = daily_bars['atr'].rolling(window=long_period, min_periods=1).mean()
    
    # Shift to use previous day's values
    prev_short_atr = short_atr.shift(1)
    prev_long_atr = long_atr.shift(1)
    
    # Volatility contraction: short-term ATR < long-term ATR
    contraction = prev_short_atr < prev_long_atr
    
    return contraction.fillna(False)


def calculate_trend_filter(
    daily_bars: pd.DataFrame,
    ma_period: int = 20,
    trend_direction: str = 'any'
) -> pd.Series:
    """Calculate trend filter.
    
    Filter based on price position relative to moving average.
    
    Args:
        daily_bars: DataFrame with daily bars (must have 'close' column)
        ma_period: Moving average period (default: 20)
        trend_direction: 'up' (price > MA), 'down' (price < MA), 'any' (always True)
        
    Returns:
        Boolean Series indicating trend filter pass
    """
    if 'close' not in daily_bars.columns:
        raise ValueError("daily_bars must have 'close' column")
    
    daily_bars = daily_bars.copy()
    
    # Calculate moving average
    ma = daily_bars['close'].rolling(window=ma_period, min_periods=1).mean()
    
    # Previous day's close and MA
    prev_close = daily_bars['close'].shift(1)
    prev_ma = ma.shift(1)
    
    if trend_direction == 'up':
        trend_pass = prev_close > prev_ma
    elif trend_direction == 'down':
        trend_pass = prev_close < prev_ma
    else:  # 'any'
        trend_pass = pd.Series([True] * len(daily_bars), index=daily_bars.index)
    
    return trend_pass.fillna(False)


def calculate_volatility_expansion(
    daily_bars: pd.DataFrame,
    period: int = 5
) -> pd.Series:
    """Calculate volatility expansion filter.
    
    Volatility expansion occurs when ATR is increasing, indicating active market.
    
    Args:
        daily_bars: DataFrame with daily bars (must have 'atr' column)
        period: Period for detecting expansion (default: 5)
        
    Returns:
        Boolean Series indicating volatility expansion days
    """
    if 'atr' not in daily_bars.columns:
        raise ValueError("daily_bars must have 'atr' column")
    
    daily_bars = daily_bars.copy()
    
    # Calculate ATR change
    atr_change = daily_bars['atr'].diff(period)
    
    # Shift to use previous day's value
    prev_atr_change = atr_change.shift(1)
    
    # Volatility expansion: ATR is increasing
    expansion = prev_atr_change > 0
    
    return expansion.fillna(False)

