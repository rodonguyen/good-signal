"""
Walk-Forward Optimization entry point.

Usage:
    python wfo.py --wfo-config config/backtest/wfo_config.yaml
"""

from __future__ import annotations

import argparse
import yaml
from pathlib import Path
from datetime import datetime

from src.backtest.runner import BacktestConfig
from src.backtest.optimization.wfo_config import calculate_wfo_windows
from src.backtest.optimization.walk_forward import WalkForwardOptimizer
from src.backtest.optimization.wfo_report import WFOReportGenerator


def load_wfo_config(config_path: str) -> dict:
    """Load WFO configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"WFO config file not found: {config_path}")

    with config_file.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_data_date_range(data_file: Path) -> tuple[datetime, datetime]:
    """Get date range from data file."""
    import pandas as pd

    # Read first and last lines
    with open(data_file, "r") as f:
        lines = f.readlines()
        if len(lines) < 2:
            raise ValueError(f"Data file {data_file} has insufficient data")

        # Parse first data line (skip header)
        first_line = lines[1].strip().split(",")
        last_line = lines[-1].strip().split(",")

        # Find timestamp column index
        header = lines[0].strip().split(",")
        try:
            ts_idx = header.index("timestamp")
        except ValueError:
            raise ValueError(f"Data file {data_file} missing 'timestamp' column")

        start_date = pd.to_datetime(first_line[ts_idx], utc=True)
        end_date = pd.to_datetime(last_line[ts_idx], utc=True)

    return start_date, end_date


def find_data_file(raw_dir: str, symbol: str, pattern: str | None = None) -> Path:
    """Find data file for symbol."""
    base_dir = Path(raw_dir) / symbol

    # If pattern specified, use it
    if pattern:
        file_path = base_dir / pattern.format(symbol=symbol)
        if file_path.exists():
            return file_path

    # Try standard filenames
    candidates = [
        base_dir / f"{symbol}_1min.csv",
        base_dir / f"{symbol}_1min_from202305.csv",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Data file not found in {base_dir}. Tried: {[c.name for c in candidates]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run walk-forward optimization")
    parser.add_argument(
        "--wfo-config",
        type=str,
        default="config/backtest/wfo_config.yaml",
        help="Path to WFO config YAML (default: config/backtest/wfo_config.yaml)",
    )

    args = parser.parse_args()

    # Load WFO config
    print(f"Loading WFO config from {args.wfo_config}...")
    wfo_cfg = load_wfo_config(args.wfo_config)

    # Get symbol
    symbol = wfo_cfg.get("symbol")
    if not symbol:
        raise ValueError("'symbol' must be specified in WFO config")

    # Get strategy
    strategy = wfo_cfg.get("strategy")
    if not strategy:
        raise ValueError("'strategy' must be specified in WFO config")

    # Get data directory
    data_cfg = wfo_cfg.get("data", {})
    raw_dir = data_cfg.get("raw_dir", "data/raw/crypto")

    # Get data file
    data_file_pattern = wfo_cfg.get("data_file_pattern")
    data_file = find_data_file(raw_dir, symbol, data_file_pattern)

    print(f"Reading date range from {data_file}...")
    data_start, data_end = get_data_date_range(data_file)
    print(f"Data range: {data_start.date()} to {data_end.date()}")

    # Get window configuration
    windows_cfg = wfo_cfg.get("windows", {})
    train_months = windows_cfg.get("train_months", 6)
    test_months = windows_cfg.get("test_months", 3)
    step_months = windows_cfg.get("step_months", 3)

    # Get parameter ranges
    params_cfg = wfo_cfg.get("parameters", {})
    breakout_cfg = params_cfg.get("breakout_multiplier", {})
    stop_cfg = params_cfg.get("stop_multiplier", {})

    breakout_range = (
        breakout_cfg.get("start", 0.24),
        breakout_cfg.get("end", 0.60),
        breakout_cfg.get("step", 0.02),
    )
    stop_range = (
        stop_cfg.get("start", 0.16),
        stop_cfg.get("end", 0.50),
        stop_cfg.get("step", 0.02),
    )

    # Get optimization target
    optimization_target = wfo_cfg.get("optimization_target", "sharpe")

    # Get other settings from WFO config
    engine_cfg = wfo_cfg.get("engine", {})
    fee_rate = engine_cfg.get("fee_rate", 0.0015)
    cache_dir = engine_cfg.get("cache_dir", "data/cache/backtest")
    cache_enabled = engine_cfg.get("cache_enabled", True)
    cache_version = engine_cfg.get("cache_version", "v1")

    output_dir_cfg = wfo_cfg.get("output", {})
    reports_dir = output_dir_cfg.get("dir") or f"outputs/reports/wfo_{strategy}"
    trades_dir = output_dir_cfg.get("trades_dir", "data/trades")
    portfolio_dir = output_dir_cfg.get("portfolio_dir", "data/portfolio")

    # Get strategy-specific config from WFO config
    strategy_config = wfo_cfg.get("strategy_config", {})
    if not strategy_config:
        # Create minimal strategy config for ATR breakout
        strategy_config = {
            "type": strategy,
            "id": strategy,
            "enabled": True,
            "params": {
                "atr_period": wfo_cfg.get("atr_period", 14),
                "day_start_hour": wfo_cfg.get("day_start_hour", 13),
            },
        }

    # Create minimal BacktestConfig from WFO config
    backtest_config_dict = {
        "engine": {
            "fee_rate": fee_rate,
            "debug": False,
            "cache": {
                "enabled": cache_enabled,
                "dir": cache_dir,
                "version": cache_version,
            },
            "outputs": {
                "trades_dir": trades_dir,
                "portfolio_dir": portfolio_dir,
                "reports_dir": reports_dir,
            },
        },
        "data": {
            "raw_1m_dir": raw_dir,
            "raw_dir": raw_dir,
        },
        "universe": {
            "symbols": [symbol],
        },
        "strategies": [strategy_config],
        "steps": {
            "filters": wfo_cfg.get("filters", {"enabled": False}),
            "portfolio": wfo_cfg.get("portfolio", {"enabled": True, "config_path": "config/backtest/portfolio_config.yaml"}),
        },
    }
    backtest_config = BacktestConfig(raw=backtest_config_dict)

    print(f"\nWalk-Forward Configuration:")
    print(f"  Strategy: {strategy}")
    print(f"  Symbol: {symbol}")
    print(f"  Training period: {train_months} months")
    print(f"  Testing period: {test_months} months")
    print(f"  Step forward: {step_months} months")
    print(f"  Breakout range: {breakout_range[0]} to {breakout_range[1]} (step {breakout_range[2]})")
    print(f"  Stop range: {stop_range[0]} to {stop_range[1]} (step {stop_range[2]})")
    print(f"  Optimization target: {optimization_target}")

    # Calculate date windows
    windows = calculate_wfo_windows(
        data_start,
        data_end,
        train_months=train_months,
        test_months=test_months,
        step_months=step_months,
    )

    print(f"\nGenerated {len(windows)} walk-forward windows")
    if len(windows) == 0:
        print("ERROR: No windows generated. Check data range and window sizes.")
        return

    # Create optimizer
    print(f"\nInitializing optimizer for {symbol}...")
    optimizer = WalkForwardOptimizer(
        config=backtest_config,
        strategy_type=strategy,
        symbol=symbol,
        date_windows=windows,
        breakout_range=breakout_range,
        stop_range=stop_range,
        optimization_target=optimization_target,
    )

    # Run all cycles
    print(f"\n{'='*60}")
    print("Starting walk-forward optimization...")
    print(f"{'='*60}\n")

    cycle_results = optimizer.run_all_cycles()

    if not cycle_results:
        print("ERROR: No cycle results generated.")
        return

    print(f"\n{'='*60}")
    print(f"Completed {len(cycle_results)} cycles")
    print(f"{'='*60}\n")

    # Generate report
    output_dir = Path(reports_dir)

    print(f"Generating report in {output_dir}...")

    report_generator = WFOReportGenerator(output_dir)
    report_path = report_generator.generate_report(cycle_results)

    print(f"\n✓ Report generated: {report_path}")
    print(f"  Open in browser to view results")


if __name__ == "__main__":
    main()
