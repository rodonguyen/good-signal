"""Portfolio builder step wrapper for backtest runner."""

import pandas as pd
import numpy as np
import yaml
from pathlib import Path
from typing import Any, Mapping, Optional, List, Dict
import json


class PortfolioBuilder:
    """Build portfolio from trades with position sizing."""

    def __init__(self, config_path: str = "src/config/portfolio_config.yaml"):
        """Initialize portfolio builder with configuration.

        Args:
            config_path: Path to portfolio configuration file
        """
        self.config = self._load_config(config_path)
        self.capital_config = self.config["capital"]
        self.sizing_config = self.config["position_sizing"]
        self.symbols = self.config["symbols"]
        self.paths = self.config["paths"]
        self.output = self.config["output"]

        # Create output directory
        Path(self.output["portfolio_dir"]).mkdir(parents=True, exist_ok=True)

    def _load_config(self, config_path: str) -> Dict:
        """Load portfolio configuration."""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_file, "r") as f:
            config = yaml.safe_load(f)

        return config

    def load_trades(self, symbol: str) -> pd.DataFrame:
        """Load trades for a symbol.

        Args:
            symbol: Symbol name (e.g., 'ETHUSDT')

        Returns:
            DataFrame with trades (only allowed trades if loading from filtered_dir)
        """
        # Determine which directory to use
        if self.paths.get("use_filtered", False):
            trades_dir = self.paths["filtered_dir"]
        else:
            trades_dir = self.paths["trades_dir"]

        trades_file = Path(trades_dir) / f"{symbol}_trades.csv"

        if not trades_file.exists():
            raise FileNotFoundError(f"Trades file not found: {trades_file}")

        df = pd.read_csv(trades_file)
        df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
        df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)

        # If loading from filtered_dir, filter out trades where isFiltered=True
        # (isFiltered=True means the trade was filtered out, False means it passed)
        if self.paths.get("use_filtered", False) and "isFiltered" in df.columns:
            original_count = len(df)
            df = df[~df["isFiltered"]].copy()
            filtered_count = len(df)
            if original_count != filtered_count:
                print(f"  Filtered out {original_count - filtered_count} trades (isFiltered=True)")

        return df

    def load_all_trades(self) -> pd.DataFrame:
        """Load trades from all symbols.

        Returns:
            Combined DataFrame with all trades
        """
        all_trades = []

        for symbol in self.symbols:
            try:
                trades_df = self.load_trades(symbol)
                all_trades.append(trades_df)
                print(f"  Loaded {len(trades_df)} trades for {symbol}")
            except FileNotFoundError as e:
                print(f"  Warning: {e}")
                continue

        if not all_trades:
            raise ValueError("No trades found for any symbol")

        # Combine all trades
        combined = pd.concat(all_trades, ignore_index=True)

        # Sort by entry time
        combined = combined.sort_values("entry_time").reset_index(drop=True)

        return combined

    def calculate_position_size_risk_based(self, trade: pd.Series, capital: float, risk_per_trade: float) -> float:
        """Calculate position size using risk-based method.

        Args:
            trade: Trade row with entry_price, stop_level, prev_atr
            capital: Current capital
            risk_per_trade: Risk percentage per trade (e.g., 0.01 = 1%)

        Returns:
            Position size (number of contracts/units)
        """
        # Calculate risk amount
        risk_amount = capital * risk_per_trade

        # Calculate risk per unit (distance to stop)
        risk_per_unit = abs(trade["entry_price"] - trade["stop_level"])

        # Avoid division by zero
        if risk_per_unit <= 0:
            raise ValueError("Risk per unit is less than or equal to zero")

        position_size = risk_amount / risk_per_unit
        return position_size

    def apply_position_sizing(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """Apply position sizing to all trades.

        Args:
            trades_df: DataFrame with trades

        Returns:
            DataFrame with position_size and adjusted PnL columns
        """
        trades_df = trades_df.copy()
        method = self.sizing_config["method"]
        initial_capital = self.capital_config["initial"]

        if method == "risk_based":
            risk_per_trade = self.sizing_config["risk_based"]["risk_per_trade"]
            capital = initial_capital

            # Calculate position size for each trade
            position_sizes = []
            for idx, trade in trades_df.iterrows():
                size = self.calculate_position_size_risk_based(trade, capital, risk_per_trade)
                position_sizes.append(size)

                # Update capital (simple: add/subtract PnL)
                # In reality, capital changes after each trade
                capital += trade["net_pnl"] * size

            trades_df["position_size"] = position_sizes
        else:
            raise ValueError(f"Unknown position sizing method: {method}")

        # Adjust PnL based on position size
        trades_df["portfolio_pnl"] = trades_df["net_pnl"] * trades_df["position_size"]

        return trades_df

    def calculate_equity_curve(self, trades_df: pd.DataFrame) -> pd.Series:
        """Calculate portfolio equity curve.

        Args:
            trades_df: DataFrame with trades and portfolio_pnl

        Returns:
            Series with cumulative equity
        """
        # Sort by exit time
        trades_sorted = trades_df.sort_values("exit_time").copy()

        # Calculate cumulative PnL
        initial_capital = self.capital_config["initial"]
        cumulative_pnl = trades_sorted["portfolio_pnl"].cumsum()
        equity = initial_capital + cumulative_pnl

        # Create time series
        equity_curve = pd.Series(equity.values, index=trades_sorted["exit_time"])

        return equity_curve

    def calculate_drawdown(self, equity_curve: pd.Series) -> pd.Series:
        """Calculate drawdown from equity curve.

        Args:
            equity_curve: Series with equity values

        Returns:
            Series with drawdown values
        """
        # Calculate running maximum
        running_max = equity_curve.expanding().max()

        # Calculate drawdown
        drawdown = (equity_curve - running_max) / running_max * 100

        return drawdown

    def build_portfolio(self) -> pd.DataFrame:
        """Build complete portfolio from trades.

        Returns:
            DataFrame with portfolio trades
        """
        print("Building portfolio...")

        # Load all trades
        trades_df = self.load_all_trades()
        print(f"  Total trades loaded: {len(trades_df)}")

        # Apply position sizing
        trades_df = self.apply_position_sizing(trades_df)
        print(f"  Applied position sizing: {self.sizing_config['method']}")

        # Calculate equity curve
        equity_curve = self.calculate_equity_curve(trades_df)

        # Calculate drawdown
        drawdown = self.calculate_drawdown(equity_curve)

        # Add equity and drawdown to trades (mapped by exit time)
        trades_df["equity"] = trades_df["exit_time"].map(equity_curve)
        trades_df["drawdown"] = trades_df["exit_time"].map(drawdown)

        # Save portfolio
        output_file = Path(self.output["portfolio_dir"]) / self.output["portfolio_file"]
        trades_df.to_csv(output_file, index=False)
        print(f"  Saved to: {output_file}")

        # Print summary
        print(f"\nPortfolio Summary:")
        print(f"  Total trades: {len(trades_df)}")
        print(f"  Initial capital: ${self.capital_config['initial']:,.2f}")
        print(f"  Final equity: ${equity_curve.iloc[-1]:,.2f}")
        print(f"  Total return: {(equity_curve.iloc[-1] / self.capital_config['initial'] - 1) * 100:.2f}%")
        print(f"  Max drawdown: {drawdown.min():.2f}%")

        return trades_df

    def export_chart_data(self, trades_df: pd.DataFrame, symbol: str, raw_data_dir: str, output_dir: str) -> Optional[str]:
        """Export chart data as JSON for a specific symbol.

        Args:
            trades_df: DataFrame with all portfolio trades
            symbol: Symbol to export data for
            raw_data_dir: Directory containing raw price data
            output_dir: Directory to save JSON file

        Returns:
            Path to exported JSON file or None if no data
        """
        # Always try to load from filtered_dir first (has isFiltered column with all trades)
        filtered_file = Path(self.paths["filtered_dir"]) / f"{symbol}_trades.csv"
        if filtered_file.exists():
            try:
                all_trades_df = pd.read_csv(filtered_file)
                all_trades_df["entry_time"] = pd.to_datetime(all_trades_df["entry_time"], utc=True)
                all_trades_df["exit_time"] = pd.to_datetime(all_trades_df["exit_time"], utc=True)
                symbol_trades = all_trades_df.copy()  # Use all trades with isFiltered flag
            except Exception:
                # Fallback to portfolio trades
                symbol_trades = trades_df[trades_df["symbol"] == symbol].copy()
        else:
            # Fallback to portfolio trades if filtered file doesn't exist
            symbol_trades = trades_df[trades_df["symbol"] == symbol].copy()

        if len(symbol_trades) == 0:
            print(f"  No trades found for {symbol}, skipping chart data export")
            return None

        # Load price data
        data_file = Path(raw_data_dir) / symbol / f"{symbol}_1min.csv"

        if not data_file.exists():
            print(f"  Price data not found for {symbol}: {data_file}")
            return None

        price_df = pd.read_csv(data_file)
        price_df["timestamp"] = pd.to_datetime(price_df["timestamp"], utc=True)

        # Get date range from trades
        min_date = symbol_trades["entry_time"].min()
        max_date = symbol_trades["exit_time"].max()

        # Filter price data to relevant range (add 1 day buffer)
        price_filtered = price_df[
            (price_df["timestamp"] >= min_date - pd.Timedelta(days=1)) & (price_df["timestamp"] <= max_date + pd.Timedelta(days=1))
        ].copy()

        if len(price_filtered) == 0:
            print(f"  No price data in range for {symbol}")
            return None

        # Resample to 15-minute bars for better performance if dataset is large
        if len(price_filtered) > 10000:
            price_chart = (
                price_filtered.set_index("timestamp")
                .resample("15min")
                .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                .reset_index()
            )
        else:
            price_chart = price_filtered.copy()

        # Convert timestamps to Unix seconds
        if price_chart["timestamp"].dtype == "object":
            price_chart["timestamp"] = pd.to_datetime(price_chart["timestamp"], utc=True)
        price_chart["time"] = (price_chart["timestamp"].astype("int64") // 10**9).astype(int)

        # Prepare candlestick data
        candlestick_data = []
        for _, row in price_chart.iterrows():
            candlestick_data.append(
                {
                    "time": int(row["time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            )

        # Prepare trades data - check if isFiltered column exists (from Block 3)
        trades_list = []
        has_isFiltered = "isFiltered" in symbol_trades.columns

        # If using filtered trades and isFiltered column exists, load all trades from filtered_dir
        if self.paths.get("use_filtered", False) and has_isFiltered:
            # Load all trades from filtered_dir (includes both filtered and unfiltered with flag)
            filtered_file = Path(self.paths["filtered_dir"]) / f"{symbol}_trades.csv"
            if filtered_file.exists():
                try:
                    all_trades_df = pd.read_csv(filtered_file)
                    all_trades_df["entry_time"] = pd.to_datetime(all_trades_df["entry_time"], utc=True)
                    all_trades_df["exit_time"] = pd.to_datetime(all_trades_df["exit_time"], utc=True)
                    symbol_trades = all_trades_df  # Use all trades with isFiltered flag
                except Exception:
                    pass

        for _, trade in symbol_trades.iterrows():
            entry_time = int(pd.Timestamp(trade["entry_time"]).timestamp())
            exit_time = int(pd.Timestamp(trade["exit_time"]).timestamp())

            # Determine isFiltered: True if trade was filtered out, False if passed filters
            is_filtered = False
            if "isFiltered" in trade.index:
                is_filtered = bool(trade["isFiltered"]) if pd.notna(trade["isFiltered"]) else False
            elif has_isFiltered:
                is_filtered = bool(trade.get("isFiltered", False))

            trade_data = {
                "entryTime": entry_time,
                "exitTime": exit_time,
                "entryPrice": float(trade["entry_price"]),
                "exitPrice": float(trade["exit_price"]),
                "direction": str(trade["direction"]),
                "portfolioPnl": (
                    float(trade.get("portfolio_pnl", trade.get("net_pnl", 0)))
                    if pd.notna(trade.get("portfolio_pnl", trade.get("net_pnl", 0)))
                    else 0.0
                ),
                "isFiltered": is_filtered,
            }

            # Add optional fields
            if pd.notna(trade.get("stop_level")):
                trade_data["stopLevel"] = float(trade["stop_level"])
            if pd.notna(trade.get("upper_level")):
                trade_data["upperLevel"] = float(trade["upper_level"])
            if pd.notna(trade.get("lower_level")):
                trade_data["lowerLevel"] = float(trade["lower_level"])
            if "exit_reason" in trade.index and pd.notna(trade["exit_reason"]):
                trade_data["exitReason"] = str(trade["exit_reason"])

            trades_list.append(trade_data)

        # Prepare equity data (filtered by symbol trades exit times)
        equity_data = []
        symbol_trades_sorted = symbol_trades.sort_values("exit_time")
        for _, trade in symbol_trades_sorted.iterrows():
            if pd.notna(trade.get("equity")):
                exit_time = int(pd.Timestamp(trade["exit_time"]).timestamp())
                equity_data.append({"time": exit_time, "value": float(trade["equity"])})

        # Create output directory
        chart_data_dir = Path(output_dir) / "chart_data"
        chart_data_dir.mkdir(parents=True, exist_ok=True)

        # Prepare JSON data
        chart_data = {"symbol": symbol, "candlestickData": candlestick_data, "trades": trades_list, "equityData": equity_data}

        # Save JSON file
        json_file = chart_data_dir / f"{symbol}_chart_data.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(chart_data, f, indent=2)

        print(f"  Exported chart data for {symbol}: {Path(json_file).resolve()}")
        return str(json_file)


def run_portfolio_step(
    trades_dir: str,
    portfolio_dir: str,
    portfolio_config_path: str,
    symbols: list[str],
    strategy_id: str,
) -> Path | None:
    """Run portfolio builder step for a strategy.

    Args:
        trades_dir: Directory containing trade CSVs
        portfolio_dir: Output directory for portfolio files
        portfolio_config_path: Path to portfolio config YAML
        symbols: List of symbols to include
        strategy_id: Strategy identifier (for per-strategy portfolio)

    Returns:
        Path to generated portfolio CSV, or None if failed
    """
    # Create a temporary config dict that points to the strategy's trades
    # We'll modify the portfolio builder to use strategy-specific paths
    strategy_trades_dir = Path(trades_dir) / strategy_id

    if not strategy_trades_dir.exists():
        print(f"  Warning: No trades directory found for strategy {strategy_id}")
        return None

    # Check if we have any trade files
    trade_files = list(strategy_trades_dir.glob("*_trades.csv"))
    if not trade_files:
        print(f"  Warning: No trade files found in {strategy_trades_dir}")
        return None

    # Create portfolio builder with modified config
    # We need to patch the config to point to our strategy's trades
    try:
        builder = PortfolioBuilder(config_path=portfolio_config_path)

        # Override paths to use strategy-specific trades
        builder.paths["trades_dir"] = str(strategy_trades_dir)
        builder.paths["filtered_dir"] = str(strategy_trades_dir)  # Use same dir for now
        builder.paths["use_filtered"] = False  # Use raw trades (no isFiltered column yet)

        # Override symbols to match what we actually have
        builder.symbols = symbols

        # Override output to be strategy-specific
        strategy_portfolio_dir = Path(portfolio_dir) / strategy_id
        strategy_portfolio_dir.mkdir(parents=True, exist_ok=True)
        builder.output["portfolio_dir"] = str(strategy_portfolio_dir)
        builder.output["portfolio_file"] = "portfolio_trades.csv"

        # Build portfolio
        portfolio_df = builder.build_portfolio()

        portfolio_file = strategy_portfolio_dir / "portfolio_trades.csv"
        return portfolio_file

    except Exception as e:
        print(f"  Error building portfolio for {strategy_id}: {e}")
        return None
