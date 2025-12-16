"""Block 5: Portfolio Analysis

Generates performance statistics and visualizations.
Creates HTML report with embedded charts.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict
import argparse
import base64
from io import BytesIO

from utils.analysis_utils import calculate_statistics, calculate_monthly_returns


class PortfolioAnalysis:
    """Analyze portfolio performance and generate reports."""
    
    def __init__(
        self,
        portfolio_file: str = "data/portfolio/portfolio_trades.csv",
        output_dir: str = "outputs/reports"
    ):
        """Initialize analysis engine.
        
        Args:
            portfolio_file: Path to portfolio trades CSV
            output_dir: Directory for output reports
        """
        self.portfolio_file = Path(portfolio_file)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set style
        sns.set_style("whitegrid")
        plt.rcParams['figure.figsize'] = (12, 6)
    
    def load_portfolio(self) -> tuple[pd.DataFrame, pd.Series, float]:
        """Load portfolio data.
        
        Returns:
            Tuple of (trades_df, equity_curve, initial_capital)
        """
        if not self.portfolio_file.exists():
            raise FileNotFoundError(f"Portfolio file not found: {self.portfolio_file}")
        
        df = pd.read_csv(self.portfolio_file)
        df['entry_time'] = pd.to_datetime(df['entry_time'], utc=True)
        df['exit_time'] = pd.to_datetime(df['exit_time'], utc=True)
        
        # Get equity curve
        equity_curve = pd.Series(
            df['equity'].values,
            index=df['exit_time']
        ).sort_index()
        
        # Get initial capital (from first equity value or calculate)
        initial_capital = df['equity'].iloc[0] - df['portfolio_pnl'].iloc[0] if len(df) > 0 else 10000
        
        return df, equity_curve, initial_capital
    
    def plot_to_base64(self, fig: plt.Figure) -> str:
        """Convert matplotlib figure to base64 string for HTML embedding.
        
        Args:
            fig: Matplotlib figure
            
        Returns:
            Base64 encoded image string
        """
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)
        return img_str
    
    def plot_equity_curve(self, equity_curve: pd.Series) -> str:
        """Plot equity curve.
        
        Args:
            equity_curve: Series with equity values
            
        Returns:
            Base64 encoded image string
        """
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(equity_curve.index, equity_curve.values, linewidth=2, color='#2E86AB')
        ax.set_title('Portfolio Equity Curve', fontsize=16, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Equity ($)', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis='x', rotation=45)
        
        # Format y-axis as currency
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        plt.tight_layout()
        return self.plot_to_base64(fig)
    
    def plot_drawdown(self, equity_curve: pd.Series) -> str:
        """Plot drawdown chart.
        
        Args:
            equity_curve: Series with equity values
            
        Returns:
            Base64 encoded image string
        """
        # Calculate drawdown
        running_max = equity_curve.expanding().max()
        drawdown = (equity_curve - running_max) / running_max * 100
        
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.fill_between(drawdown.index, drawdown.values, 0, color='#A23B72', alpha=0.6)
        ax.plot(drawdown.index, drawdown.values, linewidth=1, color='#A23B72')
        ax.set_title('Portfolio Drawdown', fontsize=16, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Drawdown (%)', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        return self.plot_to_base64(fig)
    
    def plot_monthly_returns(self, equity_curve: pd.Series, initial_capital: float) -> str:
        """Plot monthly returns.
        
        Args:
            equity_curve: Series with equity values
            initial_capital: Starting capital
            
        Returns:
            Base64 encoded image string
        """
        monthly_df = calculate_monthly_returns(equity_curve, initial_capital)
        
        if monthly_df.empty:
            # Create empty plot
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.text(0.5, 0.5, 'Insufficient data for monthly returns', 
                   ha='center', va='center', fontsize=14)
            ax.set_title('Monthly Returns', fontsize=16, fontweight='bold')
            return self.plot_to_base64(fig)
        
        fig, ax = plt.subplots(figsize=(12, 6))
        colors = ['#06A77D' if x >= 0 else '#D00000' for x in monthly_df['return_pct']]
        ax.bar(monthly_df['month'], monthly_df['return_pct'], color=colors, alpha=0.7)
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
        ax.set_title('Monthly Returns', fontsize=16, fontweight='bold')
        ax.set_xlabel('Month', fontsize=12)
        ax.set_ylabel('Return (%)', fontsize=12)
        ax.grid(True, alpha=0.3, axis='y')
        ax.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        return self.plot_to_base64(fig)
    
    def plot_pnl_distribution(self, trades_df: pd.DataFrame) -> str:
        """Plot PnL distribution histogram.
        
        Args:
            trades_df: DataFrame with trades
            
        Returns:
            Base64 encoded image string
        """
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.hist(trades_df['portfolio_pnl'], bins=20, color='#F18F01', alpha=0.7, edgecolor='black')
        ax.axvline(x=0, color='black', linestyle='--', linewidth=1)
        ax.set_title('Trade PnL Distribution', fontsize=16, fontweight='bold')
        ax.set_xlabel('PnL ($)', fontsize=12)
        ax.set_ylabel('Frequency', fontsize=12)
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        return self.plot_to_base64(fig)
    
    def generate_html_report(
        self,
        stats: Dict,
        equity_img: str,
        drawdown_img: str,
        monthly_img: str,
        pnl_img: str
    ) -> str:
        """Generate HTML report with embedded charts.
        
        Args:
            stats: Dictionary with statistics
            equity_img: Base64 encoded equity curve image
            drawdown_img: Base64 encoded drawdown image
            monthly_img: Base64 encoded monthly returns image
            pnl_img: Base64 encoded PnL distribution image
            
        Returns:
            HTML report as string
        """
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Performance Report</title>
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
        .chart {{
            margin: 30px 0;
            text-align: center;
        }}
        .chart img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
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
        
        <h2>Equity Curve</h2>
        <div class="chart">
            <img src="data:image/png;base64,{equity_img}" alt="Equity Curve">
        </div>
        
        <h2>Drawdown</h2>
        <div class="chart">
            <img src="data:image/png;base64,{drawdown_img}" alt="Drawdown">
        </div>
        
        <h2>Monthly Returns</h2>
        <div class="chart">
            <img src="data:image/png;base64,{monthly_img}" alt="Monthly Returns">
        </div>
        
        <h2>Trade PnL Distribution</h2>
        <div class="chart">
            <img src="data:image/png;base64,{pnl_img}" alt="PnL Distribution">
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
</body>
</html>
"""
        return html
    
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
        
        # Generate charts
        print("  Generating charts...")
        equity_img = self.plot_equity_curve(equity_curve)
        drawdown_img = self.plot_drawdown(equity_curve)
        monthly_img = self.plot_monthly_returns(equity_curve, initial_capital)
        pnl_img = self.plot_pnl_distribution(trades_df)
        
        # Generate HTML report
        html = self.generate_html_report(stats, equity_img, drawdown_img, monthly_img, pnl_img)
        
        # Save report
        report_file = self.output_dir / "portfolio_report.html"
        with open(report_file, 'w', encoding='utf-8') as f:
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
    parser = argparse.ArgumentParser(description='Analyze portfolio performance')
    parser.add_argument('--portfolio-file', type=str, 
                       default='data/portfolio/portfolio_trades.csv',
                       help='Path to portfolio trades CSV')
    parser.add_argument('--output-dir', type=str, default='outputs/reports',
                       help='Output directory for reports')
    
    args = parser.parse_args()
    
    # Create analyzer
    analyzer = PortfolioAnalysis(
        portfolio_file=args.portfolio_file,
        output_dir=args.output_dir
    )
    
    # Run analysis
    report_file = analyzer.analyze()
    
    print(f"\n✓ Analysis complete: {report_file}")


if __name__ == "__main__":
    main()

