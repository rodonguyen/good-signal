"""
Unit tests for TaskManager - SQLite-backed async task queue.

Tests cover task lifecycle: enqueuing, claiming, completion, failure,
cancellation, and retry logic with various edge cases.
"""

import json
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.core.exceptions import DatabaseError, NotFoundError
from backend.infrastructure.database.models import TaskQueue
from backend.infrastructure.queue.task_manager import TaskManager


@pytest.mark.asyncio
class TestTaskManagerEnqueue:
    """Test task enqueuing functionality."""

    async def test_enqueue_task_returns_id(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Test that enqueuing a task returns a valid UUID."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
        )

        assert task_id is not None
        assert isinstance(task_id, str)
        assert len(task_id) == 36  # UUID format

    async def test_enqueue_task_with_priority(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that tasks can be enqueued with custom priority."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
            priority=5,
        )

        # Verify task was created with correct priority
        stmt = select(TaskQueue).where(TaskQueue.id == task_id)
        result = await async_session.execute(stmt)
        task = result.scalar_one()

        assert task.priority == 5
        assert task.status == "pending"
        assert task.task_type == "backtest"

    async def test_enqueue_task_with_max_attempts(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that tasks can be enqueued with custom max_attempts."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="data_fetch",
            payload=sample_task_payload,
            max_attempts=5,
        )

        # Verify task was created with correct max_attempts
        stmt = select(TaskQueue).where(TaskQueue.id == task_id)
        result = await async_session.execute(stmt)
        task = result.scalar_one()

        assert task.max_attempts == 5
        assert task.attempts == 0

    async def test_enqueue_task_with_scheduled_time(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that tasks can be scheduled for future execution."""
        manager = TaskManager(session_factory=session_factory)

        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
            scheduled_at=future_time,
        )

        # Verify scheduled time was set
        stmt = select(TaskQueue).where(TaskQueue.id == task_id)
        result = await async_session.execute(stmt)
        task = result.scalar_one()

        assert task.scheduled_at == future_time

    async def test_enqueue_stores_payload_as_json(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that task payload is correctly stored as JSON."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
        )

        # Verify payload was stored correctly
        stmt = select(TaskQueue).where(TaskQueue.id == task_id)
        result = await async_session.execute(stmt)
        task = result.scalar_one()

        stored_payload = json.loads(task.payload_json)
        assert stored_payload == sample_task_payload


@pytest.mark.asyncio
class TestTaskManagerClaim:
    """Test task claiming functionality."""

    async def test_claim_task_returns_highest_priority(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Test that claiming returns the highest priority pending task."""
        manager = TaskManager(session_factory=session_factory)

        # Enqueue tasks with different priorities
        low_priority_id = await manager.enqueue(
            task_type="backtest", payload=sample_task_payload, priority=1
        )
        high_priority_id = await manager.enqueue(
            task_type="backtest", payload=sample_task_payload, priority=10
        )
        medium_priority_id = await manager.enqueue(
            task_type="backtest", payload=sample_task_payload, priority=5
        )

        # Claim task should return highest priority
        claimed = await manager.claim_task(worker_id="worker-1")

        assert claimed is not None
        assert claimed["id"] == high_priority_id
        assert claimed["priority"] == 10

    async def test_claim_task_marks_as_running(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that claiming a task marks it as running."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
        )

        # Claim the task
        claimed = await manager.claim_task(worker_id="worker-1")

        assert claimed is not None
        assert claimed["id"] == task_id

        # Verify task status changed to running
        stmt = select(TaskQueue).where(TaskQueue.id == task_id)
        result = await async_session.execute(stmt)
        task = result.scalar_one()

        assert task.status == "running"
        assert task.worker_id == "worker-1"
        assert task.started_at is not None
        assert task.attempts == 1

    async def test_claim_task_returns_none_when_no_tasks(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that claiming returns None when no tasks are available."""
        manager = TaskManager(session_factory=session_factory)

        claimed = await manager.claim_task(worker_id="worker-1")

        assert claimed is None

    async def test_claim_task_skips_future_scheduled_tasks(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Test that claiming skips tasks scheduled for the future."""
        manager = TaskManager(session_factory=session_factory)

        # Schedule task for 1 hour in the future
        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
            scheduled_at=future_time,
        )

        # Try to claim - should return None
        claimed = await manager.claim_task(worker_id="worker-1")

        assert claimed is None

    async def test_claim_task_increments_attempts(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that claiming a task increments the attempt counter."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
        )

        # Claim the task
        claimed = await manager.claim_task(worker_id="worker-1")

        assert claimed["attempts"] == 1

        # Verify in database
        stmt = select(TaskQueue).where(TaskQueue.id == task_id)
        result = await async_session.execute(stmt)
        task = result.scalar_one()

        assert task.attempts == 1

    async def test_claim_task_respects_fifo_for_same_priority(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Test that tasks with same priority are claimed in FIFO order."""
        manager = TaskManager(session_factory=session_factory)

        # Enqueue multiple tasks with same priority
        first_id = await manager.enqueue(
            task_type="backtest", payload=sample_task_payload, priority=1
        )
        second_id = await manager.enqueue(
            task_type="backtest", payload=sample_task_payload, priority=1
        )
        third_id = await manager.enqueue(
            task_type="backtest", payload=sample_task_payload, priority=1
        )

        # Claim tasks should respect FIFO
        first_claimed = await manager.claim_task(worker_id="worker-1")
        second_claimed = await manager.claim_task(worker_id="worker-2")
        third_claimed = await manager.claim_task(worker_id="worker-3")

        assert first_claimed["id"] == first_id
        assert second_claimed["id"] == second_id
        assert third_claimed["id"] == third_id


@pytest.mark.asyncio
class TestTaskManagerComplete:
    """Test task completion functionality."""

    async def test_complete_task_updates_status(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that completing a task updates its status to completed."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
        )

        await manager.claim_task(worker_id="worker-1")

        # Complete the task
        result = {"status": "success", "trades": 42}
        await manager.complete_task(task_id=task_id, result=result)

        # Verify task status and result
        stmt = select(TaskQueue).where(TaskQueue.id == task_id)
        db_result = await async_session.execute(stmt)
        task = db_result.scalar_one()

        assert task.status == "completed"
        assert task.completed_at is not None
        assert json.loads(task.result_json) == result

    async def test_complete_task_raises_not_found_for_invalid_id(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that completing a non-existent task raises NotFoundError."""
        manager = TaskManager(session_factory=session_factory)

        with pytest.raises(NotFoundError) as exc_info:
            await manager.complete_task(
                task_id="invalid-task-id",
                result={"status": "success"},
            )

        assert "Task not found" in str(exc_info.value)


@pytest.mark.asyncio
class TestTaskManagerFail:
    """Test task failure functionality."""

    async def test_fail_task_increments_attempts(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that failing a task stores the error message."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
            max_attempts=3,
        )

        await manager.claim_task(worker_id="worker-1")

        # Fail the task
        error_msg = "Network timeout error"
        await manager.fail_task(task_id=task_id, error=error_msg)

        # Verify error was stored and attempts incremented
        stmt = select(TaskQueue).where(TaskQueue.id == task_id)
        result = await async_session.execute(stmt)
        task = result.scalar_one()

        assert task.error_message == error_msg
        assert task.attempts == 1

    async def test_fail_task_returns_to_pending_if_retries_remain(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that task returns to pending if retries are available."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
            max_attempts=3,
        )

        await manager.claim_task(worker_id="worker-1")

        # Fail the task (attempt 1 of 3)
        await manager.fail_task(task_id=task_id, error="Temporary error")

        # Verify task returned to pending
        stmt = select(TaskQueue).where(TaskQueue.id == task_id)
        result = await async_session.execute(stmt)
        task = result.scalar_one()

        assert task.status == "pending"
        assert task.worker_id is None
        assert task.started_at is None
        assert task.attempts == 1

    async def test_fail_task_stays_failed_if_max_attempts_reached(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that task stays failed after max attempts."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
            max_attempts=2,
        )

        # First attempt
        await manager.claim_task(worker_id="worker-1")
        await manager.fail_task(task_id=task_id, error="Error 1")

        # Second attempt
        await manager.claim_task(worker_id="worker-1")
        await manager.fail_task(task_id=task_id, error="Error 2")

        # Verify task is permanently failed
        stmt = select(TaskQueue).where(TaskQueue.id == task_id)
        result = await async_session.execute(stmt)
        task = result.scalar_one()

        assert task.status == "failed"
        assert task.completed_at is not None
        assert task.attempts == 2

    async def test_fail_task_raises_not_found_for_invalid_id(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that failing a non-existent task raises NotFoundError."""
        manager = TaskManager(session_factory=session_factory)

        with pytest.raises(NotFoundError) as exc_info:
            await manager.fail_task(
                task_id="invalid-task-id",
                error="Some error",
            )

        assert "Task not found" in str(exc_info.value)


@pytest.mark.asyncio
class TestTaskManagerCancel:
    """Test task cancellation functionality."""

    async def test_cancel_task_only_pending(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
        async_session: AsyncSession,
    ) -> None:
        """Test that only pending tasks can be cancelled."""
        manager = TaskManager(session_factory=session_factory)

        # Create and cancel pending task
        pending_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
        )

        result = await manager.cancel_task(task_id=pending_id)
        assert result is True

        # Verify task is cancelled
        stmt = select(TaskQueue).where(TaskQueue.id == pending_id)
        db_result = await async_session.execute(stmt)
        task = db_result.scalar_one()

        assert task.status == "cancelled"
        assert task.completed_at is not None

    async def test_cancel_running_task_returns_false(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Test that running tasks cannot be cancelled."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
        )

        # Claim the task (makes it running)
        await manager.claim_task(worker_id="worker-1")

        # Try to cancel - should return False
        result = await manager.cancel_task(task_id=task_id)
        assert result is False

    async def test_cancel_nonexistent_task_returns_false(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that cancelling a non-existent task returns False."""
        manager = TaskManager(session_factory=session_factory)

        result = await manager.cancel_task(task_id="invalid-task-id")
        assert result is False


@pytest.mark.asyncio
class TestTaskManagerGetStatus:
    """Test task status retrieval functionality."""

    async def test_get_task_status(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Test retrieving task status and details."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
            priority=5,
        )

        # Get task status
        status = await manager.get_task_status(task_id=task_id)

        assert status is not None
        assert status["id"] == task_id
        assert status["task_type"] == "backtest"
        assert status["status"] == "pending"
        assert status["priority"] == 5
        assert status["attempts"] == 0
        assert status["payload"] == sample_task_payload

    async def test_get_task_status_returns_none_for_invalid_id(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that getting status for non-existent task returns None."""
        manager = TaskManager(session_factory=session_factory)

        status = await manager.get_task_status(task_id="invalid-task-id")
        assert status is None

    async def test_get_task_status_includes_result_when_completed(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Test that completed task status includes result."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
        )

        await manager.claim_task(worker_id="worker-1")

        result = {"status": "success", "total_return": 0.25}
        await manager.complete_task(task_id=task_id, result=result)

        # Get task status
        status = await manager.get_task_status(task_id=task_id)

        assert status["status"] == "completed"
        assert status["result"] == result

    async def test_get_task_status_includes_error_when_failed(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Test that failed task status includes error message."""
        manager = TaskManager(session_factory=session_factory)

        task_id = await manager.enqueue(
            task_type="backtest",
            payload=sample_task_payload,
            max_attempts=1,
        )

        await manager.claim_task(worker_id="worker-1")

        error_msg = "Data fetch failed"
        await manager.fail_task(task_id=task_id, error=error_msg)

        # Get task status
        status = await manager.get_task_status(task_id=task_id)

        assert status["status"] == "failed"
        assert status["error_message"] == error_msg


@pytest.mark.asyncio
class TestTaskManagerHelperMethods:
    """Test helper methods for task queue management."""

    async def test_get_pending_count(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Test getting count of pending tasks."""
        manager = TaskManager(session_factory=session_factory)

        # Initially no pending tasks
        count = await manager.get_pending_count()
        assert count == 0

        # Enqueue some tasks
        await manager.enqueue(task_type="backtest", payload=sample_task_payload)
        await manager.enqueue(task_type="backtest", payload=sample_task_payload)
        await manager.enqueue(task_type="data_fetch", payload=sample_task_payload)

        # Should have 3 pending
        count = await manager.get_pending_count()
        assert count == 3

        # Claim one task
        await manager.claim_task(worker_id="worker-1")

        # Should have 2 pending
        count = await manager.get_pending_count()
        assert count == 2

    async def test_get_running_tasks(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Test getting list of running tasks."""
        manager = TaskManager(session_factory=session_factory)

        # Initially no running tasks
        running = await manager.get_running_tasks()
        assert len(running) == 0

        # Enqueue and claim some tasks
        await manager.enqueue(task_type="backtest", payload=sample_task_payload)
        await manager.enqueue(task_type="backtest", payload=sample_task_payload)

        await manager.claim_task(worker_id="worker-1")
        await manager.claim_task(worker_id="worker-2")

        # Should have 2 running
        running = await manager.get_running_tasks()
        assert len(running) == 2
        assert running[0]["worker_id"] in ["worker-1", "worker-2"]
        assert running[1]["worker_id"] in ["worker-1", "worker-2"]
