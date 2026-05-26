"""
Patch 7G-6: CORS helper unit tests and StaticFiles/control-center integration tests.

StaticFiles/route tests use a minimal throwaway FastAPI app rather than importing
src.main directly. Importing src.main triggers get_settings() which validates
DATABASE_URL and SECRET_KEY env vars at module load time. The throwaway app
mirrors the exact mount/route/middleware pattern from main.py so the tests remain
meaningful while avoiding the env-var dependency.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.testclient import TestClient

from src.core.cors import get_cors_allow_origins

# Resolved relative to this test file — independent of cwd
_STATIC_DIR = Path(__file__).parent.parent / "src" / "static"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(cors_origins: list[str]) -> FastAPI:
    """Minimal app that mirrors main.py's serving pattern."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/control-center", include_in_schema=False)
    async def control_center() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/api/v1/sentinel")
    async def sentinel():
        return {"ok": True}

    return app


# ---------------------------------------------------------------------------
# CORS helper — pure unit tests, no app creation
# ---------------------------------------------------------------------------

def test_cors_default_no_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    assert "*" not in get_cors_allow_origins()


def test_cors_default_includes_localhost_8000(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    assert "http://localhost:8000" in get_cors_allow_origins()


def test_cors_default_includes_127_8080(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    assert "http://127.0.0.1:8080" in get_cors_allow_origins()


def test_cors_env_override_single_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:9000")
    assert get_cors_allow_origins() == ["http://localhost:9000"]


def test_cors_env_override_trims_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "  http://localhost:3000  ,  http://localhost:8000  ")
    origins = get_cors_allow_origins()
    assert "http://localhost:3000" in origins
    assert "http://localhost:8000" in origins
    assert all(o == o.strip() for o in origins)


def test_cors_env_override_drops_empty_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", ",http://localhost:3000,,,")
    origins = get_cors_allow_origins()
    assert origins == ["http://localhost:3000"]


def test_cors_empty_env_string_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "")
    origins = get_cors_allow_origins()
    assert len(origins) > 1
    assert "*" not in origins


def test_cors_explicit_wildcard_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    assert get_cors_allow_origins() == ["*"]


# ---------------------------------------------------------------------------
# StaticFiles and control-center route tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    app = _make_app(["http://localhost:8000", "http://127.0.0.1:8000"])
    return TestClient(app, raise_server_exceptions=True)


def test_control_center_returns_200_html(client: TestClient) -> None:
    response = client.get("/control-center")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_control_center_body_contains_marker(client: TestClient) -> None:
    response = client.get("/control-center")
    assert "L.U.V.E" in response.text or "Control Center" in response.text


def test_static_css_served(client: TestClient) -> None:
    response = client.get("/static/styles.css")
    assert response.status_code == 200
    ct = response.headers.get("content-type", "")
    assert "css" in ct or "text/" in ct


def test_api_route_not_shadowed_by_static_mount(client: TestClient) -> None:
    # Static mount must not absorb /api/v1 paths
    response = client.get("/api/v1/sentinel")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_api_nonexistent_returns_404_not_html(client: TestClient) -> None:
    response = client.get("/api/v1/nonexistent_route_xyz")
    assert response.status_code == 404
    # Must not serve the control-center HTML for missing API paths
    assert "text/html" not in response.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# CORS middleware preflight tests
# ---------------------------------------------------------------------------

def test_cors_preflight_allowed_origin_echoed(client: TestClient) -> None:
    response = client.options(
        "/api/v1/sentinel",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    allow_origin = response.headers.get("access-control-allow-origin", "")
    assert allow_origin == "http://localhost:8000"
    assert allow_origin != "*"


def test_cors_preflight_unlisted_origin_gets_no_header(client: TestClient) -> None:
    response = client.options(
        "/api/v1/sentinel",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert "access-control-allow-origin" not in response.headers
