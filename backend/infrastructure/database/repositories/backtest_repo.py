"""
Repository for Backtest entity operations.

Provides specialized query methods for backtest management
including status filtering, progress updates, and result storage.
"""

import json
from datetime import datetime
from typing import Optional, Type

from sqlalchemy import select, update, desc

from backend.core.exceptions import NotFoundError, DatabaseError
from backend.infrastructure.database.models import Backtest

from .base import BaseRepository


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat()


class BacktestRepository(BaseRepository[Backtest]):
    """
    Repository for Backtest entity operations.

    Extends BaseRepository with backtest-specific query methods
    for status management, progress tracking, and result storage.

    Example:
        >>> repo = BacktestRepository(session)
        >>> pending = await repo.get_by_status("pending")
        >>> await repo.update_progress(backtest_id, 0.5, "BTCUSDT")
    """

    @property
    def _model(self) -> Type[Backtest]:
        return Backtest

    async def get_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Backtest]:
        """
        Get backtests filtered by status.

        Args:
            status: Status to filter by (pending, running, completed, failed, cancelled).
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            list[Backtest]: Backtests with the specified status, ordered by created_at desc.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(Backtest)
                .where(Backtest.status == status)
                .order_by(desc(Backtest.created_at))
                .offset(skip)
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get backtests by status: {e}",
                error_code="BACKTEST_STATUS_QUERY_FAILED",
                details={"status": status, "error": str(e)},
            )

    async def get_recent(
        self,
        limit: int = 10,
    ) -> list[Backtest]:
        """
        Get most recent backtests.

        Args:
            limit: Maximum number of records to return.

        Returns:
            list[Backtest]: Most recent backtests ordered by created_at desc.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(Backtest)
                .order_by(desc(Backtest.created_at))
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get recent backtests: {e}",
                error_code="BACKTEST_RECENT_QUERY_FAILED",
                details={"error": str(e)},
            )

    async def update_progress(
        self,
        id: str,
        progress: float,
        current_symbol: Optional[str] = None,
    ) -> None:
        """
        Update backtest progress.

        Args:
            id: Backtest ID.
            progress: Progress value between 0.0 and 1.0.
            current_symbol: Currently processing symbol (optional).

        Raises:
            NotFoundError: If backtest is not found.
            DatabaseError: If update fails.
        """
        try:
            # Build update values
            values: dict = {
                "progress": progress,
            }

            # If current_symbol provided, store in metadata
            if current_symbol is not None:
                # Get existing backtest to update metadata
                backtest = await self.get_by_id(id)
                if backtest is None:
                    raise NotFoundError(
                        message=f"Backtest not found: {id}",
                        error_code="BACKTEST_NOT_FOUND",
                        details={"id": id},
                    )

                # Parse existing results_json or create new
                existing_results = {}
                if backtest.results_json:
                    try:
                        existing_results = json.loads(backtest.results_json)
                    except json.JSONDecodeError:
                        pass

                existing_results["current_symbol"] = current_symbol
                values["results_json"] = json.dumps(existing_results)

            stmt = (
                update(Backtest)
                .where(Backtest.id == id)
                .values(**values)
                .returning(Backtest.id)
            )
            result = await self._session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated is None:
                raise NotFoundError(
                    message=f"Backtest not found: {id}",
                    error_code="BACKTEST_NOT_FOUND",
                    details={"id": id},
                )

            await self._session.flush()
        except NotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to update backtest progress: {e}",
                error_code="BACKTEST_PROGRESS_UPDATE_FAILED",
                details={"id": id, "progress": progress, "error": str(e)},
            )

    async def update_status(
        self,
        id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Update backtest status.

        Args:
            id: Backtest ID.
            status: New status (pending, running, completed, failed, cancelled).
            error_message: Error message if status is failed (optional).

        Raises:
            NotFoundError: If backtest is not found.
            DatabaseError: If update fails.
        """
        try:
            values: dict = {"status": status}

            # Set timestamps based on status
            if status == "running":
                values["started_at"] = _utc_now()
            elif status in ("completed", "failed", "cancelled"):
                values["completed_at"] = _utc_now()

            # Set error message if provided
            if error_message is not None:
                values["error_message"] = error_message

            # Set progress to 100% on completion
            if status == "completed":
                values["progress"] = 1.0

            stmt = (
                update(Backtest)
                .where(Backtest.id == id)
                .values(**values)
                .returning(Backtest.id)
            )
            result = await self._session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated is None:
                raise NotFoundError(
                    message=f"Backtest not found: {id}",
                    error_code="BACKTEST_NOT_FOUND",
                    details={"id": id},
                )

            await self._session.flush()
        except NotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to update backtest status: {e}",
                error_code="BACKTEST_STATUS_UPDATE_FAILED",
                details={"id": id, "status": status, "error": str(e)},
            )

    async def update_results(
        self,
        id: str,
        results: dict,
    ) -> None:
        """
        Update backtest results.

        Stores full results JSON and extracts key metrics to indexed columns.

        Args:
            id: Backtest ID.
            results: Full results dictionary with metrics.

        Raises:
            NotFoundError: If backtest is not found.
            DatabaseError: If update fails.
        """
        try:
            values: dict = {
                "results_json": json.dumps(results),
                "status": "completed",
                "progress": 1.0,
                "completed_at": _utc_now(),
            }

            # Extract key metrics to indexed columns if present
            if "total_return" in results:
                values["total_return"] = results["total_return"]
            if "sharpe_ratio" in results:
                values["sharpe_ratio"] = results["sharpe_ratio"]
            if "max_drawdown" in results:
                values["max_drawdown"] = results["max_drawdown"]
            if "win_rate" in results:
                values["win_rate"] = results["win_rate"]
            if "profit_factor" in results:
                values["profit_factor"] = results["profit_factor"]
            if "total_trades" in results:
                values["total_trades"] = results["total_trades"]
            if "report_path" in results:
                values["report_path"] = results["report_path"]

            stmt = (
                update(Backtest)
                .where(Backtest.id == id)
                .values(**values)
                .returning(Backtest.id)
            )
            result = await self._session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated is None:
                raise NotFoundError(
                    message=f"Backtest not found: {id}",
                    error_code="BACKTEST_NOT_FOUND",
                    details={"id": id},
                )

            await self._session.flush()
        except NotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to update backtest results: {e}",
                error_code="BACKTEST_RESULTS_UPDATE_FAILED",
                details={"id": id, "error": str(e)},
            )

    async def count_by_status(self, status: str) -> int:
        """
        Count backtests with a specific status.

        Args:
            status: Status to count (pending, running, completed, failed, cancelled).

        Returns:
            int: Number of backtests with the status.

        Raises:
            DatabaseError: If count query fails.
        """
        try:
            from sqlalchemy import func

            stmt = (
                select(func.count())
                .select_from(Backtest)
                .where(Backtest.status == status)
            )
            result = await self._session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to count backtests by status: {e}",
                error_code="BACKTEST_COUNT_FAILED",
                details={"status": status, "error": str(e)},
            )

    async def get_running(self) -> list[Backtest]:
        """
        Get all currently running backtests.

        Returns:
            list[Backtest]: All running backtests.

        Raises:
            DatabaseError: If query execution fails.
        """
        return await self.get_by_status("running", limit=1000)

    async def cancel_pending(self, id: str) -> bool:
        """
        Cancel a pending backtest.

        Only pending backtests can be cancelled.

        Args:
            id: Backtest ID.

        Returns:
            bool: True if cancelled, False if not found or not pending.

        Raises:
            DatabaseError: If update fails.
        """
        try:
            stmt = (
                update(Backtest)
                .where(
                    Backtest.id == id,
                    Backtest.status == "pending",
                )
                .values(
                    status="cancelled",
                    completed_at=_utc_now(),
                )
                .returning(Backtest.id)
            )
            result = await self._session.execute(stmt)
            cancelled = result.scalar_one_or_none()
            await self._session.flush()
            return cancelled is not None
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to cancel backtest: {e}",
                error_code="BACKTEST_CANCEL_FAILED",
                details={"id": id, "error": str(e)},
            )
