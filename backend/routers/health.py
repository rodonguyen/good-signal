"""
Health check endpoints for monitoring and load balancer integration.

Provides endpoints for:
- Basic liveness checks
- Detailed readiness checks with dependency status
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from backend.config import Settings, get_settings
from backend.dependencies import db_manager

router = APIRouter()


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str = Field(description="Overall health status")
    version: str = Field(description="Application version")
    timestamp: str = Field(description="Current server timestamp (ISO 8601)")


class DetailedHealthResponse(HealthResponse):
    """Response model for detailed health check with dependency status."""

    dependencies: dict[str, Any] = Field(
        description="Status of application dependencies"
    )


@router.get(
    "/api/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Basic health check endpoint for load balancers and monitoring.",
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "version": "1.0.0",
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        }
    },
)
async def health_check(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """
    Basic health check endpoint.

    Returns a simple status indicating the service is running.
    This endpoint is designed for load balancer health checks
    and should return quickly without checking dependencies.
    """
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/api/health/ready",
    response_model=DetailedHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness Check",
    description="Detailed health check including dependency status.",
    responses={
        200: {
            "description": "Service is ready to accept requests",
        },
        503: {
            "description": "Service is not ready (dependency failure)",
        },
    },
)
async def readiness_check(
    settings: Settings = Depends(get_settings),
) -> DetailedHealthResponse:
    """
    Detailed readiness check endpoint.

    Verifies all dependencies are available and the service
    is ready to handle requests. Use this for Kubernetes
    readiness probes.
    """
    dependencies: dict[str, Any] = {
        "database": {
            "status": "ok" if db_manager.is_initialized else "unavailable",
            "type": "sqlite" if settings.is_sqlite else "postgresql",
        },
    }

    # Determine overall status
    all_healthy = all(
        dep.get("status") == "ok"
        for dep in dependencies.values()
        if isinstance(dep, dict)
    )

    return DetailedHealthResponse(
        status="ok" if all_healthy else "degraded",
        version=settings.APP_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        dependencies=dependencies,
    )


@router.get(
    "/api/health/live",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Liveness Check",
    description="Minimal liveness check for Kubernetes liveness probes.",
)
async def liveness_check() -> None:
    """
    Minimal liveness check endpoint.

    Returns 204 No Content if the service is alive.
    This endpoint should never fail unless the process is dead.
    Use this for Kubernetes liveness probes.
    """
    return None
