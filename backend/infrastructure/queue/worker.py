"""
Background worker for processing tasks from the queue.

Provides concurrent task processing with graceful shutdown,
exponential backoff on errors, and handler registration.
"""

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable, Optional

from .task_manager import TaskManager


logger = logging.getLogger(__name__)


# Type alias for task handlers
TaskHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class BackgroundWorker:
    """
    Background worker for processing tasks from the queue.

    Supports concurrent task processing, exponential backoff on errors,
    and graceful shutdown with task completion.

    Attributes:
        worker_id: Unique identifier for this worker instance.
        task_manager: TaskManager instance for queue operations.
        handlers: Registered task type handlers.

    Example:
        >>> worker = BackgroundWorker("worker-1", task_manager)
        >>> worker.register_handler("backtest", handle_backtest)
        >>> await worker.start()  # Runs until stop() is called
    """

    # Exponential backoff configuration
    BASE_BACKOFF_SECONDS: float = 1.0
    MAX_BACKOFF_SECONDS: float = 60.0
    BACKOFF_MULTIPLIER: float = 2.0

    # Polling configuration
    POLL_INTERVAL_SECONDS: float = 1.0
    IDLE_POLL_INTERVAL_SECONDS: float = 5.0

    def __init__(
        self,
        worker_id: str,
        task_manager: TaskManager,
        handlers: Optional[dict[str, TaskHandler]] = None,
        max_concurrent_tasks: int = 1,
    ) -> None:
        """
        Initialize the BackgroundWorker.

        Args:
            worker_id: Unique identifier for this worker.
            task_manager: TaskManager instance for queue operations.
            handlers: Optional dict mapping task types to handler functions.
            max_concurrent_tasks: Maximum tasks to process concurrently.
        """
        self.worker_id = worker_id
        self.task_manager = task_manager
        self._handlers: dict[str, TaskHandler] = handlers or {}
        self._max_concurrent = max_concurrent_tasks

        self._running = False
        self._shutdown_event = asyncio.Event()
        self._active_tasks: set[asyncio.Task[None]] = set()
        self._consecutive_errors = 0
        self._semaphore: Optional[asyncio.Semaphore] = None

    @classmethod
    def create_with_id(
        cls,
        task_manager: TaskManager,
        handlers: Optional[dict[str, TaskHandler]] = None,
        max_concurrent_tasks: int = 1,
    ) -> "BackgroundWorker":
        """
        Factory method to create a worker with auto-generated ID.

        Args:
            task_manager: TaskManager instance for queue operations.
            handlers: Optional dict mapping task types to handler functions.
            max_concurrent_tasks: Maximum tasks to process concurrently.

        Returns:
            BackgroundWorker: New worker instance with unique ID.
        """
        worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        return cls(worker_id, task_manager, handlers, max_concurrent_tasks)

    def register_handler(
        self,
        task_type: str,
        handler: TaskHandler,
    ) -> None:
        """
        Register a handler function for a task type.

        Args:
            task_type: Task type identifier to handle.
            handler: Async function that processes the task payload.
                     Should accept dict payload and return dict result.

        Raises:
            ValueError: If handler is already registered for task_type.
        """
        if task_type in self._handlers:
            raise ValueError(
                f"Handler already registered for task type: {task_type}"
            )
        self._handlers[task_type] = handler
        logger.info(
            "Registered handler for task type '%s' on worker '%s'",
            task_type,
            self.worker_id,
        )

    def unregister_handler(self, task_type: str) -> bool:
        """
        Unregister a handler for a task type.

        Args:
            task_type: Task type identifier to unregister.

        Returns:
            bool: True if handler was removed, False if not found.
        """
        if task_type in self._handlers:
            del self._handlers[task_type]
            logger.info(
                "Unregistered handler for task type '%s' on worker '%s'",
                task_type,
                self.worker_id,
            )
            return True
        return False

    @property
    def is_running(self) -> bool:
        """Check if the worker is currently running."""
        return self._running

    @property
    def active_task_count(self) -> int:
        """Get the number of currently active tasks."""
        return len(self._active_tasks)

    async def start(self) -> None:
        """
        Start the worker loop.

        The worker will continuously poll for and process tasks until
        stop() is called. Uses exponential backoff on consecutive errors.

        This method blocks until the worker is stopped.
        """
        if self._running:
            logger.warning(
                "Worker '%s' is already running",
                self.worker_id,
            )
            return

        self._running = True
        self._shutdown_event.clear()
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

        logger.info(
            "Starting worker '%s' with max_concurrent=%d",
            self.worker_id,
            self._max_concurrent,
        )

        try:
            await self._run_loop()
        finally:
            self._running = False
            logger.info("Worker '%s' stopped", self.worker_id)

    async def stop(self, timeout: float = 30.0) -> None:
        """
        Gracefully stop the worker.

        Signals the worker to stop accepting new tasks and waits for
        currently active tasks to complete.

        Args:
            timeout: Maximum seconds to wait for active tasks to complete.
        """
        if not self._running:
            logger.warning(
                "Worker '%s' is not running",
                self.worker_id,
            )
            return

        logger.info(
            "Stopping worker '%s' (waiting for %d active tasks)",
            self.worker_id,
            len(self._active_tasks),
        )

        # Signal the main loop to stop
        self._shutdown_event.set()

        # Wait for active tasks to complete
        if self._active_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_tasks, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Timeout waiting for tasks on worker '%s', "
                    "cancelling %d remaining tasks",
                    self.worker_id,
                    len(self._active_tasks),
                )
                for task in self._active_tasks:
                    task.cancel()

    async def _run_loop(self) -> None:
        """Main worker loop that polls for and processes tasks."""
        while not self._shutdown_event.is_set():
            try:
                # Try to claim a task if we have capacity
                if self._semaphore is not None:
                    can_acquire = self._semaphore.locked() is False

                    if can_acquire:
                        task_data = await self.task_manager.claim_task(
                            self.worker_id
                        )

                        if task_data is not None:
                            # Reset error counter on successful claim
                            self._consecutive_errors = 0

                            # Start processing task concurrently
                            asyncio_task = asyncio.create_task(
                                self._process_task(task_data)
                            )
                            self._active_tasks.add(asyncio_task)
                            asyncio_task.add_done_callback(
                                self._active_tasks.discard
                            )

                            # Short poll interval when tasks are available
                            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)
                            continue

                # No tasks available or at capacity - longer poll interval
                await asyncio.sleep(self.IDLE_POLL_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info(
                    "Worker '%s' loop cancelled",
                    self.worker_id,
                )
                break
            except Exception as e:
                self._consecutive_errors += 1
                backoff = self._calculate_backoff()

                logger.error(
                    "Error in worker '%s' loop (attempt %d, backoff %.1fs): %s",
                    self.worker_id,
                    self._consecutive_errors,
                    backoff,
                    e,
                    exc_info=True,
                )

                await asyncio.sleep(backoff)

    async def _process_task(self, task: dict[str, Any]) -> None:
        """
        Process a single task.

        Acquires semaphore, executes the appropriate handler,
        and marks the task as completed or failed.

        Args:
            task: Task data from the queue.
        """
        task_id = task["id"]
        task_type = task["task_type"]
        payload = task["payload"]

        if self._semaphore is None:
            logger.error("Semaphore not initialized for worker '%s'", self.worker_id)
            return

        async with self._semaphore:
            logger.info(
                "Worker '%s' processing task '%s' (type=%s, attempt=%d/%d)",
                self.worker_id,
                task_id,
                task_type,
                task["attempts"],
                task["max_attempts"],
            )

            handler = self._handlers.get(task_type)

            if handler is None:
                error_msg = f"No handler registered for task type: {task_type}"
                logger.error(error_msg)
                await self.task_manager.fail_task(task_id, error_msg)
                return

            try:
                # Execute the handler
                result = await handler(payload)

                # Mark task as completed
                await self.task_manager.complete_task(task_id, result)

                logger.info(
                    "Worker '%s' completed task '%s'",
                    self.worker_id,
                    task_id,
                )

            except asyncio.CancelledError:
                # Task was cancelled during shutdown
                error_msg = "Task cancelled due to worker shutdown"
                logger.warning(
                    "Worker '%s' task '%s' cancelled",
                    self.worker_id,
                    task_id,
                )
                await self.task_manager.fail_task(task_id, error_msg)
                raise

            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.error(
                    "Worker '%s' task '%s' failed: %s",
                    self.worker_id,
                    task_id,
                    error_msg,
                    exc_info=True,
                )
                await self.task_manager.fail_task(task_id, error_msg)

    def _calculate_backoff(self) -> float:
        """
        Calculate exponential backoff duration.

        Returns:
            float: Seconds to wait before next retry.
        """
        backoff = self.BASE_BACKOFF_SECONDS * (
            self.BACKOFF_MULTIPLIER ** (self._consecutive_errors - 1)
        )
        return min(backoff, self.MAX_BACKOFF_SECONDS)


class WorkerPool:
    """
    Pool of background workers for distributed task processing.

    Manages multiple workers with coordinated startup and shutdown.

    Example:
        >>> pool = WorkerPool(task_manager, num_workers=4)
        >>> pool.register_handler("backtest", handle_backtest)
        >>> await pool.start()
        >>> # ... later ...
        >>> await pool.stop()
    """

    def __init__(
        self,
        task_manager: TaskManager,
        num_workers: int = 2,
        max_tasks_per_worker: int = 1,
    ) -> None:
        """
        Initialize the WorkerPool.

        Args:
            task_manager: TaskManager instance for queue operations.
            num_workers: Number of workers to create.
            max_tasks_per_worker: Maximum concurrent tasks per worker.
        """
        self.task_manager = task_manager
        self.num_workers = num_workers
        self.max_tasks_per_worker = max_tasks_per_worker

        self._workers: list[BackgroundWorker] = []
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._handlers: dict[str, TaskHandler] = {}

    def register_handler(
        self,
        task_type: str,
        handler: TaskHandler,
    ) -> None:
        """
        Register a handler for all workers in the pool.

        Args:
            task_type: Task type identifier to handle.
            handler: Async function that processes the task payload.
        """
        self._handlers[task_type] = handler

        # Register on existing workers
        for worker in self._workers:
            if task_type not in worker._handlers:
                worker.register_handler(task_type, handler)

    async def start(self) -> None:
        """
        Start all workers in the pool.

        Creates and starts the configured number of workers.
        """
        logger.info("Starting worker pool with %d workers", self.num_workers)

        for i in range(self.num_workers):
            worker = BackgroundWorker.create_with_id(
                task_manager=self.task_manager,
                handlers=self._handlers.copy(),
                max_concurrent_tasks=self.max_tasks_per_worker,
            )
            self._workers.append(worker)

            task = asyncio.create_task(worker.start())
            self._worker_tasks.append(task)

        logger.info(
            "Worker pool started: %s",
            [w.worker_id for w in self._workers],
        )

    async def stop(self, timeout: float = 30.0) -> None:
        """
        Stop all workers in the pool.

        Args:
            timeout: Maximum seconds to wait for workers to stop.
        """
        logger.info("Stopping worker pool")

        # Signal all workers to stop
        stop_tasks = [
            asyncio.create_task(worker.stop(timeout=timeout))
            for worker in self._workers
        ]

        # Wait for all stops to complete
        await asyncio.gather(*stop_tasks, return_exceptions=True)

        # Cancel any remaining worker tasks
        for task in self._worker_tasks:
            if not task.done():
                task.cancel()

        self._workers.clear()
        self._worker_tasks.clear()

        logger.info("Worker pool stopped")

    @property
    def active_task_count(self) -> int:
        """Get total active tasks across all workers."""
        return sum(w.active_task_count for w in self._workers)

    @property
    def worker_count(self) -> int:
        """Get number of workers in the pool."""
        return len(self._workers)
