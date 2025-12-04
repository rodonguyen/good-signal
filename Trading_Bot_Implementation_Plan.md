# Bitcoin Trading Signal Bot - Complete Implementation Plan

## Document Information
- **Date**: December 2, 2024
- **Purpose**: Comprehensive implementation guide for trading signal bot
- **Target Platform**: Python 3.9+
- **Exchange**: Bybit Derivatives
- **Initial Asset**: Bitcoin (BTCUSDT)

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Detailed Implementation](#detailed-implementation)
6. [Configuration Files](#configuration-files)
7. [Error Handling & Logging](#error-handling--logging)
8. [Testing Plan](#testing-plan)
9. [Deployment Instructions](#deployment-instructions)
10. [Future Extensibility](#future-extensibility)

---

## Executive Summary

### Project Goals
Build a modular, extensible trading signal bot that:
- Monitors Bitcoin on Bybit derivatives (perpetual futures)
- Uses Bollinger Band trendline breakout strategy
- Sends signals via Discord notifications
- Logs all signals to CSV
- Follows SOLID principles for easy extension

### Key Features
- **Multi-asset support**: Easy to add ETH, SP500 via YAML config
- **Strategy flexibility**: Base classes allow quick strategy additions
- **Indicator library**: Modular indicator system (starting with Bollinger Bands)
- **Notification system**: Extensible notifier (Discord now, Telegram/email later)
- **Error resilience**: 3-retry logic with failure notifications
- **No trading execution**: Signal generation only (Phase 1)

### Non-Goals (Future Phases)
- Automated trading execution via exchange API
- Backtesting framework
- Multiple timeframe analysis (currently 1h only)
- Position tracking/cooldown periods

---

## System Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                         Main.py                              │
│                    (Entry Point)                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    TradingScheduler                          │
│  • Loads asset configs                                       │
│  • Runs 1h loop for all assets                              │
│  • Orchestrates: Fetch → Calculate → Signal → Notify        │
└──┬──────────────┬──────────────┬──────────────┬─────────────┘
   │              │              │              │
   ▼              ▼              ▼              ▼
┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐
│ Bybit   │  │Indicator │  │Strategy  │  │  Notifier    │
│ Fetcher │  │ System   │  │ Engine   │  │   System     │
└─────────┘  └──────────┘  └──────────┘  └──────────────┘
   │              │              │              │
   │              │              │              │
   ▼              ▼              ▼              ▼
┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐
│ CCXT    │  │Bollinger │  │BBTrendln │  │   Discord    │
│ Exchange│  │  Bands   │  │ Strategy │  │   Webhook    │
└─────────┘  └──────────┘  └──────────┘  └──────────────┘
                                               │
                                               ▼
                                         ┌──────────┐
                                         │ signals  │
                                         │   .csv   │
                                         └──────────┘
```

### Component Responsibilities

**BybitFetcher**
- Fetch OHLCV data from Bybit derivatives
- Handle API errors with 3-retry exponential backoff
- Notify on complete failure
- Return pandas DataFrame

**Indicator System**
- Abstract base for all indicators
- BollingerBands: Calculate upper/lower/middle bands
- Expose raw values for strategy access
- Configurable parameters (period, std_dev)

**Strategy Engine**
- Abstract base for all strategies
- BBTrendlineStrategy: Calculate trendline from t-1, t-2 points
- Generate BUY/SELL signals on breakouts
- Return structured signal data

**Notifier System**
- Abstract base for all notifiers
- DiscordNotifier: Send formatted messages via webhook
- Extensible for Telegram, Email, SMS

**TradingScheduler**
- Load configurations (assets, Discord)
- Schedule 1h jobs
- Dynamic strategy/indicator instantiation
- CSV logging for signals
- Console logging for operations

---

## Technology Stack

### Core Dependencies

```python
# requirements.txt
ccxt>=4.0.0              # Unified exchange API (Bybit support)
pandas>=2.0.0            # Data manipulation
pyyaml>=6.0              # YAML config parsing
requests>=2.31.0         # HTTP for Discord webhook
schedule>=1.2.0          # Job scheduling
numpy>=1.24.0            # Numerical operations (pandas dependency)
python-dateutil>=2.8.0   # Date handling
```

### Why Python?
1. **CCXT library**: Battle-tested, supports 100+ exchanges including Bybit
2. **pandas/numpy**: Industry standard for financial data analysis
3. **Fast prototyping**: Quick iteration on strategies
4. **Rich ecosystem**: Easy to add TA-Lib, pandas-ta for more indicators
5. **Async ready**: Future upgrade to async/await for multiple timeframes

### Alternative Considerations (Rejected)
- **Rust**: 10x faster but 5x dev time, overkill for 1h polling
- **JavaScript**: Weaker data analysis, no pandas equivalent
- **Go**: Good for performance, but limited quant libraries

---

## Project Structure

### Directory Layout

```
trading_bot/
│
├── config/                          # Configuration files
│   ├── assets.yaml                  # Asset/strategy definitions
│   └── discord.yaml                 # Discord webhook config
│
├── src/                             # Source code
│   ├── __init__.py
│   │
│   ├── data/                        # Data fetching layer
│   │   ├── __init__.py
│   │   └── bybit_fetcher.py        # Bybit API wrapper
│   │
│   ├── indicators/                  # Indicator library
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract indicator
│   │   └── bollinger_bands.py      # BB implementation
│   │
│   ├── strategies/                  # Trading strategies
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract strategy
│   │   └── bb_trendline.py         # BB trendline strategy
│   │
│   ├── notifiers/                   # Notification system
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract notifier
│   │   └── discord_notifier.py     # Discord implementation
│   │
│   └── scheduler.py                 # Main orchestrator
│
├── logs/                            # Log directory
│   └── signals.csv                  # Signal history (auto-created)
│
├── main.py                          # Application entry point
├── requirements.txt                 # Python dependencies
└── README.md                        # User documentation

Total files: 18 (14 Python + 2 config + 2 docs)
```

### File Dependencies Graph

```
main.py
  └── scheduler.py
        ├── data/bybit_fetcher.py
        │     └── notifiers/discord_notifier.py (for error notifications)
        ├── indicators/bollinger_bands.py
        │     └── indicators/base.py
        ├── strategies/bb_trendline.py
        │     └── strategies/base.py
        └── notifiers/discord_notifier.py
              └── notifiers/base.py
```

---

## Detailed Implementation

### Phase 1: Base Classes

#### File: `src/indicators/base.py`

```python
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
```

**Design Notes:**
- ABC enforces implementation of calculate()
- DataFrame in/out pattern allows chaining indicators
- Preserves original data for multi-indicator strategies

---

#### File: `src/strategies/base.py`

```python
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
                'timestamp': datetime,    # Signal generation time
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
                'timestamp': datetime(2024, 12, 2, 14, 0),
                'metadata': {'slope': -76.5, 'distance': 76.5}
            }
        """
        pass
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}()"
```

**Design Notes:**
- Optional return allows "no signal" state
- Dict structure ensures all needed data for logging
- Metadata field allows strategy-specific extras
- Timestamp included for accurate logging

---

#### File: `src/notifiers/base.py`

```python
"""
Abstract base class for all notification systems.
Ensures consistent notification interface.
"""
from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    """
    Base class for all notification implementations.
    
    All notifiers must implement send() which:
    - Accepts a message string
    - Sends via appropriate channel (Discord, Telegram, etc.)
    - Returns success/failure boolean
    """
    
    @abstractmethod
    def send(self, message: str) -> bool:
        """
        Send notification message.
        
        Args:
            message: Formatted message string to send
            
        Returns:
            True if sent successfully, False otherwise
            
        Implementation should:
        - Handle connection errors gracefully
        - Log failures
        - Not raise exceptions (return False instead)
        """
        pass
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}()"
```

**Design Notes:**
- Boolean return allows caller to handle failures
- No exceptions = more resilient
- Single string parameter = notifier handles formatting

---

### Phase 2: Data Fetching

#### File: `src/data/bybit_fetcher.py`

```python
"""
Bybit exchange data fetcher with retry logic.
Handles OHLCV data retrieval for derivatives (perpetual futures).
"""
import ccxt
import pandas as pd
import time
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BybitFetcher:
    """
    Fetches OHLCV data from Bybit derivatives market.
    
    Features:
    - 3-retry logic with exponential backoff
    - Notifies on complete failure
    - Returns pandas DataFrame
    - Handles Bybit-specific symbol format
    """
    
    def __init__(self, notifier=None):
        """
        Initialize Bybit fetcher.
        
        Args:
            notifier: Optional BaseNotifier instance for error notifications
        """
        self.exchange = ccxt.bybit({
            'enableRateLimit': True,  # Respect Bybit rate limits
            'options': {
                'defaultType': 'linear'  # Perpetual futures (USDT-margined)
            }
        })
        self.notifier = notifier
        self.max_retries = 3
        self.base_retry_delay = 5  # seconds
    
    def get_ohlcv(
        self, 
        symbol: str, 
        timeframe: str = '1h', 
        limit: int = 100
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data with retry logic.
        
        Args:
            symbol: Bybit symbol format 'BTCUSDT' (perpetual futures)
            timeframe: Candle interval ('1m', '5m', '15m', '1h', '4h', '1d')
            limit: Number of candles to fetch (default 100)
            
        Returns:
            DataFrame with columns [timestamp, open, high, low, close, volume]
            Returns None if all retries fail
            
        Example:
            df = fetcher.get_ohlcv('BTCUSDT', '1h', 50)
            # Returns last 50 hourly candles
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"Fetching {symbol} {timeframe} data (attempt {attempt}/{self.max_retries})"
                )
                
                # Fetch OHLCV from Bybit
                ohlcv = self.exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=limit
                )
                
                if not ohlcv:
                    logger.warning(f"Empty data returned for {symbol}")
                    continue
                
                # Convert to DataFrame
                df = pd.DataFrame(
                    ohlcv,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                
                # Convert timestamp to datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                # Sort by timestamp (oldest first)
                df = df.sort_values('timestamp').reset_index(drop=True)
                
                logger.info(
                    f"Successfully fetched {len(df)} candles for {symbol} "
                    f"(latest: {df['timestamp'].iloc[-1]})"
                )
                
                return df
                
            except ccxt.NetworkError as e:
                logger.error(f"Network error on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    delay = self.base_retry_delay * (2 ** (attempt - 1))  # Exponential backoff
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                    
            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    delay = self.base_retry_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                    
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    delay = self.base_retry_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
        
        # All retries failed - notify and return None
        error_msg = (
            f"⚠️ BYBIT API FAILURE ⚠️\n"
            f"Symbol: {symbol}\n"
            f"Failed after {self.max_retries} attempts\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.error(error_msg)
        
        if self.notifier:
            self.notifier.send(error_msg)
        
        return None
    
    def test_connection(self) -> bool:
        """
        Test Bybit connection by fetching market info.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.exchange.load_markets()
            logger.info("Bybit connection test successful")
            return True
        except Exception as e:
            logger.error(f"Bybit connection test failed: {e}")
            return False
```

**Design Notes:**
- Exponential backoff: 5s, 10s, 20s delays
- Handles all ccxt exception types
- Notifier integration for critical failures
- Test method for initial validation
- Symbol format: 'BTCUSDT' (Bybit perpetual futures)

---

### Phase 3: Indicators

#### File: `src/indicators/bollinger_bands.py`

```python
"""
Bollinger Bands indicator implementation.
Calculates upper/lower bands based on SMA and standard deviation.
"""
import pandas as pd
import numpy as np
from .base import BaseIndicator


class BollingerBands(BaseIndicator):
    """
    Bollinger Bands technical indicator.
    
    Components:
    - Middle Band: Simple Moving Average (SMA)
    - Upper Band: SMA + (std_dev * standard deviation)
    - Lower Band: SMA - (std_dev * standard deviation)
    
    Usage:
        bb = BollingerBands(period=20, std_dev=2.0)
        df = bb.calculate(df)
        # Now df has: bb_middle, bb_upper, bb_lower columns
    """
    
    def __init__(self, period: int = 20, std_dev: float = 2.0):
        """
        Initialize Bollinger Bands calculator.
        
        Args:
            period: Number of periods for SMA calculation (default 20)
            std_dev: Standard deviation multiplier (default 2.0)
        """
        self.period = period
        self.std_dev = std_dev
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Bollinger Bands and add to DataFrame.
        
        Args:
            df: DataFrame with 'close' column
            
        Returns:
            DataFrame with added columns:
            - bb_middle: SMA of close prices
            - bb_upper: Upper band (SMA + std_dev * std)
            - bb_lower: Lower band (SMA - std_dev * std)
            
        Note:
            First (period-1) rows will have NaN for BB values
        """
        # Validate input
        if 'close' not in df.columns:
            raise ValueError("DataFrame must have 'close' column")
        
        if len(df) < self.period:
            raise ValueError(
                f"Not enough data: need at least {self.period} rows, got {len(df)}"
            )
        
        # Calculate middle band (SMA)
        df['bb_middle'] = df['close'].rolling(window=self.period).mean()
        
        # Calculate rolling standard deviation
        rolling_std = df['close'].rolling(window=self.period).std()
        
        # Calculate upper and lower bands
        df['bb_upper'] = df['bb_middle'] + (self.std_dev * rolling_std)
        df['bb_lower'] = df['bb_middle'] - (self.std_dev * rolling_std)
        
        return df
    
    def get_current_bands(self, df: pd.DataFrame) -> dict:
        """
        Get current (latest) Bollinger Band values.
        
        Args:
            df: DataFrame with calculated BB columns
            
        Returns:
            Dict with current band values:
            {
                'upper': float,
                'middle': float,
                'lower': float,
                'timestamp': datetime
            }
        """
        if df.empty:
            raise ValueError("DataFrame is empty")
        
        latest = df.iloc[-1]
        
        return {
            'upper': float(latest['bb_upper']),
            'middle': float(latest['bb_middle']),
            'lower': float(latest['bb_lower']),
            'timestamp': latest['timestamp']
        }
    
    def __repr__(self) -> str:
        return f"BollingerBands(period={self.period}, std_dev={self.std_dev})"
```

**Design Notes:**
- Rolling calculations using pandas for performance
- NaN handling for initial rows (expected behavior)
- Helper method for current values
- Type safety with float conversions

---

### Phase 4: Strategy Implementation

#### File: `src/strategies/bb_trendline.py`

```python
"""
Bollinger Band Trendline Breakout Strategy.

Strategy Logic:
- Calculate trendline from BB values at t-2 and t-1
- Extrapolate to current time t
- Generate BUY signal if price breaks below lower trendline
- Generate SELL signal if price breaks above upper trendline
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
    - BUY: Close price crosses below extrapolated lower BB trendline
    - SELL: Close price crosses above extrapolated upper BB trendline
    
    Trendline Calculation:
    - Lower: slope = (BB_lower[t-1] - BB_lower[t-2]) / 1
    - Threshold_lower = BB_lower[t-1] + slope
    - Similar for upper band
    
    Example:
        If BB_lower at t-2 = 45000, t-1 = 44900 (declining)
        slope = -100
        threshold = 44900 + (-100) = 44800
        If current price = 44750 < 44800 → BUY signal
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
        required_cols = ['close', 'bb_upper', 'bb_lower', 'bb_middle', 'timestamp']
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
        if pd.isna([t_minus_2['bb_lower'], t_minus_1['bb_lower'], 
                    t_minus_2['bb_upper'], t_minus_1['bb_upper']]).any():
            logger.warning("NaN values in Bollinger Bands, skipping signal")
            return None
        
        # === LOWER BAND TRENDLINE (BUY SIGNAL) ===
        lower_slope = float(t_minus_1['bb_lower'] - t_minus_2['bb_lower'])
        lower_threshold = float(t_minus_1['bb_lower'] + lower_slope)
        
        current_price = float(t_current['close'])
        
        # Check for BUY signal (price breaks below lower trendline)
        if current_price < lower_threshold:
            distance = lower_threshold - current_price
            bb_width = float(t_current['bb_upper'] - t_current['bb_lower'])
            
            signal_data = {
                'signal': 'BUY',
                'price': current_price,
                'threshold': lower_threshold,
                'bb_upper': float(t_current['bb_upper']),
                'bb_lower': float(t_current['bb_lower']),
                'bb_middle': float(t_current['bb_middle']),
                'timestamp': t_current['timestamp'],
                'metadata': {
                    'slope': lower_slope,
                    'distance_to_threshold': distance,
                    'bb_width': bb_width,
                    'penetration_pct': (distance / lower_threshold) * 100
                }
            }
            
            logger.info(
                f"BUY signal generated: price={current_price:.2f}, "
                f"threshold={lower_threshold:.2f}, distance={distance:.2f}"
            )
            
            return signal_data
        
        # === UPPER BAND TRENDLINE (SELL SIGNAL) ===
        upper_slope = float(t_minus_1['bb_upper'] - t_minus_2['bb_upper'])
        upper_threshold = float(t_minus_1['bb_upper'] + upper_slope)
        
        # Check for SELL signal (price breaks above upper trendline)
        if current_price > upper_threshold:
            distance = current_price - upper_threshold
            bb_width = float(t_current['bb_upper'] - t_current['bb_lower'])
            
            signal_data = {
                'signal': 'SELL',
                'price': current_price,
                'threshold': upper_threshold,
                'bb_upper': float(t_current['bb_upper']),
                'bb_lower': float(t_current['bb_lower']),
                'bb_middle': float(t_current['bb_middle']),
                'timestamp': t_current['timestamp'],
                'metadata': {
                    'slope': upper_slope,
                    'distance_to_threshold': distance,
                    'bb_width': bb_width,
                    'penetration_pct': (distance / upper_threshold) * 100
                }
            }
            
            logger.info(
                f"SELL signal generated: price={current_price:.2f}, "
                f"threshold={upper_threshold:.2f}, distance={distance:.2f}"
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
```

**Design Notes:**
- Explicit slope calculation for transparency
- Distance and penetration % in metadata (useful for backtesting)
- BB width tracked (volatility context)
- Robust NaN checking
- Detailed logging for debugging

---

### Phase 5: Notification System

#### File: `src/notifiers/discord_notifier.py`

```python
"""
Discord webhook notification implementation.
Sends formatted trading signals to Discord channel.
"""
import requests
import logging
from typing import Dict, Any
from datetime import datetime
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class DiscordNotifier(BaseNotifier):
    """
    Discord webhook notifier for trading signals.
    
    Features:
    - Rich formatted messages
    - Emoji indicators for signal type
    - Color-coded embeds (optional)
    - Error handling for webhook failures
    
    Setup:
    1. Create Discord webhook in channel settings
    2. Copy webhook URL
    3. Add to discord.yaml config
    """
    
    def __init__(self, webhook_url: str):
        """
        Initialize Discord notifier.
        
        Args:
            webhook_url: Discord webhook URL from channel settings
        """
        if not webhook_url or webhook_url == "PLACEHOLDER_ADD_YOUR_WEBHOOK":
            logger.warning("Discord webhook not configured!")
        
        self.webhook_url = webhook_url
        self.timeout = 10  # seconds
    
    def send(self, message: str) -> bool:
        """
        Send message to Discord via webhook.
        
        Args:
            message: Plain text message to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            payload = {
                'content': message
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 204:
                logger.info("Discord notification sent successfully")
                return True
            else:
                logger.error(
                    f"Discord webhook failed: {response.status_code} - {response.text}"
                )
                return False
                
        except requests.Timeout:
            logger.error("Discord webhook timeout")
            return False
            
        except requests.RequestException as e:
            logger.error(f"Discord webhook error: {e}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error sending Discord notification: {e}")
            return False
    
    def send_signal(self, symbol: str, signal_data: Dict[str, Any]) -> bool:
        """
        Send formatted trading signal to Discord.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            signal_data: Signal dict from strategy
            
        Returns:
            True if sent successfully, False otherwise
        """
        signal_type = signal_data['signal']
        emoji = "🟢" if signal_type == "BUY" else "🔴"
        
        # Format message
        message = self._format_signal_message(symbol, signal_data, emoji)
        
        return self.send(message)
    
    def _format_signal_message(
        self, 
        symbol: str, 
        signal_data: Dict[str, Any], 
        emoji: str
    ) -> str:
        """
        Format trading signal into readable Discord message.
        
        Args:
            symbol: Trading pair
            signal_data: Signal dict
            emoji: Signal emoji indicator
            
        Returns:
            Formatted message string
        """
        # Clean symbol for display (remove :USDT suffix)
        display_symbol = symbol.replace(':USDT', '')
        
        # Extract data
        signal_type = signal_data['signal']
        price = signal_data['price']
        threshold = signal_data['threshold']
        bb_upper = signal_data['bb_upper']
        bb_lower = signal_data['bb_lower']
        bb_middle = signal_data['bb_middle']
        timestamp = signal_data['timestamp']
        
        # Extract metadata
        metadata = signal_data.get('metadata', {})
        slope = metadata.get('slope', 0)
        distance = metadata.get('distance_to_threshold', 0)
        bb_width = metadata.get('bb_width', 0)
        
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
• Width: ${bb_width:,.2f}

**Trendline:**
• Slope: {slope:+.2f}

**Time:** {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        
        return message.strip()
    
    def send_error(self, error_message: str) -> bool:
        """
        Send error notification to Discord.
        
        Args:
            error_message: Error description
            
        Returns:
            True if sent successfully, False otherwise
        """
        formatted = f"⚠️ **ERROR** ⚠️\n\n{error_message}"
        return self.send(formatted)
    
    def test(self) -> bool:
        """
        Test Discord webhook by sending test message.
        
        Returns:
            True if test successful, False otherwise
        """
        test_message = "✅ Discord webhook test successful - Bot is online!"
        return self.send(test_message)
    
    def __repr__(self) -> str:
        return f"DiscordNotifier(webhook_configured={bool(self.webhook_url)})"
```

**Design Notes:**
- Separate methods for signals vs errors
- Rich formatting with emojis
- Symbol cleaning for readability
- Test method for initial validation
- Percentage calculations for context

---

### Phase 6: Scheduler & Orchestration

#### File: `src/scheduler.py`

```python
"""
Main orchestrator for trading bot.
Schedules periodic strategy execution and coordinates all components.
"""
import schedule
import time
import yaml
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from src.data.bybit_fetcher import BybitFetcher
from src.indicators.bollinger_bands import BollingerBands
from src.strategies.bb_trendline import BBTrendlineStrategy
from src.notifiers.discord_notifier import DiscordNotifier

logger = logging.getLogger(__name__)


class TradingScheduler:
    """
    Main orchestrator for trading signal bot.
    
    Responsibilities:
    - Load configuration files
    - Initialize components (fetcher, notifier)
    - Schedule periodic strategy execution
    - Coordinate: Fetch → Calculate → Signal → Notify → Log
    - Handle errors and edge cases
    
    Usage:
        scheduler = TradingScheduler('config/assets.yaml', 'config/discord.yaml')
        scheduler.start()  # Runs forever
    """
    
    def __init__(self, config_path: str, discord_config_path: str):
        """
        Initialize trading scheduler.
        
        Args:
            config_path: Path to assets.yaml
            discord_config_path: Path to discord.yaml
        """
        logger.info("Initializing TradingScheduler...")
        
        # Load configurations
        self.assets_config = self._load_yaml(config_path)
        self.discord_config = self._load_yaml(discord_config_path)
        
        # Initialize notifier
        webhook_url = self.discord_config.get('webhook_url', '')
        self.notifier = DiscordNotifier(webhook_url)
        
        # Initialize data fetcher with notifier for error alerts
        self.fetcher = BybitFetcher(notifier=self.notifier)
        
        # Setup CSV logging
        self.signals_csv_path = Path('logs/signals.csv')
        self._setup_signals_csv()
        
        # Strategy/Indicator factory mapping
        self.strategy_map = {
            'BBTrendlineStrategy': BBTrendlineStrategy
        }
        
        self.indicator_map = {
            'BollingerBands': BollingerBands
        }
        
        logger.info("TradingScheduler initialized successfully")
    
    def _load_yaml(self, path: str) -> Dict:
        """Load YAML configuration file."""
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded config from {path}")
            return config
        except FileNotFoundError:
            logger.error(f"Config file not found: {path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file {path}: {e}")
            raise
    
    def _setup_signals_csv(self):
        """Create signals.csv with headers if it doesn't exist."""
        self.signals_csv_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not self.signals_csv_path.exists():
            headers = [
                'timestamp',
                'symbol',
                'signal',
                'price',
                'threshold',
                'bb_upper',
                'bb_lower',
                'bb_middle',
                'slope',
                'distance',
                'bb_width'
            ]
            
            with open(self.signals_csv_path, 'w') as f:
                f.write(','.join(headers) + '\n')
            
            logger.info(f"Created signals CSV at {self.signals_csv_path}")
    
    def _log_signal_to_csv(self, symbol: str, signal_data: Dict[str, Any]):
        """
        Append signal to CSV file.
        
        Args:
            symbol: Trading pair
            signal_data: Signal dict from strategy
        """
        try:
            metadata = signal_data.get('metadata', {})
            
            row = [
                signal_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                symbol,
                signal_data['signal'],
                f"{signal_data['price']:.2f}",
                f"{signal_data['threshold']:.2f}",
                f"{signal_data['bb_upper']:.2f}",
                f"{signal_data['bb_lower']:.2f}",
                f"{signal_data['bb_middle']:.2f}",
                f"{metadata.get('slope', 0):.2f}",
                f"{metadata.get('distance_to_threshold', 0):.2f}",
                f"{metadata.get('bb_width', 0):.2f}"
            ]
            
            with open(self.signals_csv_path, 'a') as f:
                f.write(','.join(row) + '\n')
            
            logger.info(f"Signal logged to CSV: {symbol} {signal_data['signal']}")
            
        except Exception as e:
            logger.error(f"Error logging signal to CSV: {e}")
    
    def run_strategy(self, asset_config: Dict[str, Any]):
        """
        Execute strategy for a single asset.
        
        Args:
            asset_config: Asset configuration dict from assets.yaml
            
        Process:
        1. Fetch OHLCV data from Bybit
        2. Calculate indicators (Bollinger Bands)
        3. Run strategy (BBTrendlineStrategy)
        4. If signal: notify + log to CSV
        5. Handle errors gracefully
        """
        symbol = asset_config['symbol']
        timeframe = asset_config['timeframe']
        strategy_name = asset_config['strategy']
        indicator_name = asset_config['indicator']
        indicator_params = asset_config.get('indicator_params', {})
        
        logger.info(f"Running strategy for {symbol}...")
        
        try:
            # Step 1: Fetch data
            df = self.fetcher.get_ohlcv(symbol, timeframe, limit=100)
            
            if df is None or df.empty:
                logger.warning(f"No data fetched for {symbol}, skipping")
                return
            
            # Step 2: Initialize and calculate indicator
            indicator_class = self.indicator_map.get(indicator_name)
            if not indicator_class:
                logger.error(f"Unknown indicator: {indicator_name}")
                return
            
            indicator = indicator_class(**indicator_params)
            df = indicator.calculate(df)
            
            logger.info(f"Calculated {indicator_name} for {symbol}")
            
            # Step 3: Initialize and run strategy
            strategy_class = self.strategy_map.get(strategy_name)
            if not strategy_class:
                logger.error(f"Unknown strategy: {strategy_name}")
                return
            
            strategy = strategy_class()
            signal_data = strategy.generate_signal(df)
            
            # Step 4: Process signal if generated
            if signal_data:
                logger.info(
                    f"Signal generated for {symbol}: "
                    f"{signal_data['signal']} at {signal_data['price']:.2f}"
                )
                
                # Send Discord notification
                success = self.notifier.send_signal(symbol, signal_data)
                if success:
                    logger.info(f"Discord notification sent for {symbol}")
                else:
                    logger.warning(f"Failed to send Discord notification for {symbol}")
                
                # Log to CSV
                self._log_signal_to_csv(symbol, signal_data)
                
            else:
                logger.info(f"No signal for {symbol}")
                
        except Exception as e:
            logger.error(f"Error running strategy for {symbol}: {e}", exc_info=True)
            error_msg = f"Error processing {symbol}: {str(e)}"
            self.notifier.send_error(error_msg)
    
    def run_all_assets(self):
        """
        Execute strategies for all configured assets.
        Called by scheduler every hour.
        """
        logger.info("=" * 60)
        logger.info(f"Running strategies at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
        
        assets = self.assets_config.get('assets', [])
        
        if not assets:
            logger.warning("No assets configured in assets.yaml")
            return
        
        for asset_config in assets:
            self.run_strategy(asset_config)
            time.sleep(1)  # Small delay between assets to avoid rate limits
        
        logger.info("Completed strategy run for all assets")
        logger.info("=" * 60)
    
    def test_components(self) -> bool:
        """
        Test all components before starting scheduler.
        
        Tests:
        - Bybit connection
        - Discord webhook
        - Config loading
        
        Returns:
            True if all tests pass, False otherwise
        """
        logger.info("Testing components...")
        
        all_pass = True
        
        # Test Bybit connection
        logger.info("Testing Bybit connection...")
        if self.fetcher.test_connection():
            logger.info("✓ Bybit connection OK")
        else:
            logger.error("✗ Bybit connection FAILED")
            all_pass = False
        
        # Test Discord webhook
        logger.info("Testing Discord webhook...")
        if self.notifier.test():
            logger.info("✓ Discord webhook OK")
        else:
            logger.error("✗ Discord webhook FAILED")
            all_pass = False
        
        # Verify assets config
        assets = self.assets_config.get('assets', [])
        if assets:
            logger.info(f"✓ Found {len(assets)} asset(s) configured")
        else:
            logger.error("✗ No assets configured")
            all_pass = False
        
        return all_pass
    
    def start(self):
        """
        Start the scheduler with 1h interval.
        Runs indefinitely until interrupted.
        """
        logger.info("Starting TradingScheduler...")
        
        # Test components first
        if not self.test_components():
            logger.error("Component tests failed! Fix issues before starting.")
            return
        
        # Schedule hourly runs
        schedule.every(1).hour.do(self.run_all_assets)
        
        # Run immediately on start (optional)
        logger.info("Running initial strategy execution...")
        self.run_all_assets()
        
        # Start scheduler loop
        logger.info("Scheduler started. Running every 1 hour. Press Ctrl+C to stop.")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            self.notifier.send_error(f"Scheduler crashed: {str(e)}")
```

**Design Notes:**
- Factory pattern for dynamic strategy/indicator instantiation
- Component testing before start
- Immediate execution on start (optional, useful for testing)
- CSV logging with error handling
- Rate limit protection (1s delay between assets)
- Comprehensive error logging

---

### Phase 7: Main Entry Point

#### File: `main.py`

```python
"""
Trading Signal Bot - Main Entry Point

Description:
    Monitors Bitcoin (and other assets) using Bollinger Band trendline strategy.
    Sends signals via Discord webhook when breakouts occur.
    
Usage:
    python main.py
    
Requirements:
    - Python 3.9+
    - Dependencies in requirements.txt
    - Discord webhook configured in config/discord.yaml
    - Assets configured in config/assets.yaml
"""
import logging
import sys
from pathlib import Path

from src.scheduler import TradingScheduler


def setup_logging():
    """
    Configure logging for the application.
    
    Logging Strategy:
    - Console: INFO level (general operations)
    - File (future): DEBUG level (detailed debugging)
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Reduce noise from external libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('ccxt').setLevel(logging.WARNING)


def validate_config_files():
    """
    Check if required configuration files exist.
    
    Raises:
        FileNotFoundError: If required config files are missing
    """
    required_files = [
        'config/assets.yaml',
        'config/discord.yaml'
    ]
    
    for file_path in required_files:
        if not Path(file_path).exists():
            raise FileNotFoundError(
                f"Required config file not found: {file_path}\n"
                f"Please create it before running the bot."
            )


def main():
    """Main entry point for trading signal bot."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 70)
    logger.info("TRADING SIGNAL BOT - Starting Up")
    logger.info("=" * 70)
    
    try:
        # Validate config files exist
        validate_config_files()
        
        # Initialize scheduler
        scheduler = TradingScheduler(
            config_path='config/assets.yaml',
            discord_config_path='config/discord.yaml'
        )
        
        # Start scheduler (runs forever)
        scheduler.start()
        
    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        logger.info("=" * 70)
        logger.info("TRADING SIGNAL BOT - Shut Down")
        logger.info("=" * 70)
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Design Notes:**
- Clear startup/shutdown messages
- Config validation before start
- External library noise reduction
- Exit codes for automation
- Graceful KeyboardInterrupt handling

---

## Configuration Files

### File: `config/assets.yaml`

```yaml
# Trading Assets Configuration
# Define which assets to monitor and which strategies to apply

assets:
  # Bitcoin - Bollinger Band Trendline Strategy
  - symbol: BTCUSDT          # Bybit perpetual futures format
    timeframe: 1h                  # Candle interval
    strategy: BBTrendlineStrategy  # Strategy class name
    indicator: BollingerBands      # Indicator class name
    indicator_params:              # Indicator configuration
      period: 20                   # BB period (SMA length)
      std_dev: 2.0                 # Standard deviation multiplier

  # Ethereum - Example (uncomment to enable)
  # - symbol: ETHUSDT
  #   timeframe: 1h
  #   strategy: BBTrendlineStrategy
  #   indicator: BollingerBands
  #   indicator_params:
  #     period: 20
  #     std_dev: 2.0

  # S&P 500 - Example (uncomment to enable)
  # Note: Check Bybit for correct SPX futures symbol
  # - symbol: SPXUSDT
  #   timeframe: 1h
  #   strategy: BBTrendlineStrategy
  #   indicator: BollingerBands
  #   indicator_params:
  #     period: 20
  #     std_dev: 2.5              # Wider bands for indices

# Notes:
# - Symbol format: {BASE}{QUOTE} for Bybit perpetuals (e.g., BTCUSDT)
# - Timeframe options: 1m, 5m, 15m, 1h, 4h, 1d (1h only currently)
# - Each asset runs independently
# - Easy to add new assets: just add new entry
# - Easy to test different parameters: adjust indicator_params
```

### File: `config/discord.yaml`

```yaml
# Discord Webhook Configuration
# Get webhook URL from Discord:
# 1. Go to channel settings → Integrations
# 2. Create webhook
# 3. Copy webhook URL
# 4. Paste below

webhook_url: "PLACEHOLDER_ADD_YOUR_WEBHOOK"

# Example:
# webhook_url: "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"

# Security:
# - Keep this file private (in .gitignore)
# - Don't commit webhook URL to version control
# - Rotate webhook if exposed
```

### File: `requirements.txt`

```
# Trading Bot Dependencies

# Exchange API (Bybit support)
ccxt>=4.0.0

# Data manipulation
pandas>=2.0.0
numpy>=1.24.0

# Configuration
pyyaml>=6.0

# HTTP requests (Discord webhook)
requests>=2.31.0

# Job scheduling
schedule>=1.2.0

# Date handling (pandas dependency)
python-dateutil>=2.8.0
```

---

## Error Handling & Logging

### Logging Strategy

**Console Output (INFO level):**
```
2024-12-02 14:00:00 - scheduler - INFO - Running strategies at 2024-12-02 14:00:00
2024-12-02 14:00:01 - bybit_fetcher - INFO - Fetching BTCUSDT 1h data
2024-12-02 14:00:02 - scheduler - INFO - Calculated BollingerBands for BTCUSDT
2024-12-02 14:00:03 - bb_trendline - INFO - BUY signal generated: price=45123.50
2024-12-02 14:00:04 - discord_notifier - INFO - Discord notification sent
2024-12-02 14:00:05 - scheduler - INFO - Signal logged to CSV
```

**CSV Output (`logs/signals.csv`):**
```csv
timestamp,symbol,signal,price,threshold,bb_upper,bb_lower,bb_middle,slope,distance,bb_width
2024-12-02 14:00:00,BTCUSDT,BUY,45123.50,45200.00,46000.00,44500.00,45250.00,-76.50,76.50,1500.00
```

### Error Scenarios & Handling

**1. Bybit API Failure**
```
Action:
- Retry 3 times with exponential backoff (5s, 10s, 20s)
- On final failure: Send Discord error notification
- Log error to console
- Skip current run, continue next hour

Discord Message:
⚠️ BYBIT API FAILURE ⚠️
Symbol: BTCUSDT
Failed after 3 attempts
Time: 2024-12-02 14:00:00
```

**2. Discord Webhook Failure**
```
Action:
- Log error to console
- Continue execution (signal still logged to CSV)
- No retry (not critical for system operation)

Console Log:
ERROR - Discord webhook failed: 404 - Webhook not found
```

**3. Insufficient Data**
```
Action:
- Log warning
- Skip current asset
- Continue with next asset

Console Log:
WARNING - Need at least 3 rows for trendline calculation
```

**4. Configuration Error**
```
Action:
- Fail fast on startup
- Display helpful error message
- Exit with code 1

Console Log:
ERROR - Config file not found: config/assets.yaml
Please create it before running the bot.
```

### Error Recovery Matrix

| Error Type | Retry? | Notify Discord? | Continue? | Exit? |
|------------|--------|-----------------|-----------|-------|
| Network error | Yes (3x) | After retries | Yes | No |
| API rate limit | Yes (3x) | After retries | Yes | No |
| Invalid config | No | No | No | Yes |
| Webhook fail | No | No (can't notify!) | Yes | No |
| Insufficient data | No | No | Yes | No |
| Strategy exception | No | Yes | Yes | No |
| Fatal exception | No | Yes | No | Yes |

---

## Testing Plan

### Pre-Deployment Tests

**1. Dependency Installation**
```bash
cd trading_bot
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. Configuration Setup**
```bash
# Create Discord webhook
# Add to config/discord.yaml

# Verify assets.yaml syntax
python -c "import yaml; yaml.safe_load(open('config/assets.yaml'))"
```

**3. Component Testing**
```bash
# Test imports
python -c "from src.scheduler import TradingScheduler; print('OK')"

# Test Bybit connection
python -c "from src.data.bybit_fetcher import BybitFetcher; f = BybitFetcher(); f.test_connection()"

# Test Discord webhook
python -c "from src.notifiers.discord_notifier import DiscordNotifier; import yaml; config = yaml.safe_load(open('config/discord.yaml')); n = DiscordNotifier(config['webhook_url']); n.test()"
```

**4. Dry Run**
```bash
# Run bot for one cycle (will exit after first hour)
python main.py

# Check outputs:
# - Console logs show execution
# - Discord receives test message
# - logs/signals.csv created (may be empty if no signals)
```

### Post-Deployment Monitoring

**Daily Checks:**
- [ ] Bot process still running
- [ ] logs/signals.csv being updated
- [ ] Discord notifications working
- [ ] No error messages in console

**Weekly Checks:**
- [ ] Review signal frequency (too many = bad strategy)
- [ ] Verify Bybit API connectivity
- [ ] Check disk space for logs
- [ ] Update dependencies if needed

### Test Checklist

```
[ ] Dependencies installed successfully
[ ] Config files created and valid
[ ] Bybit connection test passes
[ ] Discord webhook test passes
[ ] Bot starts without errors
[ ] Initial strategy run completes
[ ] CSV logging works
[ ] Discord notifications received
[ ] Bot handles Ctrl+C gracefully
[ ] Can add new asset via YAML (test with ETH)
[ ] Logs readable and informative
```

---

## Deployment Instructions

### Local Development Setup

```bash
# 1. Clone/create project directory
mkdir trading_bot
cd trading_bot

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup configuration
# Edit config/assets.yaml (set BTC parameters)
# Edit config/discord.yaml (add webhook URL)

# 5. Test components
python -c "from src.scheduler import TradingScheduler; s = TradingScheduler('config/assets.yaml', 'config/discord.yaml'); s.test_components()"

# 6. Run bot
python main.py
```

### Production Deployment (VPS/Cloud)

**Option 1: Screen Session (Simple)**
```bash
# Start screen session
screen -S trading_bot

# Run bot
python main.py

# Detach: Ctrl+A then D
# Reattach: screen -r trading_bot
```

**Option 2: Systemd Service (Recommended)**

Create `/etc/systemd/system/trading-bot.service`:
```ini
[Unit]
Description=Trading Signal Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/your_user/trading_bot
Environment="PATH=/home/your_user/trading_bot/venv/bin"
ExecStart=/home/your_user/trading_bot/venv/bin/python main.py
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl status trading-bot
```

**Option 3: Docker (Advanced)**
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

Build and run:
```bash
docker build -t trading-bot .
docker run -d --name trading-bot --restart unless-stopped trading-bot
```

### Environment Setup Checklist

```
[ ] Python 3.9+ installed
[ ] Virtual environment created
[ ] Dependencies installed
[ ] Config files configured
[ ] Discord webhook tested
[ ] Bybit API accessible
[ ] Logs directory writable
[ ] Timezone set correctly (UTC recommended)
[ ] Firewall allows outbound HTTPS
[ ] Process manager configured (systemd/screen/docker)
```

---

## Future Extensibility

### Adding New Assets (Ethereum Example)

**1. Edit `config/assets.yaml`:**
```yaml
assets:
  - symbol: BTCUSDT
    timeframe: 1h
    strategy: BBTrendlineStrategy
    indicator: BollingerBands
    indicator_params:
      period: 20
      std_dev: 2.0
  
  # Add Ethereum
  - symbol: ETHUSDT
    timeframe: 1h
    strategy: BBTrendlineStrategy
    indicator: BollingerBands
    indicator_params:
      period: 20
      std_dev: 2.0
```

**2. Restart bot**
```bash
# No code changes needed!
python main.py
```

### Adding New Indicator (RSI Example)

**1. Create `src/indicators/rsi.py`:**
```python
import pandas as pd
from .base import BaseIndicator

class RSI(BaseIndicator):
    def __init__(self, period: int = 14):
        self.period = period
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        return df
```

**2. Register in `scheduler.py`:**
```python
self.indicator_map = {
    'BollingerBands': BollingerBands,
    'RSI': RSI  # Add this line
}
```

**3. Use in `assets.yaml`:**
```yaml
- symbol: BTCUSDT
  timeframe: 1h
  strategy: RSICrossStrategy  # New strategy needed too
  indicator: RSI
  indicator_params:
    period: 14
```

### Adding New Strategy (RSI Cross Example)

**1. Create `src/strategies/rsi_cross.py`:**
```python
import pandas as pd
from typing import Optional, Dict, Any
from .base import BaseStrategy

class RSICrossStrategy(BaseStrategy):
    def __init__(self, oversold: int = 30, overbought: int = 70):
        self.oversold = oversold
        self.overbought = overbought
    
    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if len(df) < 2:
            return None
        
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        # BUY: RSI crosses above oversold
        if previous['rsi'] < self.oversold and current['rsi'] >= self.oversold:
            return {
                'signal': 'BUY',
                'price': float(current['close']),
                'threshold': self.oversold,
                'timestamp': current['timestamp'],
                'metadata': {'rsi': float(current['rsi'])}
            }
        
        # SELL: RSI crosses below overbought
        if previous['rsi'] > self.overbought and current['rsi'] <= self.overbought:
            return {
                'signal': 'SELL',
                'price': float(current['close']),
                'threshold': self.overbought,
                'timestamp': current['timestamp'],
                'metadata': {'rsi': float(current['rsi'])}
            }
        
        return None
```

**2. Register in `scheduler.py`:**
```python
self.strategy_map = {
    'BBTrendlineStrategy': BBTrendlineStrategy,
    'RSICrossStrategy': RSICrossStrategy  # Add this line
}
```

### Adding New Notifier (Telegram Example)

**1. Create `src/notifiers/telegram_notifier.py`:**
```python
import requests
from .base import BaseNotifier
import logging

logger = logging.getLogger(__name__)

class TelegramNotifier(BaseNotifier):
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    def send(self, message: str) -> bool:
        try:
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            response = requests.post(self.api_url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False
```

**2. Update `scheduler.py` to support multiple notifiers:**
```python
# Initialize both notifiers
self.discord_notifier = DiscordNotifier(webhook_url)
self.telegram_notifier = TelegramNotifier(bot_token, chat_id)

# Send to both
self.discord_notifier.send_signal(symbol, signal_data)
self.telegram_notifier.send(formatted_message)
```

### Multi-Timeframe Support (Future Phase)

**Current Limitation:** All assets run on 1h interval

**Proposed Architecture:**
```python
class TradingScheduler:
    def start(self):
        # Group assets by timeframe
        timeframe_groups = self._group_by_timeframe()
        
        # Schedule each timeframe separately
        for timeframe, assets in timeframe_groups.items():
            if timeframe == '1h':
                schedule.every(1).hour.do(self.run_assets, assets=assets)
            elif timeframe == '15m':
                schedule.every(15).minutes.do(self.run_assets, assets=assets)
            elif timeframe == '4h':
                schedule.every(4).hours.do(self.run_assets, assets=assets)
        
        while True:
            schedule.run_pending()
            time.sleep(60)
```

**Benefits:**
- BTC on 1h, ETH on 15m, SP500 on 4h
- Optimal signal frequency per asset
- Shared data fetching for same timeframe

### Automated Trading (Future Phase)

**Architecture Addition:**
```python
# src/execution/bybit_executor.py
class BybitExecutor:
    def place_market_order(self, symbol, side, quantity):
        # Implement order execution
        pass
    
    def calculate_position_size(self, account_balance, risk_pct, stop_loss_distance):
        # Risk management
        pass

# Update scheduler.py
if signal_data and self.auto_trade_enabled:
    position_size = self.executor.calculate_position_size(...)
    self.executor.place_market_order(symbol, signal_data['signal'], position_size)
```

**Requirements:**
- Bybit API key with trading permissions
- Position tracking system
- Risk management rules
- TP/SL calculation logic
- Order status monitoring

---

## Implementation Timeline

### Phase 1: Foundation (Day 1)
- [ ] Create project structure
- [ ] Implement base classes
- [ ] Setup configuration files
- [ ] Create requirements.txt

### Phase 2: Core Components (Day 1-2)
- [ ] Implement BybitFetcher
- [ ] Implement BollingerBands
- [ ] Implement BBTrendlineStrategy
- [ ] Implement DiscordNotifier

### Phase 3: Orchestration (Day 2)
- [ ] Implement TradingScheduler
- [ ] Implement main.py
- [ ] Setup CSV logging
- [ ] Error handling

### Phase 4: Testing (Day 2-3)
- [ ] Component unit tests
- [ ] Integration testing
- [ ] Error scenario testing
- [ ] Production dry run

### Phase 5: Deployment (Day 3)
- [ ] Deploy to production environment
- [ ] Configure monitoring
- [ ] Document operations
- [ ] Setup alerts

**Total Estimated Time:** 2-3 days for complete implementation and testing

---

## Maintenance & Operations

### Daily Operations
- Monitor Discord for signals
- Check bot is running (systemctl status)
- Review console logs for errors

### Weekly Operations
- Review signals.csv for patterns
- Analyze signal frequency
- Check Bybit API health
- Update dependencies if needed

### Monthly Operations
- Rotate Discord webhook (security)
- Archive old signal logs
- Review strategy performance
- Plan parameter adjustments

### Troubleshooting Guide

**Bot Not Starting:**
```bash
# Check Python version
python --version  # Should be 3.9+

# Check dependencies
pip list | grep ccxt

# Check config files exist
ls -la config/

# Run with verbose logging
python main.py 2>&1 | tee bot.log
```

**No Signals Generated:**
```bash
# Check Bybit data is fetching
python -c "from src.data.bybit_fetcher import BybitFetcher; f = BybitFetcher(); print(f.get_ohlcv('BTCUSDT', '1h'))"

# Verify BB calculation
# (Check console logs for "Calculated BollingerBands")

# Review strategy parameters
# (20 period, 2 std_dev may be too wide/narrow)
```

**Discord Not Receiving Notifications:**
```bash
# Test webhook manually
curl -X POST -H "Content-Type: application/json" \
  -d '{"content":"Test"}' \
  YOUR_WEBHOOK_URL

# Check webhook in config
grep webhook_url config/discord.yaml

# Verify notifier test
python -c "from src.notifiers.discord_notifier import DiscordNotifier; import yaml; config = yaml.safe_load(open('config/discord.yaml')); n = DiscordNotifier(config['webhook_url']); n.test()"
```

---

## Security Considerations

### API Keys & Webhooks
- **Never commit** discord.yaml to version control
- Add to .gitignore: `config/discord.yaml`
- Rotate webhooks if exposed
- Use environment variables for production

### Bybit API (Future)
- Use API keys with **trading-only** permissions
- Never store keys in code
- Use environment variables or secrets manager
- Enable IP whitelist if possible

### Server Security
- Keep system packages updated
- Use firewall (only allow outbound HTTPS)
- Run bot as non-root user
- Enable fail2ban for SSH

### Code Security
- Review dependencies regularly
- Pin exact versions in requirements.txt
- Scan for vulnerabilities: `pip-audit`

---

## Support & Resources

### Official Documentation
- **CCXT**: https://docs.ccxt.com/
- **Bybit API**: https://bybit-exchange.github.io/docs/
- **Discord Webhooks**: https://discord.com/developers/docs/resources/webhook
- **Pandas**: https://pandas.pydata.org/docs/

### Community Resources
- CCXT GitHub Issues
- Bybit Trading API Telegram
- Python Discord servers

### Project Contacts
- GitHub Issues: [Your Repo]
- Discord Support: [Your Server]
- Email: [Your Email]

---

## Glossary

**Bollinger Bands (BB)**: Technical indicator with upper/lower bands around moving average

**OHLCV**: Open, High, Low, Close, Volume - standard candle data

**Trendline Extrapolation**: Calculating future value from past slope

**Bybit Perpetuals**: Futures contracts with no expiry date

**CCXT**: Cryptocurrency Exchange Trading Library (unified API)

**Webhook**: HTTP callback for real-time notifications

**SMA**: Simple Moving Average

**Standard Deviation**: Measure of price volatility

**Signal**: Trading recommendation (BUY/SELL)

**Timeframe**: Candle interval (1h, 15m, etc.)

---

## Appendix A: File Checklist

```
trading_bot/
├── config/
│   ├── assets.yaml           ✓ Create & configure
│   └── discord.yaml          ✓ Create & add webhook
├── src/
│   ├── __init__.py           ✓ Create (empty file)
│   ├── data/
│   │   ├── __init__.py       ✓ Create (empty file)
│   │   └── bybit_fetcher.py  ✓ Implement
│   ├── indicators/
│   │   ├── __init__.py       ✓ Create (empty file)
│   │   ├── base.py           ✓ Implement
│   │   └── bollinger_bands.py ✓ Implement
│   ├── strategies/
│   │   ├── __init__.py       ✓ Create (empty file)
│   │   ├── base.py           ✓ Implement
│   │   └── bb_trendline.py   ✓ Implement
│   ├── notifiers/
│   │   ├── __init__.py       ✓ Create (empty file)
│   │   ├── base.py           ✓ Implement
│   │   └── discord_notifier.py ✓ Implement
│   └── scheduler.py          ✓ Implement
├── logs/
│   └── signals.csv           ✓ Auto-created by bot
├── main.py                   ✓ Implement
├── requirements.txt          ✓ Create
└── README.md                 ✓ Create (optional)

Total: 18 files
```

---

## Appendix B: Quick Start Commands

```bash
# Initial setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
nano config/discord.yaml  # Add webhook
nano config/assets.yaml   # Verify BTC config

# Test
python -c "from src.scheduler import TradingScheduler; s = TradingScheduler('config/assets.yaml', 'config/discord.yaml'); s.test_components()"

# Run
python main.py

# Monitor
tail -f logs/signals.csv

# Stop
Ctrl+C
```

---

## Document Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-12-02 | Initial comprehensive implementation plan |

---

**END OF IMPLEMENTATION PLAN**

This document contains all information needed to build the trading signal bot from scratch. Hand this to your implementation agent and they should be able to execute without further questions.
