"""
Integration tests for health check endpoints.

Tests verify the health, readiness, and liveness endpoints
that are used for monitoring and load balancer integration.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Test basic health check endpoint."""

    async def test_health_endpoint_returns_ok(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that health endpoint returns 200 OK status."""
        response = await test_client.get("/api/health")

        assert response.status_code == 200

    async def test_health_endpoint_returns_version(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that health endpoint returns application version."""
        response = await test_client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    async def test_health_endpoint_returns_status(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that health endpoint returns status field."""
        response = await test_client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert data["status"] == "ok"

    async def test_health_endpoint_returns_timestamp(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that health endpoint returns timestamp in ISO format."""
        response = await test_client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)
        # Verify it's a valid ISO timestamp format
        from datetime import datetime
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

    async def test_health_endpoint_content_type(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that health endpoint returns JSON content type."""
        response = await test_client.get("/api/health")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    async def test_health_endpoint_response_structure(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test complete response structure of health endpoint."""
        response = await test_client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present
        assert "status" in data
        assert "version" in data
        assert "timestamp" in data

        # Verify field types
        assert isinstance(data["status"], str)
        assert isinstance(data["version"], str)
        assert isinstance(data["timestamp"], str)


@pytest.mark.asyncio
class TestReadinessEndpoint:
    """Test readiness check endpoint with dependency status."""

    async def test_health_ready_endpoint_returns_ok(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that readiness endpoint returns 200 OK when ready."""
        response = await test_client.get("/api/health/ready")

        assert response.status_code == 200

    async def test_health_ready_endpoint_includes_dependencies(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that readiness endpoint includes dependency status."""
        response = await test_client.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()

        assert "dependencies" in data
        assert isinstance(data["dependencies"], dict)

    async def test_health_ready_endpoint_checks_database(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that readiness endpoint checks database status."""
        response = await test_client.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()

        assert "dependencies" in data
        assert "database" in data["dependencies"]
        assert "status" in data["dependencies"]["database"]
        assert "type" in data["dependencies"]["database"]

    async def test_health_ready_endpoint_database_status_ok(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that database status is 'ok' when initialized."""
        response = await test_client.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()

        db_status = data["dependencies"]["database"]["status"]
        assert db_status == "ok"

    async def test_health_ready_endpoint_overall_status(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that overall status reflects dependency health."""
        response = await test_client.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()

        # When database is healthy, overall status should be "ok"
        assert data["status"] == "ok"

    async def test_health_ready_endpoint_response_structure(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test complete response structure of readiness endpoint."""
        response = await test_client.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields
        assert "status" in data
        assert "version" in data
        assert "timestamp" in data
        assert "dependencies" in data

        # Verify types
        assert isinstance(data["status"], str)
        assert isinstance(data["version"], str)
        assert isinstance(data["timestamp"], str)
        assert isinstance(data["dependencies"], dict)


@pytest.mark.asyncio
class TestLivenessEndpoint:
    """Test liveness check endpoint."""

    async def test_health_live_endpoint_returns_204(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that liveness endpoint returns 204 No Content."""
        response = await test_client.get("/api/health/live")

        assert response.status_code == 204

    async def test_health_live_endpoint_no_body(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that liveness endpoint returns no response body."""
        response = await test_client.get("/api/health/live")

        assert response.status_code == 204
        # 204 No Content should have empty body
        assert len(response.content) == 0


@pytest.mark.asyncio
class TestHealthEndpointsPerformance:
    """Test performance and reliability of health endpoints."""

    async def test_health_endpoint_is_fast(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that health endpoint responds quickly (< 100ms)."""
        import time

        start = time.time()
        response = await test_client.get("/api/health")
        elapsed = (time.time() - start) * 1000  # Convert to ms

        assert response.status_code == 200
        assert elapsed < 100, f"Health check took {elapsed:.2f}ms, should be < 100ms"

    async def test_health_endpoints_idempotent(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that health endpoints are idempotent (multiple calls return same result)."""
        # Call health endpoint multiple times
        response1 = await test_client.get("/api/health")
        response2 = await test_client.get("/api/health")
        response3 = await test_client.get("/api/health")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

        # Verify status is consistent
        assert response1.json()["status"] == "ok"
        assert response2.json()["status"] == "ok"
        assert response3.json()["status"] == "ok"

    async def test_ready_endpoint_consistent_with_health(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Test that readiness endpoint version matches health endpoint."""
        health_response = await test_client.get("/api/health")
        ready_response = await test_client.get("/api/health/ready")

        assert health_response.status_code == 200
        assert ready_response.status_code == 200

        health_data = health_response.json()
        ready_data = ready_response.json()

        # Version should match
        assert health_data["version"] == ready_data["version"]
        # Status should both be ok
        assert health_data["status"] == "ok"
        assert ready_data["status"] == "ok"
