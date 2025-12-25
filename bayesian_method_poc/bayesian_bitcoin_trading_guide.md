# Bayesian Regression Bitcoin Trading

**Implementation Guide Based on Shah & Zhang (MIT, 2014)**

---

## 1. Executive Summary

This guide provides a complete implementation for replicating the Bayesian regression trading strategy from "Bayesian Regression and Bitcoin" (Shah & Zhang, 2014). The original paper achieved ~89% returns in 50 days with a Sharpe ratio of 4.10.

### 1.1 Core Concept

The strategy assumes price movements follow a finite number of latent patterns. Rather than explicitly identifying patterns, Bayesian regression weights predictions by historical similarity. Similar price configurations tend to produce similar outcomes.

### 1.2 Original Paper Results

| Metric | Value |
|--------|-------|
| Test Period | May 6 - June 24, 2014 (50 days) |
| Return | ~89% |
| Sharpe Ratio | 4.10 |
| Total Trades | 2,872 |
| Data Interval | 10 seconds |
| Position Size | ±1 BTC |

---

## 2. Data Acquisition

### 2.1 Required Data Types

- **Price Data**: Single price per interval (close price sufficient)
- **Order Book Data**: Bid/ask volumes at multiple price levels (paper used top 60 levels)
- **Timestamp**: Unix timestamp or ISO format

> **Note**: The paper uses only close price, not full OHLCV. Order book is used solely for the imbalance ratio.

### 2.2 Data Sources

| Source | Data Type | Notes |
|--------|-----------|-------|
| Binance API | Price + Order Book | Free, 1m minimum |
| Coinbase API | Price + Order Book | Free tier available |
| Kaiko | Historical tick data | Paid, institutional |
| CryptoCompare | Historical price | Free tier, 1m data |

### 2.3 Sample Data Download Code

```python
import ccxt
import pandas as pd
from datetime import datetime, timedelta

exchange = ccxt.binance()
symbol = 'BTC/USDT'
timeframe = '1m'  # Adjust based on strategy

# Fetch price data
ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=1000)
df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

# Extract close price only (what paper uses)
price_series = df['close'].values

# Fetch order book
order_book = exchange.fetch_order_book(symbol, limit=60)
v_bid = sum([b[1] for b in order_book['bids']])
v_ask = sum([a[1] for a in order_book['asks']])
r = (v_bid - v_ask) / (v_bid + v_ask)  # Imbalance ratio
```

### 2.4 Minimum Data Requirements

- **Pattern Extraction**: 1-2 months continuous data
- **Weight Training**: 1-2 months continuous data
- **Testing**: 1-2 months out-of-sample data
- **Total Recommended**: 3-6 months minimum

---

## 3. Data Processing Pipeline

### 3.1 Data Cleaning Steps

1. **Remove duplicates**: Eliminate duplicate timestamps
2. **Handle missing data**: Forward-fill or interpolate gaps
3. **Remove outliers**: Filter extreme price spikes (> 5 std dev)
4. **Resample if needed**: Aggregate to consistent intervals

```python
import pandas as pd
import numpy as np

def clean_price_data(df):
    # Remove duplicates
    df = df.drop_duplicates(subset='timestamp')
    
    # Sort by time
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    # Forward fill missing values
    df['close'] = df['close'].ffill()
    
    # Remove outliers (> 5 std dev)
    returns = df['close'].pct_change()
    mask = np.abs(returns) < 5 * returns.std()
    df = df[mask]
    
    return df
```

### 3.2 Feature Engineering

#### 3.2.1 Price Change Series

Convert raw prices to price changes for pattern matching:

```python
# Calculate price changes (what paper uses for labels)
df['price_change'] = df['close'].diff()

# Or percentage returns
df['return'] = df['close'].pct_change()
```

#### 3.2.2 Lookback Windows

Three lookback windows. For 1-minute intervals:

| Window | Duration | Vector Dimension |
|--------|----------|------------------|
| S1 (short) | 180 minutes | 180 |
| S2 (medium) | 360 minutes | 360 |
| S3 (long) | 720 minutes | 720 |

#### 3.2.3 Order Book Imbalance

```python
def get_order_book_imbalance(order_book):
    """
    Calculate bid-ask volume imbalance ratio.
    Returns value in range [-1, +1]
    - Positive = buying pressure
    - Negative = selling pressure
    """
    v_bid = sum([level[1] for level in order_book['bids'][:60]])
    v_ask = sum([level[1] for level in order_book['asks'][:60]])
    
    if v_bid + v_ask == 0:
        return 0
    
    return (v_bid - v_ask) / (v_bid + v_ask)
```

### 3.3 Data Split Strategy

Divide data into three equal chronological periods:

```python
def split_data(price_series, labels):
    n = len(price_series)
    split1 = n // 3
    split2 = 2 * n // 3
    
    # Period 1: Pattern extraction
    pattern_data = price_series[:split1]
    pattern_labels = labels[:split1]
    
    # Period 2: Weight training
    train_data = price_series[split1:split2]
    train_labels = labels[split1:split2]
    
    # Period 3: Testing
    test_data = price_series[split2:]
    test_labels = labels[split2:]
    
    return (pattern_data, pattern_labels), (train_data, train_labels), (test_data, test_labels)
```

---

## 4. Pattern Extraction (Model Training Phase 1)

### 4.1 Generate All Possible Patterns

Extract sliding windows from price series:

```python
import numpy as np
from sklearn.cluster import KMeans

def extract_patterns(price_series, window_size):
    """
    Extract all possible patterns of given window size.
    Each pattern is a vector of consecutive prices.
    Label is the price change immediately following the pattern.
    """
    patterns = []
    labels = []
    
    for i in range(len(price_series) - window_size - 1):
        window = price_series[i:i+window_size]
        future_change = price_series[i+window_size] - price_series[i+window_size-1]
        patterns.append(window)
        labels.append(future_change)
    
    return np.array(patterns), np.array(labels)

# Extract for each timeframe
S1_patterns, S1_labels = extract_patterns(price_series, 180)
S2_patterns, S2_labels = extract_patterns(price_series, 360)
S3_patterns, S3_labels = extract_patterns(price_series, 720)
```

### 4.2 Pattern Normalization

Normalize each pattern to zero mean and unit standard deviation:

```python
def normalize_pattern(pattern):
    """
    Normalize pattern to mean=0, std=1.
    This enables Pearson correlation as dot product.
    """
    mean = np.mean(pattern)
    std = np.std(pattern)
    
    if std == 0:
        return np.zeros_like(pattern)
    
    return (pattern - mean) / std

def normalize_all_patterns(patterns):
    """Normalize all patterns in library."""
    return np.array([normalize_pattern(p) for p in patterns])
```

### 4.3 K-Means Clustering

Cluster patterns to reduce computational complexity:

```python
def cluster_patterns(patterns, labels, n_clusters=100, n_select=20):
    """
    Cluster patterns using k-means.
    Select top clusters based on effectiveness.
    """
    # Normalize patterns first
    normalized = normalize_all_patterns(patterns)
    
    # Cluster
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    cluster_ids = kmeans.fit_predict(normalized)
    
    # Evaluate each cluster
    cluster_scores = []
    for k in range(n_clusters):
        mask = cluster_ids == k
        cluster_labels = labels[mask]
        
        if len(cluster_labels) < 10:  # Skip small clusters
            cluster_scores.append(-np.inf)
            continue
        
        # Effectiveness = |mean price change| / std (signal-to-noise)
        mean_change = np.abs(np.mean(cluster_labels))
        std_change = np.std(cluster_labels)
        
        if std_change == 0:
            cluster_scores.append(-np.inf)
        else:
            cluster_scores.append(mean_change / std_change)
    
    # Select top clusters
    top_clusters = np.argsort(cluster_scores)[-n_select:]
    
    # Get representative patterns (cluster centers)
    selected_patterns = kmeans.cluster_centers_[top_clusters]
    
    # Get average labels for each selected cluster
    selected_labels = []
    for k in top_clusters:
        mask = cluster_ids == k
        selected_labels.append(np.mean(labels[mask]))
    
    return selected_patterns, np.array(selected_labels)
```

### 4.4 Cluster Selection Criteria

Select top 20 clusters based on:

- **Price Variation**: High average absolute price change
- **Confidence**: Consistent direction (low variance in sign)
- **Sample Size**: Sufficient samples for statistical significance

---

## 5. Bayesian Regression Model

### 5.1 Core Prediction Formula

The empirical Bayesian prediction:

$$\hat{y} = \frac{\sum_{i=1}^{n} y_i \cdot \exp(c \cdot s(x, x_i))}{\sum_{i=1}^{n} \exp(c \cdot s(x, x_i))}$$

Where:
- $x$ = current pattern
- $x_i$ = historical pattern from library
- $y_i$ = label (price change) for pattern $x_i$
- $s(x, x_i)$ = similarity (Pearson correlation)
- $c$ = scaling constant (optimized during training)

### 5.2 Similarity Function

```python
def similarity(a, b):
    """
    Pearson correlation between two patterns.
    For normalized patterns, this is just the dot product / length.
    """
    a_norm = (a - np.mean(a)) / np.std(a)
    b_norm = (b - np.mean(b)) / np.std(b)
    return np.dot(a_norm, b_norm) / len(a)

def fast_similarity(a_normalized, b_normalized):
    """
    Fast similarity for pre-normalized patterns.
    """
    return np.dot(a_normalized, b_normalized) / len(a_normalized)

def batch_similarity(current_pattern, pattern_library):
    """
    Compute similarity between current pattern and all patterns in library.
    Vectorized for speed.
    """
    # Normalize current pattern
    current_norm = normalize_pattern(current_pattern)
    
    # Pattern library should already be normalized
    # Compute all similarities at once
    similarities = np.dot(pattern_library, current_norm) / len(current_norm)
    
    return similarities
```

### 5.3 Single Timeframe Prediction

```python
def predict_single_timeframe(current_pattern, pattern_library, labels, c):
    """
    Generate prediction using one timeframe's pattern library.
    
    Args:
        current_pattern: Current price window (raw)
        pattern_library: Pre-normalized pattern library
        labels: Price change labels for each pattern
        c: Scaling constant
    
    Returns:
        Predicted price change
    """
    # Normalize current pattern
    current_norm = normalize_pattern(current_pattern)
    
    # Compute similarities
    similarities = np.dot(pattern_library, current_norm) / len(current_norm)
    
    # Compute weights
    weights = np.exp(c * similarities)
    
    # Weighted average of labels
    prediction = np.sum(weights * labels) / np.sum(weights)
    
    return prediction
```

### 5.4 Multi-Timeframe Prediction

```python
def predict_combined(price_series, t, pattern_libs, label_libs, c_values, weights, order_book):
    """
    Generate final prediction combining all timeframes + order book.
    
    Final prediction: Δp = w0 + w1*Δp1 + w2*Δp2 + w3*Δp3 + w4*r
    """
    # Extract current patterns for each timeframe
    x1 = price_series[t-180:t]
    x2 = price_series[t-360:t]
    x3 = price_series[t-720:t]
    
    # Generate predictions for each timeframe
    dp1 = predict_single_timeframe(x1, pattern_libs[0], label_libs[0], c_values[0])
    dp2 = predict_single_timeframe(x2, pattern_libs[1], label_libs[1], c_values[1])
    dp3 = predict_single_timeframe(x3, pattern_libs[2], label_libs[2], c_values[2])
    
    # Order book imbalance
    r = get_order_book_imbalance(order_book)
    
    # Combine predictions
    w0, w1, w2, w3, w4 = weights
    delta_p = w0 + w1*dp1 + w2*dp2 + w3*dp3 + w4*r
    
    return delta_p
```

### 5.5 Weight Optimization

```python
from sklearn.linear_model import LinearRegression

def optimize_weights(train_data, train_labels, pattern_libs, label_libs, c_values):
    """
    Learn optimal combination weights using Period 2 data.
    """
    X = []
    y = []
    
    # Generate predictions for each training point
    for t in range(720, len(train_data) - 1):
        x1 = train_data[t-180:t]
        x2 = train_data[t-360:t]
        x3 = train_data[t-720:t]
        
        dp1 = predict_single_timeframe(x1, pattern_libs[0], label_libs[0], c_values[0])
        dp2 = predict_single_timeframe(x2, pattern_libs[1], label_libs[1], c_values[1])
        dp3 = predict_single_timeframe(x3, pattern_libs[2], label_libs[2], c_values[2])
        
        # Note: r (order book) would need to be retrieved for each historical point
        # For simplicity, using 0 or retrieving from stored data
        r = 0  # Placeholder - use actual order book data
        
        X.append([dp1, dp2, dp3, r])
        y.append(train_labels[t])
    
    X = np.array(X)
    y = np.array(y)
    
    # Fit linear regression
    model = LinearRegression()
    model.fit(X, y)
    
    w0 = model.intercept_
    w1, w2, w3, w4 = model.coef_
    
    return [w0, w1, w2, w3, w4]
```

### 5.6 Scaling Constant Optimization

```python
from scipy.optimize import minimize_scalar

def optimize_c(train_data, train_labels, pattern_library, library_labels, c_range=(0.1, 10)):
    """
    Optimize scaling constant c for a single timeframe.
    """
    def loss(c):
        errors = []
        for t in range(len(pattern_library[0]), len(train_data) - 1):
            window_size = len(pattern_library[0])
            current = train_data[t-window_size:t]
            
            pred = predict_single_timeframe(current, pattern_library, library_labels, c)
            actual = train_labels[t]
            
            errors.append((pred - actual) ** 2)
        
        return np.mean(errors)
    
    result = minimize_scalar(loss, bounds=c_range, method='bounded')
    return result.x
```

---

## 6. Trading Strategy Implementation

### 6.1 Position Management

```python
class TradingStrategy:
    """
    Simple position-based strategy.
    Position: -1 (short), 0 (neutral), +1 (long)
    """
    
    def __init__(self, threshold):
        self.position = 0
        self.threshold = threshold
        self.trades = []
    
    def decide(self, delta_p, current_price, timestamp):
        """
        Make trading decision based on predicted price change.
        """
        action = 'HOLD'
        
        if delta_p > self.threshold and self.position <= 0:
            action = 'BUY'
            if self.position == -1:
                # Close short first
                self.trades.append({
                    'type': 'CLOSE_SHORT',
                    'price': current_price,
                    'timestamp': timestamp
                })
            self.position = 1
            self.trades.append({
                'type': 'OPEN_LONG',
                'price': current_price,
                'timestamp': timestamp
            })
            
        elif delta_p < -self.threshold and self.position >= 0:
            action = 'SELL'
            if self.position == 1:
                # Close long first
                self.trades.append({
                    'type': 'CLOSE_LONG',
                    'price': current_price,
                    'timestamp': timestamp
                })
            self.position = -1
            self.trades.append({
                'type': 'OPEN_SHORT',
                'price': current_price,
                'timestamp': timestamp
            })
        
        return action
```

### 6.2 Threshold Selection

| Threshold Range | Trade Frequency | Profit/Trade | Use Case |
|-----------------|-----------------|--------------|----------|
| 0.1 - 0.3 | High | Lower | High-frequency |
| 0.4 - 0.8 | Medium | Medium | Balanced |
| 0.9 - 1.5 | Low | Higher | Conservative |

### 6.3 Complete Trading Loop

```python
def run_backtest(test_data, pattern_libs, label_libs, c_values, weights, threshold):
    """
    Run complete backtest on test period.
    """
    strategy = TradingStrategy(threshold)
    results = []
    
    lookback_max = 720  # Longest window
    
    for t in range(lookback_max, len(test_data)):
        # Extract current patterns
        x1 = test_data[t-180:t]
        x2 = test_data[t-360:t]
        x3 = test_data[t-720:t]
        
        # Generate predictions
        dp1 = predict_single_timeframe(x1, pattern_libs[0], label_libs[0], c_values[0])
        dp2 = predict_single_timeframe(x2, pattern_libs[1], label_libs[1], c_values[1])
        dp3 = predict_single_timeframe(x3, pattern_libs[2], label_libs[2], c_values[2])
        
        r = 0  # Placeholder for order book imbalance
        
        # Combine predictions
        w0, w1, w2, w3, w4 = weights
        delta_p = w0 + w1*dp1 + w2*dp2 + w3*dp3 + w4*r
        
        # Execute decision
        current_price = test_data[t]
        action = strategy.decide(delta_p, current_price, t)
        
        results.append({
            'timestamp': t,
            'price': current_price,
            'prediction': delta_p,
            'action': action,
            'position': strategy.position
        })
    
    return results, strategy.trades
```

---

## 7. Performance Evaluation

### 7.1 Sharpe Ratio Calculation

```python
def calculate_sharpe_ratio(trades, start_price, end_price):
    """
    Calculate Sharpe ratio as defined in the paper.
    
    Sharpe = (Total Profit - C) / (L * σp)
    
    Where:
    - C = |end_price - start_price| (buy-and-hold return)
    - L = number of trades
    - σp = standard deviation of per-trade profits
    """
    if len(trades) == 0:
        return 0
    
    # Calculate per-trade profits
    profits = []
    for i in range(0, len(trades) - 1, 2):  # Pair open/close trades
        if i + 1 < len(trades):
            entry = trades[i]['price']
            exit_price = trades[i+1]['price']
            
            if trades[i]['type'].startswith('OPEN_LONG'):
                profit = exit_price - entry
            else:  # SHORT
                profit = entry - exit_price
            
            profits.append(profit)
    
    if len(profits) == 0:
        return 0
    
    C = abs(end_price - start_price)
    L = len(profits)
    total_profit = sum(profits)
    std_profit = np.std(profits)
    
    if std_profit == 0:
        return 0
    
    sharpe = (total_profit - C) / (L * std_profit)
    return sharpe
```

### 7.2 Additional Metrics

```python
def calculate_metrics(trades, results):
    """Calculate comprehensive performance metrics."""
    
    profits = []
    for i in range(0, len(trades) - 1, 2):
        if i + 1 < len(trades):
            entry = trades[i]['price']
            exit_price = trades[i+1]['price']
            
            if trades[i]['type'].startswith('OPEN_LONG'):
                profit = exit_price - entry
            else:
                profit = entry - exit_price
            
            profits.append(profit)
    
    if len(profits) == 0:
        return {}
    
    profits = np.array(profits)
    
    metrics = {
        'total_trades': len(profits),
        'total_profit': np.sum(profits),
        'avg_profit_per_trade': np.mean(profits),
        'win_rate': np.mean(profits > 0),
        'max_profit': np.max(profits),
        'max_loss': np.min(profits),
        'profit_std': np.std(profits),
    }
    
    # Maximum drawdown
    cumulative = np.cumsum(profits)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    metrics['max_drawdown'] = np.max(drawdown)
    
    return metrics
```

---

## 8. Practical Considerations

### 8.1 Computational Optimization

- **Pre-normalize patterns**: Store with mean=0, std=1
- **Vectorize operations**: Use numpy broadcasting
- **Parallel processing**: Similarity calculations are embarrassingly parallel

```python
# Vectorized similarity computation
def batch_predict(current_patterns, pattern_library, labels, c):
    """
    Predict for multiple current patterns at once.
    """
    # current_patterns: (N, window_size)
    # pattern_library: (M, window_size) - pre-normalized
    
    # Normalize current patterns
    means = current_patterns.mean(axis=1, keepdims=True)
    stds = current_patterns.std(axis=1, keepdims=True)
    current_norm = (current_patterns - means) / stds
    
    # Compute all similarities: (N, M)
    similarities = np.dot(current_norm, pattern_library.T) / pattern_library.shape[1]
    
    # Compute weights
    weights = np.exp(c * similarities)
    
    # Weighted predictions
    predictions = np.dot(weights, labels) / weights.sum(axis=1)
    
    return predictions
```

### 8.2 Costs Not Modeled in Paper

| Cost | Typical Value | Impact |
|------|---------------|--------|
| Transaction fees | 0.1% per trade | High (2872 trades) |
| Slippage | 0.05-0.2% | Medium |
| Market impact | Variable | Low for small sizes |
| API latency | 10-100ms | Critical for HFT |

### 8.3 Risk Management Additions

```python
class EnhancedTradingStrategy(TradingStrategy):
    """Extended strategy with risk management."""
    
    def __init__(self, threshold, stop_loss_pct=0.02, max_position=1):
        super().__init__(threshold)
        self.stop_loss_pct = stop_loss_pct
        self.max_position = max_position
        self.entry_price = None
    
    def check_stop_loss(self, current_price):
        """Check if stop loss triggered."""
        if self.position == 0 or self.entry_price is None:
            return False
        
        if self.position == 1:  # Long
            loss_pct = (self.entry_price - current_price) / self.entry_price
        else:  # Short
            loss_pct = (current_price - self.entry_price) / self.entry_price
        
        return loss_pct > self.stop_loss_pct
```

---

## 9. Adapting to Different Timeframes

Scale lookback windows proportionally:

| Interval | S1 Window | S2 Window | S3 Window |
|----------|-----------|-----------|-----------|
| 10 sec (paper) | 180 bars (30m) | 360 bars (1h) | 720 bars (2h) |
| 1 minute | 30 bars (30m) | 60 bars (1h) | 120 bars (2h) |
| 5 minute | 36 bars (3h) | 72 bars (6h) | 144 bars (12h) |
| 15 minute | 24 bars (6h) | 48 bars (12h) | 96 bars (24h) |
| 1 hour | 24 bars (1d) | 48 bars (2d) | 96 bars (4d) |

```python
def get_window_sizes(interval_minutes):
    """
    Calculate window sizes for given interval.
    Maintains similar time coverage as original paper.
    """
    # Original: 10-sec intervals with 30/60/120 min windows
    base_interval = 10 / 60  # 10 seconds in minutes
    
    # Time durations to cover (in minutes)
    durations = [30, 60, 120]
    
    # Calculate bar counts
    window_sizes = [int(d / interval_minutes) for d in durations]
    
    return window_sizes
```

---

## 10. Known Limitations & Caveats

1. **Market regime dependence**: Performed better during high volatility (May-June 2014)

2. **Scalability unknown**: Only tested ±1 BTC; larger sizes face liquidity constraints

3. **Pattern staleness**: Historical patterns may not persist as market evolves

4. **Overfitting risk**: Clustering and weight optimization could overfit to training period

5. **Single market**: Only tested on one exchange (Okcoin) during one period

6. **No transaction costs**: 2,872 trades × fees would significantly impact returns

7. **Order book requirement**: Real-time order book data needed for imbalance ratio

8. **Computational load**: Pattern matching at every interval requires optimization

---

## 11. Implementation Checklist

- [ ] Set up data pipeline (exchange API or historical data source)
- [ ] Implement data cleaning and preprocessing
- [ ] Build pattern extraction with k-means clustering
- [ ] Implement similarity function (Pearson correlation)
- [ ] Build Bayesian prediction module
- [ ] Train weights using linear regression
- [ ] Optimize scaling constant c
- [ ] Implement trading logic with threshold
- [ ] Backtest on out-of-sample data
- [ ] Add transaction costs and slippage modeling
- [ ] Implement risk management (stops, position sizing)
- [ ] Paper trade before deploying real capital

---

## Appendix: Complete Implementation

```python
"""
Complete Bayesian Regression Bitcoin Trading Implementation
Based on Shah & Zhang (2014)
"""

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression
from scipy.optimize import minimize_scalar

class BayesianBitcoinTrader:
    def __init__(self, window_sizes=[180, 360, 720], n_clusters=100, n_select=20):
        self.window_sizes = window_sizes
        self.n_clusters = n_clusters
        self.n_select = n_select
        
        self.pattern_libs = [None, None, None]
        self.label_libs = [None, None, None]
        self.c_values = [1.0, 1.0, 1.0]
        self.weights = [0, 0.25, 0.25, 0.25, 0.25]
        
    def normalize_pattern(self, pattern):
        mean = np.mean(pattern)
        std = np.std(pattern)
        if std == 0:
            return np.zeros_like(pattern)
        return (pattern - mean) / std
    
    def extract_patterns(self, price_series, window_size):
        patterns, labels = [], []
        for i in range(len(price_series) - window_size - 1):
            patterns.append(price_series[i:i+window_size])
            labels.append(price_series[i+window_size] - price_series[i+window_size-1])
        return np.array(patterns), np.array(labels)
    
    def cluster_patterns(self, patterns, labels):
        normalized = np.array([self.normalize_pattern(p) for p in patterns])
        kmeans = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)
        cluster_ids = kmeans.fit_predict(normalized)
        
        scores = []
        for k in range(self.n_clusters):
            mask = cluster_ids == k
            if mask.sum() < 10:
                scores.append(-np.inf)
                continue
            cluster_labels = labels[mask]
            score = np.abs(np.mean(cluster_labels)) / (np.std(cluster_labels) + 1e-8)
            scores.append(score)
        
        top_clusters = np.argsort(scores)[-self.n_select:]
        selected_patterns = kmeans.cluster_centers_[top_clusters]
        selected_labels = np.array([np.mean(labels[cluster_ids == k]) for k in top_clusters])
        
        return selected_patterns, selected_labels
    
    def predict_single(self, current_pattern, pattern_lib, labels, c):
        current_norm = self.normalize_pattern(current_pattern)
        similarities = np.dot(pattern_lib, current_norm) / len(current_norm)
        weights = np.exp(c * similarities)
        return np.sum(weights * labels) / np.sum(weights)
    
    def fit(self, price_series):
        """Train on first 2/3 of data."""
        n = len(price_series)
        split = 2 * n // 3
        
        pattern_data = price_series[:split//2]
        train_data = price_series[split//2:split]
        
        # Extract and cluster patterns for each timeframe
        for i, ws in enumerate(self.window_sizes):
            patterns, labels = self.extract_patterns(pattern_data, ws)
            self.pattern_libs[i], self.label_libs[i] = self.cluster_patterns(patterns, labels)
        
        # Optimize c values and weights on training data
        # (Simplified - full implementation would optimize c)
        
        return self
    
    def predict(self, price_series, t, r=0):
        """Predict price change at time t."""
        predictions = []
        for i, ws in enumerate(self.window_sizes):
            if t < ws:
                predictions.append(0)
            else:
                current = price_series[t-ws:t]
                pred = self.predict_single(current, self.pattern_libs[i], 
                                          self.label_libs[i], self.c_values[i])
                predictions.append(pred)
        
        w0, w1, w2, w3, w4 = self.weights
        return w0 + w1*predictions[0] + w2*predictions[1] + w3*predictions[2] + w4*r

# Usage
if __name__ == "__main__":
    # Load your data
    # price_series = ...
    
    trader = BayesianBitcoinTrader()
    # trader.fit(price_series)
    # prediction = trader.predict(price_series, t=1000)
    pass
```

---

*Document generated based on "Bayesian Regression and Bitcoin" by Devavrat Shah and Kang Zhang, MIT (2014)*
