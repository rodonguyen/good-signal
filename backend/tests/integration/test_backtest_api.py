"""
Integration tests for backtest API endpoints.

Tests verify the complete backtest lifecycle including creation, listing,
retrieval, trade access, cancellation, and deletion. Uses real database
operations with async test clients and proper isolation between tests.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.models import Backtest, BacktestTrade


@pytest.mark.asyncio
class TestCreateBacktest:
    """Test backtest creation endpoint."""

    async def test_create_backtest_returns_201(
        self,
        test_client: AsyncClient,
        sample_backtest_request: dict[str, Any],
    ) -> None:
        """Test that creating a backtest returns 201 Created status."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            # Mock task manager to avoid actual task queue operations
            mock_tm = AsyncMock()
            mock_tm.enqueue = AsyncMock(return_value="task-123")
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                "/api/backtests",
                json=sample_backtest_request,
            )

            assert response.status_code == 201

    async def test_create_backtest_returns_id(
        self,
        test_client: AsyncClient,
        sample_backtest_request: dict[str, Any],
    ) -> None:
        """Test that created backtest response includes an ID."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            mock_tm.enqueue = AsyncMock(return_value="task-123")
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                "/api/backtests",
                json=sample_backtest_request,
            )

            assert response.status_code == 201
            data = response.json()

            assert "id" in data
            assert isinstance(data["id"], str)
            assert len(data["id"]) > 0

    async def test_create_backtest_queues_task(
        self,
        test_client: AsyncClient,
        sample_backtest_request: dict[str, Any],
    ) -> None:
        """Test that creating a backtest enqueues a task for processing."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            mock_tm.enqueue = AsyncMock(return_value="task-123")
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                "/api/backtests",
                json=sample_backtest_request,
            )

            assert response.status_code == 201
            data = response.json()

            # Verify task was enqueued
            mock_tm.enqueue.assert_called_once()
            call_args = mock_tm.enqueue.call_args

            # Verify enqueue was called with correct task_type
            assert call_args.kwargs["task_type"] == "backtest"
            assert "payload" in call_args.kwargs
            assert call_args.kwargs["payload"]["backtest_id"] == data["id"]

    async def test_create_backtest_validates_symbols(
        self,
        test_client: AsyncClient,
        sample_backtest_request: dict[str, Any],
    ) -> None:
        """Test that backtest creation validates symbols."""
        # Test with empty symbols list
        invalid_request = sample_backtest_request.copy()
        invalid_request["symbols"] = []

        response = await test_client.post(
            "/api/backtests",
            json=invalid_request,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    async def test_create_backtest_validates_strategies(
        self,
        test_client: AsyncClient,
        sample_backtest_request: dict[str, Any],
    ) -> None:
        """Test that backtest creation validates strategies."""
        # Test with empty strategies list
        invalid_request = sample_backtest_request.copy()
        invalid_request["strategies"] = []

        response = await test_client.post(
            "/api/backtests",
            json=invalid_request,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    async def test_create_backtest_validates_strategy_enabled(
        self,
        test_client: AsyncClient,
        sample_backtest_request: dict[str, Any],
    ) -> None:
        """Test that at least one strategy must be enabled."""
        # Test with all strategies disabled
        invalid_request = sample_backtest_request.copy()
        for strategy in invalid_request["strategies"]:
            strategy["enabled"] = False

        response = await test_client.post(
            "/api/backtests",
            json=invalid_request,
        )

        assert response.status_code == 422

    async def test_create_backtest_stores_configuration(
        self,
        test_client: AsyncClient,
        sample_backtest_request: dict[str, Any],
        clean_db: AsyncSession,
    ) -> None:
        """Test that backtest configuration is properly stored in database."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            mock_tm.enqueue = AsyncMock(return_value="task-123")
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                "/api/backtests",
                json=sample_backtest_request,
            )

            assert response.status_code == 201
            data = response.json()

            # Verify backtest was created in database
            from sqlalchemy import select
            result = await clean_db.execute(
                select(Backtest).where(Backtest.id == data["id"])
            )
            backtest = result.scalar_one_or_none()

            assert backtest is not None
            assert backtest.name == sample_backtest_request["name"]
            assert backtest.status == "pending"
            assert backtest.fee_rate == sample_backtest_request["fee_rate"]

    async def test_create_backtest_pending_status(
        self,
        test_client: AsyncClient,
        sample_backtest_request: dict[str, Any],
    ) -> None:
        """Test that newly created backtest has pending status."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            mock_tm.enqueue = AsyncMock(return_value="task-123")
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                "/api/backtests",
                json=sample_backtest_request,
            )

            assert response.status_code == 201
            data = response.json()

            assert data["status"] == "pending"
            assert data["progress"] == 0.0

    async def test_create_backtest_includes_config(
        self,
        test_client: AsyncClient,
        sample_backtest_request: dict[str, Any],
    ) -> None:
        """Test that response includes complete configuration."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            mock_tm.enqueue = AsyncMock(return_value="task-123")
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                "/api/backtests",
                json=sample_backtest_request,
            )

            assert response.status_code == 201
            data = response.json()

            assert "config" in data
            assert "symbols" in data
            assert "strategies" in data
            assert data["symbols"] == sample_backtest_request["symbols"]


@pytest.mark.asyncio
class TestListBacktests:
    """Test backtest listing endpoint."""

    async def test_list_backtests_returns_list(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that list backtests endpoint returns a paginated list."""
        response = await test_client.get("/api/backtests")

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "pages" in data
        assert isinstance(data["items"], list)

    async def test_list_backtests_pagination(
        self,
        test_client: AsyncClient,
        multiple_backtest_records: list[Backtest],
    ) -> None:
        """Test that pagination parameters work correctly."""
        # Test first page
        response = await test_client.get("/api/backtests?page=1&page_size=2")

        assert response.status_code == 200
        data = response.json()

        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2
        assert data["total"] >= 3

        # Test second page
        response = await test_client.get("/api/backtests?page=2&page_size=2")

        assert response.status_code == 200
        data = response.json()

        assert data["page"] == 2
        assert len(data["items"]) >= 1

    async def test_list_backtests_filter_by_status(
        self,
        test_client: AsyncClient,
        multiple_backtest_records: list[Backtest],
    ) -> None:
        """Test filtering backtests by status."""
        # Filter for completed backtests
        response = await test_client.get("/api/backtests?status=completed")

        assert response.status_code == 200
        data = response.json()

        # All returned items should have completed status
        for item in data["items"]:
            assert item["status"] == "completed"

    async def test_list_backtests_empty_database(
        self,
        test_client: AsyncClient,
        clean_db: AsyncSession,
    ) -> None:
        """Test listing backtests when database is empty."""
        response = await test_client.get("/api/backtests")

        assert response.status_code == 200
        data = response.json()

        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    async def test_list_backtests_includes_summary_fields(
        self,
        test_client: AsyncClient,
        multiple_backtest_records: list[Backtest],
    ) -> None:
        """Test that list response includes summary fields."""
        response = await test_client.get("/api/backtests")

        assert response.status_code == 200
        data = response.json()

        if data["items"]:
            item = data["items"][0]
            assert "id" in item
            assert "name" in item
            assert "status" in item
            assert "progress" in item
            assert "symbols" in item
            assert "created_at" in item

    async def test_list_backtests_ordered_by_created_at(
        self,
        test_client: AsyncClient,
        multiple_backtest_records: list[Backtest],
    ) -> None:
        """Test that backtests are ordered by creation date (most recent first)."""
        response = await test_client.get("/api/backtests?page_size=10")

        assert response.status_code == 200
        data = response.json()

        if len(data["items"]) > 1:
            # Verify descending order by created_at
            from datetime import datetime
            timestamps = [
                datetime.fromisoformat(item["created_at"])
                for item in data["items"]
            ]
            # Should be in descending order (most recent first)
            assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
class TestGetBacktest:
    """Test individual backtest retrieval endpoint."""

    async def test_get_backtest_returns_details(
        self,
        test_client: AsyncClient,
        sample_backtest_record: Backtest,
    ) -> None:
        """Test that get backtest returns detailed information."""
        response = await test_client.get(f"/api/backtests/{sample_backtest_record.id}")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == sample_backtest_record.id
        assert data["status"] == sample_backtest_record.status
        assert "config" in data
        assert "symbols" in data
        assert "strategies" in data

    async def test_get_backtest_not_found(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that getting non-existent backtest returns 404."""
        response = await test_client.get("/api/backtests/nonexistent-id")

        assert response.status_code == 404
        data = response.json()

        assert "detail" in data
        assert "error_code" in data["detail"] or "error" in data["detail"]

    async def test_get_backtest_includes_performance_metrics(
        self,
        test_client: AsyncClient,
        completed_backtest_record: Backtest,
    ) -> None:
        """Test that completed backtest includes performance metrics."""
        response = await test_client.get(f"/api/backtests/{completed_backtest_record.id}")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "completed"
        assert "total_return" in data
        assert "sharpe_ratio" in data
        assert "max_drawdown" in data
        assert "win_rate" in data
        assert "profit_factor" in data
        assert "total_trades" in data

    async def test_get_backtest_includes_timestamps(
        self,
        test_client: AsyncClient,
        sample_backtest_record: Backtest,
    ) -> None:
        """Test that backtest response includes timestamp fields."""
        response = await test_client.get(f"/api/backtests/{sample_backtest_record.id}")

        assert response.status_code == 200
        data = response.json()

        assert "created_at" in data
        assert isinstance(data["created_at"], str)

        # Validate ISO timestamp format
        from datetime import datetime
        datetime.fromisoformat(data["created_at"])

    async def test_get_backtest_error_message_on_failure(
        self,
        test_client: AsyncClient,
        failed_backtest_record: Backtest,
    ) -> None:
        """Test that failed backtest includes error message."""
        response = await test_client.get(f"/api/backtests/{failed_backtest_record.id}")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "failed"
        assert "error_message" in data
        assert data["error_message"] is not None


@pytest.mark.asyncio
class TestGetBacktestTrades:
    """Test backtest trades retrieval endpoint."""

    async def test_get_backtest_trades_returns_list(
        self,
        test_client: AsyncClient,
        sample_backtest_record: Backtest,
    ) -> None:
        """Test that get trades endpoint returns paginated list."""
        response = await test_client.get(
            f"/api/backtests/{sample_backtest_record.id}/trades"
        )

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["items"], list)

    async def test_get_backtest_trades_not_found(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that getting trades for non-existent backtest returns 404."""
        response = await test_client.get("/api/backtests/nonexistent-id/trades")

        assert response.status_code == 404
        data = response.json()

        assert "detail" in data

    async def test_get_backtest_trades_pagination(
        self,
        test_client: AsyncClient,
        backtest_with_trades: tuple[Backtest, list[BacktestTrade]],
    ) -> None:
        """Test trades pagination works correctly."""
        backtest, trades = backtest_with_trades

        # Test first page
        response = await test_client.get(
            f"/api/backtests/{backtest.id}/trades?page=1&page_size=5"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["page"] == 1
        assert data["page_size"] == 5
        assert len(data["items"]) <= 5

    async def test_get_backtest_trades_includes_details(
        self,
        test_client: AsyncClient,
        backtest_with_trades: tuple[Backtest, list[BacktestTrade]],
    ) -> None:
        """Test that trade response includes all required fields."""
        backtest, trades = backtest_with_trades

        response = await test_client.get(f"/api/backtests/{backtest.id}/trades")

        assert response.status_code == 200
        data = response.json()

        if data["items"]:
            trade = data["items"][0]
            assert "id" in trade
            assert "symbol" in trade
            assert "strategy_id" in trade
            assert "direction" in trade
            assert "entry_time" in trade
            assert "exit_time" in trade
            assert "entry_price" in trade
            assert "exit_price" in trade
            assert "raw_pnl" in trade
            assert "fees" in trade
            assert "net_pnl" in trade

    async def test_get_backtest_trades_empty(
        self,
        test_client: AsyncClient,
        sample_backtest_record: Backtest,
    ) -> None:
        """Test getting trades for backtest with no trades."""
        response = await test_client.get(
            f"/api/backtests/{sample_backtest_record.id}/trades"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["items"] == []
        assert data["total"] == 0

    async def test_get_backtest_trades_ordered_by_entry_time(
        self,
        test_client: AsyncClient,
        backtest_with_trades: tuple[Backtest, list[BacktestTrade]],
    ) -> None:
        """Test that trades are ordered by entry time."""
        backtest, trades = backtest_with_trades

        response = await test_client.get(
            f"/api/backtests/{backtest.id}/trades?page_size=100"
        )

        assert response.status_code == 200
        data = response.json()

        if len(data["items"]) > 1:
            # Verify ordered by entry_time
            from datetime import datetime
            entry_times = [
                datetime.fromisoformat(trade["entry_time"])
                for trade in data["items"]
            ]
            # Should be in ascending order
            assert entry_times == sorted(entry_times)


@pytest.mark.asyncio
class TestDeleteBacktest:
    """Test backtest deletion endpoint."""

    async def test_delete_backtest_success(
        self,
        test_client: AsyncClient,
        completed_backtest_record: Backtest,
        clean_db: AsyncSession,
    ) -> None:
        """Test that completed backtest can be deleted successfully."""
        response = await test_client.delete(
            f"/api/backtests/{completed_backtest_record.id}"
        )

        assert response.status_code == 204

        # Verify backtest was deleted from database
        from sqlalchemy import select
        result = await clean_db.execute(
            select(Backtest).where(Backtest.id == completed_backtest_record.id)
        )
        backtest = result.scalar_one_or_none()

        assert backtest is None

    async def test_delete_backtest_not_found(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that deleting non-existent backtest returns 404."""
        response = await test_client.delete("/api/backtests/nonexistent-id")

        assert response.status_code == 404
        data = response.json()

        assert "detail" in data

    async def test_delete_backtest_running_fails(
        self,
        test_client: AsyncClient,
        running_backtest_record: Backtest,
    ) -> None:
        """Test that running backtest cannot be deleted."""
        response = await test_client.delete(
            f"/api/backtests/{running_backtest_record.id}"
        )

        assert response.status_code == 409
        data = response.json()

        assert "detail" in data
        assert "error" in data["detail"] or "message" in data["detail"]

    async def test_delete_backtest_pending_fails(
        self,
        test_client: AsyncClient,
        sample_backtest_record: Backtest,
    ) -> None:
        """Test that pending backtest cannot be deleted."""
        response = await test_client.delete(
            f"/api/backtests/{sample_backtest_record.id}"
        )

        assert response.status_code == 409

    async def test_delete_backtest_deletes_trades(
        self,
        test_client: AsyncClient,
        backtest_with_trades: tuple[Backtest, list[BacktestTrade]],
        clean_db: AsyncSession,
    ) -> None:
        """Test that deleting backtest also deletes associated trades."""
        backtest, trades = backtest_with_trades

        # First, mark backtest as completed so it can be deleted
        from sqlalchemy import update
        await clean_db.execute(
            update(Backtest)
            .where(Backtest.id == backtest.id)
            .values(status="completed")
        )
        await clean_db.commit()

        response = await test_client.delete(f"/api/backtests/{backtest.id}")

        assert response.status_code == 204

        # Verify trades were deleted
        from sqlalchemy import select
        result = await clean_db.execute(
            select(BacktestTrade).where(BacktestTrade.backtest_id == backtest.id)
        )
        remaining_trades = result.scalars().all()

        assert len(remaining_trades) == 0

    async def test_delete_backtest_failed_success(
        self,
        test_client: AsyncClient,
        failed_backtest_record: Backtest,
    ) -> None:
        """Test that failed backtest can be deleted."""
        response = await test_client.delete(
            f"/api/backtests/{failed_backtest_record.id}"
        )

        assert response.status_code == 204


@pytest.mark.asyncio
class TestCancelBacktest:
    """Test backtest cancellation endpoint."""

    async def test_cancel_backtest_success(
        self,
        test_client: AsyncClient,
        sample_backtest_record: Backtest,
        clean_db: AsyncSession,
    ) -> None:
        """Test that pending backtest can be cancelled successfully."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                f"/api/backtests/{sample_backtest_record.id}/cancel"
            )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert "message" in data
            assert data["backtest_id"] == sample_backtest_record.id

            # Verify backtest status was updated to cancelled
            await clean_db.refresh(sample_backtest_record)
            assert sample_backtest_record.status == "cancelled"

    async def test_cancel_backtest_not_found(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that cancelling non-existent backtest returns 404."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            MockTaskManager.return_value = mock_tm

            response = await test_client.post("/api/backtests/nonexistent-id/cancel")

            assert response.status_code == 404
            data = response.json()

            assert "detail" in data

    async def test_cancel_backtest_completed_fails(
        self,
        test_client: AsyncClient,
        completed_backtest_record: Backtest,
    ) -> None:
        """Test that completed backtest cannot be cancelled."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                f"/api/backtests/{completed_backtest_record.id}/cancel"
            )

            assert response.status_code == 409
            data = response.json()

            assert "detail" in data
            assert "error" in data["detail"] or "message" in data["detail"]

    async def test_cancel_backtest_running_fails(
        self,
        test_client: AsyncClient,
        running_backtest_record: Backtest,
    ) -> None:
        """Test that running backtest cannot be cancelled via this endpoint."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                f"/api/backtests/{running_backtest_record.id}/cancel"
            )

            assert response.status_code == 409

    async def test_cancel_backtest_failed_fails(
        self,
        test_client: AsyncClient,
        failed_backtest_record: Backtest,
    ) -> None:
        """Test that failed backtest cannot be cancelled."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                f"/api/backtests/{failed_backtest_record.id}/cancel"
            )

            assert response.status_code == 409

    async def test_cancel_backtest_returns_response_schema(
        self,
        test_client: AsyncClient,
        sample_backtest_record: Backtest,
    ) -> None:
        """Test that cancel response matches expected schema."""
        with patch("backend.routers.backtest.TaskManager") as MockTaskManager:
            mock_tm = AsyncMock()
            MockTaskManager.return_value = mock_tm

            response = await test_client.post(
                f"/api/backtests/{sample_backtest_record.id}/cancel"
            )

            assert response.status_code == 200
            data = response.json()

            # Verify response structure
            assert "success" in data
            assert "message" in data
            assert "backtest_id" in data
            assert isinstance(data["success"], bool)
            assert isinstance(data["message"], str)
            assert isinstance(data["backtest_id"], str)
