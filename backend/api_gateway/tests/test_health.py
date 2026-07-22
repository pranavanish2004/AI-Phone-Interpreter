"""
Tests for GET /health.

Note: these tests run WITHOUT a real Postgres/Redis available (see
conftest.py) and WITHOUT triggering the app's lifespan (TestClient only
runs startup/shutdown when used as a context manager - see client fixture).
This deliberately exercises the "dependency unreachable" path, proving the
health endpoint degrades gracefully instead of crashing when Postgres/Redis
aren't reachable - exactly the scenario the endpoint exists to detect.
"""

from fastapi.testclient import TestClient


def test_health_returns_consistent_shape_even_when_dependencies_down(
    client: TestClient,
) -> None:
    response = client.get("/health")

    # Degraded (503) is the CORRECT outcome here since no real Postgres/
    # Redis are reachable in this test environment - see module docstring.
    assert response.status_code == 503

    body = response.json()
    assert body["service"] == "api_gateway"
    assert body["status"] == "degraded"
    assert body["dependencies"]["database"] == "unreachable"
    assert body["dependencies"]["redis"] == "unreachable"


def test_health_response_has_no_unhandled_exception_shape(client: TestClient) -> None:
    """
    Guards against a regression where an unreachable dependency causes an
    unhandled exception (which would return our generic 500 error shape
    from exception_handlers.py) instead of a clean, informative 503.
    """
    response = client.get("/health")
    body = response.json()
    assert "error_code" not in body
