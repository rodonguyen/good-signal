"""Block 2: Breakout Engine for Crypto Trading

Executes breakout logic on 1-minute data and generates raw trades.
Implements 24-hour virtual trading days starting at 13:00 UTC.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import yaml

from utils.crypto_utils import (
    define_crypto_day,
    get_day_boundaries,
    get_previous_day_close,
    aggregate_24h_periods,
    calculate_crypto_atr,
    get_previous_day_atr,
)
from utils.fee_calculator import calculate_pnl_with_fees
from utils.config import load_config, get_symbol_config, get_default_symbol


class CryptoBreakoutEngine:
    """Breakout engine for crypto trading with 24-hour virtual days."""

    def __init__(
        self,
        atr_period: int = 14,
        breakout_multiplier: float = 0.33,
        stop_multiplier: float = 0.33,
        day_start_hour: int = 13,
        fee_rate: float = 0.0015,
        config_path: str = "src/config/crypto_symbols.yaml",
    ):
        """Initialize breakout engine.

        Args:
            atr_period: Number of 24-hour periods for ATR calculation
            breakout_multiplier: Multiplier for breakout levels (k × ATR)
            stop_multiplier: Multiplier for stop loss (k × ATR)
            day_start_hour: Hour when trading day starts (13 = 13:00 UTC)
            fee_rate: Total fee rate per trade (0.0015 = 0.15%)
            config_path: Path to configuration file
        """
        self.atr_period = atr_period
        self.breakout_multiplier = breakout_multiplier
        self.stop_multiplier = stop_multiplier
        self.day_start_hour = day_start_hour
        self.fee_rate = fee_rate
        self.config = load_config(config_path)

    def load_data(self, symbol: str, data_dir: str = "data/raw/crypto") -> pd.DataFrame:
        """Load 1-minute data from CSV.

        Args:
            symbol: Symbol name (e.g., 'ETHUSDT')
            data_dir: Directory containing data files

        Returns:
            DataFrame with 1-minute bars
        """
        filepath = Path(data_dir) / symbol / f"{symbol}_1min.csv"

        if not filepath.exists():
            raise FileNotFoundError(f"Data file not found: {filepath}")

        df = pd.read_csv(filepath)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        return df

    def calculate_breakout_levels(self, prev_close: float, prev_atr: float, multiplier: float) -> Tuple[float, float]:
        """Calculate upper and lower breakout levels.

        Args:
            prev_close: Previous day's close price (at 13:00 UTC)
            prev_atr: Previous day's ATR value
            multiplier: Multiplier for breakout distance

        Returns:
            Tuple of (upper_level, lower_level)
        """
        distance = prev_atr * multiplier
        upper_level = prev_close + distance
        lower_level = prev_close - distance

        return upper_level, lower_level

    def detect_breakout(
        self, minute_bars: pd.DataFrame, upper_level: float, lower_level: float, day_start: datetime, day_end: datetime
    ) -> Optional[Dict]:
        """Detect first breakout during trading day.

        Args:
            minute_bars: DataFrame with 1-minute bars for the day
            upper_level: Upper breakout level
            lower_level: Lower breakout level
            day_start: Start of trading day (13:00 UTC)
            day_end: End of trading day (next 13:00 UTC)

        Returns:
            Dict with entry info (direction, entry_time, entry_price) or None
        """
        # Filter bars for this day
        mask = (minute_bars["timestamp"] >= day_start) & (minute_bars["timestamp"] < day_end)
        day_bars = minute_bars[mask].copy()

        if day_bars.empty:
            return None

        # Check for breakout (price crosses level)
        for idx, row in day_bars.iterrows():
            # Check for upper breakout (long)
            if row["high"] >= upper_level:
                # Entry at breakout level
                entry_price = upper_level
                return {"direction": 1, "entry_time": row["timestamp"], "entry_price": entry_price}  # Long

            # Check for lower breakout (short)
            if row["low"] <= lower_level:
                # Entry at breakout level
                entry_price = lower_level
                return {"direction": -1, "entry_time": row["timestamp"], "entry_price": entry_price}  # Short

        return None

    def execute_trade(self, entry: Dict, stop_level: float, day_end: datetime, minute_bars: pd.DataFrame, size: float = 1.0) -> Dict:
        """Execute a trade and determine exit.

        Args:
            entry: Entry information (direction, entry_time, entry_price)
            stop_level: Stop loss level
            day_end: End of day time (13:00 UTC next day)
            minute_bars: DataFrame with 1-minute bars
            size: Position size (default: 1.0)

        Returns:
            Dict with complete trade information
        """
        direction = entry["direction"]
        entry_time = entry["entry_time"]
        entry_price = entry["entry_price"]

        # Get bars after entry
        mask = minute_bars["timestamp"] > entry_time
        future_bars = minute_bars[mask].copy()

        if future_bars.empty:
            # No data after entry, exit at entry (shouldn't happen)
            exit_time = entry_time
            exit_price = entry_price
            exit_reason = "no_data"
        else:
            # Check for stop loss first
            stop_hit = False
            stop_time = None
            stop_price = None

            for idx, row in future_bars.iterrows():
                if direction == 1:  # Long
                    if row["low"] <= stop_level:
                        stop_hit = True
                        stop_time = row["timestamp"]
                        stop_price = stop_level
                        break
                else:  # Short
                    if row["high"] >= stop_level:
                        stop_hit = True
                        stop_time = row["timestamp"]
                        stop_price = stop_level
                        break

            # Check for end of day
            eod_bars = future_bars[future_bars["timestamp"] >= day_end]

            if stop_hit and (stop_time < day_end):
                # Stop loss hit before end of day
                exit_time = stop_time
                exit_price = stop_price
                exit_reason = "stop_loss"
            elif not eod_bars.empty:
                # End of day exit
                exit_time = day_end
                exit_price = eod_bars.iloc[0]["close"]  # Close at 13:00 UTC
                exit_reason = "end_of_day"
            else:
                # Use last available bar (shouldn't happen if data is complete)
                exit_time = future_bars.iloc[-1]["timestamp"]
                exit_price = future_bars.iloc[-1]["close"]
                exit_reason = "last_bar"

        # Calculate PnL
        raw_pnl = (exit_price - entry_price) * direction * size
        net_pnl = calculate_pnl_with_fees(entry_price, exit_price, size, direction, self.fee_rate)

        return {
            "entry_time": entry_time,
            "entry_price": entry_price,
            "exit_time": exit_time,
            "exit_price": exit_price,
            "direction": "long" if direction == 1 else "short",
            "size": size,
            "stop_level": stop_level,
            "exit_reason": exit_reason,
            "raw_pnl": raw_pnl,
            "fees": raw_pnl - net_pnl,
            "net_pnl": net_pnl,
        }

    def process_symbol(self, symbol: str, data_dir: str = "data/raw/crypto", output_dir: str = "data/trades") -> pd.DataFrame:
        """Process a symbol and generate all trades.

        Args:
            symbol: Symbol name (e.g., 'ETHUSDT')
            data_dir: Directory containing input data
            output_dir: Directory for output trades

        Returns:
            DataFrame with all trades
        """
        print(f"Processing {symbol}...")

        # Load data
        df = self.load_data(symbol, data_dir)
        print(f"  Loaded {len(df)} 1-minute bars")

        # Aggregate into 24-hour periods
        daily_bars = aggregate_24h_periods(df, self.day_start_hour)
        print(f"  Aggregated into {len(daily_bars)} 24-hour periods")

        # Calculate ATR
        atr_series = calculate_crypto_atr(daily_bars, self.atr_period)
        daily_bars["atr"] = atr_series

        # Get unique trading days
        unique_days = daily_bars["day"].unique()

        trades = []

        # Process each trading day
        for i, day_str in enumerate(unique_days):
            # Skip first day (need previous day's ATR)
            if i == 0:
                continue

            # Get previous day's close and ATR
            prev_day = unique_days[i - 1]
            prev_day_data = daily_bars[daily_bars["day"] == prev_day].iloc[0]
            prev_close = prev_day_data["close"]
            prev_atr = prev_day_data["atr"]

            # Calculate breakout levels
            upper_level, lower_level = self.calculate_breakout_levels(prev_close, prev_atr, self.breakout_multiplier)

            # Calculate stop level (will be set after entry is determined)
            stop_distance = prev_atr * self.stop_multiplier

            # Get day boundaries
            day_date = datetime.strptime(day_str, "%Y-%m-%d")
            day_start, day_end = get_day_boundaries(day_date, self.day_start_hour)

            # Detect breakout
            entry = self.detect_breakout(df, upper_level, lower_level, day_start, day_end)

            if entry is None:
                # No breakout this day
                continue

            # Set stop loss level
            if entry["direction"] == 1:  # Long
                stop_level = entry["entry_price"] - stop_distance
            else:  # Short
                stop_level = entry["entry_price"] + stop_distance

            # Execute trade
            trade = self.execute_trade(entry, stop_level, day_end, df)

            # Add metadata
            trade["symbol"] = symbol
            trade["day"] = day_str
            trade["prev_close"] = prev_close
            trade["prev_atr"] = prev_atr
            trade["upper_level"] = upper_level
            trade["lower_level"] = lower_level

            trades.append(trade)

        if not trades:
            print(f"  No trades generated for {symbol}")
            return pd.DataFrame()

        # Create DataFrame
        trades_df = pd.DataFrame(trades)

        # Save to CSV
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        output_file = output_path / f"{symbol}_trades.csv"
        trades_df.to_csv(output_file, index=False)

        print(f"  Generated {len(trades_df)} trades")
        print(f"  Saved to: {output_file}")

        return trades_df


def main():
    """Main function for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Crypto breakout engine")
    parser.add_argument("--symbol", type=str, default=None, help="Symbol to process (e.g., ETHUSDT). Defaults to config default.")
    parser.add_argument("--atr-period", type=int, default=14, help="ATR period (default: 14)")
    parser.add_argument("--breakout-multiplier", type=float, default=0.33, help="Breakout multiplier (default: 0.33)")
    parser.add_argument("--stop-multiplier", type=float, default=0.33, help="Stop loss multiplier (default: 0.33)")
    parser.add_argument("--data-dir", type=str, default="data/raw/crypto", help="Input data directory")
    parser.add_argument("--output-dir", type=str, default="data/trades", help="Output trades directory")
    parser.add_argument("--config", type=str, default="src/config/crypto_symbols.yaml", help="Path to config file")

    args = parser.parse_args()

    # Use default symbol if not provided
    if args.symbol is None:
        config = load_config(args.config)
        args.symbol = get_default_symbol(config)

    # Create engine
    engine = CryptoBreakoutEngine(
        atr_period=args.atr_period, breakout_multiplier=args.breakout_multiplier, stop_multiplier=args.stop_multiplier, config_path=args.config
    )

    # Process symbol
    trades_df = engine.process_symbol(symbol=args.symbol, data_dir=args.data_dir, output_dir=args.output_dir)

    if not trades_df.empty:
        print(f"\n✓ Processing complete: {len(trades_df)} trades generated")
        print(f"\nTrade Summary:")
        print(f"  Total trades: {len(trades_df)}")
        print(f"  Long trades: {len(trades_df[trades_df['direction'] == 'long'])}")
        print(f"  Short trades: {len(trades_df[trades_df['direction'] == 'short'])}")
        print(f"  Total PnL: {trades_df['net_pnl'].sum():.2f}")
        print(f"  Win rate: {len(trades_df[trades_df['net_pnl'] > 0]) / len(trades_df) * 100:.1f}%")


if __name__ == "__main__":
    main()
