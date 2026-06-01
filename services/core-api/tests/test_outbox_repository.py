"""T7a: unit tests for the transactional outbox enqueue primitive.

These use a minimal fake AsyncSession (no real DB, no event loop plugin) to
assert the emitted SQL shape, bound parameters, and the no-commit contract. Real
SQL semantics (ON CONFLICT idempotency) are verified separately against a
throwaway Postgres.
"""
from __future__ import annotations

import asyncio
import json

from src.services import outbox_repository as repo


class _FakeSession:
    """Records execute() calls; never commits on its own."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.committed = False

    async def execute(self, statement, params=None):  # noqa: ANN001
        self.calls.append((str(statement), params or {}))
        return None

    async def commit(self) -> None:
        self.committed = True


def test_enqueue_inserts_on_conflict_do_nothing_and_does_not_commit() -> None:
    db = _FakeSession()
    asyncio.run(
        repo.enqueue_session_event(
            db,
            session_id="s-1",
            event_type="session.completed",
            payload={"event_type": "session.completed", "session_id": "s-1"},
        )
    )

    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert "INSERT INTO session_outbox" in sql
    assert "ON CONFLICT (session_id, event_type) DO NOTHING" in sql
    assert params["session_id"] == "s-1"
    assert params["event_type"] == "session.completed"
    assert params["schema_version"] == "v1"
    assert json.loads(params["payload"])["session_id"] == "s-1"
    # Outbox row durability is bound to the caller's transaction, not ours.
    assert db.committed is False


def test_enqueue_accepts_custom_schema_version() -> None:
    db = _FakeSession()
    asyncio.run(
        repo.enqueue_session_event(
            db,
            session_id="s-2",
            event_type="session.completed",
            payload={},
            schema_version="v2",
        )
    )
    _, params = db.calls[0]
    assert params["schema_version"] == "v2"
