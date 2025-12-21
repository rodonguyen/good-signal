"""Portfolio builder step wrapper for backtest runner."""

from pathlib import Path
from typing import Any, Mapping
import sys

# Add breakout src to path to import portfolio_builder
breakout_src = Path(__file__).parent.parent.parent.parent / "breakout" / "src"
sys.path.insert(0, str(breakout_src))

from portfolio_builder import PortfolioBuilder


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

