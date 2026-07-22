"""
Tests for app/core/exception_handlers.py.

Approach: rather than needing a real business route that raises these
errors (none exist yet in Phase 3 - auth arrives in Phase 4), we mount a
few throwaway test-only routes on a fresh app instance that deliberately
raise each exception type. This tests the HANDLER behavior in isolation,
which is exactly what this phase is responsible for - Phase 4's real routes
will get this same handling "for free" once they raise AppException
subtypes.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.exceptions import ConflictError, NotFoundError, ValidationError


@pytest.fixture
def test_app() -> FastAPI:
    from app.main import create_app

    app = create_app()

    class Item(BaseModel):
        name: str

    @app.get("/test/not-found")
    async def raise_not_found():
        raise NotFoundError("Widget not found", details={"widget_id": "123"})

    @app.get("/test/conflict")
    async def raise_conflict():
        raise ConflictError("Widget already exists")

    @app.get("/test/validation")
    async def raise_validation():
        raise ValidationError("Widget name is reserved")

    @app.get("/test/unexpected")
    async def raise_unexpected():
        raise RuntimeError("something exploded internally, with secret details")

    @app.post("/test/schema-validated")
    async def schema_validated(item: Item):
        return item

    return app


@pytest.fixture
def test_client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, raise_server_exceptions=False)


def test_not_found_error_maps_to_404_with_consistent_shape(test_client: TestClient) -> None:
    response = test_client.get("/test/not-found")
    assert response.status_code == 404
    body = response.json()
    assert body == {
        "error_code": "NOT_FOUND",
        "message": "Widget not found",
        "details": {"widget_id": "123"},
    }


def test_conflict_error_maps_to_409(test_client: TestClient) -> None:
    response = test_client.get("/test/conflict")
    assert response.status_code == 409
    assert response.json()["error_code"] == "CONFLICT"


def test_validation_error_maps_to_422(test_client: TestClient) -> None:
    response = test_client.get("/test/validation")
    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


def test_unexpected_exception_maps_to_generic_500_without_leaking_details(
    test_client: TestClient,
) -> None:
    response = test_client.get("/test/unexpected")
    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "INTERNAL_ERROR"
    # Critical: the real exception message must NEVER reach the client.
    assert "secret details" not in body["message"]
    assert "secret details" not in str(body["details"])


def test_pydantic_request_validation_error_uses_consistent_shape(
    test_client: TestClient,
) -> None:
    # Missing the required `name` field triggers Pydantic's own
    # request-schema validation, BEFORE our route code runs.
    response = test_client.post("/test/schema-validated", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "REQUEST_VALIDATION_ERROR"
    assert "errors" in body["details"]
