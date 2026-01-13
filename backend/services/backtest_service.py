"""
Backtest service for orchestrating backtest execution.

Provides high-level operations for creating, executing, and managing
backtests with database persistence and task queue integration.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import BacktestError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.infrastructure.database.models import Backtest, BacktestTrade
from backend.infrastructure.database.repositories.backtest_repo import BacktestRepository
from backend.infrastructure.database.repositories.trade_repo import BacktestTradeRepository
from backend.infrastructure.queue.task_manager import TaskManager

if TYPE_CHECKING:
    from src.backtest.runner import BacktestConfig, BacktestRunner

logger = get_logger(__name__)


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat()


def _generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


# Thread pool for running sync backtest code
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="backtest_worker")


class BacktestService:
    """
    Service for managing backtest lifecycle.

    Orchestrates backtest creation, execution, and result storage
    with proper async/sync boundaries and progress tracking.

    Attributes:
        session: Database session for persistence operations.
        backtest_repo: Repository for backtest entity operations.
        trade_repo: Repository for backtest trade operations.
        task_manager: Task queue manager for background processing.

    Example:
        >>> service = BacktestService(session, backtest_repo, trade_repo, task_manager)
        >>> backtest_id = await service.create_backtest(request)
        >>> await service.execute_backtest(backtest_id)
    """

    def __init__(
        self,
        session: AsyncSession,
        backtest_repo: BacktestRepository,
        trade_repo: BacktestTradeRepository,
        task_manager: TaskManager,
    ) -> None:
        """
        Initialize the BacktestService.

        Args:
            session: SQLAlchemy async session for database operations.
            backtest_repo: Repository for backtest entity operations.
            trade_repo: Repository for backtest trade operations.
            task_manager: Task queue manager for background processing.
        """
        self._session = session
        self._backtest_repo = backtest_repo
        self._trade_repo = trade_repo
        self._task_manager = task_manager

    async def create_backtest(self, request: dict[str, Any]) -> str:
        """
        Create a backtest record and queue for execution.

        Validates the request, creates a pending backtest record in the database,
        and enqueues a task for background execution.

        Args:
            request: Backtest configuration request containing:
                - name (optional): Human-readable name for the backtest
                - symbols: List of trading symbols
                - strategies: List of strategy configurations
                - filters (optional): Filter configurations
                - fee_rate: Trading fee rate (e.g., 0.001 for 0.1%)
                - initial_equity: Starting capital
                - risk_per_trade (optional): Risk percentage per trade
                - start_date (optional): Backtest start date (YYYY-MM-DD)
                - end_date (optional): Backtest end date (YYYY-MM-DD)
                - config (optional): Full runner configuration override

        Returns:
            str: Unique backtest identifier.

        Raises:
            ValidationError: If request validation fails.
            BacktestError: If backtest creation fails.
        """
        try:
            # Validate required fields
            self._validate_request(request)

            # Generate backtest ID
            backtest_id = _generate_uuid()

            # Extract and serialize configuration
            symbols = request.get("symbols", [])
            strategies = request.get("strategies", [])
            filters = request.get("filters")
            config_json = json.dumps(request)

            # Create backtest record
            backtest = Backtest(
                id=backtest_id,
                name=request.get("name") or f"Backtest {backtest_id[:8]}",
                status="pending",
                progress=0.0,
                config_json=config_json,
                symbols=json.dumps(symbols),
                strategies=json.dumps(strategies),
                filters=json.dumps(filters) if filters else None,
                fee_rate=float(request.get("fee_rate", 0.001)),
                initial_equity=float(request.get("initial_equity", 10000)),
                risk_per_trade=request.get("risk_per_trade"),
                start_date=request.get("start_date"),
                end_date=request.get("end_date"),
                created_at=_utc_now(),
            )

            # Save to database
            await self._backtest_repo.create(backtest)
            await self._session.commit()

            logger.info(
                "Backtest created",
                backtest_id=backtest_id,
                symbols=symbols,
                strategies=[s.get("type") for s in strategies],
            )

            # Queue task for execution
            await self._task_manager.enqueue(
                task_type="backtest",
                payload={"backtest_id": backtest_id},
                priority=1,  # Normal priority
            )

            logger.info("Backtest queued for execution", backtest_id=backtest_id)

            return backtest_id

        except ValidationError:
            raise
        except Exception as e:
            logger.error("Failed to create backtest", error=str(e))
            raise BacktestError(
                message=f"Failed to create backtest: {e}",
                error_code="BACKTEST_CREATE_FAILED",
                details={"error": str(e)},
            )

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

            # Load configuration
            config = json.loads(backtest.config_json)
            runner_config = self._convert_request_to_runner_config(config)

            # Import here to avoid circular imports and allow lazy loading
            from src.backtest.runner import BacktestConfig, BacktestRunner

            # Create backtest config and runner
            backtest_config = BacktestConfig(raw=runner_config)

            # Run backtest in thread pool (sync operation)
            loop = asyncio.get_running_loop()

            # Create a progress tracker for the sync execution
            symbols = json.loads(backtest.symbols)
            total_symbols = len(symbols)

            async def update_progress(symbol_idx: int, symbol: str) -> None:
                progress = (symbol_idx + 1) / total_symbols if total_symbols > 0 else 1.0
                await self._backtest_repo.update_progress(backtest_id, progress, symbol)
                await self._session.commit()
                if progress_callback:
                    await progress_callback(progress, "running", symbol)

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

    async def get_backtest(self, backtest_id: str) -> Optional[Backtest]:
        """
        Get backtest by ID.

        Args:
            backtest_id: Unique backtest identifier.

        Returns:
            Optional[Backtest]: Backtest entity if found, None otherwise.
        """
        return await self._backtest_repo.get_by_id(backtest_id)

    async def list_backtests(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> list[Backtest]:
        """
        List backtests with pagination.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            status: Optional status filter.

        Returns:
            list[Backtest]: List of backtest entities.
        """
        if status:
            return await self._backtest_repo.get_by_status(status, skip=skip, limit=limit)
        return await self._backtest_repo.get_all(skip=skip, limit=limit)

    async def cancel_backtest(self, backtest_id: str) -> bool:
        """
        Cancel a pending or running backtest.

        Only pending backtests can be fully cancelled. Running backtests
        will be marked for cancellation but may complete their current operation.

        Args:
            backtest_id: Unique backtest identifier.

        Returns:
            bool: True if cancellation was successful, False otherwise.

        Raises:
            NotFoundError: If backtest is not found.
        """
        backtest = await self._backtest_repo.get_by_id(backtest_id)
        if backtest is None:
            raise NotFoundError(
                message=f"Backtest not found: {backtest_id}",
                error_code="BACKTEST_NOT_FOUND",
                details={"backtest_id": backtest_id},
            )

        if backtest.status == "pending":
            # Cancel pending backtest
            cancelled = await self._backtest_repo.cancel_pending(backtest_id)
            await self._session.commit()

            if cancelled:
                logger.info("Backtest cancelled", backtest_id=backtest_id)
            return cancelled

        if backtest.status == "running":
            # Mark as cancelled - the worker should check this status
            await self._backtest_repo.update_status(backtest_id, "cancelled")
            await self._session.commit()
            logger.info("Running backtest marked for cancellation", backtest_id=backtest_id)
            return True

        # Already completed, failed, or cancelled
        logger.warning(
            "Cannot cancel backtest with status",
            backtest_id=backtest_id,
            status=backtest.status,
        )
        return False

    async def delete_backtest(self, backtest_id: str) -> bool:
        """
        Delete backtest and associated trades.

        Args:
            backtest_id: Unique backtest identifier.

        Returns:
            bool: True if deletion was successful, False if not found.

        Raises:
            BacktestError: If deletion fails.
        """
        try:
            backtest = await self._backtest_repo.get_by_id(backtest_id)
            if backtest is None:
                return False

            # Don't delete running backtests
            if backtest.status == "running":
                raise BacktestError(
                    message="Cannot delete a running backtest",
                    error_code="BACKTEST_DELETE_RUNNING",
                    details={"backtest_id": backtest_id, "status": "running"},
                )

            # Delete associated trades first (cascade should handle this, but be explicit)
            await self._trade_repo.delete_by_backtest(backtest_id)

            # Delete backtest
            deleted = await self._backtest_repo.delete(backtest_id)
            await self._session.commit()

            if deleted:
                logger.info("Backtest deleted", backtest_id=backtest_id)
            return deleted

        except BacktestError:
            raise
        except Exception as e:
            logger.error("Failed to delete backtest", backtest_id=backtest_id, error=str(e))
            raise BacktestError(
                message=f"Failed to delete backtest: {e}",
                error_code="BACKTEST_DELETE_FAILED",
                details={"backtest_id": backtest_id, "error": str(e)},
            )

    async def get_backtest_trades(
        self,
        backtest_id: str,
        skip: int = 0,
        limit: int = 1000,
    ) -> list[BacktestTrade]:
        """
        Get trades for a specific backtest.

        Args:
            backtest_id: Unique backtest identifier.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            list[BacktestTrade]: List of trade entities.
        """
        return await self._trade_repo.get_by_backtest(backtest_id, skip=skip, limit=limit)

    async def get_backtest_statistics(self, backtest_id: str) -> dict[str, Any]:
        """
        Get trade statistics for a backtest.

        Args:
            backtest_id: Unique backtest identifier.

        Returns:
            dict: Trade statistics including win rate, profit factor, etc.
        """
        return await self._trade_repo.get_statistics(backtest_id)

    def _validate_request(self, request: dict[str, Any]) -> None:
        """
        Validate backtest request.

        Args:
            request: Backtest configuration request.

        Raises:
            ValidationError: If validation fails.
        """
        errors = []

        # Check required fields
        symbols = request.get("symbols")
        if not symbols or not isinstance(symbols, list) or len(symbols) == 0:
            errors.append("symbols: at least one symbol is required")

        strategies = request.get("strategies")
        if not strategies or not isinstance(strategies, list) or len(strategies) == 0:
            errors.append("strategies: at least one strategy is required")

        # Validate strategy structure
        if strategies:
            for i, strategy in enumerate(strategies):
                if not isinstance(strategy, dict):
                    errors.append(f"strategies[{i}]: must be an object")
                    continue
                if "type" not in strategy:
                    errors.append(f"strategies[{i}].type: strategy type is required")

        # Validate numeric fields
        fee_rate = request.get("fee_rate")
        if fee_rate is not None:
            try:
                fee_rate = float(fee_rate)
                if fee_rate < 0 or fee_rate > 1:
                    errors.append("fee_rate: must be between 0 and 1")
            except (TypeError, ValueError):
                errors.append("fee_rate: must be a number")

        initial_equity = request.get("initial_equity")
        if initial_equity is not None:
            try:
                initial_equity = float(initial_equity)
                if initial_equity <= 0:
                    errors.append("initial_equity: must be positive")
            except (TypeError, ValueError):
                errors.append("initial_equity: must be a number")

        if errors:
            raise ValidationError(
                message="Invalid backtest request",
                error_code="BACKTEST_VALIDATION_FAILED",
                details={"errors": errors},
            )

    def _convert_request_to_runner_config(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Convert API request config to BacktestRunner config format.

        Maps the API request structure to the YAML configuration structure
        expected by the BacktestRunner.

        Args:
            request: API request configuration.

        Returns:
            dict: Configuration in BacktestRunner format.
        """
        # If full config override is provided, use it
        if "config" in request and isinstance(request["config"], dict):
            return request["config"]

        # Build configuration from request fields
        symbols = request.get("symbols", [])
        strategies = request.get("strategies", [])
        fee_rate = float(request.get("fee_rate", 0.0029))
        initial_equity = float(request.get("initial_equity", 9900))

        # Build engine configuration
        engine_config = {
            "fee_rate": fee_rate,
            "debug": request.get("debug", False),
            "outputs": {
                "trades_dir": request.get("trades_dir"),
                "portfolio_dir": request.get("portfolio_dir"),
                "reports_dir": request.get("reports_dir"),
            },
        }

        logger.info(f"Engine config: {engine_config}")

        # Build cache configuration
        cache_config = request.get("cache", {})
        if cache_config:
            engine_config["cache"] = {
                "enabled": cache_config.get("enabled", True),
                "dir": cache_config.get("dir"),
                "version": cache_config.get("version", "v1"),
            }

        # Build data configuration
        data_config = {
            "raw_1m_dir": request.get("raw_1m_dir", "data/raw/crypto"),
        }

        # Add download configuration if provided
        download_config = request.get("download", {})
        if download_config:
            data_config["download"] = {
                "enabled": download_config.get("enabled", False),
                "provider": download_config.get("provider", "bybit"),
                "start_date": request.get("start_date"),
                "end_date": request.get("end_date"),
            }

        # Build steps configuration
        steps_config = {
            "enabled_blocks": request.get("enabled_blocks", [1, 2, 3, 4, 5]),
        }

        # Add filters configuration if provided
        filters = request.get("filters", {})
        if filters:
            steps_config["filters"] = {
                "enabled": filters.get("enabled", True),
                "config_path": filters.get("config_path", "config/backtest/filters.yaml"),
            }

        # Add portfolio configuration
        portfolio = request.get("portfolio", {})
        steps_config["portfolio"] = {
            "enabled": portfolio.get("enabled", True),
            "initial_equity": initial_equity,
            "risk_per_trade": request.get("risk_per_trade", 0.02),
            "config_path": portfolio.get("config_path", "config/backtest/portfolio_config.yaml"),
        }

        # Add analysis configuration
        analysis = request.get("analysis", {})
        steps_config["analysis"] = {
            "enabled": analysis.get("enabled", True),
        }

        # Assemble final configuration
        config = {
            "engine": engine_config,
            "data": data_config,
            "universe": {
                "symbols": symbols,
            },
            "strategies": strategies,
            "steps": steps_config,
        }

        logger.info(f"Final config: {config}")

        return config

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
                    # Use net_pnl as returns proxy
                    if len(net_pnl) > 1 and net_pnl.std() > 0:
                        # Approximate daily Sharpe, annualize with sqrt(252)
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
                report_pattern = reports_dir / strategy_id / "*.html"
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

        # Create a minimal task manager (not needed for execution, only for service init)
        # We pass None since we don't need to enqueue more tasks during execution
        service = BacktestService(
            session=session,
            backtest_repo=backtest_repo,
            trade_repo=trade_repo,
            task_manager=None,  # type: ignore
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
