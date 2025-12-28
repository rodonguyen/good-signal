"""
Main script to run the Bayesian Regression Trading POC.

This script:
1. Loads ETHUSDT price and imbalance data
2. Trains the Bayesian regression model
3. Runs backtest on test period
4. Displays performance metrics
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt

from bayesian_trader import (
    BayesianBitcoinTrader,
    run_backtest,
    run_backtest_with_sl,
    calculate_metrics,
    print_performance_report,
    FeeConfig,
)
from stop_loss_strategies import PredictionReversalStop


def load_data(data_path: str) -> pd.DataFrame:
    """Load and validate data."""
    print(f"Loading data from: {data_path}")
    df = pd.read_csv(data_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    print(f"[OK] Loaded {len(df)} rows")
    print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"  Columns: {list(df.columns)}")

    # Basic validation
    if df.isnull().any().any():
        print(f"  WARNING: Found {df.isnull().sum().sum()} null values")
        print("  Filling nulls with forward fill...")
        df = df.fillna(method="ffill").fillna(method="bfill")

    return df


def split_data(df: pd.DataFrame, train_ratio: float = 2 / 3) -> tuple:
    """
    Split data into train and test sets.

    For the Bayesian model, training data is further split into:
    - Pattern extraction (first half of train)
    - Weight optimization (second half of train)

    Args:
        df: Full dataset
        train_ratio: Ratio of data to use for training (default 2/3)

    Returns:
        Tuple of (train_df, test_df)
    """
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


def plot_results(test_df: pd.DataFrame, results: list, metrics: dict, output_path: str = None):
    """
    Plot backtest results.

    Args:
        test_df: Test data DataFrame
        results: List of result dictionaries from backtest
        metrics: Performance metrics dictionary
        output_path: Path to save plot (optional)
    """
    results_df = pd.DataFrame(results)

    # Calculate cumulative P&L
    positions = results_df["position"].values
    prices = results_df["price"].values
    price_changes = np.diff(prices, prepend=prices[0])
    pnl = positions[:-1] * price_changes[1:]  # P&L from position changes
    cumulative_pnl = np.cumsum(np.concatenate([[0], pnl]))

    fig, axes = plt.subplots(3, 1, figsize=(14, 10))

    # Plot 1: Price and Position
    ax1 = axes[0]
    ax1.plot(prices, label="Price", color="black", linewidth=1)
    ax1_twin = ax1.twinx()

    # Color-code positions
    long_mask = positions == 1
    short_mask = positions == -1
    neutral_mask = positions == 0

    ax1_twin.fill_between(range(len(positions)), 0, positions, where=long_mask, color="green", alpha=0.3, label="Long")
    ax1_twin.fill_between(range(len(positions)), 0, positions, where=short_mask, color="red", alpha=0.3, label="Short")

    ax1.set_xlabel("Time Step")
    ax1.set_ylabel("Price")
    ax1_twin.set_ylabel("Position")
    ax1.set_title("Price and Trading Positions")
    ax1.legend(loc="upper left")
    ax1_twin.legend(loc="upper right")
    ax1.grid(True, alpha=0.3)

    # Plot 2: Cumulative P&L
    ax2 = axes[1]
    ax2.plot(cumulative_pnl, color="blue", linewidth=2)
    ax2.axhline(y=0, color="black", linestyle="--", alpha=0.5)
    ax2.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl, where=cumulative_pnl >= 0, color="green", alpha=0.3)
    ax2.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl, where=cumulative_pnl < 0, color="red", alpha=0.3)
    ax2.set_xlabel("Time Step")
    ax2.set_ylabel("Cumulative P&L ($)")
    ax2.set_title(f'Cumulative Profit/Loss - Total: ${metrics.get("total_profit", 0):.2f}')
    ax2.grid(True, alpha=0.3)

    # Plot 3: Predictions vs Actual
    ax3 = axes[2]
    predictions = results_df["prediction"].values
    actual_changes = np.diff(prices, prepend=prices[0])[1:]  # Skip first

    # Sample to avoid overplotting
    sample_size = min(1000, len(predictions))
    sample_indices = np.random.choice(len(predictions), sample_size, replace=False)
    sample_indices = np.sort(sample_indices)

    ax3.scatter(actual_changes[sample_indices], predictions[sample_indices], alpha=0.5, s=10)
    ax3.axhline(y=0, color="black", linestyle="--", alpha=0.5)
    ax3.axvline(x=0, color="black", linestyle="--", alpha=0.5)
    ax3.set_xlabel("Actual Price Change")
    ax3.set_ylabel("Predicted Price Change")
    ax3.set_title("Prediction Accuracy (Sample)")
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"[OK] Plot saved to: {output_path}")

    plt.show()


def main():
    """Main execution function."""
    import sys

    print(f"\n{'='*60}")
    print("BAYESIAN REGRESSION TRADING - PROOF OF CONCEPT")
    print("Based on Shah & Zhang (2014)")
    print(f"{'='*60}\n")
    sys.stdout.flush()

    # Configuration
    data_path = "E:/Personal/GitHub/good-signal/bayesian_method_poc/ETHUSDT_1min_with_imbalance.csv"
    window_sizes = [180, 360, 720]  # Same bar counts as paper: 180, 360, 720 bars (3hr, 6hr, 12hr for 1-min intervals)
    n_clusters = 100  # Increased for full dataset (paper uses 100)
    n_select = 20  # Increased for full dataset (paper uses 20)
    threshold = 0.10  # Trading threshold (adjusted based on prediction scale)
    use_sample = False  # USE FULL DATASET
    sample_size = 50000  # Not used when use_sample=False

    # Stop-loss configuration
    use_stop_loss = True
    stop_threshold = 0.04  # Lower threshold for faster exit on reversal

    print(f"[LOG] Configuration:")
    print(f"  Window sizes: {window_sizes}")
    print(f"  Clusters: {n_clusters}, Select: {n_select}")
    print(f"  Threshold: {threshold}")
    print(f"  Stop-Loss: {'PredictionReversalStop (threshold=' + str(stop_threshold) + ')' if use_stop_loss else 'None'}")
    print(f"  Sample size: {sample_size if use_sample else 'Full dataset'}\n")
    sys.stdout.flush()

    # Load data
    print(f"[LOG] Loading data...")
    sys.stdout.flush()
    df = load_data(data_path)
    sys.stdout.flush()

    # Use sample for POC if configured
    if use_sample and len(df) > sample_size:
        print(f"\n[INFO] Using last {sample_size} rows for POC (out of {len(df)} total)")
        df = df.iloc[-sample_size:].copy().reset_index(drop=True)
        print(f"  Sampled data: {len(df)} rows")
        print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    # Split data
    train_df, test_df = split_data(df, train_ratio=2 / 3)

    # Extract price and imbalance series
    train_prices = train_df["close"].values
    train_imbalance = train_df["imbalance_ratio"].values if "imbalance_ratio" in train_df.columns else None

    test_prices = test_df["close"].values
    test_imbalance = test_df["imbalance_ratio"].values if "imbalance_ratio" in test_df.columns else None

    # Initialize and train model
    print(f"\n[LOG] Initializing Bayesian model...")
    sys.stdout.flush()
    model = BayesianBitcoinTrader(window_sizes=window_sizes, n_clusters=n_clusters, n_select=n_select)

    print(f"[LOG] Starting model training...")
    sys.stdout.flush()
    model.fit(train_prices, train_imbalance)

    # Run backtest on test set
    print(f"[LOG] Running backtest on test set...")
    sys.stdout.flush()

    if use_stop_loss:
        stop_strategy = PredictionReversalStop(threshold=stop_threshold)
        results, trades, stop_stats = run_backtest_with_sl(
            test_data=test_prices, test_imbalance=test_imbalance, model=model, threshold=threshold, stop_strategy=stop_strategy
        )
    else:
        results, trades = run_backtest(test_data=test_prices, test_imbalance=test_imbalance, model=model, threshold=threshold)
        stop_stats = None

    # Calculate metrics
    print(f"\n[LOG] Calculating performance metrics...")
    sys.stdout.flush()
    start_price = test_prices[max(window_sizes)]  # First price after lookback
    end_price = test_prices[-1]

    metrics = calculate_metrics(trades, start_price, end_price)

    # Calculate test period duration
    test_duration = (test_df["timestamp"].max() - test_df["timestamp"].min()).total_seconds() / 86400  # days

    # Print performance report
    print_performance_report(metrics, test_duration)

    # Save detailed results
    results_df = pd.DataFrame(results)
    results_df["timestamp"] = test_df.iloc[max(window_sizes) :]["timestamp"].values

    output_dir = Path("E:/Personal/GitHub/good-signal/bayesian_method_poc/results")
    output_dir.mkdir(exist_ok=True)

    results_csv = output_dir / f"backtest_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    results_df.to_csv(results_csv, index=False)
    print(f"[OK] Detailed results saved to: {results_csv}")

    trades_df = pd.DataFrame(trades)
    trades_csv = output_dir / f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    trades_df.to_csv(trades_csv, index=False)
    print(f"[OK] Trade log saved to: {trades_csv}")

    # Save stop-loss stats if available
    if stop_stats:
        import json

        stop_stats_file = output_dir / f"stop_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(stop_stats_file, "w") as f:
            json.dump(stop_stats, f, indent=2)
        print(f"[OK] Stop-loss stats saved to: {stop_stats_file}")

    # Plot results (disabled for POC to avoid blocking)
    plot_path = output_dir / f"performance_plot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    try:
        plot_results(test_df, results, metrics, str(plot_path))
    except Exception as e:
        print(f"[WARNING] Could not generate plot: {e}")

    # Summary
    print(f"\n{'='*60}")
    print("POC EXECUTION COMPLETE")
    print(f"{'='*60}")
    print(f"Model: Bayesian Regression with {n_select} patterns per timeframe")
    print(f"Timeframes: {window_sizes} bars")
    print(f"Test Period: {test_duration:.1f} days")
    print(f"Final Return: {metrics.get('return_pct', 0):.2f}%")
    print(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"Total Trades: {metrics.get('completed_trades', 0)}")

    if stop_stats:
        print(f"\nSTOP-LOSS STATS:")
        print(f"  Strategy: PredictionReversalStop (threshold={stop_threshold})")
        print(f"  Stop Exits: {stop_stats.get('stop_exits', 0)} ({stop_stats.get('stop_exit_pct', 0):.1f}%)")
        print(f"  Signal Exits: {stop_stats.get('signal_exits', 0)}")
        print(f"  Avg P&L on Stop Exits: ${stop_stats.get('avg_stop_pnl', 0):.2f}")
        print(f"  Avg P&L on Signal Exits: ${stop_stats.get('avg_signal_pnl', 0):.2f}")
        print(f"\nFEE STATS:")
        print(f"  Total Fees: ${stop_stats.get('total_fees', 0):.2f}")
        print(f"  Gross P&L: ${stop_stats.get('total_gross_pnl', 0):.2f}")
        print(f"  Net P&L: ${stop_stats.get('total_net_pnl', 0):.2f}")
        print(f"  Fees as % of Gross: {stop_stats.get('fee_pct_of_gross', 0):.1f}%")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
