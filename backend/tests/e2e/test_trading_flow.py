"""
End-to-end tests for live trading flow.

Tests the complete trading lifecycle including:
- Risk management (kill switch, limits)
- Position management API responses
- Health endpoint
"""

import pytest
from httpx import AsyncClient


class TestRiskManagementFlow:
    """Test risk management API endpoints."""

    @pytest.mark.asyncio
    async def test_get_risk_state(self, test_client: AsyncClient) -> None:
        """Test getting risk state."""
        response = await test_client.get("/api/risk")
        assert response.status_code == 200

        data = response.json()
        assert "kill_switch_active" in data
        assert "daily_pnl" in data
        assert "total_open_positions" in data
        assert "total_exposure" in data

    @pytest.mark.asyncio
    async def test_activate_and_deactivate_kill_switch(
        self, test_client: AsyncClient
    ) -> None:
        """Test activating and deactivating the kill switch."""
        # First ensure it's deactivated
        await test_client.delete("/api/risk/kill-switch")

        # Verify initial state
        response = await test_client.get("/api/risk")
        assert response.status_code == 200
        initial_state = response.json()

        # Activate kill switch
        response = await test_client.post(
            "/api/risk/kill-switch",
            json={"reason": "Manual activation for testing"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Manual activation for testing" in data["message"]

        # Verify state changed via GET
        response = await test_client.get("/api/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["kill_switch_active"] is True
        assert data["kill_switch_reason"] == "Manual activation for testing"

        # Deactivate kill switch
        response = await test_client.delete("/api/risk/kill-switch")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "deactivated" in data["message"].lower()

        # Verify state changed via GET
        response = await test_client.get("/api/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["kill_switch_active"] is False

    @pytest.mark.asyncio
    async def test_update_risk_limits(self, test_client: AsyncClient) -> None:
        """Test updating risk limits."""
        response = await test_client.put(
            "/api/risk/limits",
            json={
                "max_daily_loss": 1000.0,
                "max_positions": 5,
                "max_exposure": 50000.0,
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["max_daily_loss"] == 1000.0
        assert data["max_positions"] == 5
        assert data["max_exposure"] == 50000.0
        assert "within_limits" in data

    @pytest.mark.asyncio
    async def test_update_risk_limits_validation(
        self, test_client: AsyncClient
    ) -> None:
        """Test that at least one limit must be provided."""
        response = await test_client.put(
            "/api/risk/limits",
            json={},
        )
        # Should fail validation - need at least one limit
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_daily_counters(self, test_client: AsyncClient) -> None:
        """Test resetting daily counters."""
        response = await test_client.post("/api/risk/reset-daily")
        assert response.status_code == 200

        data = response.json()
        assert "message" in data
        assert "reset" in data["message"].lower()

        # Verify counters reset via GET
        response = await test_client.get("/api/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["daily_pnl"] == 0.0
        assert data["daily_trades"] == 0


class TestPositionManagementFlow:
    """Test position management API endpoints."""

    @pytest.mark.asyncio
    async def test_list_positions(self, test_client: AsyncClient) -> None:
        """Test listing positions returns proper structure."""
        response = await test_client.get("/api/positions")
        assert response.status_code == 200

        data = response.json()
        assert "positions" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data
        assert isinstance(data["positions"], list)

    @pytest.mark.asyncio
    async def test_get_position_not_found(self, test_client: AsyncClient) -> None:
        """Test getting a non-existent position."""
        response = await test_client.get("/api/positions/non-existent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_filter_positions_by_status_parameter(
        self, test_client: AsyncClient
    ) -> None:
        """Test filtering positions by status parameter."""
        # Test open status
        response = await test_client.get("/api/positions?status=open")
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data

        # Test closed status
        response = await test_client.get("/api/positions?status=closed")
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data

    @pytest.mark.asyncio
    async def test_filter_positions_by_symbol_parameter(
        self, test_client: AsyncClient
    ) -> None:
        """Test filtering positions by symbol parameter."""
        response = await test_client.get("/api/positions?symbol=BTCUSDT")
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data

    @pytest.mark.asyncio
    async def test_position_pagination(self, test_client: AsyncClient) -> None:
        """Test position pagination parameters."""
        response = await test_client.get("/api/positions?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["skip"] == 0
        assert data["limit"] == 10


class TestHealthCheck:
    """Test health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, test_client: AsyncClient) -> None:
        """Test that health endpoint returns OK."""
        response = await test_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "ok"]

    @pytest.mark.asyncio
    async def test_health_response_structure(self, test_client: AsyncClient) -> None:
        """Test health endpoint response structure."""
        response = await test_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "timestamp" in data


class TestBacktestApiIntegration:
    """Test backtest API endpoints."""

    @pytest.mark.asyncio
    async def test_list_backtests(self, test_client: AsyncClient) -> None:
        """Test listing backtests returns proper structure."""
        response = await test_client.get("/api/backtests")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        # API returns "pages" not "total_pages"
        assert "pages" in data or "total_pages" in data

    @pytest.mark.asyncio
    async def test_get_backtest_not_found(self, test_client: AsyncClient) -> None:
        """Test getting a non-existent backtest."""
        response = await test_client.get("/api/backtests/non-existent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_backtest_validation(
        self, test_client: AsyncClient
    ) -> None:
        """Test backtest creation validates required fields."""
        # Missing required fields
        response = await test_client.post(
            "/api/backtests",
            json={"name": "Test"},
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_backtest_with_valid_data(
        self, test_client: AsyncClient
    ) -> None:
        """Test creating a backtest with valid data."""
        response = await test_client.post(
            "/api/backtests",
            json={
                "name": "E2E Test Backtest",
                "symbols": ["BTCUSDT"],
                "strategies": [
                    {
                        "type": "supertrend",
                        "enabled": True,
                        "signal_timeframe": "4h",
                        "params": {"atr_period": 10, "atr_multiplier": 3.0},
                    }
                ],
                "filters": [],
                "fee_rate": 0.0015,
                "initial_equity": 10000.0,
                "risk_per_trade": 0.02,
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert "id" in data
        assert data["name"] == "E2E Test Backtest"
        assert data["status"] == "pending"


