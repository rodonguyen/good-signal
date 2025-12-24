"""Portfolio analysis step wrapper for backtest runner."""

from pathlib import Path
from typing import Any, Mapping
import sys

import pandas as pd

# Add breakout src to path to import portfolio_analysis
breakout_src = Path(__file__).parent.parent.parent.parent / "breakout" / "src"
sys.path.insert(0, str(breakout_src))

from portfolio_analysis import PortfolioAnalysis


def run_analysis_step(
    portfolio_file: Path,
    reports_dir: str,
    raw_data_dir: str,
    trades_dir: str,
    strategy_id: str,
    breakout_config_path: str | None = None,
    strategy_config: Mapping[str, Any] | None = None,
    fee_rate: float | None = None,
) -> Path | None:
    """Run portfolio analysis step for a strategy.

    Args:
        portfolio_file: Path to portfolio trades CSV
        reports_dir: Output directory for reports
        trades_dir: Directory containing unfiltered trades (for comparison)
        strategy_id: Strategy identifier (for per-strategy reports)
        breakout_config_path: Path to breakout config (optional)

    Returns:
        Path to generated HTML report, or None if failed
    """
    if not portfolio_file.exists():
        print(f"  Warning: Portfolio file not found: {portfolio_file}")
        return None

    try:
        # Create strategy-specific reports directory
        strategy_reports_dir = Path(reports_dir) / strategy_id
        strategy_reports_dir.mkdir(parents=True, exist_ok=True)

        # Create analysis instance
        analysis = PortfolioAnalysis(
            portfolio_file=str(portfolio_file),
            output_dir=str(strategy_reports_dir),
            raw_data_dir=raw_data_dir,
            breakout_config_path=breakout_config_path or "breakout/src/config/breakout_config.yaml",
            trades_dir=str(Path(trades_dir) / strategy_id),
        )

        # Override config values from backtest.yaml if provided
        # These will be used by _generate_html to override breakout_config.yaml values
        if strategy_config is not None:
            analysis._strategy_config_override = strategy_config
        if fee_rate is not None:
            analysis._fee_rate_override = fee_rate
        analysis._raw_data_dir_override = raw_data_dir
        analysis._trades_dir_override = str(Path(trades_dir) / strategy_id)

        # Monkey-patch PortfolioBuilder creation in generate_chart_files to use proper config
        # This fixes the 'PortfolioBuilder' object has no attribute 'paths' error
        original_generate_chart_files = analysis.generate_chart_files

        def patched_generate_chart_files(trades_df, equity_curve):
            """Patched version that creates PortfolioBuilder with proper config."""
            from portfolio_builder import PortfolioBuilder

            # Get unique symbols
            symbols = trades_df["symbol"].unique()
            if len(symbols) == 0:
                return

            # Create PortfolioBuilder with a minimal config that has paths
            # We'll use the portfolio config path if available
            portfolio_config_path = "config/backtest/portfolio_config.yaml"
            try:
                builder = PortfolioBuilder(config_path=portfolio_config_path)
            except Exception:
                # Fallback: create instance and manually set paths
                builder = PortfolioBuilder.__new__(PortfolioBuilder)
                builder.paths = {
                    "trades_dir": str(Path(trades_dir) / strategy_id),
                    "filtered_dir": str(Path(trades_dir) / strategy_id),
                    "use_filtered": False,
                }

            # Now call export_chart_data for each symbol
            for symbol in symbols:
                try:
                    json_file = builder.export_chart_data(
                        trades_df=trades_df,
                        symbol=symbol,
                        raw_data_dir=str(raw_data_dir),
                        output_dir=str(strategy_reports_dir),
                    )
                    if json_file:
                        import json

                        with open(json_file, "r", encoding="utf-8") as f:
                            chart_data = json.load(f)

                        # Add Bollinger Bands data if this is a BB strategy
                        # Check strategy type from strategy_id or trade columns
                        symbol_trades = trades_df[trades_df["symbol"] == symbol]
                        if not symbol_trades.empty:
                            # Check if BB strategy (bb_trendline) or breakout (atr_breakout)
                            has_bb = "bb_trendline" in strategy_id.lower()
                            has_breakout = "atr_breakout" in strategy_id.lower() or any("upperLevel" in str(t) for t in chart_data.get("trades", []))

                            # For BB strategies, we need to calculate BB on hourly bars and add to chart_data
                            if has_bb:
                                print(f"    Adding Bollinger Bands data for {symbol} (strategy: {strategy_id})")
                                # Load hourly bars and calculate BB
                                try:
                                    from src.backtest.data.ohlcv_store import OhlcvStore, OhlcvStoreConfig
                                    from src.indicators.bollinger_bands import BollingerBands

                                    store_cfg = OhlcvStoreConfig(
                                        raw_1m_dir=raw_data_dir,
                                        cache_dir="data/cache/backtest",
                                        cache_enabled=True,
                                        cache_version="v1",
                                    )
                                    store = OhlcvStore(store_cfg)
                                    hourly_df = store.load_resampled(symbol, timeframe="1h")

                                    # Calculate BB (use default params or from config)
                                    bb = BollingerBands(period=20, std_dev=2.0)
                                    hourly_df = bb.calculate(hourly_df)

                                    # Convert to chart data format (hourly timestamps)
                                    hourly_df["timestamp"] = pd.to_datetime(hourly_df["timestamp"], utc=True)
                                    hourly_df["time"] = (hourly_df["timestamp"].astype("int64") // 10**9).astype(int)

                                    bb_data = []
                                    for _, row in hourly_df.iterrows():
                                        if pd.notna(row.get("bb_upper")) and pd.notna(row.get("bb_middle")) and pd.notna(row.get("bb_lower")):
                                            bb_data.append(
                                                {
                                                    "time": int(row["time"]),
                                                    "upper": float(row["bb_upper"]),
                                                    "middle": float(row["bb_middle"]),
                                                    "lower": float(row["bb_lower"]),
                                                }
                                            )

                                    if bb_data:
                                        chart_data["bollingerBands"] = bb_data
                                        print(f"    Added {len(bb_data)} BB data points")
                                        # Update JSON file with BB data for consistency
                                        with open(json_file, "w", encoding="utf-8") as f:
                                            json.dump(chart_data, f, indent=2)
                                    else:
                                        print(f"    Warning: No BB data points generated (all NaN?)")
                                except Exception as e:
                                    print(f"    Warning: Could not add BB data: {e}")
                                    import traceback

                                    traceback.print_exc()

                        html_file = Path(strategy_reports_dir) / f"{symbol}_chart.html"
                        # Pass the modified chart_data (with BB data if added) to HTML generator
                        analysis.generate_symbol_chart_html(html_file, symbol, chart_data)
                        print(f"  Generated chart file: {html_file.resolve()}")
                except Exception as e:
                    print(f"  Error generating chart for {symbol}: {e}")
                    continue

        # Replace the method temporarily
        analysis.generate_chart_files = patched_generate_chart_files

        # Run analysis (this method handles everything)
        report_path = analysis.analyze()

        return Path(report_path) if report_path else None

    except Exception as e:
        print(f"  Error generating analysis for {strategy_id}: {e}")
        import traceback

        traceback.print_exc()
        return None
