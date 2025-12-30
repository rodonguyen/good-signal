"""
LightGBM Trading POC - Main Script
Implements Step 3 from improvements.md: Replace K-Means with Gradient Boosting

This replaces the Bayesian k-means clustering approach with LightGBM,
providing supervised learning that optimizes for actual returns.

Stop-Loss Strategies Available:
- "none": No stop-loss (baseline)
- "prediction_reversal": Exit when prediction flips (DEFAULT)
- "atr_trailing": Volatility-adjusted trailing stop
- "both": Combine prediction reversal + ATR trailing
- "all": All strategies combined
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt

from lgb_trader import (
    LightGBMTrader,
    engineer_features,
    run_backtest,
    calculate_metrics,
    print_performance_report
)
from stop_strategies import create_stop_strategy


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
                 output_path: str = None, feature_importance: pd.DataFrame = None):
    """Plot backtest results with feature importance."""
    results_df = pd.DataFrame(results)

    # Calculate cumulative P&L
    positions = results_df['position'].values
    prices = results_df['price'].values
    price_changes = np.diff(prices, prepend=prices[0])
    pnl = positions[:-1] * price_changes[1:]
    cumulative_pnl = np.cumsum(np.concatenate([[0], pnl]))

    n_plots = 4 if feature_importance is not None else 3
    fig, axes = plt.subplots(n_plots, 1, figsize=(14, 4 * n_plots))

    # Title
    title = (
        f"LightGBM Trading Results | "
        f"Profit=${metrics.get('total_profit', 0):.2f} | "
        f"Trades={metrics.get('completed_trades', 0)} | "
        f"Win Rate={metrics.get('win_rate', 0)*100:.1f}%"
    )
    fig.suptitle(title, fontsize=12, y=0.98)

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

    # Plot 2: Cumulative P&L
    ax2 = axes[1]
    ax2.plot(cumulative_pnl, color='blue', linewidth=2)
    ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
    ax2.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl,
                     where=cumulative_pnl >= 0, color='green', alpha=0.3)
    ax2.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl,
                     where=cumulative_pnl < 0, color='red', alpha=0.3)
    ax2.set_xlabel('Time Step')
    ax2.set_ylabel('Cumulative P&L ($)')
    ax2.set_title(f'Cumulative P&L - ${metrics.get("total_profit", 0):.2f}')
    ax2.grid(True, alpha=0.3)

    # Plot 3: Predictions Distribution
    ax3 = axes[2]
    predictions = results_df['prediction'].values
    ax3.hist(predictions, bins=100, edgecolor='black', alpha=0.7)
    ax3.axvline(x=0, color='red', linestyle='--', label='Zero')
    ax3.set_xlabel('Predicted Return')
    ax3.set_ylabel('Frequency')
    ax3.set_title('Prediction Distribution')
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # Plot 4: Feature Importance
    if feature_importance is not None:
        ax4 = axes[3]
        top_features = feature_importance.head(15)
        bars = ax4.barh(top_features['feature'], top_features['importance'])
        ax4.set_xlabel('Importance (Gain)')
        ax4.set_title('Top 15 Feature Importance')
        ax4.invert_yaxis()
        ax4.grid(True, alpha=0.3, axis='x')

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"[OK] Plot saved to: {output_path}")

    plt.show()


def main():
    """Main execution function."""
    import sys

    print(f"\n{'='*60}")
    print("LIGHTGBM TRADING POC")
    print("Step 3: Replace K-Means with Gradient Boosting")
    print(f"{'='*60}\n")
    sys.stdout.flush()

    # =================================================================
    # CONFIGURATION - Easy to modify
    # =================================================================
    data_path = "E:/Personal/GitHub/good-signal/bayesian_method_poc/ETHUSDT_15min_with_imbalance.csv"
    n_splits = 5
    horizon = 4  # Predict 4 bars ahead (1 hour)
    threshold = 0.0005  # 0.05% minimum predicted return

    # -----------------------------------------------------------------
    # STOP-LOSS STRATEGY CONFIGURATION
    # Options: "none", "prediction_reversal", "atr_trailing", "both", "all"
    # -----------------------------------------------------------------
    STOP_STRATEGY = "prediction_reversal"  # <-- CHANGE THIS TO SWITCH STRATEGIES

    # Strategy-specific parameters
    stop_params = {
        "threshold": 0.0,       # For prediction_reversal: min prediction to trigger
        "min_bars": 1,          # Minimum bars before stop can trigger
        "atr_multiplier": 2.0,  # For atr_trailing: stop distance in ATR units
        "max_loss_pct": 2.0,    # For max_drawdown: max allowed loss %
        "max_bars": 96,         # For time_based: max bars to hold
    }
    # =================================================================

    # Create stop strategy
    stop_strategy = create_stop_strategy(STOP_STRATEGY, **stop_params)

    print(f"[LOG] Configuration:")
    print(f"  Data: {data_path}")
    print(f"  CV Folds: {n_splits}")
    print(f"  Prediction Horizon: {horizon} bars")
    print(f"  Trading Threshold: {threshold*100:.4f}%")
    print(f"  Stop Strategy: {stop_strategy.name}")
    sys.stdout.flush()

    # Load data
    print(f"\n[LOG] Loading data...")
    sys.stdout.flush()
    df = load_data(data_path)

    # Engineer features
    print(f"\n[LOG] Engineering features...")
    sys.stdout.flush()
    df = engineer_features(df)

    # Show feature statistics
    print(f"\n[LOG] Feature Statistics:")
    feature_cols = ['returns_1', 'volatility_20', 'vol_regime', 'trend_short', 'rsi_14']
    for col in feature_cols:
        if col in df.columns:
            print(f"  {col}: mean={df[col].mean():.6f}, std={df[col].std():.6f}")
    sys.stdout.flush()

    # Split data
    train_df, test_df = split_data(df, train_ratio=2/3)

    # Initialize and train model
    print(f"\n[LOG] Initializing LightGBM model...")
    sys.stdout.flush()

    model = LightGBMTrader(n_splits=n_splits, horizon=horizon)

    # Train on training data
    print(f"[LOG] Training model...")
    sys.stdout.flush()
    model.fit(train_df)

    # Run backtest on test set
    print(f"\n[LOG] Running backtest on test set...")
    sys.stdout.flush()

    # Skip rows with NaN features (first ~60 rows due to rolling windows)
    start_idx = 100  # Safe buffer for feature computation

    results, trades, stop_stats = run_backtest(
        test_df,
        model,
        threshold=threshold,
        start_idx=start_idx,
        stop_strategy=stop_strategy if STOP_STRATEGY != "none" else None
    )

    # Calculate metrics
    print(f"\n[LOG] Calculating performance metrics...")
    sys.stdout.flush()

    prices = test_df['close'].values
    start_price = prices[start_idx]
    end_price = prices[-1]

    metrics = calculate_metrics(trades, start_price, end_price)

    # Calculate test period duration
    test_duration = (test_df['timestamp'].max() - test_df['timestamp'].min()).total_seconds() / 86400

    # Print performance report
    print_performance_report(metrics, test_duration)

    # Save results
    output_dir = Path("E:/Personal/GitHub/good-signal/gradient_boosting_poc/results")
    output_dir.mkdir(exist_ok=True)

    # Plot results
    plot_path = output_dir / f"lgb_performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    try:
        plot_results(test_df, results, metrics, str(plot_path), model.feature_importance)
    except Exception as e:
        print(f"[WARNING] Could not generate plot: {e}")

    # Save model
    model_path = output_dir / "lgb_model.pkl"
    try:
        model.save(str(model_path))
        print(f"[OK] Model saved to: {model_path}")
    except Exception as e:
        print(f"[WARNING] Could not save model: {e}")

    # Summary
    print(f"\n{'='*60}")
    print("LIGHTGBM POC COMPLETE")
    print(f"{'='*60}")
    print(f"Model: LightGBM with {n_splits}-fold time-series CV")
    print(f"Features: {len(model.feature_importance)} features")
    print(f"Stop Strategy: {stop_strategy.name}")
    print(f"Test Period: {test_duration:.1f} days")
    print(f"\nResults:")
    print(f"  Completed Trades: {metrics.get('completed_trades', 0)}")
    print(f"  Total Profit: ${metrics.get('total_profit', 0):.2f}")
    print(f"  Win Rate: {metrics.get('win_rate', 0)*100:.1f}%")
    print(f"  Profit Factor: {metrics.get('profit_factor', 0):.2f}x")
    print(f"  Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")

    # Stop-loss stats
    if stop_stats:
        print(f"\nStop-Loss Stats:")
        print(f"  Stop Exits: {stop_stats.get('stop_exits', 0)} ({stop_stats.get('stop_exit_pct', 0):.1f}%)")
        print(f"  Signal Exits: {stop_stats.get('signal_exits', 0)}")
        print(f"  Avg Stop P&L: ${stop_stats.get('avg_stop_pnl', 0):.2f}")
        print(f"  Avg Signal P&L: ${stop_stats.get('avg_signal_pnl', 0):.2f}")

    print(f"\nTop 5 Features:")
    for _, row in model.feature_importance.head(5).iterrows():
        print(f"  {row['feature']}: {row['importance']:.2f}")

    return metrics, model, stop_stats


if __name__ == "__main__":
    main()
