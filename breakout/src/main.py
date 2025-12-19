"""Main entry point to run all 5 blocks of the breakout system.

Runs the complete workflow:
1. Block 1: Download data
2. Block 2: Generate trades
3. Block 3: Filter trades
4. Block 4: Build portfolio
5. Block 5: Analyze portfolio
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from bybit_downloader import BybitDownloader
from breakout_engine import CryptoBreakoutEngine
from trade_filter import TradeFilter
from portfolio_builder import PortfolioBuilder
from portfolio_analysis import PortfolioAnalysis
from utils.config import load_config, get_default_symbol


def run_all_blocks(config: dict = None, breakout_config_path: str = "src/config/breakout_config.yaml"):
    """Run all 5 blocks with provided configuration.

    Args:
        config: Optional configuration dictionary. If None, uses defaults.
        breakout_config_path: Path to breakout engine config file.
    """
    # Load breakout config defaults
    breakout_config = load_config(breakout_config_path)
    strategy = breakout_config.get("strategy", {})
    paths = breakout_config.get("paths", {})

    # Default configuration
    defaults = {
        # Block 1: Data Downloader
        "downloader": {
            "config_path": "src/config/crypto_symbols.yaml",
            "symbol": None,  # Will use default from config
            "start_date": None,  # Will default to 1 year ago
            "end_date": None,  # Will default to now
        },
        # Block 2: Breakout Engine (load from config file)
        "breakout": {
            "atr_period": strategy.get("atr_period", 14),
            "breakout_multiplier": strategy.get("breakout_multiplier", 0.33),
            "stop_multiplier": strategy.get("stop_multiplier", 0.33),
            "day_start_hour": strategy.get("day_start_hour", 13),
            "fee_rate": strategy.get("fee_rate", 0.0015),
            "data_dir": paths.get("data_dir", "data/raw/crypto"),
            "output_dir": paths.get("output_dir", "data/trades"),
        },
        # Block 3: Trade Filter
        "filter": {
            "config_path": "src/config/filter_config.yaml",
        },
        # Block 4: Portfolio Builder
        "portfolio": {
            "config_path": "src/config/portfolio_config.yaml",
        },
        # Block 5: Portfolio Analysis
        "analysis": {
            "portfolio_file": "data/portfolio/portfolio_trades.csv",
            "output_dir": "src/reports",
            "raw_data_dir": "data/raw/crypto",
        },
    }

    # Merge with provided config
    if config:
        for key in defaults:
            if key in config:
                defaults[key].update(config[key])

    config = defaults

    print("=" * 60)
    print("Running Complete Breakout System Workflow")
    print("=" * 60)

    # # Block 1: Download data
    # print("\n[Block 1] Downloading data...")
    # downloader = BybitDownloader(config_path=config["downloader"]["config_path"])

    # Get symbol
    symbol = config["downloader"]["symbol"]
    if symbol is None:
        crypto_config = load_config(config["downloader"]["config_path"])
        symbol = get_default_symbol(crypto_config)

    # # Parse dates
    # start_date = config["downloader"]["start_date"]
    # end_date = config["downloader"]["end_date"]
    # if start_date and isinstance(start_date, str):
    #     start_date = datetime.strptime(start_date, "%Y-%m-%d")
    # if end_date and isinstance(end_date, str):
    #     end_date = datetime.strptime(end_date, "%Y-%m-%d")

    # filepath = downloader.download_and_save(symbol=symbol, start_date=start_date, end_date=end_date)
    # print(f"  ✓ Data downloaded: {filepath}")

    # Block 2: Generate trades
    print("\n[Block 2] Generating trades...")
    engine = CryptoBreakoutEngine(
        atr_period=config["breakout"].get("atr_period"),
        breakout_multiplier=config["breakout"].get("breakout_multiplier"),
        stop_multiplier=config["breakout"].get("stop_multiplier"),
        day_start_hour=config["breakout"].get("day_start_hour"),
        fee_rate=config["breakout"].get("fee_rate"),
        config_path=config["downloader"]["config_path"],
        breakout_config_path=breakout_config_path,
    )
    trades_df = engine.process_symbol(
        symbol=symbol,
        data_dir=config["breakout"].get("data_dir"),
        output_dir=config["breakout"].get("output_dir"),
    )
    print(f"  ✓ Generated {len(trades_df)} trades")

    # Block 3: Filter trades
    print("\n[Block 3] Filtering trades...")
    trade_filter = TradeFilter(config_path=config["filter"]["config_path"])
    filtered_trades = trade_filter.filter_symbol(symbol)
    print(f"  ✓ Filtered to {len(filtered_trades)} trades")

    # Block 4: Build portfolio
    print("\n[Block 4] Building portfolio...")
    builder = PortfolioBuilder(config_path=config["portfolio"]["config_path"])
    portfolio_df = builder.build_portfolio()
    print(f"  ✓ Portfolio built with {len(portfolio_df)} trades")

    # Block 5: Analyze portfolio
    print("\n[Block 5] Analyzing portfolio...")
    analyzer = PortfolioAnalysis(
        portfolio_file=config["analysis"]["portfolio_file"],
        output_dir=config["analysis"]["output_dir"],
        raw_data_dir=config["analysis"]["raw_data_dir"],
    )
    report_file = analyzer.analyze()
    print(f"  ✓ Analysis complete: {report_file}")

    print("\n" + "=" * 60)
    print("All blocks completed successfully!")
    print("=" * 60)
    print(f"\nReport location: {report_file}")


def main():
    """Main function with command-line interface."""
    parser = argparse.ArgumentParser(
        description="Run complete breakout system workflow (all 5 blocks)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with defaults
  python src/main.py
  
  # Run with custom symbol and dates
  python src/main.py --symbol ETHUSDT --start-date 2024-01-01 --end-date 2024-12-31
  
  # Run with custom breakout parameters
  python src/main.py --atr-period 20 --breakout-multiplier 0.5
        """,
    )

    # Block 1 options
    parser.add_argument("--symbol", type=str, default=None, help="Symbol to process (default: from config)")
    parser.add_argument("--start-date", type=str, default=None, help="Start date YYYY-MM-DD (default: 1 year ago)")
    parser.add_argument("--end-date", type=str, default=None, help="End date YYYY-MM-DD (default: now)")
    parser.add_argument("--crypto-config", type=str, default="src/config/crypto_symbols.yaml", help="Crypto config path")

    # Block 2 options
    parser.add_argument("--atr-period", type=int, default=None, help="ATR period (overrides config)")
    parser.add_argument("--breakout-multiplier", type=float, default=None, help="Breakout multiplier (overrides config)")
    parser.add_argument("--stop-multiplier", type=float, default=None, help="Stop loss multiplier (overrides config)")
    parser.add_argument("--data-dir", type=str, default=None, help="Raw data directory (overrides config)")
    parser.add_argument("--trades-dir", type=str, default=None, help="Trades output directory (overrides config)")
    parser.add_argument("--breakout-config", type=str, default="src/config/breakout_config.yaml", help="Breakout engine config path")

    # Block 3 options
    parser.add_argument("--filter-config", type=str, default="src/config/filter_config.yaml", help="Filter config path")

    # Block 4 options
    parser.add_argument("--portfolio-config", type=str, default="src/config/portfolio_config.yaml", help="Portfolio config path")

    # Block 5 options
    parser.add_argument("--portfolio-file", type=str, default="data/portfolio/portfolio_trades.csv", help="Portfolio trades file")
    parser.add_argument("--output-dir", type=str, default="src/reports", help="Reports output directory")

    args = parser.parse_args()

    # Build config from arguments (only include non-None values to allow config defaults)
    config = {
        "downloader": {
            "config_path": args.crypto_config,
            "symbol": args.symbol,
            "start_date": args.start_date,
            "end_date": args.end_date,
        },
        "breakout": {},
        "filter": {
            "config_path": args.filter_config,
        },
        "portfolio": {
            "config_path": args.portfolio_config,
        },
        "analysis": {
            "portfolio_file": args.portfolio_file,
            "output_dir": args.output_dir,
            "raw_data_dir": args.data_dir,
        },
    }

    # Only add breakout args if provided (to allow config defaults)
    if args.atr_period is not None:
        config["breakout"]["atr_period"] = args.atr_period
    if args.breakout_multiplier is not None:
        config["breakout"]["breakout_multiplier"] = args.breakout_multiplier
    if args.stop_multiplier is not None:
        config["breakout"]["stop_multiplier"] = args.stop_multiplier
    if args.data_dir is not None:
        config["breakout"]["data_dir"] = args.data_dir
    if args.trades_dir is not None:
        config["breakout"]["output_dir"] = args.trades_dir
    # Run all blocks
    run_all_blocks(config, breakout_config_path=args.breakout_config)


if __name__ == "__main__":
    main()
