"""Portfolio analysis step — CLI stats, markdown report, single chart PNG."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from src.backtest.utils.analysis_utils import calculate_statistics


def _load_portfolio(portfolio_file: Path):
    """Load portfolio CSV and return (trades_df, equity_curve, initial_capital)."""
    df = pd.read_csv(portfolio_file)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)

    equity_curve = pd.Series(df["equity"].values, index=df["exit_time"]).sort_index()
    initial_capital = df["equity"].iloc[0] - df["portfolio_pnl"].iloc[0]
    return df, equity_curve, initial_capital


def _build_stats_table(stats: dict) -> str:
    """Return a markdown-formatted stats table."""
    start = stats.get("start_date", "N/A")
    end = stats.get("end_date", "N/A")
    if hasattr(start, "strftime"):
        start = start.strftime("%Y-%m-%d")
    if hasattr(end, "strftime"):
        end = end.strftime("%Y-%m-%d")

    rows = [
        ("Period", f"{start} -> {end}"),
        ("Total Return", f"{stats.get('total_return_pct', 0):.2f}%"),
        ("Annualized Return", f"{stats.get('annualized_return', 0):.2f}%"),
        ("", ""),
        ("Total Trades", f"{stats.get('total_trades', 0)}"),
        ("Long / Short", f"{stats.get('long_trades', 0)} / {stats.get('short_trades', 0)}"),
        ("Win Rate", f"{stats.get('win_rate', 0):.1f}%"),
        ("Avg Win", f"${stats.get('avg_win', 0):,.2f}"),
        ("Avg Loss", f"${stats.get('avg_loss', 0):,.2f}"),
        ("Profit Factor", f"{stats.get('profit_factor', 0):.2f}"),
        ("", ""),
        ("Max Drawdown", f"{stats.get('max_drawdown', 0):.2f}%"),
        ("Avg Drawdown", f"{stats.get('avg_drawdown', 0):.2f}%"),
        ("Sharpe Ratio", f"{stats.get('sharpe_ratio', 0):.2f}"),
        ("Sortino Ratio", f"{stats.get('sortino_ratio', 0):.2f}"),
        ("", ""),
        ("Initial Capital", f"${stats.get('initial_capital', 0):,.2f}"),
        ("Final Equity", f"${stats.get('final_equity', 0):,.2f}"),
    ]

    # Build markdown table
    lines = ["| Metric | Value |", "|--------|-------|"]
    for metric, value in rows:
        if metric == "":
            lines.append("| | |")
        else:
            lines.append(f"| {metric} | {value} |")
    return "\n".join(lines)


def _print_stats(stats: dict) -> None:
    """Print stats table to CLI."""
    table = _build_stats_table(stats)
    print("\n--- Performance Summary ---")
    for line in table.split("\n"):
        print(line)
    print()


def _load_symbol_price(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series | None:
    """Try to load daily close prices for a symbol from cached parquet or raw data."""
    cache_dir = Path("data/cache/backtest/resample")
    # Try common cache patterns
    for pattern in [f"{symbol}__1m_to_4h__*.parquet", f"{symbol}__*.parquet"]:
        matches = sorted(cache_dir.glob(pattern))
        if matches:
            df = pd.read_parquet(matches[0])
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")
            df.index = pd.to_datetime(df.index, utc=True)
            price = df["close"].loc[start:end]
            # Resample to daily for cleaner chart
            return price.resample("1D").last().ffill().dropna()
    return None


def _generate_chart(equity_curve: pd.Series, out_path: Path, symbols: list[str] | None = None, trades_df: pd.DataFrame | None = None) -> None:
    """Generate a single PNG with 3 vertically-stacked subplots."""
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=False)
    fig.suptitle("Backtest Results", fontsize=14, fontweight="bold")

    # --- Top: Equity curve + symbol price overlay ---
    ax = axes[0]
    ax.plot(equity_curve.index, equity_curve.values, linewidth=1, color="steelblue", label="Equity")
    ax.set_title("Equity Curve")
    ax.set_ylabel("Equity ($)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.grid(True, alpha=0.3)

    # Overlay symbol price on right y-axis
    if symbols:
        price = _load_symbol_price(symbols[0], equity_curve.index[0], equity_curve.index[-1])
        if price is not None and len(price) > 1:
            ax2 = ax.twinx()
            ax2.plot(price.index, price.values, linewidth=1, color="orange", alpha=0.7, label=symbols[0])
            ax2.set_ylabel(f"{symbols[0]} Price ($)", color="orange")
            ax2.tick_params(axis="y", labelcolor="orange")
            ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
            # Combined legend
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)

    # --- Middle: Drawdown ---
    running_max = equity_curve.expanding().max()
    drawdown_pct = (equity_curve - running_max) / running_max * 100
    ax = axes[1]
    ax.fill_between(drawdown_pct.index, drawdown_pct.values, 0, color="indianred", alpha=0.6)
    ax.set_title("Drawdown")
    ax.set_ylabel("Drawdown (%)")
    ax.grid(True, alpha=0.3)

    # --- Bottom: Monthly returns ---
    equity_monthly = equity_curve.resample("ME").last().ffill()
    monthly_returns = equity_monthly.pct_change().dropna() * 100
    ax = axes[2]
    colors = ["forestgreen" if r >= 0 else "indianred" for r in monthly_returns.values]
    ax.bar(monthly_returns.index, monthly_returns.values, width=20, color=colors, alpha=0.8)
    ax.set_title("Monthly Returns")
    ax.set_ylabel("Return (%)")
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _load_symbol_ohlcv(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame | None:
    """Load signal-timeframe OHLCV + NW indicator for a symbol in the equity curve period."""
    cache_dir = Path("data/cache/backtest/resample")
    for pattern in [f"{symbol}__1m_to_4h__*.parquet", f"{symbol}__*.parquet"]:
        matches = sorted(cache_dir.glob(pattern))
        if matches:
            df = pd.read_parquet(matches[0])
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")
            df.index = pd.to_datetime(df.index, utc=True)
            return df.loc[start:end]
    return None


def _generate_interactive_chart(
    trades_df: pd.DataFrame,
    symbols: list[str] | None,
    equity_curve: pd.Series,
    out_path: Path,
) -> None:
    """Generate an interactive Plotly HTML chart with candlesticks, NW envelope, and trade markers."""
    import plotly.graph_objects as go
    from src.indicators.nadaraya_watson import NadarayaWatsonEnvelope

    if not symbols:
        return

    symbol = symbols[0]
    ohlcv = _load_symbol_ohlcv(symbol, equity_curve.index[0], equity_curve.index[-1])
    if ohlcv is None or len(ohlcv) < 2:
        return

    # Compute indicator on the loaded data
    indicator = NadarayaWatsonEnvelope()
    ohlcv_ind = indicator.calculate(ohlcv.reset_index().rename(columns={ohlcv.index.name or "index": "timestamp"}))
    ohlcv_ind["timestamp"] = pd.to_datetime(ohlcv_ind["timestamp"], utc=True)

    fig = go.Figure()

    # Candlestick chart
    fig.add_trace(go.Candlestick(
        x=ohlcv_ind["timestamp"],
        open=ohlcv_ind["open"], high=ohlcv_ind["high"],
        low=ohlcv_ind["low"], close=ohlcv_ind["close"],
        name=symbol,
        increasing_line_color="#2a6e2a", increasing_fillcolor="#2a6e2a",
        decreasing_line_color="#6e2a2a", decreasing_fillcolor="#6e2a2a",
        opacity=0.8,
    ))

    # NW Envelope lines
    valid = ohlcv_ind.dropna(subset=["nw_smooth"])
    fig.add_trace(go.Scatter(
        x=valid["timestamp"], y=valid["nw_smooth"],
        mode="lines", name="NW Smooth",
        line=dict(color="cyan", width=1.5),
    ))
    fig.add_trace(go.Scatter(
        x=valid["timestamp"], y=valid["nw_upper"],
        mode="lines", name="NW Upper",
        line=dict(color="rgba(255,255,0,0.5)", width=1, dash="dash"),
    ))
    fig.add_trace(go.Scatter(
        x=valid["timestamp"], y=valid["nw_lower"],
        mode="lines", name="NW Lower",
        line=dict(color="rgba(255,255,0,0.5)", width=1, dash="dash"),
    ))

    # Trade markers
    tdf = trades_df.copy()
    tdf["entry_time"] = pd.to_datetime(tdf["entry_time"], utc=True)
    tdf["exit_time"] = pd.to_datetime(tdf["exit_time"], utc=True)

    for direction, color, marker_sym in [("long", "lime", "triangle-up"), ("short", "red", "triangle-down")]:
        subset = tdf[tdf["direction"] == direction]
        if subset.empty:
            continue
        hover = [
            f"<b>{direction.upper()}</b><br>"
            f"Entry: ${row.entry_price:,.2f}<br>"
            f"Exit: ${row.exit_price:,.2f}<br>"
            f"PnL: ${row.net_pnl:,.2f}<br>"
            f"Reason: {row.exit_reason}<br>"
            f"Exit: {row.exit_time:%Y-%m-%d %H:%M}"
            for row in subset.itertuples()
        ]
        fig.add_trace(go.Scatter(
            x=subset["entry_time"], y=subset["entry_price"],
            mode="markers", name=direction.capitalize(),
            marker=dict(color=color, size=10, symbol=marker_sym, line=dict(width=0.5, color="white")),
            hovertext=hover, hoverinfo="text",
        ))

    fig.update_layout(
        title=f"{symbol} - Trades & NW Envelope",
        xaxis_title="Date", yaxis_title="Price ($)",
        template="plotly_dark", hovermode="closest",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    fig.write_html(str(out_path))


def run_analysis_step(
    portfolio_file: Path,
    reports_dir: str,
    strategy_id: str,
    fee_rate: float | None = None,
) -> Path | None:
    """Run portfolio analysis: compute stats, print to CLI, save report + chart.

    Returns:
        Path to generated report.md, or None if failed.
    """
    portfolio_file = Path(portfolio_file)
    if not portfolio_file.exists():
        print(f"Portfolio file not found: {portfolio_file}")
        return None

    # 1. Load data
    trades_df, equity_curve, initial_capital = _load_portfolio(portfolio_file)

    if len(trades_df) == 0:
        print("No trades found in portfolio.")
        return None

    # 2. Compute stats
    stats = calculate_statistics(equity_curve, trades_df, initial_capital)

    # 3. Print to CLI
    _print_stats(stats)

    # 4. Prepare output dir
    out_dir = Path(reports_dir) / strategy_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 5. Generate chart
    chart_path = out_dir / "charts.png"
    symbols = trades_df["symbol"].unique().tolist() if "symbol" in trades_df.columns else None
    _generate_chart(equity_curve, chart_path, symbols=symbols, trades_df=trades_df)

    # 6. Generate interactive trade chart (HTML)
    interactive_path = out_dir / "trades.html"
    _generate_interactive_chart(trades_df, symbols, equity_curve, interactive_path)

    # 7. Write markdown report
    report_path = out_dir / "report.md"
    md_table = _build_stats_table(stats)
    report_content = f"# Backtest Report — {strategy_id}\n\n{md_table}\n\n## Charts\n\n![Charts](charts.png)\n"
    report_path.write_text(report_content, encoding="utf-8")

    print(f"Report saved: {report_path}")
    print(f"Chart saved:  {chart_path}")
    print(f"Interactive:  {interactive_path}")

    return report_path
