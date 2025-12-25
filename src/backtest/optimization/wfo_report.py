"""
Walk-forward optimization report generator.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List
from datetime import datetime

import pandas as pd

from src.backtest.optimization.walk_forward import CycleResult, BacktestResult

logger = logging.getLogger(__name__)


class WFOReportGenerator:
    """Generate comprehensive HTML reports for walk-forward optimization."""

    def __init__(self, output_dir: Path):
        """
        Initialize report generator.

        Args:
            output_dir: Directory to save report and data files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = self.output_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Report generator initialized: output_dir={self.output_dir}")

    def _generate_scatter_plot_data(self, cycle_result: CycleResult) -> dict:
        """Generate scatter plot data for a cycle."""
        data = []
        for result in cycle_result.grid_results:
            sharpe = result.sharpe
            # Use actual PnL value, not absolute value, to match return calculation
            pnl = result.total_pnl
            data.append(
                {
                    "x": result.params["breakout_multiplier"],
                    "y": result.params["stop_multiplier"],
                    "sharpe": sharpe,
                    "pnl": pnl,
                    "total_return": result.total_return,
                    "max_drawdown": result.max_drawdown,
                    "win_rate": result.win_rate,
                    "total_trades": result.total_trades,
                }
            )

        # Find top 10% by Sharpe for robustness zone
        if data:
            sharpe_values = [d["sharpe"] for d in data]
            sharpe_values.sort(reverse=True)
            top_10_percent_threshold = sharpe_values[max(0, len(sharpe_values) // 10 - 1)] if sharpe_values else 0

            for d in data:
                d["is_top_10"] = d["sharpe"] >= top_10_percent_threshold

        # Mark best config
        best_x = cycle_result.best_config.params["breakout_multiplier"]
        best_y = cycle_result.best_config.params["stop_multiplier"]
        for d in data:
            d["is_best"] = d["x"] == best_x and d["y"] == best_y

        return data

    def _generate_parameter_stability_heatmap(self, cycle_results: List[CycleResult]) -> dict:
        """Generate parameter stability heatmap data."""
        # Count how many times each parameter combination was selected as best
        param_counts = {}
        for cycle in cycle_results:
            breakout = cycle.best_config.params["breakout_multiplier"]
            stop = cycle.best_config.params["stop_multiplier"]
            key = (round(breakout, 2), round(stop, 2))
            param_counts[key] = param_counts.get(key, 0) + 1

        # Convert to heatmap format
        heatmap_data = []
        for (breakout, stop), count in param_counts.items():
            heatmap_data.append(
                {
                    "x": breakout,
                    "y": stop,
                    "count": count,
                }
            )

        return heatmap_data

    def _generate_combined_oos_equity_curve(self, cycle_results: List[CycleResult]) -> List[dict]:
        """Generate combined out-of-sample equity curve."""
        equity_data = []
        cumulative_equity = 1000.0  # Starting capital

        for cycle in cycle_results:
            test_result = cycle.test_result
            # Get equity curve for test period
            equity_curve = test_result.equity_curve

            # MEMORY OPTIMIZATION: Handle optional equity_curve
            if equity_curve is None or len(equity_curve) == 0:
                logger.warning(f"Cycle {cycle.cycle_num}: No equity curve data available")
                continue

            # Normalize to cumulative
            first_equity = equity_curve.iloc[0]
            for timestamp, equity in equity_curve.items():
                # Convert to cumulative
                normalized_equity = cumulative_equity + (equity - first_equity)
                equity_data.append(
                    {
                        "time": int(pd.Timestamp(timestamp).timestamp()),
                        "value": float(normalized_equity),
                        "cycle": cycle.cycle_num,
                    }
                )
            # Update cumulative for next cycle
            cumulative_equity = normalized_equity

        return equity_data

    def _generate_summary_section(self, cycle_results: List[CycleResult]) -> str:
        """Generate summary section HTML."""
        if not cycle_results:
            return "<p>No cycle results available.</p>"

        # Aggregate metrics
        total_oos_return = sum(c.test_result.total_return for c in cycle_results)
        avg_oos_return = total_oos_return / len(cycle_results)
        total_oos_trades = sum(c.test_result.total_trades for c in cycle_results)
        avg_win_rate = sum(c.test_result.win_rate for c in cycle_results) / len(cycle_results)
        max_dd = min(c.test_result.max_drawdown for c in cycle_results)

        # Parameter stability
        param_counts = {}
        for cycle in cycle_results:
            breakout = cycle.best_config.params["breakout_multiplier"]
            stop = cycle.best_config.params["stop_multiplier"]
            key = f"{breakout:.2f}/{stop:.2f}"
            param_counts[key] = param_counts.get(key, 0) + 1

        most_common = max(param_counts.items(), key=lambda x: x[1]) if param_counts else ("N/A", 0)

        html = f"""
        <div class="summary-section">
            <h2>Summary</h2>
            <div class="summary-grid">
                <div class="summary-metric">
                    <h3>Aggregate Out-of-Sample Performance</h3>
                    <table>
                        <tr><td>Total Return:</td><td>{total_oos_return:.2f}%</td></tr>
                        <tr><td>Average Return per Cycle:</td><td>{avg_oos_return:.2f}%</td></tr>
                        <tr><td>Max Drawdown:</td><td>{max_dd:.2f}%</td></tr>
                        <tr><td>Average Win Rate:</td><td>{avg_win_rate:.1f}%</td></tr>
                        <tr><td>Total Trades:</td><td>{total_oos_trades}</td></tr>
                    </table>
                </div>
                <div class="summary-metric">
                    <h3>Parameter Stability</h3>
                    <p>Most frequently selected config: <strong>{most_common[0]}</strong> ({most_common[1]} times)</p>
                    <p>Total cycles: {len(cycle_results)}</p>
                </div>
            </div>
        </div>
        """
        return html

    def _generate_cycle_section(self, cycle_result: CycleResult) -> str:
        """Generate HTML section for a single cycle."""
        test_result = cycle_result.test_result
        best_config = cycle_result.best_config

        html = f"""
        <div class="cycle-section">
            <h2>Cycle {cycle_result.cycle_num}</h2>
            <p class="cycle-dates">
                Training: {cycle_result.train_start.date()} to {cycle_result.train_end.date()} (6 months)<br>
                Testing: {cycle_result.test_start.date()} to {cycle_result.test_end.date()} (3 months)
            </p>
            <div class="cycle-content">
                <div class="cycle-left">
                    <h3>Parameter Optimization</h3>
                    <div id="scatter-plot-{cycle_result.cycle_num}"></div>
                    <p class="plot-legend">
                        <strong>Legend:</strong> Color = Sharpe Ratio (yellow = low, dark red = high), Size = PnL magnitude<br>
                        ★ = Selected best config, ○ = Top 10% robustness zone
                    </p>
                </div>
                <div class="cycle-right">
                    <h3>Out-of-Sample Results</h3>
                    <div class="config-used">
                        <strong>Best Config Selected:</strong><br>
                        • breakout_multiplier: {best_config.params['breakout_multiplier']:.2f}<br>
                        • stop_multiplier: {best_config.params['stop_multiplier']:.2f}<br>
                        • In-Sample Sharpe: {best_config.sharpe:.2f}
                    </div>
                    <table class="results-table">
                        <tr><td>Total Return</td><td>{test_result.total_return:.2f}%</td></tr>
                        <tr><td>Annualized Return</td><td>{test_result.annualized_return:.2f}%</td></tr>
                        <tr><td>Max Drawdown</td><td>{test_result.max_drawdown:.2f}%</td></tr>
                        <tr><td>Sharpe Ratio</td><td>{test_result.sharpe:.2f}</td></tr>
                        <tr><td>Win Rate</td><td>{test_result.win_rate:.1f}%</td></tr>
                        <tr><td>Avg Win</td><td>${test_result.avg_win:.2f}</td></tr>
                        <tr><td>Avg Loss</td><td>${test_result.avg_loss:.2f}</td></tr>
                        <tr><td>Total Trades</td><td>{test_result.total_trades}</td></tr>
                    </table>
                </div>
            </div>
        </div>
        """
        return html

    def _generate_html_template(self, cycle_results: List[CycleResult]) -> str:
        """Generate complete HTML report."""
        # Generate data files
        scatter_data = {}
        for cycle in cycle_results:
            scatter_data[f"cycle_{cycle.cycle_num}"] = self._generate_scatter_plot_data(cycle)

        stability_data = self._generate_parameter_stability_heatmap(cycle_results)
        equity_data = self._generate_combined_oos_equity_curve(cycle_results)

        # Save data as JSON
        logger.debug("Saving scatter plot data...")
        with open(self.data_dir / "scatter_data.json", "w") as f:
            json.dump(scatter_data, f, indent=2)

        logger.debug("Saving stability heatmap data...")
        with open(self.data_dir / "stability_heatmap.json", "w") as f:
            json.dump(stability_data, f, indent=2)

        logger.debug("Saving equity curve data...")
        with open(self.data_dir / "oos_equity_curve.json", "w") as f:
            json.dump(equity_data, f, indent=2)

        logger.debug("All data files saved successfully")

        # Generate summary
        summary_html = self._generate_summary_section(cycle_results)

        # Generate cycle sections
        cycle_sections = "\n".join([self._generate_cycle_section(c) for c in cycle_results])

        # Generate parameter stability heatmap JavaScript
        stability_heatmap_js = f"""
        // Parameter stability heatmap
        (function() {{
            const data = {json.dumps(stability_data)};
            const trace = {{
                x: data.map(d => d.x),
                y: data.map(d => d.y),
                z: data.map(d => d.count),
                type: 'heatmap',
                colorscale: 'YlOrRd',
                showscale: true,
                colorbar: {{ title: 'Selection Count' }}
            }};
            const layout = {{
                title: 'Parameter Stability Heatmap',
                xaxis: {{ title: 'Breakout Multiplier' }},
                yaxis: {{ title: 'Stop Multiplier' }}
            }};
            Plotly.newPlot('stability-heatmap', [trace], layout);
        }})();
        """

        # Generate combined OOS equity curve JavaScript
        equity_curve_js = f"""
        // Combined OOS equity curve
        (function() {{
            const data = {json.dumps(equity_data)};
            const trace = {{
                x: data.map(d => new Date(d.time * 1000)),
                y: data.map(d => d.value),
                type: 'scatter',
                mode: 'lines',
                name: 'Equity',
                line: {{ color: '#4CAF50', width: 2 }}
            }};
            const layout = {{
                title: 'Combined Out-of-Sample Equity Curve',
                xaxis: {{ title: 'Date' }},
                yaxis: {{ title: 'Equity ($)' }}
            }};
            Plotly.newPlot('equity-curve', [trace], layout);
        }})();
        """

        # Generate scatter plot JavaScript
        scatter_plots_js = stability_heatmap_js + "\n" + equity_curve_js + "\n"
        for cycle in cycle_results:
            cycle_data = scatter_data[f"cycle_{cycle.cycle_num}"]
            scatter_plots_js += f"""
            // Cycle {cycle.cycle_num} scatter plot
            (function() {{
                const data = {json.dumps(cycle_data)};
                const trace = {{
                    x: data.map(d => d.x),
                    y: data.map(d => d.y),
                    mode: 'markers',
                    type: 'scatter',
                    marker: {{
                        size: data.map(d => {{
                            const maxPnl = Math.max(...data.map(dd => Math.abs(dd.pnl)));
                            const minSize = 8;
                            const maxSize = 25;
                            // Use absolute value for size calculation only (visualization)
                            return maxPnl > 0 ? minSize + (Math.abs(d.pnl) / maxPnl) * (maxSize - minSize) : minSize;
                        }}),
                        color: data.map(d => d.sharpe),
                        colorscale: 'YlOrRd',
                        reversescale: true,
                        showscale: true,
                        colorbar: {{ title: 'Sharpe Ratio' }},
                        line: {{
                            color: data.map(d => d.is_top_10 ? 'blue' : 'transparent'),
                            width: 2
                        }},
                        symbol: data.map(d => d.is_best ? 'star' : 'circle')
                    }},
                    text: data.map(d => `Sharpe: ${{d.sharpe.toFixed(2)}}<br>PnL: ${{d.pnl.toFixed(2)}}<br>Return: ${{d.total_return.toFixed(2)}}%`),
                    hoverinfo: 'text'
                }};
                const layout = {{
                    title: 'Parameter Optimization - Cycle {cycle.cycle_num}',
                    xaxis: {{ title: 'Breakout Multiplier' }},
                    yaxis: {{ title: 'Stop Multiplier' }},
                    hovermode: 'closest'
                }};
                Plotly.newPlot('scatter-plot-{cycle.cycle_num}', [trace], layout);
            }})();
            """

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Walk-Forward Optimization Report</title>
    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .summary-section {{
            margin: 20px 0;
            padding: 20px;
            background: #f9f9f9;
            border-radius: 5px;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .summary-metric table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .summary-metric td {{
            padding: 8px;
            border-bottom: 1px solid #ddd;
        }}
        .cycle-section {{
            margin: 30px 0;
            padding: 20px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }}
        .cycle-dates {{
            color: #666;
            font-size: 0.9em;
            margin-bottom: 15px;
        }}
        .cycle-content {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .cycle-left, .cycle-right {{
            padding: 15px;
        }}
        .config-used {{
            background: #e8f5e9;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 15px;
        }}
        .results-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .results-table td {{
            padding: 8px;
            border-bottom: 1px solid #ddd;
        }}
        .results-table td:first-child {{
            font-weight: bold;
            width: 50%;
        }}
        .plot-legend {{
            font-size: 0.85em;
            color: #666;
            margin-top: 10px;
        }}
        .summary-visualizations {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 20px 0;
        }}
        .viz-container {{
            padding: 15px;
            background: #f9f9f9;
            border-radius: 5px;
        }}
        .viz-container > div {{
            width: 100%;
            height: 400px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Walk-Forward Optimization Report</h1>
        <p><strong>Strategy:</strong> ATR Breakout | <strong>Symbol:</strong> ETHUSDT</p>
        
        {summary_html}
        
        <div class="summary-visualizations">
            <div class="viz-container">
                <div id="equity-curve"></div>
            </div>
            <div class="viz-container">
                <div id="stability-heatmap"></div>
            </div>
        </div>
        
        {cycle_sections}
        
        <div class="appendix">
            <h2>Appendix: Full Grid Search Results</h2>
            <table id="grid-results-table" class="display">
                <thead>
                    <tr>
                        <th>Cycle</th>
                        <th>Breakout Mult</th>
                        <th>Stop Mult</th>
                        <th>Sharpe</th>
                        <th>Total PnL</th>
                        <th>Total Return</th>
                        <th>Max DD</th>
                        <th>Win Rate</th>
                        <th>Trades</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join([
                        f"<tr><td>{c.cycle_num}</td><td>{r.params['breakout_multiplier']:.2f}</td><td>{r.params['stop_multiplier']:.2f}</td>"
                        f"<td>{r.sharpe:.2f}</td><td>${r.total_pnl:.2f}</td><td>{r.total_return:.2f}%</td>"
                        f"<td>{r.max_drawdown:.2f}%</td><td>{r.win_rate:.1f}%</td><td>{r.total_trades}</td></tr>"
                        for c in cycle_results for r in c.grid_results
                    ])}
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        {scatter_plots_js}
        
        // Initialize DataTable
        $(document).ready(function() {{
            $('#grid-results-table').DataTable({{
                pageLength: 25,
                order: [[3, 'desc']] // Sort by Sharpe descending
            }});
        }});
    </script>
</body>
</html>
        """
        return html

    def generate_report(self, cycle_results: List[CycleResult]) -> Path:
        """
        Generate complete HTML report.

        Args:
            cycle_results: List of cycle results

        Returns:
            Path to generated HTML report
        """
        logger.info(f"Generating report for {len(cycle_results)} cycles...")
        logger.debug("Generating scatter plot data...")
        html_content = self._generate_html_template(cycle_results)
        report_path = self.output_dir / "wfo_report.html"
        logger.info(f"Writing report to {report_path}...")
        report_path.write_text(html_content, encoding="utf-8")
        logger.info(f"Report generated successfully: {report_path}")
        logger.debug(f"Report size: {len(html_content):,} characters")
        return report_path
