"""Focused tests for the authenticated session history list endpoint.

No real database is contacted. The router uses the real dependency graph, while
get_db/get_current_user are overridden only for authenticated cases.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@localhost:5432/t")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-session-api-tests")

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402

import src.api.v1.sessions as sessions_module  # noqa: E402
from src.api.deps import get_current_user  # noqa: E402
from src.core.db import get_db  # noqa: E402

USER_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SESSION_1 = UUID("11111111-1111-1111-1111-111111111111")
SESSION_2 = UUID("22222222-2222-2222-2222-222222222222")
SESSION_3 = UUID("33333333-3333-3333-3333-333333333333")
SESSION_OTHER = UUID("99999999-9999-9999-9999-999999999999")

_ITEM_FIELDS = (
    "id",
    "lesson_id",
    "status",
    "total_tokens",
    "manual_stops_count",
    "started_at",
    "ended_at",
)


class _FakeResult:
    def __init__(self, *, rows: list[dict] | None = None, scalar: int | None = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def scalar_one(self) -> int:
        assert self._scalar is not None
        return self._scalar

    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list[dict]:
        return self._rows


class _HistoryDb:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(statement)
        bound = dict(params or {})
        self.calls.append((sql, bound))

        user_id = bound.get("user_id")
        visible = [
            row
            for row in self.rows
            if str(row["user_id"]) == user_id and row.get("deleted_at") is None
        ]
        if "COUNT(*)" in sql.upper():
            return _FakeResult(scalar=len(visible))

        visible.sort(key=lambda row: (row["started_at"], str(row["id"])), reverse=True)
        offset = bound.get("offset", 0)
        limit = bound.get("limit", len(visible))
        page = visible[offset : offset + limit]
        return _FakeResult(
            rows=[
                {
                    **{field: row[field] for field in _ITEM_FIELDS},
                    "raw_backup_json": row.get("raw_backup_json"),
                }
                for row in page
            ]
        )


_KEEP_DEFAULT_BACKUP = object()
_DEFAULT_BACKUP = [{"type": "USER_TURN", "payload": {"text": "private"}}]


def _row(
    *,
    user_id: UUID,
    session_id: UUID,
    started_at: datetime,
    deleted_at: datetime | None = None,
    raw_backup_json=_KEEP_DEFAULT_BACKUP,
) -> dict:
    backup = _DEFAULT_BACKUP if raw_backup_json is _KEEP_DEFAULT_BACKUP else raw_backup_json
    return {
        "id": session_id,
        "user_id": user_id,
        "lesson_id": None,
        "status": "ready",
        "total_tokens": 0,
        "manual_stops_count": 0,
        "started_at": started_at,
        "ended_at": None,
        "deleted_at": deleted_at,
        "raw_backup_json": backup,
        "metadata": {"secretish": "not-for-history-list"},
    }


def _make_app(
    db: _HistoryDb | None = None,
    *,
    user_id: UUID = USER_A,
    override_user: bool = True,
) -> FastAPI:
    app = FastAPI()
    app.include_router(sessions_module.router, prefix="/api/v1")

    async def _override_db():
        yield db or _HistoryDb([])

    app.dependency_overrides[get_db] = _override_db

    if override_user:
        async def _override_current_user():
            return SimpleNamespace(id=user_id)

        app.dependency_overrides[get_current_user] = _override_current_user

    return app


def _get(app: FastAPI, path: str) -> httpx.Response:
    async def _call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(_call())


def test_list_sessions_requires_bearer_auth() -> None:
    app = _make_app(override_user=False)

    response = _get(app, "/api/v1/sessions")

    assert response.status_code == 401


def test_list_sessions_returns_only_current_user_sessions_newest_first() -> None:
    now = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    db = _HistoryDb(
        [
            _row(user_id=USER_A, session_id=SESSION_1, started_at=now),
            _row(user_id=USER_A, session_id=SESSION_2, started_at=now),
            _row(user_id=USER_A, session_id=SESSION_3, started_at=now - timedelta(days=1)),
            _row(user_id=USER_B, session_id=SESSION_OTHER, started_at=now + timedelta(days=1)),
        ]
    )
    app = _make_app(db)

    response = _get(app, "/api/v1/sessions")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [
        str(SESSION_2),
        str(SESSION_1),
        str(SESSION_3),
    ]
    assert str(SESSION_OTHER) not in {item["id"] for item in body["items"]}
    list_sql = db.calls[-1][0]
    assert "ORDER BY started_at DESC, id DESC" in list_sql
    assert db.calls[-1][1]["user_id"] == str(USER_A)


def test_list_sessions_limit_offset_work() -> None:
    now = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    db = _HistoryDb(
        [
            _row(user_id=USER_A, session_id=SESSION_1, started_at=now),
            _row(user_id=USER_A, session_id=SESSION_2, started_at=now + timedelta(minutes=1)),
            _row(user_id=USER_A, session_id=SESSION_3, started_at=now + timedelta(minutes=2)),
        ]
    )
    app = _make_app(db)

    response = _get(app, "/api/v1/sessions?limit=1&offset=1")

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [str(SESSION_2)]
    # Pagination is applied in Python over the content-filtered set, so limit/
    # offset are reflected in the response, not in SQL params.


def test_list_sessions_clamps_limit_to_safe_max() -> None:
    db = _HistoryDb([])
    app = _make_app(db)

    response = _get(app, "/api/v1/sessions?limit=500")

    assert response.status_code == 200
    assert response.json()["limit"] == 100


def test_list_sessions_response_shape_is_stable_and_excludes_heavy_fields() -> None:
    now = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    db = _HistoryDb([_row(user_id=USER_A, session_id=SESSION_1, started_at=now)])
    app = _make_app(db)

    response = _get(app, "/api/v1/sessions")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "limit", "offset", "total"}
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["total"] == 1
    assert set(body["items"][0]) == set(_ITEM_FIELDS)
    assert "raw_backup_json" not in body["items"][0]
    assert "metadata" not in body["items"][0]
    assert "user_id" not in body["items"][0]


def test_empty_session_hidden_from_default_list() -> None:
    now = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    db = _HistoryDb(
        [
            _row(user_id=USER_A, session_id=SESSION_1, started_at=now),  # has content
            _row(
                user_id=USER_A,
                session_id=SESSION_2,
                started_at=now + timedelta(minutes=1),
                raw_backup_json=[],  # no user turns
            ),
        ]
    )
    app = _make_app(db)

    body = _get(app, "/api/v1/sessions").json()

    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(SESSION_1)]


def test_zero_student_word_session_hidden_from_default_list() -> None:
    now = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    db = _HistoryDb(
        [
            _row(user_id=USER_A, session_id=SESSION_1, started_at=now),
            _row(
                user_id=USER_A,
                session_id=SESSION_2,
                started_at=now + timedelta(minutes=1),
                raw_backup_json=[{"type": "USER_TURN", "payload": {"text": "   "}}],
            ),
        ]
    )
    app = _make_app(db)

    body = _get(app, "/api/v1/sessions").json()

    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(SESSION_1)]


def test_include_incomplete_returns_hidden_sessions() -> None:
    now = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    db = _HistoryDb(
        [
            _row(user_id=USER_A, session_id=SESSION_1, started_at=now),
            _row(
                user_id=USER_A,
                session_id=SESSION_2,
                started_at=now + timedelta(minutes=1),
                raw_backup_json=None,  # no backup at all
            ),
        ]
    )
    app = _make_app(db)

    default_body = _get(app, "/api/v1/sessions").json()
    assert default_body["total"] == 1
    assert [item["id"] for item in default_body["items"]] == [str(SESSION_1)]

    incomplete_body = _get(app, "/api/v1/sessions?include_incomplete=true").json()
    assert incomplete_body["total"] == 2
    assert {item["id"] for item in incomplete_body["items"]} == {
        str(SESSION_1),
        str(SESSION_2),
    }
