"""
Script to populate equity and drawdown values from CSV into database.

This script reads the portfolio_trades.csv and updates the database with equity values.
"""

import asyncio
import sys
from pathlib import Path
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


async def populate_equity():
    """Populate equity and drawdown values from portfolio CSV."""
    from sqlalchemy import text, select
    from backend.infrastructure.database.connection import AsyncSessionLocal, engine
    from backend.infrastructure.database.models import BacktestTrade, Backtest

    print("Starting equity population...")

    async with AsyncSessionLocal() as session:
        # Get all backtests
        result = await session.execute(select(Backtest))
        backtests = result.scalars().all()

        if not backtests:
            print("No backtests found in database")
            return

        for backtest in backtests:
            print(f"\nProcessing backtest: {backtest.id}")

            # Find the portfolio CSV file for this backtest
            # The CSV should be in data/portfolio/{strategy_id}/portfolio_trades.csv
            import json
            config = json.loads(backtest.config_json)
            strategies = json.loads(backtest.strategies)

            if not strategies:
                print(f"  No strategies found for backtest {backtest.id}")
                continue

            # Get first strategy ID
            strategy = strategies[0]
            strategy_id = strategy.get('type', 'unknown')

            portfolio_file = Path("data/portfolio") / strategy_id / "portfolio_trades.csv"

            if not portfolio_file.exists():
                print(f"  Portfolio file not found: {portfolio_file}")
                continue

            print(f"  Reading CSV: {portfolio_file}")
            df = pd.read_csv(portfolio_file)

            if 'equity' not in df.columns:
                print(f"  No equity column in CSV")
                continue

            # Convert timestamps to match database format
            df['entry_time'] = pd.to_datetime(df['entry_time'], utc=True)
            df['exit_time'] = pd.to_datetime(df['exit_time'], utc=True)

            # Get all trades for this backtest
            trades_result = await session.execute(
                select(BacktestTrade).where(BacktestTrade.backtest_id == backtest.id)
            )
            db_trades = trades_result.scalars().all()

            print(f"  Found {len(db_trades)} trades in database, {len(df)} in CSV")

            updates = 0
            for db_trade in db_trades:
                # Find matching row in CSV
                db_entry = pd.to_datetime(db_trade.entry_time, utc=True)
                db_exit = pd.to_datetime(db_trade.exit_time, utc=True)

                # Match by symbol, entry_time, and exit_time
                matches = df[
                    (df['symbol'] == db_trade.symbol) &
                    (df['entry_time'] == db_entry) &
                    (df['exit_time'] == db_exit)
                ]

                if len(matches) == 0:
                    # Try matching with some tolerance (1 minute)
                    matches = df[
                        (df['symbol'] == db_trade.symbol) &
                        (abs((df['entry_time'] - db_entry).dt.total_seconds()) < 60) &
                        (abs((df['exit_time'] - db_exit).dt.total_seconds()) < 60)
                    ]

                if len(matches) > 0:
                    csv_row = matches.iloc[0]
                    db_trade.equity = float(csv_row['equity']) if pd.notna(csv_row['equity']) else None
                    db_trade.drawdown = float(csv_row['drawdown']) if pd.notna(csv_row['drawdown']) else None
                    updates += 1

            await session.commit()
            print(f"  Updated {updates} trades with equity values")

    print("\n[OK] Equity population complete!")


if __name__ == "__main__":
    asyncio.run(populate_equity())
