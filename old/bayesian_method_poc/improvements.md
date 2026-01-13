# Bayesian Trading Strategy - Improvements Roadmap

## Latest Analysis (15-min Data with Extended History)

**Results (310 days, fees disabled):**
| Metric | Value |
|--------|-------|
| Gross P&L | +$2,289.15 |
| Trades | 1,594 |
| Win Rate | 36.3% |
| Avg Profit | $46.62 |
| Avg Loss | -$24.27 |
| Avg Profit/Trade | $1.44 |
| Sharpe Ratio | 0.02 |

**Key Insight:** The strategy has a **low win rate (~36%)** but profits through higher average wins than losses (profit factor ~1.9x). This means:
- Each trade has a small edge (~$1.44)
- **Reducing trade count won't help** - the strategy depends on volume to compound the small edge
- **The edge ($1.44) < fees (~$4.50 per trade)** - this is why it loses money with fees enabled

### The Real Problem

The model's **prediction quality is too low** to overcome transaction costs. We need:
- Either: Higher win rate (50%+)
- Or: Higher profit factor (avg win / avg loss > 3x)

### ML Solutions to Improve Signal Quality

#### 1. Better Features (Most Impactful)

The current model only uses raw price patterns. Add:

```python
# Volatility regime - model may work better in certain regimes
volatility = df['close'].pct_change().rolling(20).std()
vol_regime = volatility / volatility.rolling(100).mean()

# Trend strength - filter trades against strong trends
trend = (df['close'].rolling(20).mean() - df['close'].rolling(60).mean()) / df['close']

# Volume confirmation
volume_ratio = df['volume'] / df['volume'].rolling(20).mean()
```

#### 2. Regime Detection (Filter Bad Periods)

Only trade when the model historically performs well:

```python
# High volatility regime: model predictions are more reliable
# Low volatility: too much noise, skip trading
if vol_regime < 0.8:
    position = 0  # Don't trade in low-vol regimes
```

#### 3. Replace K-Means with Gradient Boosting

K-means clustering is unsupervised - it finds patterns but doesn't optimize for profitability. LightGBM would:
- Learn which features actually predict returns
- Handle non-linear relationships
- Provide feature importance for debugging

#### 4. Multi-Signal Confirmation

Only trade when multiple timeframes agree:

```python
# Current: trade if combined prediction > threshold
# Better: trade only if ALL timeframes agree on direction
if sign(dp1) == sign(dp2) == sign(dp3) and abs(delta_p) > threshold:
    take_trade = True
```

---

**Date:** December 30, 2025
**Status:** Analysis Complete
**Problem:** Strategy loses money due to excessive trading (10,244 trades, $58k fees vs $2k gross profit)

---

## Executive Summary

The current implementation is **fundamentally sound** (positive gross P&L) but **operationally broken** (fees destroy all profit). The core issue is a signal-to-noise ratio problem at 1-minute timeframes.

**Key Metrics (Current):**
| Metric | Value |
|--------|-------|
| Gross P&L | +$2,185.38 |
| Fees | -$58,453.40 |
| Net P&L | -$56,268.02 |
| Trades | 10,244 |
| Avg Gross/Trade | $0.21 |
| Avg Fee/Trade | $5.71 |

**Root Cause:** Paying $5.71 in fees to capture $0.21 in gross profit per trade.

---

## Problem Analysis

### 1. Signal-to-Noise Ratio

At 1-minute resolution:
- Best cluster score: 0.0982 (only ~10% signal vs 90% noise)
- Price changes dominated by microstructure noise (bid-ask bounce, random order flow)
- Patterns are fitting to noise, not exploitable signals

### 2. Wrong Target Variable

Current: Predict `price[t+1] - price[t]` (next 1-min change)

This is nearly unpredictable. 1-minute price changes are dominated by:
- Market maker activity
- Random order flow
- Bid-ask bounce

### 3. Wrong Loss Function

Current: Minimize MSE between predicted and actual price change
What matters: Maximize risk-adjusted returns after transaction costs

### 4. No Cost Awareness

Model has no concept of transaction costs during training. Optimizes predictions that may be "correct" but unprofitable to trade.

---

## Recommended Improvements

### Phase 1: Quick Wins (Minimal Code Changes)

#### 1.1 Aggregate to Higher Timeframe

**Impact:** 10-15x trade reduction, better signal quality
**Effort:** Low

```python
import pandas as pd

def aggregate_timeframe(df, timeframe='15T'):
    """Aggregate 1-min data to higher timeframe."""
    df = df.set_index('timestamp')
    agg_df = df.resample(timeframe).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'imbalance_ratio': 'mean'
    }).dropna()
    return agg_df.reset_index()

# Usage:
# df_15min = aggregate_timeframe(df, '15T')  # 15-minute bars
# df_1h = aggregate_timeframe(df, '1H')      # 1-hour bars
```

**Expected Results:**
- 10,244 trades → ~680 trades (15-min) or ~170 trades (1-hour)
- Fees: $58k → ~$4k (15-min) or ~$1k (1-hour)
- Signal quality improves as noise averages out

---

### Phase 2: Better Target Variable

#### 2.1 Direction Classification

**Impact:** Better predictions, natural trade filtering
**Effort:** Medium

```python
def create_direction_target(prices, horizon=15, threshold_pct=0.1):
    """
    Target: Will price move up/down by >threshold% in next N bars?
    Classes: -1 (down), 0 (neutral/no trade), +1 (up)
    """
    future_max = pd.Series(prices).rolling(horizon).max().shift(-horizon)
    future_min = pd.Series(prices).rolling(horizon).min().shift(-horizon)

    up_move = (future_max - prices) / prices > threshold_pct / 100
    down_move = (prices - future_min) / prices > threshold_pct / 100

    target = np.where(up_move & ~down_move, 1,
                      np.where(down_move & ~up_move, -1, 0))
    return target
```

**Why this is better:**
- Class 0 (neutral) naturally filters out low-quality trades
- Predicting direction over N bars has higher SNR than next-bar change
- Classification is more robust than regression for trading

#### 2.2 Maximum Favorable Excursion (MFE)

**Impact:** Better entry timing
**Effort:** Medium

```python
def create_mfe_target(prices, horizon=60):
    """
    Target: Maximum profit achievable if entered long now.
    Helps model learn optimal entry points.
    """
    prices = pd.Series(prices)
    future_max = prices.rolling(horizon).max().shift(-horizon)
    mfe = future_max - prices
    return mfe.values
```

---

### Phase 3: Feature Engineering

#### 3.1 Technical Features

**Impact:** +20-30% prediction accuracy
**Effort:** Medium

```python
def engineer_features(df):
    """Create predictive features from OHLCV data."""

    # Returns
    df['returns'] = df['close'].pct_change()
    df['log_returns'] = np.log(df['close']).diff()

    # Volatility
    df['volatility_20'] = df['returns'].rolling(20).std()
    df['volatility_60'] = df['returns'].rolling(60).std()
    df['vol_regime'] = df['volatility_20'] / df['volatility_60']

    # Trend
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_60'] = df['close'].rolling(60).mean()
    df['trend'] = (df['sma_20'] - df['sma_60']) / df['sma_60']

    # Mean reversion
    df['zscore_20'] = (df['close'] - df['sma_20']) / (df['volatility_20'] * np.sqrt(20))

    # Volume
    df['volume_sma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma']

    # Momentum
    df['roc_10'] = df['close'].pct_change(10)
    df['roc_30'] = df['close'].pct_change(30)

    # Range/Volatility
    df['atr_14'] = calculate_atr(df, 14)
    df['range_pct'] = (df['high'] - df['low']) / df['close']

    # RSI
    df['rsi_14'] = calculate_rsi(df['close'], 14)

    return df

def calculate_atr(df, period=14):
    """Average True Range."""
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calculate_rsi(prices, period=14):
    """Relative Strength Index."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))
```

---

### Phase 4: Better Model Architecture

#### 4.1 Replace K-Means with Gradient Boosting

**Impact:** Better generalization, feature importance
**Effort:** Medium

```python
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit

def train_lgb_model(X, y, n_splits=5):
    """
    LightGBM with time-series cross-validation.
    Much better than k-means + linear regression.
    """
    params = {
        'objective': 'regression',
        'metric': 'mse',
        'boosting_type': 'gbdt',
        'num_leaves': 31,
        'learning_rate': 0.05,
        'feature_fraction': 0.8,
        'bagging_fraction': 0.8,
        'bagging_freq': 5,
        'verbose': -1,
        'n_jobs': -1
    }

    tscv = TimeSeriesSplit(n_splits=n_splits)
    models = []
    scores = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val)

        model = lgb.train(
            params,
            train_data,
            valid_sets=[val_data],
            num_boost_round=1000,
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )

        models.append(model)
        scores.append(model.best_score['valid_0']['l2'])
        print(f"Fold {fold+1}: MSE = {scores[-1]:.6f}")

    print(f"Average MSE: {np.mean(scores):.6f}")
    return models

def predict_ensemble(models, X):
    """Average predictions from all fold models."""
    predictions = np.zeros(len(X))
    for model in models:
        predictions += model.predict(X)
    return predictions / len(models)
```

#### 4.2 Classification Model for Direction

```python
def train_direction_classifier(X, y):
    """
    3-class classification: down (-1), neutral (0), up (+1)
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import classification_report

    params = {
        'n_estimators': 200,
        'max_depth': 10,
        'min_samples_leaf': 50,
        'class_weight': 'balanced',
        'n_jobs': -1
    }

    tscv = TimeSeriesSplit(n_splits=5)
    models = []

    for train_idx, val_idx in tscv.split(X):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        model = RandomForestClassifier(**params)
        model.fit(X_train, y_train)

        y_pred = model.predict(X_val)
        print(classification_report(y_val, y_pred, zero_division=0))

        models.append(model)

    return models
```

---

### Phase 5: Cost-Aware Training

#### 5.1 Custom Loss Function (PyTorch)

**Impact:** Model learns optimal trade frequency
**Effort:** High

```python
import torch
import torch.nn as nn

class TradingLoss(nn.Module):
    """
    Custom loss that incorporates transaction costs.
    Optimizes for Sharpe ratio, not MSE.
    """
    def __init__(self, fee_pct=0.0015, risk_free_rate=0.0):
        super().__init__()
        self.fee_pct = fee_pct
        self.risk_free_rate = risk_free_rate

    def forward(self, predictions, returns):
        """
        Args:
            predictions: Model outputs (interpreted as position signals)
            returns: Actual price returns
        """
        # Convert predictions to positions via tanh (smooth -1 to 1)
        positions = torch.tanh(predictions)

        # Gross PnL
        gross_pnl = positions[:-1] * returns[1:]

        # Transaction costs (proportional to position changes)
        position_changes = torch.abs(positions[1:] - positions[:-1])
        costs = position_changes * self.fee_pct

        # Net PnL
        net_pnl = gross_pnl - costs

        # Sharpe ratio (annualized, assuming minute data)
        mean_return = net_pnl.mean()
        std_return = net_pnl.std() + 1e-8
        sharpe = (mean_return - self.risk_free_rate) / std_return

        # Return negative Sharpe (we minimize loss)
        return -sharpe


class TradingNetwork(nn.Module):
    """Simple MLP for trading signals."""

    def __init__(self, input_dim, hidden_dims=[64, 32]):
        super().__init__()

        layers = []
        prev_dim = input_dim
        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.2)
            ])
            prev_dim = hidden_dim
        layers.append(nn.Linear(prev_dim, 1))

        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)
```

---

### Phase 6: Reinforcement Learning (Advanced)

#### 6.1 Trading Environment

**Impact:** Truly optimal policy
**Effort:** High

```python
import gymnasium as gym
import numpy as np

class TradingEnv(gym.Env):
    """
    RL environment for trading.
    Action: 0 (short), 1 (flat), 2 (long)
    Reward: PnL - transaction costs
    """

    def __init__(self, prices, features, fee_pct=0.0015):
        super().__init__()

        self.prices = prices
        self.features = features
        self.fee_pct = fee_pct
        self.initial_balance = 10000

        self.action_space = gym.spaces.Discrete(3)
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(features.shape[1] + 2,),  # features + position + unrealized_pnl
            dtype=np.float32
        )

        self.reset()

    def reset(self, seed=None):
        super().reset(seed=seed)
        self.current_step = 0
        self.position = 0
        self.entry_price = 0
        self.balance = self.initial_balance
        self.total_fees = 0
        return self._get_observation(), {}

    def step(self, action):
        action = action - 1  # Map {0,1,2} to {-1,0,1}

        current_price = self.prices[self.current_step]
        next_price = self.prices[self.current_step + 1]

        # Calculate reward
        price_return = (next_price - current_price) / current_price
        gross_pnl = self.position * price_return * self.balance

        # Transaction cost if position changes
        if action != self.position:
            position_change = abs(action - self.position)
            cost = position_change * current_price * self.fee_pct
            self.total_fees += cost
        else:
            cost = 0

        reward = gross_pnl - cost
        self.balance += reward

        # Update position
        if action != self.position:
            self.position = action
            self.entry_price = current_price

        self.current_step += 1
        done = self.current_step >= len(self.prices) - 2

        return self._get_observation(), reward, done, False, {
            'balance': self.balance,
            'total_fees': self.total_fees,
            'position': self.position
        }

    def _get_observation(self):
        features = self.features[self.current_step]
        unrealized_pnl = 0
        if self.position != 0:
            current_price = self.prices[self.current_step]
            unrealized_pnl = self.position * (current_price - self.entry_price) / self.entry_price

        return np.concatenate([
            features,
            [self.position, unrealized_pnl]
        ]).astype(np.float32)


# Training with Stable Baselines3
# from stable_baselines3 import PPO
#
# env = TradingEnv(prices, features)
# model = PPO("MlpPolicy", env, verbose=1, learning_rate=3e-4)
# model.learn(total_timesteps=100000)
```

---

## Implementation Priority Matrix

| Phase | Approach | Effort | Impact | Priority |
|-------|----------|--------|--------|----------|
| 1.1 | Higher timeframe | Low | Very High | **P0** |
| 1.2 | Increase threshold | Trivial | High | **P0** |
| 1.3 | Min hold period | Low | High | **P0** |
| 1.4 | Trade cooldown | Low | Medium | P1 |
| 2.1 | Direction target | Medium | High | P1 |
| 3.1 | Feature engineering | Medium | High | P1 |
| 4.1 | LightGBM model | Medium | High | P2 |
| 5.1 | Cost-aware loss | High | Very High | P2 |
| 6.1 | RL approach | High | Very High | P3 |

---

## Expected Results After Improvements

### Conservative Estimate (Phase 1 only)

| Metric | Current | After Phase 1 |
|--------|---------|---------------|
| Timeframe | 1-min | 15-min |
| Trades | 10,244 | ~800 |
| Fees | $58,453 | ~$4,800 |
| Gross P&L | $2,185 | ~$2,500 (better SNR) |
| Net P&L | -$56,268 | **~-$2,300** |

### Optimistic Estimate (Phase 1-3)

| Metric | Current | After Phase 1-3 |
|--------|---------|-----------------|
| Timeframe | 1-min | 15-min |
| Trades | 10,244 | ~400 |
| Fees | $58,453 | ~$2,400 |
| Gross P&L | $2,185 | ~$4,000 (better model) |
| Net P&L | -$56,268 | **~+$1,600** |

---

## Next Steps

1. **Immediate:** Implement Phase 1 changes (2-3 hours)
2. **This Week:** Add direction classification target
3. **Next Week:** Feature engineering + LightGBM
4. **Future:** Cost-aware training and RL exploration

---

## References

1. Shah, D., & Zhang, K. (2014). *Bayesian Regression and Bitcoin*. arXiv:1410.1231
2. Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*
3. Chan, E. (2013). *Algorithmic Trading: Winning Strategies and Their Rationale*

---

**Last Updated:** December 30, 2025
