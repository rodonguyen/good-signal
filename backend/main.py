"""
FastAPI application entry point for the Good Signal trading application.

This module configures and creates the FastAPI application instance
with all necessary middleware, routers, and lifecycle handlers.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.core.exceptions import GoodSignalError, NotFoundError, ValidationError
from backend.core.logging import get_logger, setup_logging
from backend.dependencies import db_manager, init_db
from backend.routers import api_router
from backend.routers.websocket import router as websocket_router, manager as ws_manager

logger = get_logger(__name__)


# Global worker pool reference for graceful shutdown
_worker_pool: Optional["WorkerPool"] = None


async def start_background_workers() -> None:
    """
    Start background worker pool for task processing.

    Initializes the worker pool with backtest task handler
    and starts processing tasks from the queue.
    """
    global _worker_pool

    from backend.infrastructure.queue.task_manager import TaskManager
    from backend.infrastructure.queue.worker import WorkerPool
    from backend.services.backtest_service import create_backtest_handler

    settings = get_settings()

    # Use the same session factory as the API for SQLite compatibility
    if db_manager._session_factory is None:
        from backend.infrastructure.database.connection import AsyncSessionLocal
        session_factory = AsyncSessionLocal
    else:
        session_factory = db_manager._session_factory

    # Create task manager
    task_manager = TaskManager(
        session_factory=session_factory,
        max_workers=settings.WORKER_COUNT if hasattr(settings, "WORKER_COUNT") else 2,
    )

    # Create worker pool
    _worker_pool = WorkerPool(
        task_manager=task_manager,
        num_workers=settings.WORKER_COUNT if hasattr(settings, "WORKER_COUNT") else 2,
        max_tasks_per_worker=1,
    )

    # Register task handlers
    _worker_pool.register_handler("backtest", create_backtest_handler)

    # Start the worker pool
    await _worker_pool.start()

    logger.info(
        "Background workers started",
        num_workers=_worker_pool.worker_count,
    )


async def stop_background_workers() -> None:
    """
    Stop background worker pool gracefully.

    Waits for active tasks to complete before shutting down.
    """
    global _worker_pool

    if _worker_pool is not None:
        logger.info("Stopping background workers...")
        await _worker_pool.stop(timeout=30.0)
        _worker_pool = None
        logger.info("Background workers stopped")


async def close_websocket_connections() -> None:
    """
    Close all WebSocket connections gracefully.
    """
    if ws_manager.connection_count > 0:
        logger.info(
            "Closing WebSocket connections",
            count=ws_manager.connection_count,
        )
        await ws_manager.close_all()
        logger.info("WebSocket connections closed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager for startup and shutdown events.

    Handles:
    - Database connection initialization
    - Logging setup
    - Background worker startup
    - WebSocket connection cleanup
    - Resource cleanup on shutdown
    """
    settings = get_settings()

    # Setup logging
    setup_logging(
        log_level=settings.LOG_LEVEL,
        json_format=settings.is_production,
    )

    logger.info(
        "Starting Good Signal application",
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        log_level=settings.LOG_LEVEL,
    )

    # Initialize database
    try:
        await db_manager.initialize(settings)
        # Also initialize existing infrastructure database (creates tables)
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise

    # Start background workers (only if not in test mode)
    if not getattr(settings, "TESTING", False):
        try:
            await start_background_workers()
        except Exception as e:
            logger.error("Failed to start background workers", error=str(e))
            # Continue without workers - not critical for API to function

    yield

    # Shutdown sequence
    logger.info("Shutting down Good Signal application")

    # Stop background workers
    try:
        await stop_background_workers()
    except Exception as e:
        logger.error("Error stopping background workers", error=str(e))

    # Close WebSocket connections
    try:
        await close_websocket_connections()
    except Exception as e:
        logger.error("Error closing WebSocket connections", error=str(e))

    # Close database connections
    await db_manager.close()
    logger.info("Application shutdown complete")


def create_application(settings: Any = None) -> FastAPI:
    """
    Application factory function.

    Creates and configures the FastAPI application with all
    middleware, routers, and exception handlers.

    Args:
        settings: Optional settings object. If not provided, uses get_settings().

    Returns:
        Configured FastAPI application instance
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="Good Signal Trading API",
        description=(
            "High-performance trading signal generation and backtesting API. "
            "Provides endpoints for strategy management, backtesting, "
            "and real-time signal generation."
        ),
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None,
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    # Include routers
    app.include_router(api_router)

    # Include WebSocket router
    app.include_router(websocket_router, tags=["websocket"])

    return app


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers for the application."""

    @app.exception_handler(GoodSignalError)
    async def good_signal_error_handler(
        request: Request,
        exc: GoodSignalError,
    ) -> JSONResponse:
        """Handle custom application errors."""
        logger.warning(
            "Application error",
            error_code=exc.error_code,
            message=exc.message,
            path=request.url.path,
        )

        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if isinstance(exc, NotFoundError):
            status_code = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, ValidationError):
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

        return JSONResponse(
            status_code=status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.exception(
            "Unhandled exception",
            error=str(exc),
            path=request.url.path,
        )

        settings = get_settings()

        # In production, don't expose internal error details
        if settings.is_production:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "details": {},
                },
            )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_ERROR",
                "message": str(exc),
                "details": {"type": type(exc).__name__},
            },
        )


# Alias for backwards compatibility with tests
create_app = create_application

# Create application instance
app = create_application()


@app.middleware("http")
async def add_request_metadata(request: Request, call_next: Any) -> Any:
    """Add request ID and timing metadata to responses."""
    import time
    import uuid

    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()

    # Add request ID to request state for logging
    request.state.request_id = request_id

    response = await call_next(request)

    # Calculate processing time
    process_time = time.perf_counter() - start_time

    # Add headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.4f}"

    return response
