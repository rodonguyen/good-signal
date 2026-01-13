"""
API router aggregation module.

Collects and exposes all API routers for inclusion in the main application.
"""

from fastapi import APIRouter

from backend.routers.health import router as health_router
from backend.routers.backtest import router as backtest_router
from backend.routers.websocket import router as websocket_router
from backend.routers.risk import router as risk_router
from backend.routers.positions import router as positions_router

# Create the main API router
api_router = APIRouter()

# Include all sub-routers
api_router.include_router(health_router, tags=["health"])
api_router.include_router(backtest_router)
api_router.include_router(risk_router)
api_router.include_router(positions_router)

__all__ = [
    "api_router",
    "websocket_router",
]
