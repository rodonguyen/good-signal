"""
Main script to run the Bayesian Regression Trading POC with 15-min data.

This is Phase 1 implementation from improvements.md:
- Uses 15-min aggregated data instead of 1-min
- Window sizes adjusted to maintain same time horizons (3hr, 6hr, 12hr)
- Expected: 15x fewer trades, better signal-to-noise ratio
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


def plot_results(test_df: pd.DataFrame, results: list, metrics: dict, output_path: str = None, config: dict = None):
    """Plot backtest results with configuration info."""
    results_df = pd.DataFrame(results)

    # Calculate cumulative P&L (GROSS - before fees)
    positions = results_df["position"].values
    prices = results_df["price"].values
    price_changes = np.diff(prices, prepend=prices[0])
    pnl = positions[:-1] * price_changes[1:]
    cumulative_pnl = np.cumsum(np.concatenate([[0], pnl]))

    fig, axes = plt.subplots(3, 1, figsize=(14, 13))

    if config:
        config_text = (
            f"Config: Timeframe={config.get('timeframe', 'N/A')} | "
            f"Windows={config.get('window_sizes', 'N/A')} | "
            f"Clusters={config.get('n_clusters', 'N/A')}/{config.get('n_select', 'N/A')} | "
            f"Threshold={config.get('threshold', 'N/A')} | "
            f"Stop={config.get('stop_strategy', 'None')} (th={config.get('stop_threshold', 'N/A')}) | "
            f"Fees={config.get('fee_pct', 0)*100:.3f}%"
        )
        results_text = (
            f"Results: Gross=${metrics.get('total_gross_profit', metrics.get('total_profit', 0)):.2f} | "
            f"Fees=${metrics.get('total_fees', 0):.2f} | "
            f"Net=${metrics.get('total_profit', 0):.2f} | "
            f"Trades={metrics.get('completed_trades', 0)} | "
            f"Win Rate={metrics.get('win_rate', 0)*100:.1f}%"
        )
        fig.suptitle(f"{config_text}\n{results_text}", fontsize=10, y=0.98)

    # Plot 1: Price and Position
    ax1 = axes[0]
    ax1.plot(prices, label="Price", color="black", linewidth=1)
    ax1_twin = ax1.twinx()

    long_mask = positions == 1
    short_mask = positions == -1

    ax1_twin.fill_between(range(len(positions)), 0, positions, where=long_mask, color="green", alpha=0.3, label="Long")
    ax1_twin.fill_between(range(len(positions)), 0, positions, where=short_mask, color="red", alpha=0.3, label="Short")

    ax1.set_xlabel("Time Step (15-min bars)")
    ax1.set_ylabel("Price")
    ax1_twin.set_ylabel("Position")
    ax1.set_title("Price and Trading Positions (15-min)")
    ax1.legend(loc="upper left")
    ax1_twin.legend(loc="upper right")
    ax1.grid(True, alpha=0.3)

    # Plot 2: Cumulative P&L (Gross)
    ax2 = axes[1]
    ax2.plot(cumulative_pnl, color="blue", linewidth=2)
    ax2.axhline(y=0, color="black", linestyle="--", alpha=0.5)
    ax2.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl, where=cumulative_pnl >= 0, color="green", alpha=0.3)
    ax2.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl, where=cumulative_pnl < 0, color="red", alpha=0.3)
    ax2.set_xlabel("Time Step (15-min bars)")
    ax2.set_ylabel("Cumulative P&L ($)")
    gross_pnl = metrics.get("total_gross_profit", metrics.get("total_profit", 0))
    net_pnl = metrics.get("total_profit", 0)
    ax2.set_title(f"Cumulative P&L (GROSS) - Gross: ${gross_pnl:.2f} | Net: ${net_pnl:.2f}")
    ax2.grid(True, alpha=0.3)

    # Plot 3: Predictions vs Actual
    ax3 = axes[2]
    predictions = results_df["prediction"].values
    actual_changes = np.diff(prices, prepend=prices[0])[1:]

    # Align arrays: actual_changes is one element shorter
    min_len = min(len(predictions), len(actual_changes))
    predictions_aligned = predictions[:min_len]
    actual_changes_aligned = actual_changes[:min_len]

    sample_size = min(1000, min_len)
    sample_indices = np.random.choice(min_len, sample_size, replace=False)
    sample_indices = np.sort(sample_indices)

    ax3.scatter(actual_changes_aligned[sample_indices], predictions_aligned[sample_indices], alpha=0.5, s=10)
    ax3.axhline(y=0, color="black", linestyle="--", alpha=0.5)
    ax3.axvline(x=0, color="black", linestyle="--", alpha=0.5)
    ax3.set_xlabel("Actual Price Change (15-min)")
    ax3.set_ylabel("Predicted Price Change")
    ax3.set_title("Prediction Accuracy (Sample)")
    ax3.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"[OK] Plot saved to: {output_path}")

    plt.show()


def main():
    """Main execution function for 15-min data."""
    import sys

    print(f"\n{'='*60}")
    print("BAYESIAN REGRESSION TRADING - 15-MINUTE VERSION")
    print("Phase 1 Implementation: Higher Timeframe")
    print(f"{'='*60}\n")
    sys.stdout.flush()

    # Configuration for 15-min data
    # Key change: window sizes adjusted for same TIME horizons
    data_path = "E:/Personal/GitHub/good-signal/bayesian_method_poc/ETHUSDT_15min_with_imbalance.csv"
    window_sizes = [12, 24, 48]
    n_clusters = 100
    n_select = 20
    threshold = 0.12
    # Stop-loss configuration
    use_stop_loss = False
    stop_threshold = 0.02

    print(f"[LOG] Configuration (15-min):")
    print(f"  Window sizes: {window_sizes} bars")
    print(f"  Clusters: {n_clusters}, Select: {n_select}")
    print(f"  Threshold: {threshold}")
    print(f"  Stop-Loss: {'PredictionReversalStop (threshold=' + str(stop_threshold) + ')' if use_stop_loss else 'None'}")
    sys.stdout.flush()

    # Load data
    print(f"[LOG] Loading 15-min data...")
    sys.stdout.flush()
    df = load_data(data_path)
    sys.stdout.flush()

    # Split data
    train_df, test_df = split_data(df, train_ratio=2 / 3)

    # Extract price and imbalance series
    train_prices = train_df["close"].values
    train_imbalance = train_df["imbalance_ratio"].values if "imbalance_ratio" in train_df.columns else None

    test_prices = test_df["close"].values
    test_imbalance = test_df["imbalance_ratio"].values if "imbalance_ratio" in test_df.columns else None

    # Initialize and train model
    print(f"\n[LOG] Initializing Bayesian model for 15-min data...")
    sys.stdout.flush()
    model = BayesianBitcoinTrader(window_sizes=window_sizes, n_clusters=n_clusters, n_select=n_select)

    print(f"[LOG] Starting model training...")
    sys.stdout.flush()
    # Note: Need fresh training for 15-min data (different cache key)
    model.fit_with_cache(train_prices, train_imbalance)

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
    start_price = test_prices[max(window_sizes)]
    end_price = test_prices[-1]

    metrics = calculate_metrics(trades, start_price, end_price)

    # Calculate test period duration
    test_duration = (test_df["timestamp"].max() - test_df["timestamp"].min()).total_seconds() / 86400

    # Print performance report
    print_performance_report(metrics, test_duration)

    # Save results
    results_df = pd.DataFrame(results)
    # Match timestamp array size to results size
    timestamps = test_df.iloc[max(window_sizes) :]["timestamp"].values
    results_df["timestamp"] = timestamps[: len(results_df)]

    output_dir = Path("E:/Personal/GitHub/good-signal/bayesian_method_poc/results")
    output_dir.mkdir(exist_ok=True)

    # Plot results with config info
    plot_path = output_dir / f"performance_15min_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plot_config = {
        "timeframe": "15-min",
        "window_sizes": window_sizes,
        "n_clusters": n_clusters,
        "n_select": n_select,
        "threshold": threshold,
        "stop_strategy": "PredictionReversalStop" if use_stop_loss else "None",
        "stop_threshold": stop_threshold if use_stop_loss else None,
        "fee_pct": FeeConfig().round_trip_pct,
    }
    try:
        plot_results(test_df, results, metrics, str(plot_path), config=plot_config)
    except Exception as e:
        print(f"[WARNING] Could not generate plot: {e}")

    # Summary with comparison notes
    print(f"\n{'='*60}")
    print("15-MIN VERSION COMPLETE")
    print(f"{'='*60}")
    print(f"Model: Bayesian Regression with {n_select} patterns per timeframe")
    print(f"Timeframes: {window_sizes} bars (= 3hr, 6hr, 12hr)")
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


if __name__ == "__main__":
    main()
