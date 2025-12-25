"""Portfolio analysis step wrapper for backtest runner."""

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
import numpy as np
import pandas as pd

from src.backtest.utils.analysis_utils import calculate_statistics
from src.backtest.utils.config import load_config


class PortfolioAnalysis:
    """Analyze portfolio performance and generate reports."""

    def __init__(
        self,
        portfolio_file: str = "data/portfolio/portfolio_trades.csv",
        output_dir: str = "src/reports",
        raw_data_dir: str = "data/raw/crypto",
        breakout_config_path: str = "src/config/breakout_config.yaml",
        trades_dir: str = "data/trades",
    ):
        """Initialize analysis engine.

        Args:
            portfolio_file: Path to portfolio trades CSV
            output_dir: Directory for output reports
            raw_data_dir: Directory containing raw price data
            breakout_config_path: Path to breakout config file
            trades_dir: Directory containing unfiltered trades (for identifying filtered trades)
        """
        self.portfolio_file = Path(portfolio_file)
        self.output_dir = Path(output_dir)
        self.raw_data_dir = Path(raw_data_dir)
        self.breakout_config_path = breakout_config_path
        self.trades_dir = Path(trades_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_portfolio(self) -> tuple[pd.DataFrame, pd.Series, float]:
        """Load portfolio data.

        Returns:
            Tuple of (trades_df, equity_curve, initial_capital)
        """
        if not self.portfolio_file.exists():
            raise FileNotFoundError(f"Portfolio file not found: {self.portfolio_file}")

        df = pd.read_csv(self.portfolio_file)
        df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
        df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)

        # Get equity curve
        equity_curve = pd.Series(df["equity"].values, index=df["exit_time"]).sort_index()

        # Get initial capital (from first equity value or calculate)
        initial_capital = df["equity"].iloc[0] - df["portfolio_pnl"].iloc[0]

        return df, equity_curve, initial_capital

    def load_price_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Load price data for a symbol.

        Args:
            symbol: Symbol name (e.g., 'ETHUSDT')

        Returns:
            DataFrame with price data or None if not found
        """
        data_file = self.raw_data_dir / symbol / f"{symbol}_1min.csv"

        if not data_file.exists():
            return None

        df = pd.read_csv(data_file)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        return df

    def _identify_filtered_trades(self, portfolio_trades: pd.DataFrame, symbol: str) -> set:
        """Identify which trades were filtered out by comparing portfolio trades with unfiltered trades.

        Args:
            portfolio_trades: DataFrame with portfolio trades (filtered)
            symbol: Symbol name

        Returns:
            Set of trade identifiers (entry_time timestamps) that were filtered out
        """
        # Load unfiltered trades for this symbol
        unfiltered_file = self.trades_dir / f"{symbol}_trades.csv"
        if not unfiltered_file.exists():
            return set()

        try:
            unfiltered_df = pd.read_csv(unfiltered_file)
            unfiltered_df["entry_time"] = pd.to_datetime(unfiltered_df["entry_time"], utc=True)

            # Create identifiers for portfolio trades (filtered) - use entry_time as identifier
            portfolio_ids = set(portfolio_trades["entry_time"].values)

            # Create identifiers for unfiltered trades
            unfiltered_ids = set(unfiltered_df["entry_time"].values)

            # Filtered out trades are in unfiltered but not in portfolio
            filtered_out = unfiltered_ids - portfolio_ids
            return filtered_out

        except Exception:
            return set()

    def create_interactive_chart(self, trades_df: pd.DataFrame, price_df: pd.DataFrame, equity_curve: pd.Series) -> str:
        """Create interactive TradingView-style chart using Lightweight Charts JavaScript.

        Args:
            trades_df: DataFrame with trades
            price_df: DataFrame with price data (1-minute bars)
            equity_curve: Series with equity values

        Returns:
            HTML string with embedded TradingView chart
        """
        # Get date range from trades
        if len(trades_df) == 0:
            return "<p>No trades to display</p>"

        min_date = trades_df["entry_time"].min()
        max_date = trades_df["exit_time"].max()

        # Filter price data to relevant range
        price_filtered = price_df[
            (price_df["timestamp"] >= min_date - pd.Timedelta(days=1)) & (price_df["timestamp"] <= max_date + pd.Timedelta(days=1))
        ].copy()

        if len(price_filtered) == 0:
            return "<p>No price data available for chart</p>"

        # Resample to 15-minute bars for better performance (or use 1-min if dataset is small)
        if len(price_filtered) > 10000:
            price_chart = (
                price_filtered.set_index("timestamp")
                .resample("15min")
                .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                .reset_index()
            )
        else:
            price_chart = price_filtered.copy()

        # Convert timestamps to Unix timestamps (seconds)
        # Ensure timestamps are timezone-aware
        if price_chart["timestamp"].dtype == "object":
            price_chart["timestamp"] = pd.to_datetime(price_chart["timestamp"], utc=True)
        price_chart["time"] = (price_chart["timestamp"].astype("int64") // 10**9).astype(int)

        # Prepare candlestick data - ensure all values are numeric
        candlestick_data = []
        for _, row in price_chart.iterrows():
            candlestick_data.append(
                {
                    "time": int(row["time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
                }
            )

        # Prepare equity curve data
        equity_df = pd.DataFrame({"timestamp": equity_curve.index, "equity": equity_curve.values})
        # Ensure timestamps are timezone-aware
        if equity_df["timestamp"].dtype == "object":
            equity_df["timestamp"] = pd.to_datetime(equity_df["timestamp"], utc=True)
        equity_df["time"] = (equity_df["timestamp"].astype("int64") // 10**9).astype(int)

        # Ensure all values are numeric - TradingView expects 'value' for line series
        equity_data = []
        for _, row in equity_df.iterrows():
            if pd.notna(row["equity"]):
                equity_data.append({"time": int(row["time"]), "value": float(row["equity"])})

        # Prepare trades data with markers
        trades_list = []
        for idx, trade in trades_df.iterrows():
            entry_time = int(pd.Timestamp(trade["entry_time"]).timestamp())
            exit_time = int(pd.Timestamp(trade["exit_time"]).timestamp())

            # Entry marker (triangle) - Buy/Sell
            entry_color = "#00ff00" if trade["direction"] == "long" else "#ff0000"
            trades_list.append(
                {
                    "time": entry_time,
                    "position": "aboveBar",
                    "color": entry_color,
                    "shape": "triangleUp" if trade["direction"] == "long" else "triangleDown",
                    "text": f"{'BUY' if trade['direction'] == 'long' else 'SELL'} @ {trade['entry_price']:.2f}",
                    "price": float(trade["entry_price"]),
                }
            )

            # Stop Loss marker (circle) at entry time
            if pd.notna(trade["stop_level"]):
                trades_list.append(
                    {
                        "time": entry_time,
                        "position": "belowBar",
                        "color": "#ffa500",
                        "shape": "circle",
                        "text": f"SL @ {trade['stop_level']:.2f}",
                        "price": float(trade["stop_level"]),
                    }
                )

            # Exit marker (circle) - shows if SL hit or EOD exit
            if "exit_reason" in trade.index:
                exit_reason = trade["exit_reason"] if pd.notna(trade["exit_reason"]) else "end_of_day"
            else:
                exit_reason = "end_of_day"
            if exit_reason == "stop_loss":
                exit_color = "#ff0000"
                exit_text = f"SL HIT @ {trade['exit_price']:.2f} (PnL: ${trade['portfolio_pnl']:.2f})"
            else:
                exit_color = "#00ff00" if trade["portfolio_pnl"] > 0 else "#ff0000"
                exit_text = f"EXIT @ {trade['exit_price']:.2f} (PnL: ${trade['portfolio_pnl']:.2f})"

            trades_list.append(
                {
                    "time": exit_time,
                    "position": "belowBar",
                    "color": exit_color,
                    "shape": "circle",
                    "text": exit_text,
                    "price": float(trade["exit_price"]),
                }
            )

        # Prepare horizontal lines (breakout levels and stops) - only for days with trades
        # Group trades by day to show levels only for days with trades
        trades_df["trade_date"] = pd.to_datetime(trades_df["entry_time"]).dt.date
        days_with_trades = trades_df["trade_date"].unique()

        horizontal_lines = []
        seen_levels_per_day = {}  # Track levels per day to avoid duplicates

        for idx, trade in trades_df.iterrows():
            trade_date = trade["trade_date"]
            trade_date_str = str(trade_date)

            # Initialize seen_levels for this day if not exists
            if trade_date_str not in seen_levels_per_day:
                seen_levels_per_day[trade_date_str] = {"upper": set(), "lower": set(), "stop": set()}

            # Upper breakout level (only show once per day)
            if pd.notna(trade["upper_level"]):
                level_key = f"{trade['upper_level']:.4f}"
                if level_key not in seen_levels_per_day[trade_date_str]["upper"]:
                    horizontal_lines.append(
                        {
                            "price": float(trade["upper_level"]),
                            "color": "#00ff00",
                            "lineWidth": 1,
                            "lineStyle": 2,  # Dashed
                            "axisLabelVisible": True,
                            "title": f'Upper Breakout: {trade["upper_level"]:.2f}',
                        }
                    )
                    seen_levels_per_day[trade_date_str]["upper"].add(level_key)

            # Lower breakout level (only show once per day)
            if pd.notna(trade["lower_level"]):
                level_key = f"{trade['lower_level']:.4f}"
                if level_key not in seen_levels_per_day[trade_date_str]["lower"]:
                    horizontal_lines.append(
                        {
                            "price": float(trade["lower_level"]),
                            "color": "#ff0000",
                            "lineWidth": 1,
                            "lineStyle": 2,  # Dashed
                            "axisLabelVisible": True,
                            "title": f'Lower Breakout: {trade["lower_level"]:.2f}',
                        }
                    )
                    seen_levels_per_day[trade_date_str]["lower"].add(level_key)

            # Stop level (only show once per day)
            if pd.notna(trade["stop_level"]):
                level_key = f"{trade['stop_level']:.4f}"
                if level_key not in seen_levels_per_day[trade_date_str]["stop"]:
                    horizontal_lines.append(
                        {
                            "price": float(trade["stop_level"]),
                            "color": "#ffa500",
                            "lineWidth": 1,
                            "lineStyle": 0,  # Dotted
                            "axisLabelVisible": True,
                            "title": f'Stop Loss: {trade["stop_level"]:.2f}',
                        }
                    )
                    seen_levels_per_day[trade_date_str]["stop"].add(level_key)

        # Generate HTML with TradingView Lightweight Charts
        # Escape JSON data properly for embedding in HTML
        candlestick_data_json = json.dumps(candlestick_data)
        equity_data_json = json.dumps(equity_data)
        horizontal_lines_json = json.dumps(horizontal_lines)
        trades_list_json = json.dumps(trades_list)

        chart_html = f"""
<div id="trading-chart-container" style="width: 100%; height: 700px; margin: 20px 0;"></div>
<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
<script>
(function() {{
    // Wait for library to load and DOM to be ready
    function initChart() {{
        if (typeof LightweightCharts === 'undefined') {{
            setTimeout(initChart, 100);
            return;
        }}
        
        const chartContainer = document.getElementById('trading-chart-container');
        if (!chartContainer) {{
            setTimeout(initChart, 100);
            return;
        }}
        
        const candlestickData = {candlestick_data_json};
        const equityData = {equity_data_json};
        const horizontalLines = {horizontal_lines_json};
        const markers = {trades_list_json};
        
        const chart = LightweightCharts.createChart(chartContainer, {{
            layout: {{
                background: {{ color: '#ffffff' }},
                textColor: '#333',
            }},
            grid: {{
                vertLines: {{ color: '#e0e0e0' }},
                horzLines: {{ color: '#e0e0e0' }},
            }},
            crosshair: {{
                mode: LightweightCharts.CrosshairMode.Normal,
            }},
            rightPriceScale: {{
                borderColor: '#cccccc',
            }},
            timeScale: {{
                borderColor: '#cccccc',
                timeVisible: true,
                secondsVisible: false,
                minBarSpacing: 0.5,
            }},
            width: chartContainer.clientWidth,
            height: 700,
        }});
        
        // Add candlestick series
        const {{ CandlestickSeries }} = LightweightCharts;
        const candlestickSeries = chart.addSeries(CandlestickSeries, {{
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        }});
        
        candlestickSeries.setData(candlestickData);
        
        // Add equity curve on right price scale
        const equitySeries = chart.addLineSeries({{
            color: '#2196F3',
            lineWidth: 2,
            title: 'Equity',
            priceFormat: {{
                type: 'price',
                precision: 2,
                minMove: 0.01,
            }},
            priceScaleId: 'right',
            lastValueVisible: true,
            priceLineVisible: false,
        }});
        
        if (equityData && equityData.length > 0) {{
            equitySeries.setData(equityData);
        }}
        
        // Configure right price scale for equity
        chart.priceScale('right').applyOptions({{
            scaleMargins: {{
                top: 0.1,
                bottom: 0.1,
            }},
        }});
        
        // Add horizontal lines
        horizontalLines.forEach(line => {{
            candlestickSeries.createPriceLine({{
                price: line.price,
                color: line.color,
                lineWidth: line.lineWidth,
                lineStyle: line.lineStyle,
                axisLabelVisible: line.axisLabelVisible,
                title: line.title,
            }});
        }});
        
        // Add trade markers
        const {{ createSeriesMarkers }} = LightweightCharts;
        if (typeof createSeriesMarkers === 'function' && markers.length > 0) {{
            createSeriesMarkers(candlestickSeries, markers);
        }}
        
        // Fit content
        chart.timeScale().fitContent();
        
        // Handle window resize
        window.addEventListener('resize', () => {{
            chart.applyOptions({{ width: chartContainer.clientWidth }});
        }});
    }}
    
    // Start initialization
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', initChart);
    }} else {{
        initChart();
    }}
}})();
</script>
"""

        return chart_html

    def generate_html_report(self, stats: Dict, equity_curve: pd.Series, trades_df: pd.DataFrame) -> str:
        """Generate HTML report with embedded charts.

        Args:
            stats: Dictionary with statistics
            equity_curve: Series with equity values over time
            trades_df: DataFrame with trades

        Returns:
            HTML report as string
        """
        # Load breakout config
        try:
            breakout_config = load_config(self.breakout_config_path)
            strategy = breakout_config.get("strategy", {}).copy()
            paths = breakout_config.get("paths", {}).copy()
        except Exception:
            strategy = {}
            paths = {}

        # Override with values from backtest.yaml if provided (via monkey-patch)
        if hasattr(self, "_strategy_config_override") and self._strategy_config_override:
            strategy.update(
                {
                    k: v
                    for k, v in self._strategy_config_override.items()
                    if v is not None and k in ["atr_period", "breakout_multiplier", "stop_multiplier", "day_start_hour"]
                }
            )

        if hasattr(self, "_fee_rate_override") and self._fee_rate_override is not None:
            strategy["fee_rate"] = self._fee_rate_override

        if hasattr(self, "_raw_data_dir_override"):
            paths["data_dir"] = self._raw_data_dir_override

        if hasattr(self, "_trades_dir_override"):
            paths["output_dir"] = self._trades_dir_override

        # Calculate equity curve data
        if len(equity_curve) > 0:
            equity_data = [
                {"time": int(pd.Timestamp(idx).timestamp()), "value": float(val)} for idx, val in zip(equity_curve.index, equity_curve.values)
            ]
        else:
            equity_data = []

        # Prepare symbol price data for comparison
        price_data = []
        primary_symbol = None
        if len(trades_df) > 0 and len(equity_curve) > 0:
            # Get the most traded symbol
            symbol_counts = trades_df["symbol"].value_counts()
            if len(symbol_counts) > 0:
                primary_symbol = symbol_counts.index[0]
                # Load price data for the primary symbol
                price_df = self.load_price_data(primary_symbol)
                if price_df is not None:
                    # Get date range from equity curve
                    min_date = equity_curve.index.min()
                    max_date = equity_curve.index.max()

                    # Filter price data to relevant range
                    price_filtered = price_df[
                        (price_df["timestamp"] >= min_date - pd.Timedelta(days=1)) & (price_df["timestamp"] <= max_date + pd.Timedelta(days=1))
                    ].copy()

                    if len(price_filtered) > 0:
                        # Resample to daily close prices to match equity curve frequency
                        price_daily = price_filtered.set_index("timestamp").resample("D").agg({"close": "last"}).reset_index()
                        price_daily = price_daily.dropna()

                        # Align price data with equity curve timestamps (use closest available price)
                        for equity_time in equity_curve.index:
                            # Find closest price timestamp
                            time_diff = abs(price_daily["timestamp"] - equity_time)
                            closest_idx = time_diff.idxmin()
                            if time_diff.iloc[closest_idx] <= pd.Timedelta(days=1):
                                price_data.append(
                                    {"time": int(pd.Timestamp(equity_time).timestamp()), "value": float(price_daily.iloc[closest_idx]["close"])}
                                )

        # Calculate drawdown series
        if len(equity_curve) > 0:
            running_max = equity_curve.expanding().max()
            drawdown_series = (equity_curve - running_max) / running_max * 100
            drawdown_data = [
                {"time": int(pd.Timestamp(idx).timestamp()), "value": float(val)} for idx, val in zip(drawdown_series.index, drawdown_series.values)
            ]
        else:
            drawdown_data = []

        # Prepare PnL histogram data
        if len(trades_df) > 0 and "portfolio_pnl" in trades_df.columns:
            pnl_values = trades_df["portfolio_pnl"].dropna().tolist()
            # Create bins for histogram
            min_pnl = min(pnl_values) if pnl_values else 0
            max_pnl = max(pnl_values) if pnl_values else 0
            num_bins = 20
            bin_width = (max_pnl - min_pnl) / num_bins if max_pnl != min_pnl else 1
            bins = [min_pnl + i * bin_width for i in range(num_bins + 1)]
            hist, bin_edges = np.histogram(pnl_values, bins=bins)
            histogram_data = {"labels": [f"{bin_edges[i]:.0f} to {bin_edges[i+1]:.0f}" for i in range(len(hist))], "values": hist.tolist()}
        else:
            histogram_data = {"labels": [], "values": []}

        # Load symbol chart data
        symbols = trades_df["symbol"].unique() if len(trades_df) > 0 else []
        symbol_chart_html = ""
        symbol_chart_script = ""

        if len(symbols) > 0:
            chart_data_dir = self.output_dir / "chart_data"
            for symbol in symbols:
                json_file = chart_data_dir / f"{symbol}_chart_data.json"
                if json_file.exists():
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            chart_data = json.load(f)
                            html_part, script_part = self._create_basic_chart_html_v2(symbol, chart_data)
                            symbol_chart_html += html_part
                            symbol_chart_script += script_part

                    except Exception as e:
                        print(f"  Warning: Could not load chart data for {symbol}: {e}")

        # Format config as plain table
        config_html = f"""
        <h2>Configuration</h2>
        <table>
            <tr>
                <td>ATR Period</td>
                <td>{strategy.get('atr_period', 'N/A')}</td>
            </tr>
            <tr>
                <td>Breakout Multiplier</td>
                <td>{strategy.get('breakout_multiplier', 'N/A')}</td>
            </tr>
            <tr>
                <td>Stop Multiplier</td>
                <td>{strategy.get('stop_multiplier', 'N/A')}</td>
            </tr>
            <tr>
                <td>Day Start Hour</td>
                <td>{strategy.get('day_start_hour', 'N/A')} UTC</td>
            </tr>
            <tr>
                <td>Fee Rate</td>
                <td>{strategy.get('fee_rate', 'N/A')} ({strategy.get('fee_rate', 0) * 100 if strategy.get('fee_rate') else 0:.2f}%)</td>
            </tr>
            <tr>
                <td>Data Directory</td>
                <td>{paths.get('data_dir', 'N/A')}</td>
            </tr>
            <tr>
                <td>Output Directory</td>
                <td>{paths.get('output_dir', 'N/A')}</td>
            </tr>
        </table>
        """
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Performance Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2E86AB;
            border-bottom: 3px solid #2E86AB;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #333;
            margin-top: 30px;
        }}
        .chart-container {{
            margin: 30px 0;
            position: relative;
            height: 400px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Portfolio Performance Report</h1>
        
        {config_html}
        
        <h2>Summary Statistics</h2>
        <table>
            <tr>
                <td>Total Return</td>
                <td>{stats['total_return']:.2f}%</td>
            </tr>
            <tr>
                <td>Annualized Return</td>
                <td>{stats['annualized_return']:.2f}%</td>
            </tr>
            <tr>
                <td>Sharpe Ratio</td>
                <td>{stats['sharpe_ratio']:.2f}</td>
            </tr>
            <tr>
                <td>Max Drawdown</td>
                <td>{stats['max_drawdown']:.2f}%</td>
            </tr>
            <tr>
                <td>Win Rate</td>
                <td>{stats['win_rate']:.1f}%</td>
            </tr>
            <tr>
                <td>Profit Factor</td>
                <td>{stats['profit_factor']:.2f}</td>
            </tr>
            <tr>
                <td>Total Trades</td>
                <td>{stats['total_trades']}</td>
            </tr>
            <tr>
                <td>Avg Trade</td>
                <td>${stats['avg_trade']:.2f}</td>
            </tr>
        </table>
        
        <h2>Portfolio Equity Chart</h2>
        <div class="chart-container">
            <canvas id="equityChart"></canvas>
        </div>
        
        <h2>Max Drawdown Chart</h2>
        <div class="chart-container">
            <canvas id="drawdownChart"></canvas>
        </div>
        
        <h2>Trade PnL Histogram</h2>
        <div class="chart-container">
            <canvas id="pnlHistogram"></canvas>
        </div>
        
        <h2>Detailed Statistics</h2>
        <table>
            <tr>
                <td>Initial Capital</td>
                <td>${stats['initial_capital']:,.2f}</td>
            </tr>
            <tr>
                <td>Final Equity</td>
                <td>${stats['final_equity']:,.2f}</td>
            </tr>
            <tr>
                <td>Total Return</td>
                <td>{stats['total_return']:.2f}%</td>
            </tr>
            <tr>
                <td>Annualized Return</td>
                <td>{stats['annualized_return']:.2f}%</td>
            </tr>
            <tr>
                <td>Sharpe Ratio</td>
                <td>{stats['sharpe_ratio']:.2f}</td>
            </tr>
            <tr>
                <td>Sortino Ratio</td>
                <td>{stats['sortino_ratio']:.2f}</td>
            </tr>
            <tr>
                <td>Max Drawdown</td>
                <td>{stats['max_drawdown']:.2f}%</td>
            </tr>
            <tr>
                <td>Average Drawdown</td>
                <td>{stats['avg_drawdown']:.2f}%</td>
            </tr>
            <tr>
                <td>Total Trades</td>
                <td>{stats['total_trades']}</td>
            </tr>
            <tr>
                <td>Winning Trades</td>
                <td>{stats['winning_trades']}</td>
            </tr>
            <tr>
                <td>Losing Trades</td>
                <td>{stats['losing_trades']}</td>
            </tr>
            <tr>
                <td>Win Rate</td>
                <td>{stats['win_rate']:.2f}%</td>
            </tr>
            <tr>
                <td>Average Win</td>
                <td>${stats['avg_win']:.2f}</td>
            </tr>
            <tr>
                <td>Average Loss</td>
                <td>${stats['avg_loss']:.2f}</td>
            </tr>
            <tr>
                <td>Profit Factor</td>
                <td>{stats['profit_factor']:.2f}</td>
            </tr>
            <tr>
                <td>Average Trade Duration</td>
                <td>{stats['avg_trade_duration_hours']:.1f} hours ({stats['avg_trade_duration_days']:.2f} days)</td>
            </tr>
            <tr>
                <td>Trades Per Year</td>
                <td>{stats['trades_per_year']:.1f}</td>
            </tr>
            <tr>
                <td>Period</td>
                <td>{stats['days']} days ({stats['years']:.2f} years)</td>
            </tr>
        </table>
        
        {symbol_chart_html}
        
        <p style="margin-top: 30px; color: #666; font-size: 12px;">
            Report generated on {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
        </p>
    </div>
    
    <script>
        // PortfolioChart module for symbol charts
        (function() {{
            'use strict';
            const PortfolioChart = {{
                init(containerId, chartData, options = {{}}) {{
                    if (typeof LightweightCharts === 'undefined') {{
                        console.error('LightweightCharts library not loaded');
                        return;
                    }}
                    const container = document.getElementById(containerId);
                    if (!container) {{
                        console.error(`Container not found: ${{containerId}}`);
                        return;
                    }}
                    container.innerHTML = '';
                    const chart = LightweightCharts.createChart(container, {{
                        layout: {{
                            background: {{ color: '#131722' }},
                            textColor: '#d1d4dc'
                        }},
                        grid: {{
                            vertLines: {{ color: '#2a2e39' }},
                            horzLines: {{ color: '#2a2e39' }}
                        }},
                        crosshair: {{
                            mode: LightweightCharts.CrosshairMode.Normal
                        }},
                        timeScale: {{
                            timeVisible: true,
                            secondsVisible: true,
                            minBarSpacing: 0.5,
                        }},
                    width: container.clientWidth,
                    height: options.height || 700
                }});
                const {{ CandlestickSeries }} = LightweightCharts;
                const candlestickSeries = chart.addSeries(CandlestickSeries, {{
                    upColor: '#26a69a',
                    downColor: '#ef5350',
                    borderVisible: false,
                    wickUpColor: '#26a69a',
                    wickDownColor: '#ef5350'
                }});
                    if (chartData.candlestickData && chartData.candlestickData.length > 0) {{
                        candlestickSeries.setData(chartData.candlestickData);
                    }}
                    
                    if (chartData.bollingerBands && chartData.bollingerBands.length > 0) {{
                        const {{ LineSeries }} = LightweightCharts;
                        const bbUpperSeries = chart.addSeries(LineSeries, {{
                            color: '#9b59b6',
                            lineWidth: 1,
                            lineStyle: LightweightCharts.LineStyle.Solid,
                            priceLineVisible: false,
                            lastValueVisible: false,
                            crosshairMarkerVisible: true,
                            title: 'BB Upper'
                        }});
                        bbUpperSeries.setData(chartData.bollingerBands.map(bb => ({{
                            time: bb.time,
                            value: bb.upper
                        }})));
                        
                        const bbMiddleSeries = chart.addSeries(LineSeries, {{
                            color: '#3498db',
                            lineWidth: 1,
                            lineStyle: LightweightCharts.LineStyle.Solid,
                            priceLineVisible: false,
                            lastValueVisible: false,
                            crosshairMarkerVisible: true,
                            title: 'BB Middle'
                        }});
                        bbMiddleSeries.setData(chartData.bollingerBands.map(bb => ({{
                            time: bb.time,
                            value: bb.middle
                        }})));
                        
                        const bbLowerSeries = chart.addSeries(LineSeries, {{
                            color: '#9b59b6',
                            lineWidth: 1,
                            lineStyle: LightweightCharts.LineStyle.Solid,
                            priceLineVisible: false,
                            lastValueVisible: false,
                            crosshairMarkerVisible: true,
                            title: 'BB Lower'
                        }});
                        bbLowerSeries.setData(chartData.bollingerBands.map(bb => ({{
                            time: bb.time,
                            value: bb.lower
                        }})));
                    }}
                    
                    // Detect strategy type from trade data
                    const hasStopLevel = chartData.trades && chartData.trades.some(t => t.stopLevel != null);
                    const hasUpperLower = chartData.trades && chartData.trades.some(t => t.upperLevel != null || t.lowerLevel != null);
                    const isSupertrend = hasStopLevel || (hasUpperLower && !chartData.bollingerBands);
                    
                    if (chartData.trades && chartData.trades.length > 0) {{
                        const markers = [];
                        const {{ LineSeries }} = LightweightCharts;
                        const processedDays = new Set();
                        chartData.trades.forEach(trade => {{
                            const isFiltered = trade.isFiltered === true;
                            const longColor = isFiltered ? '#80cc80' : '#00ff00';
                            const shortColor = isFiltered ? '#cc8080' : '#ff0000';
                            const profitColor = isFiltered ? '#80cc80' : '#00ff00';
                            const lossColor = isFiltered ? '#cc8080' : '#ff0000';
                            if (trade.entryTime && trade.direction) {{
                                const isLong = trade.direction === 'long';
                                markers.push({{
                                    time: trade.entryTime,
                                    position: 'aboveBar',
                                    color: isLong ? longColor : shortColor,
                                    shape: isLong ? 'arrowUp' : 'arrowDown',
                                    size: 2
                                }});
                            }}
                            if (trade.exitTime) {{
                                const isProfit = trade.portfolioPnl !== undefined 
                                    ? trade.portfolioPnl >= 0 
                                    : (trade.entryPrice - trade.exitPrice) >= 0;
                                markers.push({{
                                    time: trade.exitTime,
                                    position: 'belowBar',
                                    color: isProfit ? profitColor : lossColor,
                                    shape: 'circle',
                                    size: 2
                                }});
                            }}
                            
                            // Strategy-specific rendering: Supertrend (stopLevel, upperLevel, lowerLevel)
                            if (isSupertrend && trade.entryTime) {{
                                const entryDate = new Date(trade.entryTime * 1000);
                                let start13UTC = new Date(Date.UTC(
                                    entryDate.getUTCFullYear(),
                                    entryDate.getUTCMonth(),
                                    entryDate.getUTCDate(),
                                    13, 0, 0, 0
                                ));
                                if (start13UTC.getTime() > entryDate.getTime()) {{
                                    start13UTC.setUTCDate(start13UTC.getUTCDate() - 1);
                                }}
                                const dayKey = start13UTC.getTime() / 1000;
                                if (!processedDays.has(dayKey)) {{
                                    processedDays.add(dayKey);
                                    const endTime = dayKey + 86400;
                                    
                                    // Upper level (for breakout strategies)
                                    if (trade.upperLevel != null) {{
                                        const upperSeries = chart.addSeries(LineSeries, {{
                                            color: '#00ff00',
                                            lineWidth: 1,
                                            lineStyle: LightweightCharts.LineStyle.Dotted,
                                            priceLineVisible: false,
                                            lastValueVisible: false,
                                            crosshairMarkerVisible: false
                                        }});
                                        upperSeries.setData([
                                            {{ time: dayKey, value: trade.upperLevel }},
                                            {{ time: endTime, value: trade.upperLevel }}
                                        ]);
                                    }}
                                    
                                    // Lower level (for breakout strategies)
                                    if (trade.lowerLevel != null) {{
                                        const lowerSeries = chart.addSeries(LineSeries, {{
                                            color: '#ffa500',
                                            lineWidth: 1,
                                            lineStyle: LightweightCharts.LineStyle.Dotted,
                                            priceLineVisible: false,
                                            lastValueVisible: false,
                                            crosshairMarkerVisible: false
                                        }});
                                        lowerSeries.setData([
                                            {{ time: dayKey, value: trade.lowerLevel }},
                                            {{ time: endTime, value: trade.lowerLevel }}
                                        ]);
                                    }}
                                    
                                    // Stop level (for supertrend strategies)
                                    if (trade.stopLevel != null) {{
                                        const stopSeries = chart.addSeries(LineSeries, {{
                                            color: '#ffff00',
                                            lineWidth: 1,
                                            lineStyle: LightweightCharts.LineStyle.Dotted,
                                            priceLineVisible: false,
                                            lastValueVisible: false,
                                            crosshairMarkerVisible: false
                                        }});
                                        stopSeries.setData([
                                            {{ time: dayKey, value: trade.stopLevel }},
                                            {{ time: endTime, value: trade.stopLevel }}
                                        ]);
                                    }}
                                }}
                            }}
                        }});
                        if (markers.length > 0) {{
                            try {{
                                const {{ createSeriesMarkers }} = LightweightCharts;
                                if (typeof createSeriesMarkers === 'function') {{
                                    createSeriesMarkers(candlestickSeries, markers);
                                }}
                            }} catch (error) {{
                                console.error('Error adding markers:', error);
                            }}
                        }}
                    }}
                    chart.timeScale().fitContent();
                    window.addEventListener('resize', () => {{
                        chart.applyOptions({{ width: container.clientWidth }});
                    }});
                    return chart;
                }}
            }};
            window.PortfolioChart = PortfolioChart;
        }})();
        
        {symbol_chart_script}
        
        // Date formatting function for DD/MM/YYYY
        function formatDateDDMMYYYY(timestamp) {{
            const date = new Date(timestamp * 1000);
            const day = String(date.getDate()).padStart(2, '0');
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const year = date.getFullYear();
            return `${{day}}/${{month}}/${{year}}`;
        }}
        
        // Equity Chart
        const equityData = {json.dumps(equity_data)};
        const priceData = {json.dumps(price_data)};
        
        // Convert to Chart.js time scale format (timestamps in milliseconds)
        const equityChartData = equityData.map(d => ({{
            x: d.time * 1000,  // Convert to milliseconds for Chart.js
            y: d.value
        }}));
        
        // Align price data with equity timestamps
        const priceChartData = [];
        if (priceData.length > 0) {{
            const priceMap = new Map(priceData.map(d => [d.time, d.value]));
            equityData.forEach(d => {{
                const price = priceMap.get(d.time);
                if (price !== undefined) {{
                    priceChartData.push({{
                        x: d.time * 1000,
                        y: price
                    }});
                }}
            }});
        }}
        
        const equityCtx = document.getElementById('equityChart').getContext('2d');
        const datasets = [{{
            label: 'Portfolio Equity ($)',
            data: equityChartData,
            borderColor: '#2E86AB',
            backgroundColor: 'rgba(46, 134, 171, 0.1)',
            fill: true,
            tension: 0.1,
            yAxisID: 'y'
        }}];
        
        if (priceData.length > 0) {{
            const symbolName = '{primary_symbol if primary_symbol else "Symbol"}';
            datasets.push({{
                label: symbolName + ' Price ($)',
                data: priceChartData,
                borderColor: '#ff9800',
                backgroundColor: 'rgba(255, 152, 0, 0.1)',
                fill: false,
                tension: 0.1,
                yAxisID: 'y1'
            }});
        }}
        
        new Chart(equityCtx, {{
            type: 'line',
            data: {{
                datasets: datasets
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{
                    mode: 'index',
                    intersect: false
                }},
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Portfolio Equity Over Time'
                    }},
                    legend: {{
                        display: true
                    }},
                    tooltip: {{
                        callbacks: {{
                            title: function(context) {{
                                const date = new Date(context[0].parsed.x);
                                const day = String(date.getDate()).padStart(2, '0');
                                const month = String(date.getMonth() + 1).padStart(2, '0');
                                const year = date.getFullYear();
                                return day + '/' + month + '/' + year;
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        type: 'linear',
                        display: true,
                        position: 'left',
                        beginAtZero: false,
                        title: {{
                            display: true,
                            text: 'Equity ($)'
                        }},
                        ticks: {{
                            callback: function(value) {{
                                return '$' + value.toLocaleString();
                            }}
                        }}
                    }},
                    y1: {{
                        type: 'linear',
                        display: priceData.length > 0,
                        position: 'right',
                        beginAtZero: false,
                        title: {{
                            display: true,
                            text: 'Price ($)'
                        }},
                        ticks: {{
                            callback: function(value) {{
                                return '$' + value.toLocaleString();
                            }}
                        }},
                        grid: {{
                            drawOnChartArea: false
                        }}
                    }},
                    x: {{
                        type: 'time',
                        time: {{
                            unit: 'day',
                            displayFormats: {{
                                day: 'dd/MM/yyyy'
                            }},
                            tooltipFormat: 'dd/MM/yyyy'
                        }},
                        ticks: {{
                            maxRotation: 45,
                            minRotation: 45,
                            source: 'data',
                            autoSkip: true,
                            maxTicksLimit: 15
                        }},
                        title: {{
                            display: true,
                            text: 'Date'
                        }}
                    }}
                }}
            }}
        }});
        
        // Drawdown Chart
        const drawdownData = {json.dumps(drawdown_data)};
        
        // Convert to Chart.js time scale format (timestamps in milliseconds)
        const drawdownChartData = drawdownData.map(d => ({{
            x: d.time * 1000,  // Convert to milliseconds for Chart.js
            y: d.value
        }}));
        
        const drawdownCtx = document.getElementById('drawdownChart').getContext('2d');
        new Chart(drawdownCtx, {{
            type: 'line',
            data: {{
                datasets: [{{
                    label: 'Drawdown (%)',
                    data: drawdownChartData,
                    borderColor: '#ef5350',
                    backgroundColor: 'rgba(239, 83, 80, 0.1)',
                    fill: true,
                    tension: 0.1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{
                    mode: 'index',
                    intersect: false
                }},
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Portfolio Drawdown Over Time'
                    }},
                    legend: {{
                        display: true
                    }},
                    tooltip: {{
                        callbacks: {{
                            title: function(context) {{
                                const date = new Date(context[0].parsed.x);
                                const day = String(date.getDate()).padStart(2, '0');
                                const month = String(date.getMonth() + 1).padStart(2, '0');
                                const year = date.getFullYear();
                                return day + '/' + month + '/' + year;
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: false,
                        title: {{
                            display: true,
                            text: 'Drawdown (%)'
                        }}
                    }},
                    x: {{
                        type: 'time',
                        time: {{
                            unit: 'day',
                            displayFormats: {{
                                day: 'dd/MM/yyyy'
                            }},
                            tooltipFormat: 'dd/MM/yyyy'
                        }},
                        ticks: {{
                            maxRotation: 45,
                            minRotation: 45,
                            source: 'data',
                            autoSkip: true,
                            maxTicksLimit: 15
                        }},
                        title: {{
                            display: true,
                            text: 'Date'
                        }}
                    }}
                }}
            }}
        }});
        
        // PnL Histogram
        const histogramData = {json.dumps(histogram_data)};
        const pnlCtx = document.getElementById('pnlHistogram').getContext('2d');
        
        // Helper function to determine if a bin represents positive PnL
        function isPositiveBin(label) {{
            // Parse label like "-14 to 1" or "1 to 16"
            const match = label.match(/^(-?\d+(?:\.\d+)?)\s+to\s+(-?\d+(?:\.\d+)?)$/);
            if (!match) return false;
            const startValue = parseFloat(match[1]);
            const endValue = parseFloat(match[2]);
            // If bin starts at or above 0, it's positive (green)
            // If bin ends below 0, it's negative (red)
            // If bin spans zero, use the midpoint
            if (startValue >= 0) return true;
            if (endValue <= 0) return false;
            // Bin spans zero, use midpoint
            return (startValue + endValue) / 2 >= 0;
        }}
        
        new Chart(pnlCtx, {{
            type: 'bar',
            data: {{
                labels: histogramData.labels,
                datasets: [{{
                    label: 'Number of Trades',
                    data: histogramData.values,
                    backgroundColor: histogramData.values.map((v, i) => {{
                        if (histogramData.values[i] === 0) return 'rgba(158, 158, 158, 0.6)';
                        const label = histogramData.labels[i];
                        return isPositiveBin(label) ? 'rgba(76, 175, 80, 0.6)' : 'rgba(239, 83, 80, 0.6)';
                    }}),
                    borderColor: histogramData.values.map((v, i) => {{
                        if (histogramData.values[i] === 0) return '#9e9e9e';
                        const label = histogramData.labels[i];
                        return isPositiveBin(label) ? '#4caf50' : '#ef5350';
                    }}),
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Distribution of Trade PnL'
                    }},
                    legend: {{
                        display: false
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{
                            display: true,
                            text: 'Number of Trades'
                        }}
                    }},
                    x: {{
                        title: {{
                            display: true,
                            text: 'PnL Range ($)'
                        }},
                        ticks: {{
                            maxRotation: 45,
                            minRotation: 45
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
        return html

    def generate_chart_files(self, trades_df: pd.DataFrame, equity_curve: pd.Series) -> None:
        """Generate JSON data files and HTML chart files per symbol.

        Args:
            trades_df: DataFrame with all portfolio trades
            equity_curve: Series with equity values
        """
        # Get unique symbols from trades
        symbols = trades_df["symbol"].unique()

        if len(symbols) == 0:
            print("  No symbols found in trades, skipping chart file generation")
            return

        # Use PortfolioBuilder's export_chart_data method
        try:
            from src.backtest.steps.portfolio import PortfolioBuilder

            builder = PortfolioBuilder()
        except ImportError:
            raise ImportError("PortfolioBuilder not found")

        for symbol in symbols:
            try:
                # Export JSON data using PortfolioBuilder method
                json_file = builder.export_chart_data(
                    trades_df=trades_df, symbol=symbol, raw_data_dir=str(self.raw_data_dir), output_dir=str(self.output_dir)
                )

                if json_file:
                    # Load JSON data to embed in HTML (avoids CORS issues)
                    with open(json_file, "r", encoding="utf-8") as f:
                        chart_data = json.load(f)
                    # Generate HTML file for this symbol with embedded data
                    html_file = self.output_dir / f"{symbol}_chart.html"
                    self.generate_symbol_chart_html(html_file, symbol, chart_data)
                    print(f"  Generated chart file: {Path(html_file).resolve()}")

            except Exception as e:
                print(f"  Error generating chart for {symbol}: {e}")
                continue

    def export_chart_data_for_symbol(self, trades_df: pd.DataFrame, symbol: str, equity_curve: pd.Series) -> Optional[str]:
        """Export chart data as JSON for a specific symbol.

        Args:
            trades_df: DataFrame with all portfolio trades
            symbol: Symbol to export data for
            equity_curve: Series with equity values

        Returns:
            Path to exported JSON file or None if no data
        """
        # Filter trades for this symbol
        symbol_trades = trades_df[trades_df["symbol"] == symbol].copy()

        if len(symbol_trades) == 0:
            return None

        # Load price data
        price_df = self.load_price_data(symbol)
        if price_df is None:
            return None

        # Get date range from trades
        min_date = symbol_trades["entry_time"].min()
        max_date = symbol_trades["exit_time"].max()

        # Filter price data to relevant range (add 1 day buffer)
        price_filtered = price_df[
            (price_df["timestamp"] >= min_date - pd.Timedelta(days=1)) & (price_df["timestamp"] <= max_date + pd.Timedelta(days=1))
        ].copy()

        if len(price_filtered) == 0:
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

        # Identify filtered trades (trades in unfiltered but not in portfolio)
        filtered_trade_times = self._identify_filtered_trades(symbol_trades, symbol)

        # Prepare trades data (portfolio trades - these are allowed/filtered in)
        trades_list = []
        for _, trade in symbol_trades.iterrows():
            entry_time = int(pd.Timestamp(trade["entry_time"]).timestamp())
            exit_time = int(pd.Timestamp(trade["exit_time"]).timestamp())

            trade_data = {
                "entryTime": entry_time,
                "exitTime": exit_time,
                "entryPrice": float(trade["entry_price"]),
                "exitPrice": float(trade["exit_price"]),
                "direction": str(trade["direction"]),
                "portfolioPnl": float(trade["portfolio_pnl"]) if pd.notna(trade["portfolio_pnl"]) else 0.0,
                "isFiltered": False,  # These are allowed trades
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

        # Add filtered out trades (trades that were removed by filters)
        unfiltered_file = self.trades_dir / f"{symbol}_trades.csv"
        if unfiltered_file.exists():
            try:
                unfiltered_df = pd.read_csv(unfiltered_file)
                unfiltered_df["entry_time"] = pd.to_datetime(unfiltered_df["entry_time"], utc=True)
                unfiltered_df["exit_time"] = pd.to_datetime(unfiltered_df["exit_time"], utc=True)

                # Get filtered out trades (in unfiltered but not in portfolio)
                portfolio_entry_times = set(symbol_trades["entry_time"].values)
                filtered_out_df = unfiltered_df[~unfiltered_df["entry_time"].isin(portfolio_entry_times)]

                for _, trade in filtered_out_df.iterrows():
                    entry_time = int(pd.Timestamp(trade["entry_time"]).timestamp())
                    exit_time = int(pd.Timestamp(trade["exit_time"]).timestamp())

                    trade_data = {
                        "entryTime": entry_time,
                        "exitTime": exit_time,
                        "entryPrice": float(trade["entry_price"]),
                        "exitPrice": float(trade["exit_price"]),
                        "direction": str(trade["direction"]),
                        "portfolioPnl": float(trade.get("net_pnl", 0)) if pd.notna(trade.get("net_pnl")) else 0.0,
                        "isFiltered": True,  # These are filtered out trades
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
            except Exception:
                pass  # If we can't load unfiltered trades, just skip

        # Prepare equity data (filtered by symbol trades exit times)
        equity_data = []
        symbol_trades_sorted = symbol_trades.sort_values("exit_time")
        for _, trade in symbol_trades_sorted.iterrows():
            if pd.notna(trade.get("equity")):
                exit_time = int(pd.Timestamp(trade["exit_time"]).timestamp())
                equity_data.append({"time": exit_time, "value": float(trade["equity"])})

        # Create output directory
        chart_data_dir = self.output_dir / "chart_data"
        chart_data_dir.mkdir(parents=True, exist_ok=True)

        # Prepare JSON data
        chart_data = {"symbol": symbol, "candlestickData": candlestick_data, "trades": trades_list, "equityData": equity_data}

        # Save JSON file
        json_file = chart_data_dir / f"{symbol}_chart_data.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(chart_data, f, indent=2)

        return str(json_file.relative_to(self.output_dir))

    def generate_symbol_chart_html(self, html_file: Path, symbol: str, chart_data: dict) -> None:
        """Generate HTML chart file for a symbol.

        Args:
            html_file: Path to output HTML file
            symbol: Symbol name
            chart_data: Chart data dictionary to embed
        """
        # Use the basic template with embedded data
        html_content = self._create_basic_chart_html(symbol, chart_data)

        # Write HTML file
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)

    def _create_basic_chart_html(self, symbol: str, chart_data: dict) -> str:
        """Create basic HTML chart template with embedded data and JSON upload.

        Args:
            symbol: Symbol name
            chart_data: Chart data dictionary to embed

        Returns:
            HTML content as string
        """
        # Convert chart_data to JSON string, escaping for JavaScript
        chart_data_json = json.dumps(chart_data)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Portfolio Chart - {symbol}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2E86AB;
            border-bottom: 3px solid #2E86AB;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .controls {{
            margin-bottom: 20px;
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        .upload-btn {{
            background-color: #2E86AB;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }}
        .upload-btn:hover {{
            background-color: #1e5f7a;
        }}
        .upload-btn input[type="file"] {{
            display: none;
        }}
        #chart-container {{
            width: 100%;
            height: 700px;
            margin: 20px 0;
        }}
        .error {{
            color: #d32f2f;
            padding: 20px;
            background-color: #ffebee;
            border-radius: 4px;
            margin: 20px 0;
        }}
        .success {{
            color: #2e7d32;
            padding: 10px;
            background-color: #e8f5e9;
            border-radius: 4px;
            margin: 10px 0;
            display: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Portfolio Trading Chart - {symbol}</h1>
        <div class="controls">
            <label class="upload-btn">
                <input type="file" id="json-file-input" accept=".json" />
                Upload JSON to Replace Chart Data
            </label>
            <span id="status-message" class="success"></span>
        </div>
        <div id="chart-container"></div>
        <div id="error-message" class="error" style="display: none;"></div>
    </div>

    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
    <script>
        // Inline PortfolioChart module (avoids loading external file)
        (function() {{
            'use strict';
            const PortfolioChart = {{
                init(containerId, chartData, options = {{}}) {{
                    if (typeof LightweightCharts === 'undefined') {{
                        console.error('LightweightCharts library not loaded');
                        return;
                    }}
                    const container = document.getElementById(containerId);
                    if (!container) {{
                        console.error(`Container not found: ${{containerId}}`);
                        return;
                    }}
                    // Clear existing chart if any
                    container.innerHTML = '';
                    const chart = LightweightCharts.createChart(container, {{
                        layout: {{
                            background: {{ color: '#131722' }},
                            textColor: '#d1d4dc'
                        }},
                        grid: {{
                            vertLines: {{ color: '#2a2e39' }},
                            horzLines: {{ color: '#2a2e39' }}
                        }},
                        crosshair: {{
                            mode: LightweightCharts.CrosshairMode.Normal
                        }},
                        timeScale: {{
                            timeVisible: true,
                            secondsVisible: true
                        }},
                        width: container.clientWidth,
                        height: options.height || 700
                    }});
                    const {{ CandlestickSeries }} = LightweightCharts;
                    const candlestickSeries = chart.addSeries(CandlestickSeries, {{
                        upColor: '#26a69a',
                        downColor: '#ef5350',
                        borderVisible: false,
                        wickUpColor: '#26a69a',
                        wickDownColor: '#ef5350'
                    }});
                    if (chartData.candlestickData && chartData.candlestickData.length > 0) {{
                        candlestickSeries.setData(chartData.candlestickData);
                    }}
                    
                    // Add Bollinger Bands if available (for BB strategies)
                    if (chartData.bollingerBands && chartData.bollingerBands.length > 0) {{
                        const {{ LineSeries }} = LightweightCharts;
                        // Upper band
                        const bbUpperSeries = chart.addSeries(LineSeries, {{
                            color: '#9b59b6',
                            lineWidth: 1,
                            lineStyle: LightweightCharts.LineStyle.Solid,
                            priceLineVisible: false,
                            lastValueVisible: false,
                            crosshairMarkerVisible: true,
                            title: 'BB Upper'
                        }});
                        bbUpperSeries.setData(chartData.bollingerBands.map(bb => ({{
                            time: bb.time,
                            value: bb.upper
                        }})));
                        
                        // Middle band (SMA)
                        const bbMiddleSeries = chart.addSeries(LineSeries, {{
                            color: '#3498db',
                            lineWidth: 1,
                            lineStyle: LightweightCharts.LineStyle.Solid,
                            priceLineVisible: false,
                            lastValueVisible: false,
                            crosshairMarkerVisible: true,
                            title: 'BB Middle'
                        }});
                        bbMiddleSeries.setData(chartData.bollingerBands.map(bb => ({{
                            time: bb.time,
                            value: bb.middle
                        }})));
                        
                        // Lower band
                        const bbLowerSeries = chart.addSeries(LineSeries, {{
                            color: '#9b59b6',
                            lineWidth: 1,
                            lineStyle: LightweightCharts.LineStyle.Solid,
                            priceLineVisible: false,
                            lastValueVisible: false,
                            crosshairMarkerVisible: true,
                            title: 'BB Lower'
                        }});
                        bbLowerSeries.setData(chartData.bollingerBands.map(bb => ({{
                            time: bb.time,
                            value: bb.lower
                        }})));
                    }}
                    
                    if (chartData.trades && chartData.trades.length > 0) {{
                        const markers = [];
                        const {{ LineSeries }} = LightweightCharts;
                        const processedDays = new Set();
                        chartData.trades.forEach(trade => {{
                            const isFiltered = trade.isFiltered === true;
                            const longColor = isFiltered ? '#80cc80' : '#00ff00';
                            const shortColor = isFiltered ? '#cc8080' : '#ff0000';
                            const profitColor = isFiltered ? '#80cc80' : '#00ff00';
                            const lossColor = isFiltered ? '#cc8080' : '#ff0000';
                            if (trade.entryTime && trade.direction) {{
                                const isLong = trade.direction === 'long';
                                markers.push({{
                                    time: trade.entryTime,
                                    position: 'aboveBar',
                                    color: isLong ? longColor : shortColor,
                                    shape: isLong ? 'arrowUp' : 'arrowDown',
                                    size: 2
                                }});
                            }}
                            if (trade.exitTime) {{
                                const isProfit = trade.portfolioPnl !== undefined 
                                    ? trade.portfolioPnl >= 0 
                                    : (trade.entryPrice - trade.exitPrice) >= 0;
                                markers.push({{
                                    time: trade.exitTime,
                                    position: 'belowBar',
                                    color: isProfit ? profitColor : lossColor,
                                    shape: 'circle',
                                    size: 2
                                }});
                            }}
                            if (trade.entryTime) {{
                                const entryDate = new Date(trade.entryTime * 1000);
                                let start13UTC = new Date(Date.UTC(
                                    entryDate.getUTCFullYear(),
                                    entryDate.getUTCMonth(),
                                    entryDate.getUTCDate(),
                                    13, 0, 0, 0
                                ));
                                if (start13UTC.getTime() > entryDate.getTime()) {{
                                    start13UTC.setUTCDate(start13UTC.getUTCDate() - 1);
                                }}
                                const dayKey = start13UTC.getTime() / 1000;
                                if (!processedDays.has(dayKey)) {{
                                    processedDays.add(dayKey);
                                    const endTime = dayKey + 86400;
                                    if (trade.upperLevel != null) {{
                                        const upperSeries = chart.addSeries(LineSeries, {{
                                            color: '#00ff00',
                                            lineWidth: 1,
                                            lineStyle: LightweightCharts.LineStyle.Dotted,
                                            priceLineVisible: false,
                                            lastValueVisible: false,
                                            crosshairMarkerVisible: false
                                        }});
                                        upperSeries.setData([
                                            {{ time: dayKey, value: trade.upperLevel }},
                                            {{ time: endTime, value: trade.upperLevel }}
                                        ]);
                                    }}
                                    if (trade.lowerLevel != null) {{
                                        const lowerSeries = chart.addSeries(LineSeries, {{
                                            color: '#ffa500',
                                            lineWidth: 1,
                                            lineStyle: LightweightCharts.LineStyle.Dotted,
                                            priceLineVisible: false,
                                            lastValueVisible: false,
                                            crosshairMarkerVisible: false
                                        }});
                                        lowerSeries.setData([
                                            {{ time: dayKey, value: trade.lowerLevel }},
                                            {{ time: endTime, value: trade.lowerLevel }}
                                        ]);
                                    }}
                                    if (trade.stopLevel != null) {{
                                        const stopSeries = chart.addSeries(LineSeries, {{
                                            color: '#ffff00',
                                            lineWidth: 1,
                                            lineStyle: LightweightCharts.LineStyle.Dotted,
                                            priceLineVisible: false,
                                            lastValueVisible: false,
                                            crosshairMarkerVisible: false
                                        }});
                                        stopSeries.setData([
                                            {{ time: dayKey, value: trade.stopLevel }},
                                            {{ time: endTime, value: trade.stopLevel }}
                                        ]);
                                    }}
                                }}
                            }}
                        }});
                        if (markers.length > 0) {{
                            try {{
                                const {{ createSeriesMarkers }} = LightweightCharts;
                                if (typeof createSeriesMarkers === 'function') {{
                                    createSeriesMarkers(candlestickSeries, markers);
                                }}
                            }} catch (error) {{
                                console.error('Error adding markers:', error);
                            }}
                        }}
                    }}
                    chart.timeScale().fitContent();
                    window.addEventListener('resize', () => {{
                        chart.applyOptions({{ width: container.clientWidth }});
                    }});
                    return chart;
                }}
            }};
            window.PortfolioChart = PortfolioChart;
        }})();

        // Embedded chart data (avoids CORS issues when opening from file://)
        let chartData = {chart_data_json};
        let currentChart = null;

        function initChart() {{
            if (typeof LightweightCharts === 'undefined') {{
                setTimeout(initChart, 100);
                return;
            }}
            if (typeof PortfolioChart === 'undefined') {{
                setTimeout(initChart, 100);
                return;
            }}
            try {{
                currentChart = PortfolioChart.init('chart-container', chartData, {{ height: 700 }});
                showSuccess('Chart loaded successfully');
            }} catch (error) {{
                console.error('Error initializing chart:', error);
                showError(`Error loading chart: ${{error.message}}`);
            }}
        }}

        function showError(message) {{
            const errorDiv = document.getElementById('error-message');
            if (errorDiv) {{
                errorDiv.textContent = message;
                errorDiv.style.display = 'block';
            }}
            const statusDiv = document.getElementById('status-message');
            if (statusDiv) {{
                statusDiv.style.display = 'none';
            }}
        }}

        function showSuccess(message) {{
            const statusDiv = document.getElementById('status-message');
            if (statusDiv) {{
                statusDiv.textContent = message;
                statusDiv.style.display = 'block';
                setTimeout(() => {{
                    statusDiv.style.display = 'none';
                }}, 3000);
            }}
            const errorDiv = document.getElementById('error-message');
            if (errorDiv) {{
                errorDiv.style.display = 'none';
            }}
        }}

        // JSON file upload handler
        document.getElementById('json-file-input').addEventListener('change', function(e) {{
            const file = e.target.files[0];
            if (!file) return;
            
            if (!file.name.endsWith('.json')) {{
                showError('Please select a JSON file');
                return;
            }}
            
            const reader = new FileReader();
            reader.onload = function(e) {{
                try {{
                    const newData = JSON.parse(e.target.result);
                    // Validate structure
                    if (!newData.candlestickData || !newData.trades) {{
                        showError('Invalid JSON structure. Expected candlestickData and trades properties.');
                        return;
                    }}
                    // Replace chart data and re-render
                    chartData = newData;
                    initChart();
                    showSuccess('Chart data replaced successfully');
                }} catch (error) {{
                    showError(`Error parsing JSON: ${{error.message}}`);
                }}
            }};
            reader.onerror = function() {{
                showError('Error reading file');
            }};
            reader.readAsText(file);
            // Reset input so same file can be selected again
            e.target.value = '';
        }});

        // Initialize when DOM is ready
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initChart);
        }} else {{
            initChart();
        }}
    </script>
</body>
</html>"""

    def _create_basic_chart_html_v2(self, symbol: str, chart_data: dict) -> tuple[str, str]:
        """Create trimmed HTML chart section for embedding in portfolio report.

        Args:
            symbol: Symbol name
            chart_data: Chart data dictionary to embed

        Returns:
            Tuple of (HTML content with chart container, JavaScript initialization code)
        """
        chart_data_json = json.dumps(chart_data)
        chart_id = f"chart-{symbol.replace('/', '-').replace(' ', '-')}"
        chart_id_var = chart_id.replace("-", "_")

        html_part = f"""
        <h2>Symbol Chart - {symbol}</h2>
        <div id="{chart_id}" style="width: 100%; height: 700px; margin: 20px 0;"></div>
"""

        script_part = f"""
            (function() {{
                const chartData_{chart_id_var} = {chart_data_json};
                function initChart_{chart_id_var}() {{
                    if (typeof PortfolioChart === 'undefined') {{
                        setTimeout(initChart_{chart_id_var}, 100);
                        return;
                    }}
                    try {{
                        PortfolioChart.init('{chart_id}', chartData_{chart_id_var}, {{ height: 700 }});
                    }} catch (error) {{
                        console.error('Error initializing chart for {symbol}:', error);
                    }}
                }}
                if (document.readyState === 'loading') {{
                    document.addEventListener('DOMContentLoaded', initChart_{chart_id_var});
                }} else {{
                    initChart_{chart_id_var}();
                }}
            }})();
"""

        return html_part, script_part

    def analyze(self) -> str:
        """Run complete analysis and generate report.

        Returns:
            Path to generated HTML report
        """
        print("Analyzing portfolio...")

        # Load portfolio
        trades_df, equity_curve, initial_capital = self.load_portfolio()
        print(f"  Loaded {len(trades_df)} trades")

        # Calculate statistics
        stats = calculate_statistics(equity_curve, trades_df, initial_capital)
        print("  Calculated statistics")

        # Generate separate chart files per symbol
        print("  Generating chart files per symbol...")
        self.generate_chart_files(trades_df, equity_curve)

        # Generate HTML report
        html = self.generate_html_report(stats, equity_curve, trades_df)

        # Save report
        report_file = self.output_dir / "portfolio_report.html"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"  Saved report to: {Path(report_file).resolve()}")

        # Print summary
        print(f"\nPerformance Summary:")
        print(f"  Total Return: {stats['total_return']:.2f}%")
        print(f"  Annualized Return: {stats['annualized_return']:.2f}%")
        print(f"  Sharpe Ratio: {stats['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown: {stats['max_drawdown']:.2f}%")
        print(f"  Win Rate: {stats['win_rate']:.1f}%")
        print(f"  Profit Factor: {stats['profit_factor']:.2f}")

        return str(report_file)


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
            from src.backtest.steps.portfolio import PortfolioBuilder

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
                                    from src.backtest.historical_data_provider.ohlcv_store import OhlcvStore, OhlcvStoreConfig
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
