"""
Backtest entry point for Good Signal.

Usage:
  python backtest.py --config config/backtest/backtest.yaml
"""

from __future__ import annotations

import argparse

from src.backtest.runner import BacktestRunner, load_backtest_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Good Signal backtests")
    parser.add_argument("--config", type=str, default="config/backtest/backtest.yaml", help="Path to backtest config YAML")
    args = parser.parse_args()

    cfg = load_backtest_config(args.config)
    runner = BacktestRunner(cfg)
    runner.run()


if __name__ == "__main__":
    main()
