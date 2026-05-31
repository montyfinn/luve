"""T4a: /readyz readiness probe tests for core_api.

Importing src.main triggers get_settings(), which requires DATABASE_URL and
SECRET_KEY at import time, so throwaway values are set before importing. The DB
probe (_database_reachable) is monkeypatched, so no real database is contacted.
"""
from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/luve_test"
)
os.environ.setdefault("SECRET_KEY", "test-secret-not-real")

import pytest
from starlette.testclient import TestClient

import src.main as main


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app)


def test_readyz_route_registered() -> None:
    paths = {getattr(route, "path", None) for route in main.app.router.routes}
    assert "/readyz" in paths


def test_readyz_200_when_db_reachable(client: TestClient, monkeypatch) -> None:
    async def _ok() -> bool:
        return True

    monkeypatch.setattr(main, "_database_reachable", _ok)
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"


def test_readyz_503_when_db_unreachable(client: TestClient, monkeypatch) -> None:
    async def _fail() -> bool:
        return False

    monkeypatch.setattr(main, "_database_reachable", _fail)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "unreachable"


def test_readyz_does_not_leak_connection_string(
    client: TestClient, monkeypatch
) -> None:
    async def _fail() -> bool:
        return False

    monkeypatch.setattr(main, "_database_reachable", _fail)
    resp = client.get("/readyz")
    assert "postgresql" not in resp.text
    assert "localhost" not in resp.text


def test_root_liveness_unchanged(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Running"
