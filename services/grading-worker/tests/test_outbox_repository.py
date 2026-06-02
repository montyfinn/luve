"""T7c-1: unit tests for the worker outbox relay primitives.

A fake asyncpg-style connection records the SQL + bound args, so no real DB,
RabbitMQ, or pytest-asyncio is needed (the async functions run via asyncio.run).

The SQL CASE branch (pending-below-max vs failed-at-max) is verified here by
asserting the SQL encodes it; its runtime branch behaviour is left to a
throwaway-Postgres smoke in a later (Docker-gated) phase.
"""
from __future__ import annotations

import asyncio

from src import outbox_repository as repo


class _FakeConn:
    def __init__(self, fetch_result=None):
        self.fetch_calls: list[tuple] = []
        self.execute_calls: list[tuple] = []
        self._fetch_result = fetch_result if fetch_result is not None else []

    async def fetch(self, sql, *args):
        self.fetch_calls.append((sql, args))
        return self._fetch_result

    async def execute(self, sql, *args):
        self.execute_calls.append((sql, args))


def test_claim_pending_sql_shape_and_args() -> None:
    rows = [{"id": "o-1"}]
    conn = _FakeConn(fetch_result=rows)
    out = asyncio.run(repo.claim_pending_session_events(conn, 10))

    assert out == rows
    assert len(conn.fetch_calls) == 1
    sql, args = conn.fetch_calls[0]
    assert "FROM session_outbox" in sql
    assert "status = 'pending'" in sql
    assert "ORDER BY created_at" in sql
    assert "LIMIT $1" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    # returns the fields the future relay needs
    for col in ("id", "session_id", "event_type", "schema_version", "payload", "attempt_count"):
        assert col in sql
    assert args == (10,)


def test_mark_published_sets_status_and_timestamp() -> None:
    conn = _FakeConn()
    asyncio.run(repo.mark_session_event_published(conn, "o-1"))

    assert len(conn.execute_calls) == 1
    sql, args = conn.execute_calls[0]
    assert "status = 'published'" in sql
    assert "published_at = CURRENT_TIMESTAMP" in sql
    assert "updated_at = CURRENT_TIMESTAMP" in sql
    assert args == ("o-1",)


def test_retry_or_failed_sql_encodes_case_and_binds_args() -> None:
    conn = _FakeConn()
    asyncio.run(
        repo.mark_session_event_retry_or_failed(conn, "o-1", "boom", 3)
    )

    sql, args = conn.execute_calls[0]
    assert "attempt_count = attempt_count + 1" in sql
    assert "last_error = $2" in sql
    # CASE: failed at max, else pending — the atomic branch decision
    assert "WHEN attempt_count + 1 >= $3 THEN 'failed'" in sql
    assert "ELSE 'pending'" in sql
    assert "updated_at = CURRENT_TIMESTAMP" in sql
    assert args == ("o-1", "boom", 3)


def test_retry_or_failed_truncates_long_error() -> None:
    conn = _FakeConn()
    long_error = "x" * 5000
    asyncio.run(
        repo.mark_session_event_retry_or_failed(conn, "o-2", long_error, 5)
    )
    _, args = conn.execute_calls[0]
    outbox_id, bounded_error, max_attempts = args
    assert outbox_id == "o-2"
    assert max_attempts == 5
    assert len(bounded_error) == repo._MAX_LAST_ERROR_LEN
    assert set(bounded_error) == {"x"}


def test_retry_or_failed_handles_none_error() -> None:
    conn = _FakeConn()
    asyncio.run(
        repo.mark_session_event_retry_or_failed(conn, "o-3", None, 2)
    )
    _, args = conn.execute_calls[0]
    assert args == ("o-3", "", 2)
