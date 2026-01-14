"""
Backtest execution service.

Provides backtest execution functionality for the background worker.
All CRUD operations are handled directly by the router using repositories.
"""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import BacktestError, NotFoundError
from backend.core.logging import get_logger
from backend.infrastructure.database.models import Backtest, BacktestTrade
from backend.infrastructure.database.repositories.backtest_repo import BacktestRepository
from backend.infrastructure.database.repositories.trade_repo import BacktestTradeRepository

if TYPE_CHECKING:
    from src.backtest.runner import BacktestConfig, BacktestRunner

logger = get_logger(__name__)


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


# Thread pool for running sync backtest code
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="backtest_worker")


class BacktestService:
    """
    Service for executing backtests.

    Used only by the background worker to run backtest computations.
    CRUD operations are handled directly by the router.

    Attributes:
        session: Database session for persistence operations.
        backtest_repo: Repository for backtest entity operations.
        trade_repo: Repository for backtest trade operations.
    """

    def __init__(
        self,
        session: AsyncSession,
        backtest_repo: BacktestRepository,
        trade_repo: BacktestTradeRepository,
    ) -> None:
        """
        Initialize the BacktestService.

        Args:
            session: SQLAlchemy async session for database operations.
            backtest_repo: Repository for backtest entity operations.
            trade_repo: Repository for backtest trade operations.
        """
        self._session = session
        self._backtest_repo = backtest_repo
        self._trade_repo = trade_repo

    async def execute_backtest(
        self,
        backtest_id: str,
        progress_callback: Optional[Callable[[float, str, Optional[str]], Any]] = None,
    ) -> dict[str, Any]:
        """
        Execute a backtest (called by worker).

        Loads the backtest configuration, runs the backtest runner in a thread pool,
        stores results and trades, and updates the backtest status.

        Args:
            backtest_id: Unique backtest identifier.
            progress_callback: Optional async callback for progress updates.
                Signature: (progress: float, status: str, current_symbol: Optional[str]) -> None

        Returns:
            dict: Backtest results containing metrics and trade summary.

        Raises:
            NotFoundError: If backtest is not found.
            BacktestError: If backtest execution fails.
        """
        backtest = await self._backtest_repo.get_by_id(backtest_id)
        if backtest is None:
            raise NotFoundError(
                message=f"Backtest not found: {backtest_id}",
                error_code="BACKTEST_NOT_FOUND",
                details={"backtest_id": backtest_id},
            )

        try:
            # Update status to running
            await self._backtest_repo.update_status(backtest_id, "running")
            await self._session.commit()

            if progress_callback:
                await progress_callback(0.0, "running", None)

            # Load configuration directly (already built by router)
            runner_config = json.loads(backtest.config_json)

            # Import here to avoid circular imports and allow lazy loading
            from src.backtest.runner import BacktestConfig, BacktestRunner

            # Create backtest config and runner
            backtest_config = BacktestConfig(raw=runner_config)

            # Run backtest in thread pool (sync operation)
            loop = asyncio.get_running_loop()

            # Run the sync backtest in executor
            runner = BacktestRunner(backtest_config)
            await loop.run_in_executor(_executor, runner.run)

            # Collect results from output files
            results = await self._collect_results(backtest, runner_config)

            # Store trades in database
            trades_stored = await self._store_trades(backtest_id, results.get("trades", []))

            # Update results with trade count
            results["total_trades"] = trades_stored

            # Update backtest with results
            await self._backtest_repo.update_results(backtest_id, results)
            await self._session.commit()

            if progress_callback:
                await progress_callback(1.0, "completed", None)

            logger.info(
                "Backtest completed",
                backtest_id=backtest_id,
                total_trades=trades_stored,
                total_return=results.get("total_return"),
            )

            return results

        except NotFoundError:
            raise
        except Exception as e:
            error_message = f"{type(e).__name__}: {str(e)}"
            logger.error(
                "Backtest execution failed",
                backtest_id=backtest_id,
                error=error_message,
                exc_info=True,
            )

            # Update status to failed
            await self._backtest_repo.update_status(
                backtest_id,
                "failed",
                error_message=error_message,
            )
            await self._session.commit()

            if progress_callback:
                await progress_callback(0.0, "failed", None)

            raise BacktestError(
                message=f"Backtest execution failed: {e}",
                error_code="BACKTEST_EXECUTION_FAILED",
                details={"backtest_id": backtest_id, "error": str(e)},
            )

    async def _collect_results(
        self,
        backtest: Backtest,
        runner_config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Collect results from backtest output files.

        Reads the generated trade CSV files and calculates summary metrics.

        Args:
            backtest: Backtest entity.
            runner_config: Runner configuration.

        Returns:
            dict: Results including metrics and trades.
        """
        import pandas as pd
        from pathlib import Path

        results: dict[str, Any] = {
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_trades": 0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "winning_trades": 0,
            "losing_trades": 0,
            "trades": [],
        }

        try:
            trades_dir = Path(runner_config["engine"]["outputs"]["trades_dir"])
            strategies = runner_config.get("strategies", [])

            all_trades = []

            for strategy in strategies:
                strategy_id = strategy.get("id", strategy.get("type"))
                combined_file = trades_dir / strategy_id / "all_trades.csv"

                if combined_file.exists():
                    df = pd.read_csv(combined_file)
                    all_trades.append(df)

            if all_trades:
                combined_df = pd.concat(all_trades, ignore_index=True)

                # Calculate metrics
                if len(combined_df) > 0:
                    net_pnl = combined_df["net_pnl"]
                    winners = net_pnl[net_pnl > 0]
                    losers = net_pnl[net_pnl < 0]

                    gross_profit = winners.sum() if len(winners) > 0 else 0.0
                    gross_loss = abs(losers.sum()) if len(losers) > 0 else 0.0

                    results["total_return"] = float(net_pnl.sum())
                    results["win_rate"] = float(len(winners) / len(combined_df))
                    results["profit_factor"] = float(gross_profit / gross_loss if gross_loss > 0 else float("inf"))
                    results["total_trades"] = len(combined_df)
                    results["winning_trades"] = len(winners)
                    results["losing_trades"] = len(losers)

                    # Calculate avg win/loss
                    results["avg_win"] = float(winners.mean()) if len(winners) > 0 else 0.0
                    results["avg_loss"] = float(losers.mean()) if len(losers) > 0 else 0.0

                    # Calculate largest win/loss
                    results["largest_win"] = float(winners.max()) if len(winners) > 0 else 0.0
                    results["largest_loss"] = float(losers.min()) if len(losers) > 0 else 0.0

                    # Calculate max drawdown from cumulative PnL
                    initial_equity = backtest.initial_equity or 10000.0
                    cumulative_pnl = net_pnl.cumsum()
                    equity_curve = initial_equity + cumulative_pnl
                    running_max = equity_curve.cummax()
                    drawdown = running_max - equity_curve
                    results["max_drawdown"] = float(drawdown.max())

                    # Calculate Sharpe Ratio (annualized, assuming daily returns)
                    if len(net_pnl) > 1 and net_pnl.std() > 0:
                        import numpy as np

                        daily_returns = net_pnl / initial_equity
                        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
                        results["sharpe_ratio"] = float(sharpe) if not np.isnan(sharpe) else 0.0

                    # Convert trades to list of dicts
                    results["trades"] = combined_df.to_dict(orient="records")

            # Look for report file
            reports_dir = Path(runner_config["engine"]["outputs"]["reports_dir"])
            for strategy in strategies:
                strategy_id = strategy.get("id", strategy.get("type"))
                report_files = list(reports_dir.glob(f"{strategy_id}/*.html"))
                if report_files:
                    results["report_path"] = str(report_files[0])
                    break

        except Exception as e:
            logger.warning("Failed to collect results from files", error=str(e))

        return results

    async def _store_trades(
        self,
        backtest_id: str,
        trades: list[dict[str, Any]],
    ) -> int:
        """
        Store trades in the database.

        Args:
            backtest_id: Unique backtest identifier.
            trades: List of trade dictionaries.

        Returns:
            int: Number of trades stored.
        """
        if not trades:
            return 0

        stored_count = 0

        for trade_data in trades:
            try:
                trade = BacktestTrade(
                    backtest_id=backtest_id,
                    symbol=str(trade_data.get("symbol", "")),
                    strategy_id=str(trade_data.get("strategy_id", "unknown")),
                    direction=str(trade_data.get("direction", "long")),
                    entry_time=str(trade_data.get("entry_time", "")),
                    exit_time=str(trade_data.get("exit_time", "")),
                    entry_price=float(trade_data.get("entry_price", 0)),
                    exit_price=float(trade_data.get("exit_price", 0)),
                    stop_level=trade_data.get("stop_level"),
                    tp_level=trade_data.get("tp_level"),
                    raw_pnl=float(trade_data.get("raw_pnl", 0)),
                    fees=float(trade_data.get("fees", 0)),
                    net_pnl=float(trade_data.get("net_pnl", 0)),
                    portfolio_pnl=trade_data.get("portfolio_pnl"),
                    position_size=trade_data.get("position_size"),
                    exit_reason=trade_data.get("exit_reason"),
                    metadata_json=json.dumps(trade_data.get("metadata", {})),
                )
                self._session.add(trade)
                stored_count += 1
            except Exception as e:
                logger.warning(
                    "Failed to store trade",
                    backtest_id=backtest_id,
                    error=str(e),
                )

        await self._session.flush()
        return stored_count


async def create_backtest_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Task handler for backtest execution.

    This function is registered with the worker to handle backtest tasks.
    It creates a BacktestService instance and executes the backtest.

    Args:
        payload: Task payload containing backtest_id.

    Returns:
        dict: Execution result.
    """
    from backend.infrastructure.database.connection import AsyncSessionLocal
    from backend.infrastructure.database.repositories.backtest_repo import BacktestRepository
    from backend.infrastructure.database.repositories.trade_repo import BacktestTradeRepository

    backtest_id = payload.get("backtest_id")
    if not backtest_id:
        raise ValueError("backtest_id is required in payload")

    # Create a new session for the worker
    async with AsyncSessionLocal() as session:
        backtest_repo = BacktestRepository(session)
        trade_repo = BacktestTradeRepository(session)

        service = BacktestService(
            session=session,
            backtest_repo=backtest_repo,
            trade_repo=trade_repo,
        )

        # Import broadcast function for progress updates
        try:
            from backend.routers.websocket import broadcast_backtest_progress

            async def progress_callback(
                progress: float,
                status: str,
                current_symbol: Optional[str],
            ) -> None:
                await broadcast_backtest_progress(
                    backtest_id=backtest_id,
                    progress=progress,
                    status=status,
                    current_symbol=current_symbol,
                )

        except ImportError:
            progress_callback = None

        results = await service.execute_backtest(
            backtest_id=backtest_id,
            progress_callback=progress_callback,
        )

        return {
            "backtest_id": backtest_id,
            "status": "completed",
            "total_trades": results.get("total_trades", 0),
            "total_return": results.get("total_return", 0.0),
        }
