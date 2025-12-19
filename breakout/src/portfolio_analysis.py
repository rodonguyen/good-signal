"""Block 5: Portfolio Analysis

Generates performance statistics and visualizations.
Creates HTML report with embedded charts.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional
import argparse
import json

from utils.analysis_utils import calculate_statistics, calculate_monthly_returns
from utils.config import load_config


class PortfolioAnalysis:
    """Analyze portfolio performance and generate reports."""

    def __init__(
        self, portfolio_file: str = "data/portfolio/portfolio_trades.csv", output_dir: str = "src/reports", raw_data_dir: str = "data/raw/crypto", breakout_config_path: str = "src/config/breakout_config.yaml"
    ):
        """Initialize analysis engine.

        Args:
            portfolio_file: Path to portfolio trades CSV
            output_dir: Directory for output reports
            raw_data_dir: Directory containing raw price data
            breakout_config_path: Path to breakout config file
        """
        self.portfolio_file = Path(portfolio_file)
        self.output_dir = Path(output_dir)
        self.raw_data_dir = Path(raw_data_dir)
        self.breakout_config_path = breakout_config_path
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
        initial_capital = df["equity"].iloc[0] - df["portfolio_pnl"].iloc[0] if len(df) > 0 else 10000

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
            }},
            width: chartContainer.clientWidth,
            height: 700,
        }});
        
        // Add candlestick series
        const candlestickSeries = chart.addCandlestickSeries({{
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
        candlestickSeries.setMarkers(markers);
        
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
            strategy = breakout_config.get("strategy", {})
            paths = breakout_config.get("paths", {})
        except Exception:
            strategy = {}
            paths = {}
        
        # Calculate equity curve data
        if len(equity_curve) > 0:
            equity_data = [
                {"time": int(pd.Timestamp(idx).timestamp()), "value": float(val)}
                for idx, val in zip(equity_curve.index, equity_curve.values)
            ]
        else:
            equity_data = []
        
        # Calculate drawdown series
        if len(equity_curve) > 0:
            running_max = equity_curve.expanding().max()
            drawdown_series = (equity_curve - running_max) / running_max * 100
            drawdown_data = [
                {"time": int(pd.Timestamp(idx).timestamp()), "value": float(val)}
                for idx, val in zip(drawdown_series.index, drawdown_series.values)
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
            histogram_data = {
                "labels": [f"{bin_edges[i]:.0f} to {bin_edges[i+1]:.0f}" for i in range(len(hist))],
                "values": hist.tolist()
            }
        else:
            histogram_data = {"labels": [], "values": []}
        
        # Format config for display
        config_html = f"""
        <div class="config-section">
            <h3>Breakout Strategy Configuration</h3>
            <div class="config-grid">
                <div class="config-item"><strong>ATR Period:</strong> {strategy.get('atr_period', 'N/A')}</div>
                <div class="config-item"><strong>Breakout Multiplier:</strong> {strategy.get('breakout_multiplier', 'N/A')}</div>
                <div class="config-item"><strong>Stop Multiplier:</strong> {strategy.get('stop_multiplier', 'N/A')}</div>
                <div class="config-item"><strong>Day Start Hour:</strong> {strategy.get('day_start_hour', 'N/A')} UTC</div>
                <div class="config-item"><strong>Fee Rate:</strong> {strategy.get('fee_rate', 'N/A')} ({strategy.get('fee_rate', 0) * 100 if strategy.get('fee_rate') else 0:.2f}%)</div>
                <div class="config-item"><strong>Data Directory:</strong> {paths.get('data_dir', 'N/A')}</div>
                <div class="config-item"><strong>Output Directory:</strong> {paths.get('output_dir', 'N/A')}</div>
            </div>
        </div>
        """
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Performance Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
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
        h3 {{
            color: #555;
            margin-top: 20px;
            font-size: 18px;
        }}
        .config-section {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            border-left: 4px solid #2E86AB;
        }}
        .config-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 10px;
            margin-top: 10px;
        }}
        .config-item {{
            padding: 8px;
            background-color: white;
            border-radius: 3px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .stat-card {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #2E86AB;
        }}
        .stat-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
            margin-top: 5px;
        }}
        .chart-container {{
            margin: 30px 0;
            position: relative;
            height: 400px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #2E86AB;
            color: white;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Portfolio Performance Report</h1>
        
        {config_html}
        
        <h2>Summary Statistics</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Return</div>
                <div class="stat-value">{stats['total_return']:.2f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Annualized Return</div>
                <div class="stat-value">{stats['annualized_return']:.2f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Sharpe Ratio</div>
                <div class="stat-value">{stats['sharpe_ratio']:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Max Drawdown</div>
                <div class="stat-value">{stats['max_drawdown']:.2f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Win Rate</div>
                <div class="stat-value">{stats['win_rate']:.1f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Profit Factor</div>
                <div class="stat-value">{stats['profit_factor']:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Trades</div>
                <div class="stat-value">{stats['total_trades']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Avg Trade</div>
                <div class="stat-value">${stats['avg_trade']:.2f}</div>
            </div>
        </div>
        
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
                <th>Metric</th>
                <th>Value</th>
            </tr>
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
        
        <p style="margin-top: 30px; color: #666; font-size: 12px;">
            Report generated on {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
        </p>
    </div>
    
    <script>
        // Equity Chart
        const equityData = {json.dumps(equity_data)};
        const equityLabels = equityData.map(d => new Date(d.time * 1000).toLocaleDateString());
        const equityValues = equityData.map(d => d.value);
        
        const equityCtx = document.getElementById('equityChart').getContext('2d');
        new Chart(equityCtx, {{
            type: 'line',
            data: {{
                labels: equityLabels,
                datasets: [{{
                    label: 'Portfolio Equity ($)',
                    data: equityValues,
                    borderColor: '#2E86AB',
                    backgroundColor: 'rgba(46, 134, 171, 0.1)',
                    fill: true,
                    tension: 0.1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Portfolio Equity Over Time'
                    }},
                    legend: {{
                        display: true
                    }}
                }},
                scales: {{
                    y: {{
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
                    x: {{
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
        const drawdownLabels = drawdownData.map(d => new Date(d.time * 1000).toLocaleDateString());
        const drawdownValues = drawdownData.map(d => d.value);
        
        const drawdownCtx = document.getElementById('drawdownChart').getContext('2d');
        new Chart(drawdownCtx, {{
            type: 'line',
            data: {{
                labels: drawdownLabels,
                datasets: [{{
                    label: 'Drawdown (%)',
                    data: drawdownValues,
                    borderColor: '#ef5350',
                    backgroundColor: 'rgba(239, 83, 80, 0.1)',
                    fill: true,
                    tension: 0.1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Portfolio Drawdown Over Time'
                    }},
                    legend: {{
                        display: true
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
        new Chart(pnlCtx, {{
            type: 'bar',
            data: {{
                labels: histogramData.labels,
                datasets: [{{
                    label: 'Number of Trades',
                    data: histogramData.values,
                    backgroundColor: histogramData.values.map((v, i) => {{
                        if (histogramData.values[i] === 0) return 'rgba(158, 158, 158, 0.6)';
                        const midPoint = Math.floor(histogramData.labels.length / 2);
                        return i < midPoint ? 'rgba(76, 175, 80, 0.6)' : 'rgba(239, 83, 80, 0.6)';
                    }}),
                    borderColor: histogramData.values.map((v, i) => {{
                        const midPoint = Math.floor(histogramData.labels.length / 2);
                        return i < midPoint ? '#4caf50' : '#ef5350';
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
            from portfolio_builder import PortfolioBuilder
        except ImportError:
            # Try relative import if running as module
            from .portfolio_builder import PortfolioBuilder

        # Create a PortfolioBuilder instance to access export_chart_data
        # We need to pass a config, but we can create a minimal one or use default
        try:
            builder = PortfolioBuilder()
        except Exception:
            # If config doesn't exist, we'll call the method as a static method
            # by creating an uninitialized instance
            builder = PortfolioBuilder.__new__(PortfolioBuilder)

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
                    print(f"  Generated chart file: {html_file}")

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

        # Prepare trades data
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
        """Create basic HTML chart template with embedded data.

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
    </style>
</head>
<body>
    <div class="container">
        <h1>Portfolio Trading Chart - {symbol}</h1>
        <div id="chart-container"></div>
        <div id="error-message" class="error" style="display: none;"></div>
    </div>

    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
    <script src="portfolio-chart.js"></script>
    <script>
        // Embedded chart data (avoids CORS issues when opening from file://)
        const chartData = {chart_data_json};
        
        function initChart() {{
            // Wait for libraries to load
            if (typeof LightweightCharts === 'undefined') {{
                setTimeout(initChart, 100);
                return;
            }}
            
            if (typeof PortfolioChart === 'undefined') {{
                setTimeout(initChart, 100);
                return;
            }}

            try {{
                // Initialize chart with embedded data
                PortfolioChart.init('chart-container', chartData, {{ height: 700 }});
                
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
        }}

        // Initialize when DOM is ready
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initChart);
        }} else {{
            initChart();
        }}
    </script>
</body>
</html>"""

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

        print(f"  Saved report to: {report_file}")

        # Print summary
        print(f"\nPerformance Summary:")
        print(f"  Total Return: {stats['total_return']:.2f}%")
        print(f"  Annualized Return: {stats['annualized_return']:.2f}%")
        print(f"  Sharpe Ratio: {stats['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown: {stats['max_drawdown']:.2f}%")
        print(f"  Win Rate: {stats['win_rate']:.1f}%")
        print(f"  Profit Factor: {stats['profit_factor']:.2f}")

        return str(report_file)


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description="Analyze portfolio performance")
    parser.add_argument("--portfolio-file", type=str, default="data/portfolio/portfolio_trades.csv", help="Path to portfolio trades CSV")
    parser.add_argument("--output-dir", type=str, default="outputs/reports", help="Output directory for reports")
    parser.add_argument("--raw-data-dir", type=str, default="data/raw/crypto", help="Directory containing raw price data")

    args = parser.parse_args()

    # Create analyzer
    analyzer = PortfolioAnalysis(portfolio_file=args.portfolio_file, output_dir=args.output_dir, raw_data_dir=args.raw_data_dir)

    # Run analysis
    report_file = analyzer.analyze()

    print(f"\nAnalysis complete: {report_file}")


if __name__ == "__main__":
    main()
