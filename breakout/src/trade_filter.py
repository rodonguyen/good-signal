"""Block 3: Trade Filter

Applies market condition filters to raw trades from breakout engine.
Supports configurable AND/OR filter logic.
"""

import pandas as pd
import yaml
from pathlib import Path
from typing import Optional, Dict, List
import argparse

from utils.filter_utils import calculate_narrow_day, calculate_volatility_contraction, calculate_trend_filter, calculate_volatility_expansion
from utils.crypto_utils import aggregate_24h_periods, calculate_crypto_atr
from utils.config import load_config, get_symbol_config


class TradeFilter:
    """Filter trades based on market conditions."""

    def __init__(self, config_path: str = "src/config/filter_config.yaml"):
        """Initialize filter with configuration.

        Args:
            config_path: Path to filter configuration file
        """
        self.config = self._load_config(config_path)
        self.filter_config = self.config["filters"]
        self.logic_mode = self.config["logic_mode"]
        self.paths = self.config["paths"]

        # Create output directory
        Path(self.paths["filtered_dir"]).mkdir(parents=True, exist_ok=True)

    def _load_config(self, config_path: str) -> Dict:
        """Load filter configuration."""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_file, "r") as f:
            config = yaml.safe_load(f)

        return config

    def load_trades(self, symbol: str) -> pd.DataFrame:
        """Load trades CSV for a symbol.

        Args:
            symbol: Symbol name (e.g., 'ETHUSDT')

        Returns:
            DataFrame with trades
        """
        trades_file = Path(self.paths["trades_dir"]) / f"{symbol}_trades.csv"

        if not trades_file.exists():
            raise FileNotFoundError(f"Trades file not found: {trades_file}")

        df = pd.read_csv(trades_file)
        df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
        df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)

        return df

    def load_daily_bars(self, symbol: str, day_start_hour: int = 13) -> pd.DataFrame:
        """Load and aggregate daily bars for filter calculations.

        Args:
            symbol: Symbol name
            day_start_hour: Hour when trading day starts (default: 13)

        Returns:
            DataFrame with daily bars including ATR
        """
        # Load 1-minute data
        data_file = Path(self.paths["raw_data_dir"]) / symbol / f"{symbol}_1min.csv"

        if not data_file.exists():
            raise FileNotFoundError(f"Data file not found: {data_file}")

        df = pd.read_csv(data_file)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        # Aggregate into 24-hour periods
        daily_bars = aggregate_24h_periods(df, day_start_hour)

        # Calculate ATR (needed for some filters)
        atr_series = calculate_crypto_atr(daily_bars, period=14)
        daily_bars["atr"] = atr_series

        return daily_bars

    def apply_filters(self, trades_df: pd.DataFrame, daily_bars: pd.DataFrame) -> pd.DataFrame:
        """Apply all enabled filters to trades.

        Args:
            trades_df: DataFrame with trades
            daily_bars: DataFrame with daily bars for filter calculations

        Returns:
            Filtered DataFrame with trades
        """
        if trades_df.empty:
            return trades_df

        # Merge trades with daily bars to get filter values
        trades_with_daily = trades_df.merge(daily_bars[["day"]], left_on="day", right_on="day", how="left")

        # Get daily bars indexed by day for easier lookup
        daily_indexed = daily_bars.set_index("day")

        # Calculate all filter conditions
        filter_results = {}

        # Narrow day filter
        if self.filter_config["narrow_day"]["enabled"]:
            narrow_day = calculate_narrow_day(
                daily_bars,
                threshold=self.filter_config["narrow_day"]["threshold"],
                lookback_period=self.filter_config["narrow_day"]["lookback_period"],
            )
            filter_results["narrow_day"] = trades_with_daily["day"].map(
                lambda d: narrow_day[daily_bars["day"] == d].iloc[0] if len(narrow_day[daily_bars["day"] == d]) > 0 else False
            )

        # Volatility contraction filter
        if self.filter_config["volatility_contraction"]["enabled"]:
            vol_contraction = calculate_volatility_contraction(
                daily_bars,
                short_period=self.filter_config["volatility_contraction"]["short_period"],
                long_period=self.filter_config["volatility_contraction"]["long_period"],
            )
            filter_results["volatility_contraction"] = trades_with_daily["day"].map(
                lambda d: vol_contraction[daily_bars["day"] == d].iloc[0] if len(vol_contraction[daily_bars["day"] == d]) > 0 else False
            )

        # Trend filter
        if self.filter_config["trend_filter"]["enabled"]:
            trend = calculate_trend_filter(
                daily_bars,
                ma_period=self.filter_config["trend_filter"]["ma_period"],
                trend_direction=self.filter_config["trend_filter"]["trend_direction"],
            )
            filter_results["trend_filter"] = trades_with_daily["day"].map(
                lambda d: trend[daily_bars["day"] == d].iloc[0] if len(trend[daily_bars["day"] == d]) > 0 else False
            )

        # Volatility expansion filter
        if self.filter_config["volatility_expansion"]["enabled"]:
            vol_expansion = calculate_volatility_expansion(daily_bars, period=self.filter_config["volatility_expansion"]["period"])
            filter_results["volatility_expansion"] = trades_with_daily["day"].map(
                lambda d: vol_expansion[daily_bars["day"] == d].iloc[0] if len(vol_expansion[daily_bars["day"] == d]) > 0 else False
            )

        # Combine filter results based on logic mode
        if not filter_results:
            # No filters enabled, return all trades
            return trades_df

        # Create combined filter result
        filter_df = pd.DataFrame(filter_results)

        if self.logic_mode.upper() == "AND":
            # All enabled filters must pass
            combined_filter = filter_df.all(axis=1)
        else:  # OR
            # Any filter passes
            combined_filter = filter_df.any(axis=1)

        # Apply filter
        filtered_trades = trades_df[combined_filter].copy()

        return filtered_trades

    def filter_symbol(self, symbol: str, day_start_hour: int = 13) -> pd.DataFrame:
        """Filter trades for a symbol.

        Args:
            symbol: Symbol name (e.g., 'ETHUSDT')
            day_start_hour: Hour when trading day starts (default: 13)

        Returns:
            Filtered DataFrame with trades
        """
        print(f"Filtering trades for {symbol}...")

        # Load trades
        trades_df = self.load_trades(symbol)
        print(f"  Loaded {len(trades_df)} raw trades")

        # Load daily bars
        daily_bars = self.load_daily_bars(symbol, day_start_hour)
        print(f"  Loaded {len(daily_bars)} daily bars")

        # Apply filters
        filtered_trades = self.apply_filters(trades_df, daily_bars)
        print(f"  Filtered to {len(filtered_trades)} trades")

        # Save filtered trades
        output_file = Path(self.paths["filtered_dir"]) / f"{symbol}_trades.csv"
        filtered_trades.to_csv(output_file, index=False)
        print(f"  Saved to: {output_file}")

        return filtered_trades


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description="Filter trades based on market conditions")
    parser.add_argument("--symbol", type=str, default=None, help="Symbol to filter (e.g., ETHUSDT). Defaults to config default.")
    parser.add_argument("--config", type=str, default="src/config/filter_config.yaml", help="Path to filter config file")

    args = parser.parse_args()

    # Use default symbol if not provided
    if args.symbol is None:
        crypto_config = load_config("src/config/crypto_symbols.yaml")
        from utils.config import get_default_symbol

        args.symbol = get_default_symbol(crypto_config)

    # Create filter
    trade_filter = TradeFilter(config_path=args.config)

    # Filter trades
    filtered_trades = trade_filter.filter_symbol(args.symbol)

    if not filtered_trades.empty:
        print(f"\n✓ Filtering complete: {len(filtered_trades)} trades after filtering")
        print(f"\nFilter Summary:")
        print(f"  Total trades: {len(filtered_trades)}")
        print(f"  Long trades: {len(filtered_trades[filtered_trades['direction'] == 'long'])}")
        print(f"  Short trades: {len(filtered_trades[filtered_trades['direction'] == 'short'])}")
        print(f"  Total PnL: {filtered_trades['net_pnl'].sum():.2f}")
        print(f"  Win rate: {len(filtered_trades[filtered_trades['net_pnl'] > 0]) / len(filtered_trades) * 100:.1f}%")


if __name__ == "__main__":
    main()


