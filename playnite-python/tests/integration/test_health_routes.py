"""Integration tests for health check endpoints."""
import pytest
from fastapi.testclient import TestClient
from src.playnite_python.api.app import app


@pytest.fixture
def client():
    """Create test client for API."""
    return TestClient(app)


def test_health_endpoint_basic(client):
    """Test basic health check endpoint."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert data["status"] == "healthy"
    assert "version" in data


def test_health_readiness_probe(client):
    """Test Kubernetes readiness probe."""
    response = client.get("/api/v1/health/ready")

    # May return 200 or 503 depending on database/filesystem state
    assert response.status_code in [200, 503]

    data = response.json()
    assert "ready" in data
    assert "checks" in data
    assert "version" in data
    assert "uptime_seconds" in data

    # Checks should include database and filesystem
    if "checks" in data:
        assert isinstance(data["checks"], dict)


def test_health_liveness_probe(client):
    """Test Kubernetes liveness probe."""
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    data = response.json()

    assert "alive" in data
    assert data["alive"] is True
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], (int, float))


def test_health_liveness_fast_response(client):
    """Test that liveness probe responds quickly."""
    import time

    start = time.time()
    response = client.get("/api/v1/health/live")
    duration = time.time() - start

    assert response.status_code == 200
    # Should respond in under 100ms
    assert duration < 0.1


def test_health_endpoints_return_json(client):
    """Test that all health endpoints return JSON."""
    endpoints = [
        "/api/v1/health",
        "/api/v1/health/live",
        "/api/v1/health/ready"
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.headers["content-type"] == "application/json"


def test_health_uptime_increases(client):
    """Test that uptime increases between calls."""
    import time

    response1 = client.get("/api/v1/health/live")
    data1 = response1.json()
    uptime1 = data1["uptime_seconds"]

    time.sleep(0.1)

    response2 = client.get("/api/v1/health/live")
    data2 = response2.json()
    uptime2 = data2["uptime_seconds"]

    assert uptime2 >= uptime1
