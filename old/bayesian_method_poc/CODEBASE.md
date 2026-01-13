# Bayesian Method POC - Codebase Analysis

## Current State Analysis

### 1. Bayesian Method POC Structure

```
bayesian_method_poc/
├── bayesian_trader.py          # Core model (BayesianBitcoinTrader, TradingStrategy)
├── run_bayesian_poc.py         # Main execution script
├── analyze_trades.py           # Post-trade analysis utility
├── download_orderbook.py       # Order book imbalance proxy generator
├── preprocess_new_data.py      # Data preprocessing
├── check_bybit_orderbook_api.py # API investigation
├── check_binance_orderbook.py   # Binance data check
├── README.md                    # Comprehensive documentation
├── POC_SUMMARY.md               # Executive summary
├── bayesian_bitcoin_trading_guide.md # Implementation guide
├── ETHUSDT_1min.csv             # Raw OHLCV data
├── ETHUSDT_1min_with_imbalance.csv # Enhanced data with imbalance
├── ETHUSDT_1min_from202506.csv  # Additional data file
└── results/                     # Output directory
    ├── backtest_results_*.csv   # Detailed prediction results
    ├── trades_*.csv             # Trade logs
    └── performance_plot_*.png   # Performance visualizations
```

### 2. Current Trading Implementation

**Location:** `bayesian_trader.py`

#### Current TradingStrategy Class (Lines 421-518)

```python
class TradingStrategy:
    """
    Simple position-based trading strategy.
    Position: -1 (short), 0 (neutral), +1 (long)
    """

    def __init__(self, threshold: float):
        self.position = 0
        self.threshold = threshold
        self.trades = []
        self.entry_price = None
```

**Current Issues:**
- **No Stop-Loss:** Trades only exit on signal reversal
- **Fixed Position Size:** Always trades ±1 unit regardless of risk
- **No Capital Management:** No tracking of available capital
- **No Risk Limits:** Unlimited loss potential per trade

---

## Reference Implementation: src/backtest/steps/

### 3. Portfolio Builder Analysis

**Location:** `src/backtest/steps/portfolio.py`

#### Risk-Based Position Sizing (Lines 104-126)

```python
def calculate_position_size_risk_based(self, trade: pd.Series, capital: float, risk_per_trade: float) -> float:
    """Calculate position size using risk-based method.

    Args:
        trade: Trade row with entry_price, stop_level, prev_atr
        capital: Current capital
        risk_per_trade: Risk percentage per trade (e.g., 0.01 = 1%)

    Returns:
        Position size (number of contracts/units)
    """
    # Calculate risk amount
    risk_amount = capital * risk_per_trade

    # Calculate risk per unit (distance to stop)
    risk_per_unit = abs(trade["entry_price"] - trade["stop_level"])

    # Avoid division by zero
    if risk_per_unit <= 0:
        raise ValueError("Risk per unit is less than or equal to zero")

    position_size = risk_amount / risk_per_unit
    return position_size
```

**Key Elements:**
1. **Capital Tracking:** Maintains running capital balance
2. **Risk-Based Sizing:** Position size = Risk Amount / Distance to Stop
3. **Dynamic Adjustment:** Capital updates after each trade

#### Portfolio Configuration (from portfolio_config.yaml)

```yaml
capital:
  initial: 1000  # Starting capital in USD

position_sizing:
  method: risk_based

  risk_based:
    risk_per_trade: 0.02  # Risk 2% of capital per trade
    use_atr_for_risk: true  # Use ATR for stop distance

  fixed_dollar:
    amount_per_trade: 1000

  equal_weight:
    # Automatically calculated
```

---

### 4. Stop-Loss Implementation Patterns

**Stop Level Calculation (from other strategies in the codebase):**

```python
# ATR-based stop (example pattern)
stop_multiplier = 2.0  # e.g., 2x ATR
atr = calculate_atr(df, period=14)
stop_level = entry_price - (atr * stop_multiplier * direction)

# For long: stop_level = entry_price - (atr * stop_multiplier)
# For short: stop_level = entry_price + (atr * stop_multiplier)
```

**Trade Exit Logic Pattern:**

```python
def check_stop_loss(current_price, entry_price, stop_level, direction):
    if direction == "long":
        return current_price <= stop_level  # Stop hit
    else:  # short
        return current_price >= stop_level  # Stop hit
```

---

## Gap Analysis: What Bayesian POC Needs

### 5. Missing Components for SL and Position Sizing

| Component | Current State | Required |
|-----------|--------------|----------|
| Stop-Loss Level | Not implemented | ATR-based or fixed % |
| Position Sizing | Fixed ±1 unit | Risk-based calculation |
| Capital Tracking | None | Running balance |
| Risk Per Trade | None | Configurable % |
| Exit on Stop | No | Check each bar |
| Trade Logging | Basic | Enhanced with stop_level |

### 6. Required Data Fields

**Current Trade Dictionary:**
```python
{
    'type': 'OPEN_LONG' | 'CLOSE_LONG' | 'OPEN_SHORT' | 'CLOSE_SHORT',
    'price': current_price,
    'timestamp': timestamp,
    'entry_price': entry_price,
    'pnl': profit_or_loss
}
```

**Required Trade Dictionary (to match portfolio.py):**
```python
{
    'symbol': 'ETHUSDT',
    'direction': 'long' | 'short',
    'entry_time': datetime,
    'exit_time': datetime,
    'entry_price': float,
    'exit_price': float,
    'stop_level': float,          # NEW: Stop-loss price
    'position_size': float,        # NEW: Units/contracts
    'gross_pnl': float,
    'net_pnl': float,             # After fees
    'exit_reason': 'signal' | 'stop_loss' | 'end_of_period',  # NEW
    'prev_atr': float             # NEW: ATR at entry for sizing
}
```

---

## Proposed Implementation Design

### 7. Enhanced TradingStrategy Class

```python
class TradingStrategyV2:
    """
    Enhanced trading strategy with SL and position sizing.
    Compatible with src/backtest/steps/portfolio.py format.
    """

    def __init__(
        self,
        threshold: float,
        initial_capital: float = 10000.0,
        risk_per_trade: float = 0.02,
        stop_atr_multiplier: float = 2.0,
        fee_rate: float = 0.001  # 0.1%
    ):
        self.position = 0
        self.threshold = threshold
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.stop_atr_multiplier = stop_atr_multiplier
        self.fee_rate = fee_rate

        self.trades = []
        self.entry_price = None
        self.stop_level = None
        self.position_size = None
        self.entry_time = None

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR from OHLCV data."""
        high = df['high'].values[-period:]
        low = df['low'].values[-period:]
        close = df['close'].values[-period:]

        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - np.roll(close, 1)),
                np.abs(low - np.roll(close, 1))
            )
        )
        return np.mean(tr[1:])  # Exclude first NaN

    def calculate_stop_level(
        self,
        entry_price: float,
        atr: float,
        direction: int
    ) -> float:
        """Calculate stop-loss level based on ATR."""
        stop_distance = atr * self.stop_atr_multiplier
        if direction == 1:  # Long
            return entry_price - stop_distance
        else:  # Short
            return entry_price + stop_distance

    def calculate_position_size(
        self,
        entry_price: float,
        stop_level: float
    ) -> float:
        """Calculate position size using risk-based method."""
        risk_amount = self.capital * self.risk_per_trade
        risk_per_unit = abs(entry_price - stop_level)

        if risk_per_unit <= 0:
            return 0.0

        position_size = risk_amount / risk_per_unit

        # Max position check (can't risk more than available capital)
        max_position = self.capital / entry_price
        return min(position_size, max_position)

    def check_stop_hit(self, current_price: float) -> bool:
        """Check if stop-loss has been triggered."""
        if self.position == 0 or self.stop_level is None:
            return False

        if self.position == 1:  # Long position
            return current_price <= self.stop_level
        else:  # Short position
            return current_price >= self.stop_level

    def decide(
        self,
        delta_p: float,
        current_price: float,
        timestamp,
        df: pd.DataFrame = None,  # For ATR calculation
        atr: float = None
    ) -> str:
        """Make trading decision with SL and position sizing."""

        # First, check if stop is hit
        if self.check_stop_hit(current_price):
            return self._close_position(
                current_price,
                timestamp,
                exit_reason='stop_loss'
            )

        action = 'HOLD'

        # Calculate ATR if df provided
        if atr is None and df is not None:
            atr = self.calculate_atr(df)
        elif atr is None:
            atr = current_price * 0.02  # Fallback: 2% of price

        # Entry logic
        if delta_p > self.threshold and self.position <= 0:
            # Close short if exists
            if self.position == -1:
                self._close_position(current_price, timestamp, 'signal')

            # Open long
            action = 'BUY'
            self.position = 1
            self.entry_price = current_price
            self.entry_time = timestamp
            self.stop_level = self.calculate_stop_level(current_price, atr, 1)
            self.position_size = self.calculate_position_size(
                current_price,
                self.stop_level
            )

            self.trades.append({
                'type': 'OPEN_LONG',
                'symbol': 'ETHUSDT',
                'direction': 'long',
                'entry_time': timestamp,
                'entry_price': current_price,
                'stop_level': self.stop_level,
                'position_size': self.position_size,
                'prev_atr': atr
            })

        elif delta_p < -self.threshold and self.position >= 0:
            # Close long if exists
            if self.position == 1:
                self._close_position(current_price, timestamp, 'signal')

            # Open short
            action = 'SELL'
            self.position = -1
            self.entry_price = current_price
            self.entry_time = timestamp
            self.stop_level = self.calculate_stop_level(current_price, atr, -1)
            self.position_size = self.calculate_position_size(
                current_price,
                self.stop_level
            )

            self.trades.append({
                'type': 'OPEN_SHORT',
                'symbol': 'ETHUSDT',
                'direction': 'short',
                'entry_time': timestamp,
                'entry_price': current_price,
                'stop_level': self.stop_level,
                'position_size': self.position_size,
                'prev_atr': atr
            })

        return action

    def _close_position(
        self,
        current_price: float,
        timestamp,
        exit_reason: str
    ) -> str:
        """Close current position and update capital."""
        if self.position == 0:
            return 'HOLD'

        direction = 'long' if self.position == 1 else 'short'

        # Calculate P&L
        if self.position == 1:
            gross_pnl = (current_price - self.entry_price) * self.position_size
        else:
            gross_pnl = (self.entry_price - current_price) * self.position_size

        # Deduct fees
        trade_value = current_price * self.position_size
        fees = trade_value * self.fee_rate * 2  # Entry + exit
        net_pnl = gross_pnl - fees

        # Update capital
        self.capital += net_pnl

        # Record trade
        self.trades.append({
            'type': f'CLOSE_{direction.upper()}',
            'symbol': 'ETHUSDT',
            'direction': direction,
            'entry_time': self.entry_time,
            'exit_time': timestamp,
            'entry_price': self.entry_price,
            'exit_price': current_price,
            'stop_level': self.stop_level,
            'position_size': self.position_size,
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl,
            'exit_reason': exit_reason
        })

        # Reset position
        self.position = 0
        self.entry_price = None
        self.stop_level = None
        self.position_size = None
        self.entry_time = None

        return 'CLOSE'

    def get_portfolio_metrics(self) -> dict:
        """Calculate portfolio-level metrics."""
        if not self.trades:
            return {}

        closes = [t for t in self.trades if 'CLOSE' in t['type']]
        if not closes:
            return {}

        pnls = [t['net_pnl'] for t in closes]

        return {
            'initial_capital': self.initial_capital,
            'final_capital': self.capital,
            'total_return_pct': ((self.capital - self.initial_capital) /
                                  self.initial_capital) * 100,
            'total_trades': len(closes),
            'win_rate': np.mean([p > 0 for p in pnls]) * 100,
            'avg_pnl': np.mean(pnls),
            'max_drawdown': self._calculate_max_drawdown(pnls),
            'sharpe_ratio': self._calculate_sharpe(pnls),
            'stop_loss_exits': len([t for t in closes if t['exit_reason'] == 'stop_loss']),
            'signal_exits': len([t for t in closes if t['exit_reason'] == 'signal'])
        }

    def _calculate_max_drawdown(self, pnls: list) -> float:
        """Calculate maximum drawdown from P&L series."""
        cumulative = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = running_max - cumulative
        return np.max(drawdown) if len(drawdown) > 0 else 0

    def _calculate_sharpe(self, pnls: list, risk_free_rate: float = 0) -> float:
        """Calculate Sharpe ratio."""
        if len(pnls) == 0 or np.std(pnls) == 0:
            return 0.0
        return (np.mean(pnls) - risk_free_rate) / np.std(pnls) * np.sqrt(252)
```

---

### 8. Integration with run_backtest

**Modified run_backtest Function:**

```python
def run_backtest_v2(
    test_df: pd.DataFrame,  # Full OHLCV dataframe
    test_imbalance: np.ndarray,
    model: BayesianBitcoinTrader,
    threshold: float,
    initial_capital: float = 10000.0,
    risk_per_trade: float = 0.02,
    stop_atr_multiplier: float = 2.0
) -> Tuple[List[Dict], List[Dict], Dict]:
    """
    Run backtest with enhanced SL and position sizing.
    """
    strategy = TradingStrategyV2(
        threshold=threshold,
        initial_capital=initial_capital,
        risk_per_trade=risk_per_trade,
        stop_atr_multiplier=stop_atr_multiplier
    )

    test_prices = test_df['close'].values
    results = []

    lookback_max = max(model.window_sizes)
    atr_period = 14

    for t in range(lookback_max, len(test_prices)):
        # Get order book imbalance
        r = test_imbalance[t] if test_imbalance is not None else 0.0

        # Generate prediction
        delta_p = model.predict(test_prices, t, r)

        # Calculate ATR for stop-loss
        if t >= atr_period:
            atr_df = test_df.iloc[t-atr_period:t]
            atr = strategy.calculate_atr(atr_df)
        else:
            atr = test_prices[t] * 0.02

        # Execute decision with SL checking
        current_price = test_prices[t]
        timestamp = test_df.iloc[t]['timestamp']

        action = strategy.decide(
            delta_p=delta_p,
            current_price=current_price,
            timestamp=timestamp,
            atr=atr
        )

        results.append({
            'timestamp': timestamp,
            'price': current_price,
            'prediction': delta_p,
            'action': action,
            'position': strategy.position,
            'capital': strategy.capital
        })

    # Close final position
    if strategy.position != 0:
        strategy._close_position(
            test_prices[-1],
            test_df.iloc[-1]['timestamp'],
            'end_of_period'
        )

    # Get portfolio metrics
    metrics = strategy.get_portfolio_metrics()

    return results, strategy.trades, metrics
```

---

### 9. Trade Output Format Compatibility

**Required CSV Columns for portfolio.py Integration:**

```
symbol,direction,entry_time,exit_time,entry_price,exit_price,stop_level,position_size,gross_pnl,net_pnl,exit_reason,prev_atr
ETHUSDT,long,2025-07-01 13:00:00,2025-07-01 14:30:00,3500.00,3520.00,3470.00,0.5714,11.43,10.00,signal,52.50
ETHUSDT,short,2025-07-01 14:30:00,2025-07-01 15:00:00,3520.00,3535.00,3555.00,0.5556,-8.33,-10.00,stop_loss,54.00
```

---

### 10. Configuration File

**Proposed: bayesian_config.yaml**

```yaml
# Bayesian Trading Strategy Configuration

# Model parameters
model:
  window_sizes: [180, 360, 720]  # S1, S2, S3 lookback windows (bars)
  n_clusters: 100                 # K-means clusters
  n_select: 20                    # Top patterns per timeframe
  threshold: 0.10                 # Trading signal threshold

# Risk management
risk:
  initial_capital: 10000.0        # Starting capital in USD
  risk_per_trade: 0.02            # Risk 2% per trade
  stop_atr_multiplier: 2.0        # Stop-loss = ATR * multiplier
  max_position_pct: 0.25          # Max 25% of capital in single position

# Fees and costs
fees:
  maker_fee: 0.0002               # 0.02% maker
  taker_fee: 0.0006               # 0.06% taker
  use_fee: taker                  # Assume taker execution

# Data
data:
  symbol: ETHUSDT
  interval: 1min
  train_ratio: 0.667              # 2/3 train, 1/3 test

# Output
output:
  results_dir: results
  trades_file: trades.csv
  metrics_file: metrics.json
```

---

## Implementation Status

### Completed: Dynamic Stop-Loss Strategies

**Files Added/Modified:**
- `stop_loss_strategies.py` - Strategy Pattern implementation
- `bayesian_trader.py` - Added `TradingStrategyWithSL` and `run_backtest_with_sl`

### Available Strategies

| Strategy | Class | Description |
|----------|-------|-------------|
| **TimeframeDisagreement** | `TimeframeDisagreementStop` | Exit when S1 AND S3 both turn against position |
| **PredictionReversal** | `PredictionReversalStop` | Exit when delta_p flips direction |
| **PredictionMomentum** | `PredictionMomentumStop` | Exit when prediction strength fades |
| **Composite** | `CompositeStop` | Combine multiple strategies |
| **NoStop** | `NoStop` | Baseline (no stop-loss) |

### Usage Example

```python
from bayesian_trader import run_backtest_with_sl, BayesianBitcoinTrader
from stop_loss_strategies import (
    TimeframeDisagreementStop,
    PredictionReversalStop,
    CompositeStop,
    create_stop_strategy
)

# Default: TimeframeDisagreementStop
results, trades, stop_stats = run_backtest_with_sl(
    test_data=test_prices,
    test_imbalance=test_imbalance,
    model=model,
    threshold=0.10
)

# Or specify a different strategy
stop = PredictionReversalStop(threshold=0.05)
results, trades, stop_stats = run_backtest_with_sl(
    test_data=test_prices,
    test_imbalance=test_imbalance,
    model=model,
    threshold=0.10,
    stop_strategy=stop
)

# Or use factory function
stop = create_stop_strategy("prediction_reversal", threshold=0.08)

# Or combine strategies
stop = CompositeStop([
    TimeframeDisagreementStop(),
    PredictionReversalStop(threshold=0.05),
])
```

### Extending with New Strategies

```python
from stop_loss_strategies import StopLossStrategy, StopContext

class MyCustomStop(StopLossStrategy):
    @property
    def name(self) -> str:
        return "my_custom"

    def should_exit(self, ctx: StopContext) -> tuple[bool, str]:
        # Your logic here
        if some_condition:
            return True, "my_reason"
        return False, None
```

---

## Next Steps

### Phase 1: Validation (Current)
1. Run backtest with TimeframeDisagreementStop
2. Compare metrics vs original (no SL)
3. Analyze stop exit patterns

### Phase 2: Position Sizing
1. Add risk-based position sizing
2. Track capital over time
3. Calculate risk-adjusted metrics

### Phase 3: Optimization
1. Test other strategies (PredictionReversal, Momentum)
2. Compare composite vs single strategies
3. Document best configuration

---

## Key Differences from Existing Backtest Steps

| Aspect | src/backtest/steps | bayesian_method_poc |
|--------|-------------------|---------------------|
| Signal Source | ATR breakout / BB | Bayesian regression |
| Stop Calculation | At entry (ATR-based) | Needs implementation |
| Position Sizing | Post-hoc (portfolio builder) | In-strategy |
| Trade Format | Standardized CSV | Custom dict |
| Capital Tracking | Portfolio builder | In-strategy |
| Exit Logic | Stop/EOD | Signal reversal only |

---

*Document Generated: 2025-12-28*
*Analysis: Comparison of bayesian_method_poc with src/backtest/steps*
