"""
SQLite-backed async task queue manager.

Provides atomic task operations with priority ordering,
worker assignment, and status tracking.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, update, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.core.exceptions import NotFoundError, DatabaseError
from backend.infrastructure.database.models import TaskQueue


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat()


def _generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


class TaskManager:
    """
    SQLite-backed async task queue manager.

    Provides atomic operations for enqueuing, claiming, and completing tasks.
    Tasks are processed in priority order (higher first), then by scheduled time.

    Attributes:
        max_workers: Maximum number of concurrent workers allowed.
        _session_factory: SQLAlchemy async session factory.

    Example:
        >>> from backend.infrastructure.database.connection import AsyncSessionLocal
        >>> task_manager = TaskManager(session_factory=AsyncSessionLocal, max_workers=2)
        >>> task_id = await task_manager.enqueue("backtest", {"config_id": "123"}, priority=1)
        >>> task = await task_manager.claim_task("worker-1")
        >>> await task_manager.complete_task(task_id, {"result": "success"})
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_workers: int = 2,
    ) -> None:
        """
        Initialize the TaskManager.

        Args:
            session_factory: SQLAlchemy async session factory.
            max_workers: Maximum number of concurrent workers.
        """
        self._session_factory = session_factory
        self.max_workers = max_workers

    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        priority: int = 0,
        max_attempts: int = 3,
        scheduled_at: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """
        Enqueue a new task for processing.

        Args:
            task_type: Type identifier for the task (e.g., "backtest", "data_fetch").
            payload: Task payload data to be processed.
            priority: Task priority (higher values processed first). Default 0.
            max_attempts: Maximum retry attempts before permanent failure. Default 3.
            scheduled_at: ISO timestamp to schedule task. Default is now.
            session: Optional existing session to use (for SQLite transaction sharing).

        Returns:
            str: Unique task identifier.

        Raises:
            DatabaseError: If task creation fails.
        """
        task_id = _generate_uuid()
        scheduled = scheduled_at or _utc_now()

        task = TaskQueue(
            id=task_id,
            task_type=task_type,
            status="pending",
            priority=priority,
            payload_json=json.dumps(payload),
            max_attempts=max_attempts,
            scheduled_at=scheduled,
            created_at=_utc_now(),
        )

        try:
            if session is not None:
                # Use provided session (shares transaction with caller)
                session.add(task)
                await session.flush()
                return task_id
            else:
                # Create new session
                async with self._session_factory() as new_session:
                    new_session.add(task)
                    await new_session.commit()
                    return task_id
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to enqueue task: {e}",
                error_code="TASK_ENQUEUE_FAILED",
                details={"task_type": task_type, "error": str(e)},
            )

    async def claim_task(self, worker_id: str) -> Optional[dict[str, Any]]:
        """
        Atomically claim the next pending task for processing.

        Claims the highest priority pending task that is due for processing.
        Uses optimistic locking for SQLite compatibility.

        Args:
            worker_id: Unique identifier for the claiming worker.

        Returns:
            Optional[dict]: Task data if claimed, None if no tasks available.
            Contains: id, task_type, payload, priority, attempts, max_attempts.

        Raises:
            DatabaseError: If claiming operation fails.
        """
        try:
            async with self._session_factory() as session:
                # Find the next pending task ordered by priority (desc) and scheduled_at (asc)
                stmt = (
                    select(TaskQueue)
                    .where(
                        and_(
                            TaskQueue.status == "pending",
                            TaskQueue.scheduled_at <= _utc_now(),
                        )
                    )
                    .order_by(
                        desc(TaskQueue.priority),
                        TaskQueue.scheduled_at,
                    )
                    .limit(1)
                )

                result = await session.execute(stmt)
                task = result.scalar_one_or_none()

                if task is None:
                    return None

                # Store original values before update (SQLAlchemy may update cached object)
                task_id = task.id
                task_type = task.task_type
                payload = json.loads(task.payload_json)
                priority = task.priority
                max_attempts = task.max_attempts
                new_attempts = task.attempts + 1

                # Use UPDATE with WHERE to atomically claim (optimistic locking)
                # Only update if status is still 'pending' (prevents race conditions)
                claim_stmt = (
                    update(TaskQueue)
                    .where(
                        and_(
                            TaskQueue.id == task_id,
                            TaskQueue.status == "pending",
                        )
                    )
                    .values(
                        status="running",
                        worker_id=worker_id,
                        started_at=_utc_now(),
                        attempts=new_attempts,
                    )
                    .returning(TaskQueue.id)
                )

                claim_result = await session.execute(claim_stmt)
                claimed_id = claim_result.scalar_one_or_none()

                if claimed_id is None:
                    # Another worker claimed this task, return None to try again
                    return None

                await session.commit()

                return {
                    "id": task_id,
                    "task_type": task_type,
                    "payload": payload,
                    "priority": priority,
                    "attempts": new_attempts,
                    "max_attempts": max_attempts,
                }
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to claim task: {e}",
                error_code="TASK_CLAIM_FAILED",
                details={"worker_id": worker_id, "error": str(e)},
            )

    async def complete_task(
        self,
        task_id: str,
        result: dict[str, Any],
    ) -> None:
        """
        Mark a task as completed with its result.

        Args:
            task_id: Unique task identifier.
            result: Task execution result data.

        Raises:
            NotFoundError: If task does not exist.
            DatabaseError: If update operation fails.
        """
        try:
            async with self._session_factory() as session:
                stmt = (
                    update(TaskQueue)
                    .where(TaskQueue.id == task_id)
                    .values(
                        status="completed",
                        result_json=json.dumps(result),
                        completed_at=_utc_now(),
                    )
                    .returning(TaskQueue.id)
                )

                result_row = await session.execute(stmt)
                updated = result_row.scalar_one_or_none()

                if updated is None:
                    raise NotFoundError(
                        message=f"Task not found: {task_id}",
                        error_code="TASK_NOT_FOUND",
                        details={"task_id": task_id},
                    )

                await session.commit()
        except NotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to complete task: {e}",
                error_code="TASK_COMPLETE_FAILED",
                details={"task_id": task_id, "error": str(e)},
            )

    async def fail_task(
        self,
        task_id: str,
        error: str,
    ) -> None:
        """
        Mark a task as failed and increment attempt counter.

        If attempts < max_attempts, the task will be returned to pending status
        for retry. Otherwise, it will be marked as permanently failed.

        Args:
            task_id: Unique task identifier.
            error: Error message describing the failure.

        Raises:
            NotFoundError: If task does not exist.
            DatabaseError: If update operation fails.
        """
        try:
            async with self._session_factory() as session:
                # Get current task state
                stmt = select(TaskQueue).where(TaskQueue.id == task_id)
                result = await session.execute(stmt)
                task = result.scalar_one_or_none()

                if task is None:
                    raise NotFoundError(
                        message=f"Task not found: {task_id}",
                        error_code="TASK_NOT_FOUND",
                        details={"task_id": task_id},
                    )

                # Determine if we should retry or permanently fail
                if task.attempts >= task.max_attempts:
                    task.status = "failed"
                    task.completed_at = _utc_now()
                else:
                    # Return to pending for retry
                    task.status = "pending"
                    task.worker_id = None
                    task.started_at = None

                task.error_message = error

                await session.commit()
        except NotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to mark task as failed: {e}",
                error_code="TASK_FAIL_UPDATE_FAILED",
                details={"task_id": task_id, "error": str(e)},
            )

    async def get_task_status(self, task_id: str) -> Optional[dict[str, Any]]:
        """
        Get the current status and details of a task.

        Args:
            task_id: Unique task identifier.

        Returns:
            Optional[dict]: Task status data if found, None otherwise.
            Contains: id, task_type, status, priority, attempts, max_attempts,
                     worker_id, result, error_message, timestamps.
        """
        try:
            async with self._session_factory() as session:
                stmt = select(TaskQueue).where(TaskQueue.id == task_id)
                result = await session.execute(stmt)
                task = result.scalar_one_or_none()

                if task is None:
                    return None

                return {
                    "id": task.id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "priority": task.priority,
                    "attempts": task.attempts,
                    "max_attempts": task.max_attempts,
                    "worker_id": task.worker_id,
                    "payload": json.loads(task.payload_json) if task.payload_json else None,
                    "result": json.loads(task.result_json) if task.result_json else None,
                    "error_message": task.error_message,
                    "created_at": task.created_at,
                    "scheduled_at": task.scheduled_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                }
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get task status: {e}",
                error_code="TASK_STATUS_FAILED",
                details={"task_id": task_id, "error": str(e)},
            )

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.

        Only pending tasks can be cancelled. Running tasks must complete
        or fail naturally.

        Args:
            task_id: Unique task identifier.

        Returns:
            bool: True if task was cancelled, False if not found or not cancellable.

        Raises:
            DatabaseError: If cancellation operation fails.
        """
        try:
            async with self._session_factory() as session:
                stmt = (
                    update(TaskQueue)
                    .where(
                        and_(
                            TaskQueue.id == task_id,
                            TaskQueue.status == "pending",
                        )
                    )
                    .values(
                        status="cancelled",
                        completed_at=_utc_now(),
                    )
                    .returning(TaskQueue.id)
                )

                result = await session.execute(stmt)
                cancelled = result.scalar_one_or_none()

                await session.commit()

                return cancelled is not None
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to cancel task: {e}",
                error_code="TASK_CANCEL_FAILED",
                details={"task_id": task_id, "error": str(e)},
            )

    async def get_pending_count(self) -> int:
        """
        Get the count of pending tasks.

        Returns:
            int: Number of pending tasks in the queue.
        """
        try:
            async with self._session_factory() as session:
                from sqlalchemy import func

                stmt = select(func.count()).select_from(TaskQueue).where(
                    TaskQueue.status == "pending"
                )
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get pending count: {e}",
                error_code="TASK_COUNT_FAILED",
                details={"error": str(e)},
            )

    async def get_running_tasks(self) -> list[dict[str, Any]]:
        """
        Get all currently running tasks.

        Returns:
            list[dict]: List of running task data.
        """
        try:
            async with self._session_factory() as session:
                stmt = (
                    select(TaskQueue)
                    .where(TaskQueue.status == "running")
                    .order_by(TaskQueue.started_at)
                )
                result = await session.execute(stmt)
                tasks = result.scalars().all()

                return [
                    {
                        "id": task.id,
                        "task_type": task.task_type,
                        "worker_id": task.worker_id,
                        "started_at": task.started_at,
                        "attempts": task.attempts,
                    }
                    for task in tasks
                ]
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get running tasks: {e}",
                error_code="TASK_LIST_FAILED",
                details={"error": str(e)},
            )

    async def cleanup_stale_tasks(
        self,
        stale_threshold_minutes: int = 30,
    ) -> int:
        """
        Reset stale running tasks back to pending.

        Tasks that have been running longer than the threshold are considered
        stale (worker may have crashed) and are returned to pending status.

        Args:
            stale_threshold_minutes: Minutes after which a running task is stale.

        Returns:
            int: Number of tasks reset.
        """
        from datetime import timedelta

        try:
            cutoff = (
                datetime.utcnow() - timedelta(minutes=stale_threshold_minutes)
            ).isoformat()

            async with self._session_factory() as session:
                stmt = (
                    update(TaskQueue)
                    .where(
                        and_(
                            TaskQueue.status == "running",
                            TaskQueue.started_at < cutoff,
                        )
                    )
                    .values(
                        status="pending",
                        worker_id=None,
                        started_at=None,
                        error_message="Task reset due to stale worker",
                    )
                    .returning(TaskQueue.id)
                )

                result = await session.execute(stmt)
                reset_ids = result.scalars().all()

                await session.commit()

                return len(reset_ids)
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to cleanup stale tasks: {e}",
                error_code="TASK_CLEANUP_FAILED",
                details={"error": str(e)},
            )
