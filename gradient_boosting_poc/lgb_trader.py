"""
LightGBM-based Trading Strategy
Implements Step 3 from improvements.md: Replace K-Means with Gradient Boosting

Key improvements over Bayesian approach:
- Supervised learning: Optimizes for actual returns
- Non-linear relationships: Captures complex patterns
- Feature importance: Provides debugging insights
- Time-series cross-validation: Proper validation for temporal data
"""

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import pickle
import hashlib


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create predictive features from OHLCV data.

    Features include:
    - Returns at multiple horizons
    - Volatility measures
    - Trend indicators
    - Volume features
    - Technical indicators
    """
    df = df.copy()

    # === Price Returns ===
    df['returns_1'] = df['close'].pct_change(1)
    df['returns_5'] = df['close'].pct_change(5)
    df['returns_10'] = df['close'].pct_change(10)
    df['returns_20'] = df['close'].pct_change(20)
    df['log_returns'] = np.log(df['close']).diff()

    # === Volatility ===
    df['volatility_10'] = df['returns_1'].rolling(10).std()
    df['volatility_20'] = df['returns_1'].rolling(20).std()
    df['volatility_60'] = df['returns_1'].rolling(60).std()
    df['vol_regime'] = df['volatility_20'] / df['volatility_60'].replace(0, np.nan)

    # === Trend ===
    df['sma_10'] = df['close'].rolling(10).mean()
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_60'] = df['close'].rolling(60).mean()
    df['trend_short'] = (df['sma_10'] - df['sma_20']) / df['close']
    df['trend_long'] = (df['sma_20'] - df['sma_60']) / df['close']

    # === Mean Reversion ===
    df['zscore_20'] = (df['close'] - df['sma_20']) / (df['volatility_20'] * np.sqrt(20) + 1e-8)
    df['zscore_60'] = (df['close'] - df['sma_60']) / (df['volatility_60'] * np.sqrt(60) + 1e-8)

    # === Volume ===
    df['volume_sma_10'] = df['volume'].rolling(10).mean()
    df['volume_sma_20'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma_20'].replace(0, np.nan)

    # === Momentum ===
    df['roc_5'] = df['close'].pct_change(5)
    df['roc_10'] = df['close'].pct_change(10)
    df['roc_20'] = df['close'].pct_change(20)

    # === Range/Volatility ===
    df['range_pct'] = (df['high'] - df['low']) / df['close']
    df['high_close'] = (df['high'] - df['close']) / df['close']
    df['close_low'] = (df['close'] - df['low']) / df['close']

    # === ATR (Average True Range) ===
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(14).mean()
    df['atr_ratio'] = df['atr_14'] / df['close']

    # === RSI ===
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-8)
    df['rsi_14'] = 100 - (100 / (1 + rs))

    # === Bollinger Bands ===
    df['bb_middle'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_middle'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_middle'] - 2 * df['bb_std']
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-8)

    # === Order Book Imbalance (if available) ===
    if 'imbalance_ratio' in df.columns:
        df['imbalance_sma_5'] = df['imbalance_ratio'].rolling(5).mean()
        df['imbalance_sma_10'] = df['imbalance_ratio'].rolling(10).mean()

    return df


def create_target(df: pd.DataFrame, horizon: int = 1, target_type: str = 'return') -> pd.Series:
    """
    Create target variable for prediction.

    Args:
        df: DataFrame with price data
        horizon: Number of bars to look ahead
        target_type: 'return' for continuous, 'direction' for classification

    Returns:
        Target series
    """
    future_close = df['close'].shift(-horizon)

    if target_type == 'return':
        # Continuous return target
        target = (future_close - df['close']) / df['close']
    elif target_type == 'direction':
        # Binary classification: 1 = up, 0 = down
        target = (future_close > df['close']).astype(int)
    elif target_type == 'direction_3class':
        # 3-class: -1 = down, 0 = neutral, 1 = up
        pct_change = (future_close - df['close']) / df['close']
        threshold = 0.001  # 0.1% threshold
        target = np.where(pct_change > threshold, 1,
                          np.where(pct_change < -threshold, -1, 0))
        target = pd.Series(target, index=df.index)
    else:
        raise ValueError(f"Unknown target_type: {target_type}")

    return target


class LightGBMTrader:
    """
    LightGBM-based trading strategy with time-series cross-validation.
    """

    FEATURE_COLS = [
        'returns_1', 'returns_5', 'returns_10', 'returns_20',
        'volatility_10', 'volatility_20', 'vol_regime',
        'trend_short', 'trend_long',
        'zscore_20', 'zscore_60',
        'volume_ratio',
        'roc_5', 'roc_10', 'roc_20',
        'range_pct', 'high_close', 'close_low',
        'atr_ratio',
        'rsi_14',
        'bb_position',
    ]

    def __init__(
        self,
        n_splits: int = 5,
        horizon: int = 1,
        params: Dict = None
    ):
        """
        Initialize LightGBM trader.

        Args:
            n_splits: Number of CV folds
            horizon: Prediction horizon in bars
            params: LightGBM parameters
        """
        self.n_splits = n_splits
        self.horizon = horizon
        self.models = []
        self.feature_importance = None

        self.params = params or {
            'objective': 'regression',
            'metric': 'mse',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': -1,
            'n_jobs': -1,
            'seed': 42
        }

    def _get_features(self, df: pd.DataFrame) -> List[str]:
        """Get available feature columns."""
        available = [c for c in self.FEATURE_COLS if c in df.columns]

        # Add imbalance features if available
        if 'imbalance_ratio' in df.columns:
            available.extend(['imbalance_ratio', 'imbalance_sma_5', 'imbalance_sma_10'])

        return available

    def fit(self, df: pd.DataFrame, verbose: bool = True) -> 'LightGBMTrader':
        """
        Train LightGBM model with time-series cross-validation.

        Args:
            df: DataFrame with engineered features
            verbose: Print training progress

        Returns:
            Self
        """
        import sys

        if verbose:
            print(f"\n{'='*60}")
            print("TRAINING LIGHTGBM MODEL")
            print(f"{'='*60}")
            sys.stdout.flush()

        # Prepare data
        feature_cols = self._get_features(df)
        target = create_target(df, horizon=self.horizon, target_type='return')

        # Remove NaN rows
        valid_mask = ~(df[feature_cols].isna().any(axis=1) | target.isna())
        X = df.loc[valid_mask, feature_cols].values
        y = target[valid_mask].values
        indices = df[valid_mask].index

        if verbose:
            print(f"Features: {len(feature_cols)}")
            print(f"Training samples: {len(X)}")
            print(f"Target horizon: {self.horizon} bars")
            sys.stdout.flush()

        # Time-series cross-validation
        tscv = TimeSeriesSplit(n_splits=self.n_splits)
        self.models = []
        scores = []
        importances = []

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            if verbose:
                print(f"\n  Fold {fold+1}/{self.n_splits}...")
                sys.stdout.flush()

            X_train, X_val = X[train_idx], X[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            train_data = lgb.Dataset(X_train, label=y_train)
            val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

            model = lgb.train(
                self.params,
                train_data,
                valid_sets=[val_data],
                num_boost_round=1000,
                callbacks=[lgb.early_stopping(50, verbose=False)]
            )

            self.models.append(model)
            val_score = model.best_score['valid_0']['l2']
            scores.append(val_score)
            importances.append(model.feature_importance(importance_type='gain'))

            if verbose:
                print(f"    MSE: {val_score:.8f}, Trees: {model.best_iteration}")
                sys.stdout.flush()

        # Average feature importance
        self.feature_importance = pd.DataFrame({
            'feature': feature_cols,
            'importance': np.mean(importances, axis=0)
        }).sort_values('importance', ascending=False)

        if verbose:
            print(f"\n  Average MSE: {np.mean(scores):.8f}")
            print(f"\n  Top 10 Features:")
            for i, row in self.feature_importance.head(10).iterrows():
                print(f"    {row['feature']}: {row['importance']:.2f}")
            print(f"\n{'='*60}")
            print("TRAINING COMPLETE")
            print(f"{'='*60}\n")
            sys.stdout.flush()

        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """
        Generate predictions using ensemble of fold models.

        Args:
            df: DataFrame with engineered features

        Returns:
            Array of predictions
        """
        feature_cols = self._get_features(df)
        X = df[feature_cols].values

        predictions = np.zeros(len(X))
        for model in self.models:
            predictions += model.predict(X)
        predictions /= len(self.models)

        return predictions

    def save(self, path: str) -> None:
        """Save model to disk."""
        with open(path, 'wb') as f:
            pickle.dump({
                'models': self.models,
                'feature_importance': self.feature_importance,
                'params': self.params,
                'horizon': self.horizon,
                'n_splits': self.n_splits
            }, f)

    @classmethod
    def load(cls, path: str) -> 'LightGBMTrader':
        """Load model from disk."""
        with open(path, 'rb') as f:
            state = pickle.load(f)

        trader = cls(
            n_splits=state['n_splits'],
            horizon=state['horizon'],
            params=state['params']
        )
        trader.models = state['models']
        trader.feature_importance = state['feature_importance']

        return trader


class TradingStrategy:
    """
    Trading strategy using LightGBM predictions.
    """

    def __init__(self, threshold: float = 0.0001):
        """
        Initialize strategy.

        Args:
            threshold: Minimum predicted return to trigger trade
        """
        self.threshold = threshold
        self.position = 0
        self.trades = []
        self.entry_price = None

    def decide(self, prediction: float, current_price: float, timestamp: int) -> str:
        """
        Make trading decision based on prediction.

        Args:
            prediction: Predicted return
            current_price: Current price
            timestamp: Current time index

        Returns:
            Action string
        """
        action = "HOLD"

        if prediction > self.threshold and self.position <= 0:
            action = "BUY"
            if self.position == -1:
                self.trades.append({
                    'type': 'CLOSE_SHORT',
                    'price': current_price,
                    'timestamp': timestamp,
                    'entry_price': self.entry_price,
                    'pnl': self.entry_price - current_price
                })

            self.position = 1
            self.entry_price = current_price
            self.trades.append({
                'type': 'OPEN_LONG',
                'price': current_price,
                'timestamp': timestamp,
                'entry_price': current_price,
                'pnl': 0.0
            })

        elif prediction < -self.threshold and self.position >= 0:
            action = "SELL"
            if self.position == 1:
                self.trades.append({
                    'type': 'CLOSE_LONG',
                    'price': current_price,
                    'timestamp': timestamp,
                    'entry_price': self.entry_price,
                    'pnl': current_price - self.entry_price
                })

            self.position = -1
            self.entry_price = current_price
            self.trades.append({
                'type': 'OPEN_SHORT',
                'price': current_price,
                'timestamp': timestamp,
                'entry_price': current_price,
                'pnl': 0.0
            })

        return action

    def close_position(self, current_price: float, timestamp: int):
        """Close any open position."""
        if self.position == 1:
            self.trades.append({
                'type': 'CLOSE_LONG',
                'price': current_price,
                'timestamp': timestamp,
                'entry_price': self.entry_price,
                'pnl': current_price - self.entry_price
            })
            self.position = 0
        elif self.position == -1:
            self.trades.append({
                'type': 'CLOSE_SHORT',
                'price': current_price,
                'timestamp': timestamp,
                'entry_price': self.entry_price,
                'pnl': self.entry_price - current_price
            })
            self.position = 0


class TradingStrategyWithStops:
    """
    Enhanced trading strategy with dynamic stop-loss support.

    Supports pluggable stop strategies:
    - prediction_reversal: Exit when model prediction flips
    - atr_trailing: Volatility-adjusted trailing stop
    - both: Combine multiple strategies
    """

    def __init__(self, threshold: float = 0.0001, stop_strategy=None):
        """
        Initialize strategy with stop-loss.

        Args:
            threshold: Minimum predicted return to trigger trade
            stop_strategy: StopLossStrategy instance (from stop_strategies.py)
        """
        self.threshold = threshold
        self.position = 0
        self.trades = []
        self.entry_price = None
        self.entry_timestamp = None
        self.bars_in_trade = 0

        # Stop-loss strategy (import lazily to avoid circular imports)
        if stop_strategy is None:
            from stop_strategies import create_stop_strategy
            self.stop_strategy = create_stop_strategy("prediction_reversal")
        else:
            self.stop_strategy = stop_strategy

        # Stats tracking
        self.stop_exits = 0
        self.signal_exits = 0

    def _create_stop_context(self, prediction: float, current_price: float,
                             atr: float, timestamp: int):
        """Create context for stop-loss evaluation."""
        from stop_strategies import StopContext

        return StopContext(
            position=self.position,
            entry_price=self.entry_price or current_price,
            current_price=current_price,
            prediction=prediction,
            atr=atr,
            timestamp=timestamp,
            bars_in_trade=self.bars_in_trade
        )

    def _close_position(self, current_price: float, timestamp: int,
                        exit_reason: str) -> None:
        """Close current position and record trade."""
        if self.position == 0:
            return

        if self.position == 1:
            pnl = current_price - self.entry_price
            trade_type = 'CLOSE_LONG'
        else:
            pnl = self.entry_price - current_price
            trade_type = 'CLOSE_SHORT'

        self.trades.append({
            'type': trade_type,
            'price': current_price,
            'timestamp': timestamp,
            'entry_price': self.entry_price,
            'entry_timestamp': self.entry_timestamp,
            'pnl': pnl,
            'exit_reason': exit_reason,
            'bars_held': self.bars_in_trade
        })

        # Track exit type
        if exit_reason.startswith(self.stop_strategy.name):
            self.stop_exits += 1
        else:
            self.signal_exits += 1

        # Notify stop strategy
        self.stop_strategy.on_exit()

        # Reset position state
        self.position = 0
        self.entry_price = None
        self.entry_timestamp = None
        self.bars_in_trade = 0

    def _open_position(self, direction: int, current_price: float,
                       timestamp: int, prediction: float, atr: float) -> None:
        """Open a new position."""
        self.position = direction
        self.entry_price = current_price
        self.entry_timestamp = timestamp
        self.bars_in_trade = 0

        trade_type = 'OPEN_LONG' if direction == 1 else 'OPEN_SHORT'
        self.trades.append({
            'type': trade_type,
            'price': current_price,
            'timestamp': timestamp,
            'entry_price': current_price,
            'pnl': 0.0
        })

        # Notify stop strategy of entry
        ctx = self._create_stop_context(prediction, current_price, atr, timestamp)
        self.stop_strategy.on_entry(ctx)

    def decide(self, prediction: float, current_price: float, timestamp: int,
               atr: float = 0.0) -> str:
        """
        Make trading decision with stop-loss checking.

        Args:
            prediction: LightGBM predicted return
            current_price: Current price
            timestamp: Current time index
            atr: Current ATR value (for ATR-based stops)

        Returns:
            Action string: 'BUY', 'SELL', 'STOP_EXIT', or 'HOLD'
        """
        # Increment bars in trade
        if self.position != 0:
            self.bars_in_trade += 1

        # Check stop-loss first (before signal logic)
        if self.position != 0:
            ctx = self._create_stop_context(prediction, current_price, atr, timestamp)
            should_exit, exit_reason = self.stop_strategy.should_exit(ctx)

            if should_exit:
                self._close_position(current_price, timestamp, exit_reason)
                return "STOP_EXIT"

        # Entry/reversal logic (same as base strategy)
        action = "HOLD"

        if prediction > self.threshold and self.position <= 0:
            # Close short if exists
            if self.position == -1:
                self._close_position(current_price, timestamp, "signal_reversal")

            # Open long
            self._open_position(1, current_price, timestamp, prediction, atr)
            action = "BUY"

        elif prediction < -self.threshold and self.position >= 0:
            # Close long if exists
            if self.position == 1:
                self._close_position(current_price, timestamp, "signal_reversal")

            # Open short
            self._open_position(-1, current_price, timestamp, prediction, atr)
            action = "SELL"

        return action

    def close_position(self, current_price: float, timestamp: int) -> None:
        """Close any open position at end of backtest."""
        if self.position != 0:
            self._close_position(current_price, timestamp, "end_of_period")

    def get_stop_stats(self) -> Dict:
        """Get statistics on stop-loss exits."""
        closes = [t for t in self.trades if 'CLOSE' in t['type']]
        if not closes:
            return {}

        stop_trades = [t for t in closes if t.get('exit_reason', '').startswith(self.stop_strategy.name)]
        signal_trades = [t for t in closes if t.get('exit_reason') == 'signal_reversal']

        stop_pnls = [t['pnl'] for t in stop_trades]
        signal_pnls = [t['pnl'] for t in signal_trades]

        return {
            'total_exits': len(closes),
            'stop_exits': len(stop_trades),
            'signal_exits': len(signal_trades),
            'stop_exit_pct': len(stop_trades) / len(closes) * 100 if closes else 0,
            'avg_stop_pnl': np.mean(stop_pnls) if stop_pnls else 0,
            'avg_signal_pnl': np.mean(signal_pnls) if signal_pnls else 0,
            'stop_win_rate': np.mean([p > 0 for p in stop_pnls]) * 100 if stop_pnls else 0,
            'signal_win_rate': np.mean([p > 0 for p in signal_pnls]) * 100 if signal_pnls else 0,
        }


def run_backtest(
    df: pd.DataFrame,
    model: LightGBMTrader,
    threshold: float = 0.0001,
    start_idx: int = 0,
    stop_strategy=None
) -> Tuple[List[Dict], List[Dict], Optional[Dict]]:
    """
    Run backtest with LightGBM predictions and optional stop-loss.

    Args:
        df: DataFrame with engineered features
        model: Trained LightGBM model
        threshold: Trading threshold
        start_idx: Start index for backtest
        stop_strategy: StopLossStrategy instance (None = no stops)

    Returns:
        Tuple of (results, trades, stop_stats)
    """
    import sys

    use_stops = stop_strategy is not None

    print(f"\n{'='*60}")
    print("RUNNING BACKTEST" + (" WITH STOPS" if use_stops else ""))
    print(f"{'='*60}")
    print(f"Test period: {len(df)} data points")
    print(f"Threshold: {threshold}")
    if use_stops:
        print(f"Stop Strategy: {stop_strategy.name}")
    sys.stdout.flush()

    # Generate predictions for all data
    predictions = model.predict(df)

    # Choose strategy based on whether we have stops
    if use_stops:
        strategy = TradingStrategyWithStops(threshold, stop_strategy)
    else:
        strategy = TradingStrategy(threshold)

    results = []

    prices = df['close'].values
    atrs = df['atr_14'].values if 'atr_14' in df.columns else np.zeros(len(df))
    total_steps = len(df) - start_idx

    print(f"[LOG] Running {total_steps} predictions...")
    sys.stdout.flush()

    progress_interval = max(1, total_steps // 10)

    for idx in range(start_idx, len(df)):
        rel_idx = idx - start_idx

        if rel_idx % progress_interval == 0:
            print(f"  Progress: {rel_idx}/{total_steps} ({rel_idx/total_steps*100:.0f}%)")
            sys.stdout.flush()

        pred = predictions[idx]
        price = prices[idx]
        atr = atrs[idx] if not np.isnan(atrs[idx]) else 0.0

        # Call appropriate decide method
        if use_stops:
            action = strategy.decide(pred, price, idx, atr)
        else:
            action = strategy.decide(pred, price, idx)

        results.append({
            'timestamp': idx,
            'price': price,
            'prediction': pred,
            'atr': atr,
            'action': action,
            'position': strategy.position
        })

    # Close any remaining position
    if strategy.position != 0:
        strategy.close_position(prices[-1], len(prices) - 1)

    # Get stop stats if using stops
    stop_stats = None
    if use_stops:
        stop_stats = strategy.get_stop_stats()
        print(f"\n[OK] Backtest complete")
        print(f"Total trades: {len(strategy.trades)}")
        print(f"Stop exits: {stop_stats.get('stop_exits', 0)} ({stop_stats.get('stop_exit_pct', 0):.1f}%)")
        print(f"Signal exits: {stop_stats.get('signal_exits', 0)}")
    else:
        print(f"\n[OK] Backtest complete")
        print(f"Total trades: {len(strategy.trades)}")

    print(f"{'='*60}\n")
    sys.stdout.flush()

    return results, strategy.trades, stop_stats


def calculate_metrics(trades: List[Dict], start_price: float, end_price: float) -> Dict:
    """Calculate performance metrics."""
    if len(trades) == 0:
        return {}

    completed_trades = [t for t in trades if 'CLOSE' in t['type']]
    if len(completed_trades) == 0:
        return {}

    profits = np.array([t['pnl'] for t in completed_trades])
    total_profit = np.sum(profits)
    avg_profit = np.mean(profits)
    win_rate = np.mean(profits > 0)

    # Winners and losers
    winners = profits[profits > 0]
    losers = profits[profits <= 0]
    avg_win = np.mean(winners) if len(winners) > 0 else 0
    avg_loss = np.mean(losers) if len(losers) > 0 else 0

    # Sharpe ratio
    C = abs(end_price - start_price)
    L = len(completed_trades)
    std_profit = np.std(profits)

    if std_profit == 0 or L == 0:
        sharpe = 0.0
    else:
        sharpe = (total_profit - C) / (L * std_profit)

    # Max drawdown
    cumulative = np.cumsum(profits)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0

    return {
        'total_trades': len(trades),
        'completed_trades': len(completed_trades),
        'total_profit': total_profit,
        'avg_profit_per_trade': avg_profit,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': abs(avg_win / avg_loss) if avg_loss != 0 else float('inf'),
        'max_profit': np.max(profits),
        'max_loss': np.min(profits),
        'profit_std': std_profit,
        'sharpe_ratio': sharpe,
        'max_drawdown': max_drawdown,
        'buy_hold_return': C,
        'return_pct': (total_profit / start_price) * 100 if start_price > 0 else 0
    }


def print_performance_report(metrics: Dict, test_period_days: float):
    """Print formatted performance report."""
    print(f"\n{'='*60}")
    print("PERFORMANCE REPORT")
    print(f"{'='*60}")
    print(f"Test Period: {test_period_days:.1f} days")
    print(f"\nTRADING ACTIVITY:")
    print(f"  Total Trades: {metrics.get('total_trades', 0)}")
    print(f"  Completed Trades: {metrics.get('completed_trades', 0)}")
    print(f"\nPROFITABILITY:")
    print(f"  Total Profit: ${metrics.get('total_profit', 0):.2f}")
    print(f"  Return: {metrics.get('return_pct', 0):.2f}%")
    print(f"  Avg Profit/Trade: ${metrics.get('avg_profit_per_trade', 0):.2f}")
    print(f"  Win Rate: {metrics.get('win_rate', 0)*100:.1f}%")
    print(f"  Avg Win: ${metrics.get('avg_win', 0):.2f}")
    print(f"  Avg Loss: ${metrics.get('avg_loss', 0):.2f}")
    print(f"  Profit Factor: {metrics.get('profit_factor', 0):.2f}x")
    print(f"\nRISK METRICS:")
    print(f"  Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"  Max Drawdown: ${metrics.get('max_drawdown', 0):.2f}")
    print(f"  Profit Std Dev: ${metrics.get('profit_std', 0):.2f}")
    print(f"\nBENCHMARK:")
    print(f"  Buy & Hold: ${metrics.get('buy_hold_return', 0):.2f}")
    print(f"{'='*60}\n")
