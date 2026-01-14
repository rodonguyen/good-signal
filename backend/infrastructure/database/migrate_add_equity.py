"""
Migration script to add equity and drawdown columns to backtest_trades table.

Run this script to upgrade an existing database without data loss:
    python -m backend.infrastructure.database.migrate_add_equity
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


async def migrate():
    """Add equity and drawdown columns to backtest_trades table."""
    from sqlalchemy import text
    from backend.infrastructure.database.connection import engine

    async with engine.begin() as conn:
        # Check if columns already exist
        result = await conn.execute(text("PRAGMA table_info(backtest_trades)"))
        columns = {row[1] for row in result.fetchall()}

        migrations_run = []

        # Add equity column if not exists
        if "equity" not in columns:
            await conn.execute(
                text("ALTER TABLE backtest_trades ADD COLUMN equity REAL")
            )
            migrations_run.append("equity")
            print("[OK] Added 'equity' column")

        # Add drawdown column if not exists
        if "drawdown" not in columns:
            await conn.execute(
                text("ALTER TABLE backtest_trades ADD COLUMN drawdown REAL")
            )
            migrations_run.append("drawdown")
            print("[OK] Added 'drawdown' column")

        if not migrations_run:
            print("[OK] All columns already exist - no migration needed")
        else:
            print(f"\n[OK] Migration complete! Added columns: {', '.join(migrations_run)}")


if __name__ == "__main__":
    print("Running migration: add equity and drawdown columns...")
    asyncio.run(migrate())
