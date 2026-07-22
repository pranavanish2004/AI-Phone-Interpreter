"""
Shared pytest fixtures for api_gateway tests.

Why override settings via monkeypatch rather than requiring a real .env:
    Tests should run in CI/sandboxes without a real Postgres/Redis
    connection string configured. We provide fake-but-valid values so
    Settings() validation passes, and individual tests that need to hit a
    real DB (none yet, in Phase 3) would use a dedicated test-database
    fixture instead.
"""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-not-for-production-use")
    # Ensure get_settings()'s lru_cache doesn't leak a Settings instance
    # built from a DIFFERENT test's env vars across test functions.
    from app.core.config import get_settings
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    from app.main import create_app
    return TestClient(create_app())
