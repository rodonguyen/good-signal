"""
Bayesian Regression Trading POC - Enhanced Version
Implements improvements from improvements.md:

Step 1: Better Features
- Volatility regime (vol_regime)
- Trend strength
- Volume confirmation

Step 2: Regime Detection
- Only trade in high-volatility regimes (vol_regime >= 0.8)
- Skip low-volatility noise periods
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt

from bayesian_trader import (
    BayesianBitcoinTrader,
    run_backtest,
    calculate_metrics,
    print_performance_report,
    FeeConfig,
    TradingStrategy,
)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Step 1: Create predictive features from OHLCV data.

    Features added:
    - volatility_20: 20-bar rolling volatility
    - volatility_60: 60-bar rolling volatility (baseline)
    - vol_regime: volatility ratio (current vs baseline)
    - trend: SMA20 - SMA60 normalized
    - volume_ratio: current volume vs 20-bar average
    """
    df = df.copy()

    # Returns
    df['returns'] = df['close'].pct_change()

    # Volatility
    df['volatility_20'] = df['returns'].rolling(20).std()
    df['volatility_60'] = df['returns'].rolling(60).std()
    # Avoid division by zero
    df['vol_regime'] = df['volatility_20'] / df['volatility_60'].replace(0, np.nan)

    # Trend: normalized difference between short and long SMA
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_60'] = df['close'].rolling(60).mean()
    df['trend'] = (df['sma_20'] - df['sma_60']) / df['close']

    # Volume confirmation
    df['volume_sma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma'].replace(0, np.nan)

    return df


class RegimeAwareTradingStrategy(TradingStrategy):
    """
    Step 2: Enhanced trading strategy with regime detection.
    Only trades when volatility regime is favorable.
    """

    def __init__(self, threshold: float, vol_regime_min: float = 0.8):
        """
        Initialize strategy with regime filter.

        Args:
            threshold: Minimum predicted change to trigger trade
            vol_regime_min: Minimum volatility regime to allow trading (default 0.8)
        """
        super().__init__(threshold)
        self.vol_regime_min = vol_regime_min
        self.regime_filtered_count = 0

    def decide_with_regime(self, delta_p: float, current_price: float,
                           timestamp: int, vol_regime: float) -> str:
        """
        Make trading decision with regime filtering.

        Args:
            delta_p: Predicted price change
            current_price: Current market price
            timestamp: Current time index
            vol_regime: Current volatility regime ratio

        Returns:
            Action string: 'BUY', 'SELL', 'HOLD', or 'REGIME_FILTERED'
        """
        # Step 2: Regime Detection - skip low-volatility periods
        if vol_regime < self.vol_regime_min or np.isnan(vol_regime):
            self.regime_filtered_count += 1
            # If we have a position, keep it (don't exit just because regime changed)
            return "REGIME_FILTERED"

        # Otherwise, use normal trading logic
        return self.decide(delta_p, current_price, timestamp)


def run_backtest_enhanced(
    test_df: pd.DataFrame,
    model: BayesianBitcoinTrader,
    threshold: float,
    vol_regime_min: float = 0.8
):
    """
    Run backtest with feature engineering and regime detection.

    Args:
        test_df: Test dataframe with engineered features
        model: Trained Bayesian model
        threshold: Trading threshold
        vol_regime_min: Minimum vol regime for trading

    Returns:
        Tuple of (results, trades, strategy)
    """
    import sys

    print(f"\n{'='*60}")
    print("RUNNING ENHANCED BACKTEST")
    print(f"{'='*60}")
    print(f"Test period: {len(test_df)} data points")
    print(f"Threshold: {threshold}")
    print(f"Vol Regime Min: {vol_regime_min}")
    sys.stdout.flush()

    test_prices = test_df['close'].values
    test_imbalance = test_df['imbalance_ratio'].values if 'imbalance_ratio' in test_df.columns else None
    vol_regimes = test_df['vol_regime'].values

    strategy = RegimeAwareTradingStrategy(threshold, vol_regime_min)
    results = []

    lookback_max = max(model.window_sizes)
    total_steps = len(test_prices) - lookback_max

    print(f"[LOG] Running {total_steps} predictions with regime filter...")
    sys.stdout.flush()

    progress_interval = max(1, total_steps // 10)

    for idx, t in enumerate(range(lookback_max, len(test_prices))):
        if idx % progress_interval == 0:
            print(f"  Progress: {idx}/{total_steps} ({idx/total_steps*100:.0f}%)")
            sys.stdout.flush()

        # Get features
        r = test_imbalance[t] if test_imbalance is not None else 0.0
        vol_regime = vol_regimes[t]

        # Generate prediction
        delta_p = model.predict(test_prices, t, r)

        # Execute decision with regime filtering
        current_price = test_prices[t]
        action = strategy.decide_with_regime(delta_p, current_price, t, vol_regime)

        results.append({
            'timestamp': t,
            'price': current_price,
            'prediction': delta_p,
            'vol_regime': vol_regime,
            'action': action,
            'position': strategy.position
        })

    # Close any remaining position
    if strategy.position != 0:
        strategy.close_position(test_prices[-1], len(test_prices) - 1)

    print(f"\n[OK] Enhanced backtest complete")
    print(f"Total trades: {len(strategy.trades)}")
    print(f"Regime filtered signals: {strategy.regime_filtered_count}")
    print(f"{'='*60}\n")
    sys.stdout.flush()

    return results, strategy.trades, strategy


def load_data(data_path: str) -> pd.DataFrame:
    """Load and validate data."""
    print(f"Loading data from: {data_path}")
    df = pd.read_csv(data_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    print(f"[OK] Loaded {len(df)} rows")
    print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"  Columns: {list(df.columns)}")

    if df.isnull().any().any():
        print(f"  WARNING: Found {df.isnull().sum().sum()} null values")
        print("  Filling nulls with forward fill...")
        df = df.fillna(method='ffill').fillna(method='bfill')

    return df


def split_data(df: pd.DataFrame, train_ratio: float = 2/3) -> tuple:
    """Split data into train and test sets."""
    n = len(df)
    split_idx = int(n * train_ratio)

    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    print(f"\n{'='*60}")
    print("DATA SPLIT")
    print(f"{'='*60}")
    print(f"Total data: {n} rows")
    print(f"\nTRAIN SET: {len(train_df)} rows ({len(train_df)/n*100:.1f}%)")
    print(f"  From: {train_df['timestamp'].min()}")
    print(f"  To:   {train_df['timestamp'].max()}")
    print(f"\nTEST SET: {len(test_df)} rows ({len(test_df)/n*100:.1f}%)")
    print(f"  From: {test_df['timestamp'].min()}")
    print(f"  To:   {test_df['timestamp'].max()}")
    print(f"{'='*60}\n")

    return train_df, test_df


def plot_results(test_df: pd.DataFrame, results: list, metrics: dict,
                 output_path: str = None, config: dict = None, strategy = None):
    """Plot backtest results with regime info."""
    results_df = pd.DataFrame(results)

    # Calculate cumulative P&L
    positions = results_df['position'].values
    prices = results_df['price'].values
    price_changes = np.diff(prices, prepend=prices[0])
    pnl = positions[:-1] * price_changes[1:]
    cumulative_pnl = np.cumsum(np.concatenate([[0], pnl]))

    fig, axes = plt.subplots(4, 1, figsize=(14, 16))

    if config:
        config_text = (
            f"Config: Timeframe={config.get('timeframe', 'N/A')} | "
            f"Vol Regime Min={config.get('vol_regime_min', 'N/A')} | "
            f"Threshold={config.get('threshold', 'N/A')}"
        )
        results_text = (
            f"Results: Gross=${metrics.get('total_gross_profit', metrics.get('total_profit', 0)):.2f} | "
            f"Trades={metrics.get('completed_trades', 0)} | "
            f"Win Rate={metrics.get('win_rate', 0)*100:.1f}%"
        )
        if strategy:
            results_text += f" | Regime Filtered={strategy.regime_filtered_count}"
        fig.suptitle(f"{config_text}\n{results_text}", fontsize=10, y=0.98)

    # Plot 1: Price and Position
    ax1 = axes[0]
    ax1.plot(prices, label='Price', color='black', linewidth=1)
    ax1_twin = ax1.twinx()

    long_mask = positions == 1
    short_mask = positions == -1

    ax1_twin.fill_between(range(len(positions)), 0, positions,
                          where=long_mask, color='green', alpha=0.3, label='Long')
    ax1_twin.fill_between(range(len(positions)), 0, positions,
                          where=short_mask, color='red', alpha=0.3, label='Short')

    ax1.set_xlabel('Time Step')
    ax1.set_ylabel('Price')
    ax1_twin.set_ylabel('Position')
    ax1.set_title('Price and Trading Positions')
    ax1.legend(loc='upper left')
    ax1_twin.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)

    # Plot 2: Volatility Regime
    ax2 = axes[1]
    vol_regimes = results_df['vol_regime'].values
    ax2.plot(vol_regimes, label='Vol Regime', color='blue', linewidth=1)
    ax2.axhline(y=config.get('vol_regime_min', 0.8), color='red',
                linestyle='--', label=f"Min Threshold ({config.get('vol_regime_min', 0.8)})")
    ax2.fill_between(range(len(vol_regimes)), 0, vol_regimes,
                     where=vol_regimes >= config.get('vol_regime_min', 0.8),
                     color='green', alpha=0.2, label='Trading Allowed')
    ax2.fill_between(range(len(vol_regimes)), 0, vol_regimes,
                     where=vol_regimes < config.get('vol_regime_min', 0.8),
                     color='red', alpha=0.2, label='Trading Blocked')
    ax2.set_xlabel('Time Step')
    ax2.set_ylabel('Vol Regime')
    ax2.set_title('Volatility Regime (20-bar vol / 60-bar vol)')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)

    # Plot 3: Cumulative P&L
    ax3 = axes[2]
    ax3.plot(cumulative_pnl, color='blue', linewidth=2)
    ax3.axhline(y=0, color='black', linestyle='--', alpha=0.5)
    ax3.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl,
                     where=cumulative_pnl >= 0, color='green', alpha=0.3)
    ax3.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl,
                     where=cumulative_pnl < 0, color='red', alpha=0.3)
    ax3.set_xlabel('Time Step')
    ax3.set_ylabel('Cumulative P&L ($)')
    gross_pnl = metrics.get('total_gross_profit', metrics.get('total_profit', 0))
    ax3.set_title(f'Cumulative P&L (GROSS) - ${gross_pnl:.2f}')
    ax3.grid(True, alpha=0.3)

    # Plot 4: Trade Distribution
    ax4 = axes[3]
    actions = results_df['action'].values
    action_counts = pd.Series(actions).value_counts()
    colors = {'BUY': 'green', 'SELL': 'red', 'HOLD': 'gray', 'REGIME_FILTERED': 'orange'}
    bars = ax4.bar(action_counts.index, action_counts.values,
                   color=[colors.get(a, 'blue') for a in action_counts.index])
    ax4.set_xlabel('Action')
    ax4.set_ylabel('Count')
    ax4.set_title('Action Distribution')
    ax4.grid(True, alpha=0.3, axis='y')

    # Add count labels on bars
    for bar, count in zip(bars, action_counts.values):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                 str(count), ha='center', va='bottom')

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"[OK] Plot saved to: {output_path}")

    plt.show()


def main():
    """Main execution function for enhanced version."""
    import sys

    print(f"\n{'='*60}")
    print("BAYESIAN REGRESSION TRADING - ENHANCED VERSION")
    print("Step 1: Better Features + Step 2: Regime Detection")
    print(f"{'='*60}\n")
    sys.stdout.flush()

    # Configuration
    data_path = "E:/Personal/GitHub/good-signal/bayesian_method_poc/ETHUSDT_15min_with_imbalance.csv"
    window_sizes = [12, 24, 48]  # 3hr, 6hr, 12hr
    n_clusters = 100
    n_select = 20
    threshold = 0.12
    vol_regime_min = 0.8  # Step 2: Only trade when vol_regime >= 0.8

    print(f"[LOG] Configuration:")
    print(f"  Window sizes: {window_sizes} bars")
    print(f"  Clusters: {n_clusters}, Select: {n_select}")
    print(f"  Threshold: {threshold}")
    print(f"  Vol Regime Min: {vol_regime_min}")
    sys.stdout.flush()

    # Load data
    print(f"\n[LOG] Loading data...")
    sys.stdout.flush()
    df = load_data(data_path)

    # Step 1: Engineer features
    print(f"\n[LOG] Engineering features (Step 1)...")
    sys.stdout.flush()
    df = engineer_features(df)

    # Show feature statistics
    print(f"\nFeature Statistics:")
    print(f"  vol_regime: mean={df['vol_regime'].mean():.3f}, std={df['vol_regime'].std():.3f}")
    print(f"  trend: mean={df['trend'].mean():.6f}, std={df['trend'].std():.6f}")
    print(f"  volume_ratio: mean={df['volume_ratio'].mean():.3f}, std={df['volume_ratio'].std():.3f}")

    # Count how many bars are in trading regime
    trading_bars = (df['vol_regime'] >= vol_regime_min).sum()
    total_bars = len(df.dropna())
    print(f"\n  Trading regime bars: {trading_bars}/{total_bars} ({trading_bars/total_bars*100:.1f}%)")
    sys.stdout.flush()

    # Split data
    train_df, test_df = split_data(df, train_ratio=2/3)

    # Extract training data
    train_prices = train_df['close'].values
    train_imbalance = train_df['imbalance_ratio'].values if 'imbalance_ratio' in train_df.columns else None

    # Initialize and train model
    print(f"\n[LOG] Initializing Bayesian model...")
    sys.stdout.flush()
    model = BayesianBitcoinTrader(
        window_sizes=window_sizes,
        n_clusters=n_clusters,
        n_select=n_select
    )

    print(f"[LOG] Training model...")
    sys.stdout.flush()
    model.fit_with_cache(train_prices, train_imbalance)

    # Run enhanced backtest with regime detection
    print(f"\n[LOG] Running enhanced backtest with regime detection (Step 2)...")
    sys.stdout.flush()

    results, trades, strategy = run_backtest_enhanced(
        test_df=test_df,
        model=model,
        threshold=threshold,
        vol_regime_min=vol_regime_min
    )

    # Calculate metrics
    print(f"\n[LOG] Calculating performance metrics...")
    sys.stdout.flush()
    test_prices = test_df['close'].values
    start_price = test_prices[max(window_sizes)]
    end_price = test_prices[-1]

    metrics = calculate_metrics(trades, start_price, end_price)

    # Calculate test period duration
    test_duration = (test_df['timestamp'].max() - test_df['timestamp'].min()).total_seconds() / 86400

    # Print performance report
    print_performance_report(metrics, test_duration)

    # Additional regime stats
    print(f"\nREGIME DETECTION STATS:")
    print(f"  Vol Regime Min Threshold: {vol_regime_min}")
    print(f"  Signals Filtered by Regime: {strategy.regime_filtered_count}")
    total_signals = len([r for r in results if r['action'] in ['BUY', 'SELL', 'REGIME_FILTERED']])
    if total_signals > 0:
        print(f"  Filter Rate: {strategy.regime_filtered_count/total_signals*100:.1f}%")

    # Save results
    output_dir = Path("E:/Personal/GitHub/good-signal/bayesian_method_poc/results")
    output_dir.mkdir(exist_ok=True)

    # Plot results
    plot_path = output_dir / f"enhanced_performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plot_config = {
        'timeframe': '15-min',
        'window_sizes': window_sizes,
        'n_clusters': n_clusters,
        'n_select': n_select,
        'threshold': threshold,
        'vol_regime_min': vol_regime_min,
    }
    try:
        plot_results(test_df, results, metrics, str(plot_path), config=plot_config, strategy=strategy)
    except Exception as e:
        print(f"[WARNING] Could not generate plot: {e}")

    # Summary
    print(f"\n{'='*60}")
    print("ENHANCED VERSION COMPLETE")
    print(f"{'='*60}")
    print(f"Improvements Applied:")
    print(f"  Step 1: Feature Engineering (vol_regime, trend, volume_ratio)")
    print(f"  Step 2: Regime Detection (vol_regime >= {vol_regime_min})")
    print(f"\nResults:")
    print(f"  Trades: {metrics.get('completed_trades', 0)}")
    print(f"  Gross P&L: ${metrics.get('total_gross_profit', metrics.get('total_profit', 0)):.2f}")
    print(f"  Win Rate: {metrics.get('win_rate', 0)*100:.1f}%")
    print(f"  Signals Filtered: {strategy.regime_filtered_count}")

    return metrics, strategy


if __name__ == "__main__":
    main()
