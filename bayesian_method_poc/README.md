# Bayesian Regression Trading - Proof of Concept

Implementation of the Bayesian regression trading strategy from Shah & Zhang (2014) "Bayesian Regression and Bitcoin".

## Quick Start

```bash
# 1. Install dependencies
pip install numpy pandas scikit-learn scipy matplotlib pybit

# 2. Generate order book imbalance data
python download_orderbook.py

# 3. Run the POC
python run_bayesian_poc.py
```

## What This Does

This POC implements a machine learning trading strategy that:
1. **Extracts patterns** from historical price data using sliding windows
2. **Clusters patterns** using k-means to find representative price behaviors
3. **Predicts price changes** using Bayesian regression (similarity-weighted averages)
4. **Combines multiple timeframes** (30min, 1hr, 2hr) for robust predictions
5. **Executes trades** when predictions exceed a threshold
6. **Evaluates performance** with metrics like Sharpe ratio, win rate, etc.

## Files

- `bayesian_trader.py` - Core Bayesian regression model implementation
- `run_bayesian_poc.py` - Main script to train and backtest the model
- `download_orderbook.py` - Creates volume-based imbalance proxy data
- `bayesian_bitcoin_trading_guide.md` - Detailed implementation guide from the paper
- `POC_SUMMARY.md` - Results and analysis

## Configuration

Edit `run_bayesian_poc.py` to adjust:

```python
window_sizes = [30, 60, 120]  # Lookback windows (in minutes)
n_clusters = 30               # Number of k-means clusters
n_select = 10                 # Top clusters to use
threshold = 0.05              # Trading threshold
sample_size = 20000           # Data points to use (for faster testing)
```

## Results

Current POC results (4.6 day test period):
- **237 trades** executed
- **-0.33% return** (small loss, expected for limited data POC)
- **44.7% win rate**
- **Sharpe ratio: -0.10**

See `POC_SUMMARY.md` for detailed analysis and comparison to original paper.

## How It Works

### 1. Pattern Extraction
```python
# For each time window (30min, 60min, 120min):
patterns = price_series[t-window:t]  # Extract sliding window
label = price_series[t+1] - price_series[t]  # Future price change
```

### 2. Clustering
```python
# Group similar patterns using k-means
kmeans = KMeans(n_clusters=30)
clusters = kmeans.fit(normalized_patterns)

# Select top clusters by effectiveness (signal-to-noise ratio)
effectiveness = abs(mean_change) / std_change
```

### 3. Bayesian Prediction
```python
# For current pattern x, predict using historical patterns x_i
similarity = pearson_correlation(x, x_i)
weights = exp(c * similarity)  # Exponential weighting
prediction = sum(weights * labels) / sum(weights)  # Weighted average
```

### 4. Multi-Timeframe Combination
```python
# Combine predictions from all timeframes
delta_p = w0 + w1*pred1 + w2*pred2 + w3*pred3 + w4*imbalance
```

### 5. Trading Strategy
```python
if delta_p > threshold:
    buy()  # Enter long position
elif delta_p < -threshold:
    sell()  # Enter short position
else:
    hold()  # No action
```

## Data

- **Source:** Bybit ETHUSDT perpetual futures
- **Interval:** 1-minute candles
- **Features:** OHLCV + volume-based imbalance ratio
- **Period:** May 2025 - December 2025 (~6.5 months)

## Order Book Data

Since historical order book snapshots aren't available from exchanges, we use a volume-based proxy:

```python
# Estimate buy/sell pressure from price movement
buy_volume = volume * (1 + abs(price_change)/price)  # if price up
sell_volume = volume * (1 - abs(price_change)/price)  # if price down

# Imbalance ratio [-1, +1]
imbalance = (buy_volume - sell_volume) / (buy_volume + sell_volume)
```

## Improving Results

To get closer to the paper's 89% return:

1. **Use more data** - Train on 6 months instead of 14 days
2. **More patterns** - Increase clusters to 100, select top 20
3. **Finer resolution** - Use 10-second intervals if available
4. **Real order book** - Collect live order book data
5. **Optimize parameters** - Grid search for best window sizes, threshold, etc.
6. **Add risk management** - Stop losses, position sizing
7. **Model transaction costs** - Include fees and slippage

## Logging

The code includes detailed logging to track progress:
- Pattern extraction and clustering progress
- Weight training progress (10% increments)
- Backtest progress (10% increments)
- Performance metrics

## Output Files

Results are saved to `bayesian_method_poc/results/`:
- `backtest_results_*.csv` - Detailed predictions for each time step
- `trades_*.csv` - Log of all executed trades

## Comparison to Original Paper

| Metric | Paper (BTC 2014) | POC (ETH 2025) |
|--------|------------------|----------------|
| Return | +89% | -0.33% |
| Period | 50 days | 4.6 days |
| Trades | 2,872 | 237 |
| Sharpe | 4.10 | -0.10 |

Differences expected due to:
- Different asset (BTC vs ETH)
- Different market conditions (2014 vs 2025)
- Less data (14 days vs 6 months training)
- Fewer patterns (10 vs 20 per timeframe)
- Coarser resolution (1-min vs 10-sec)
- Volume proxy vs real order book

## Key Insight

The model assumes **price movements follow a finite number of latent patterns**. Instead of explicitly modeling these patterns, Bayesian regression weights predictions by similarity to historical patterns. Similar price configurations tend to produce similar outcomes.

## References

Shah, D., & Zhang, K. (2014). *Bayesian Regression and Bitcoin*. arXiv:1410.1231 [cs.AI]

## License

For educational and research purposes only. Not financial advice.
