"""T7b: _persist_event_log writes the session.completed outbox row inside the
same transaction as the completion UPDATE (before commit), while the inline
publish_session_completed call after commit stays unchanged.

Unit-level: AsyncSessionLocal, enqueue_session_event and publish_session_completed
are all patched, so no real DB/RabbitMQ is needed.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.ten_ext.luve_extension import LUVEExtension


class _Ext(LUVEExtension):
    # Minimal stand-in: _persist_event_log only touches _session_id / _event_log.
    def __init__(self) -> None:
        self._session_id = None
        self._event_log = []


def _patch(monkeypatch, order, *, enqueue_raises: bool = False) -> dict:
    import src.core.db as db_mod
    import src.services.outbox_repository as outbox_mod
    import src.ten_ext.luve_extension as ext_mod

    session = MagicMock()

    async def _execute(*a, **k):
        order.append("execute")

    async def _commit(*a, **k):
        order.append("commit")

    session.execute = _execute
    session.commit = _commit

    acm = MagicMock()
    acm.__aenter__ = AsyncMock(return_value=session)
    acm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", MagicMock(return_value=acm))

    captured: dict = {}

    async def _enqueue(db, **kw):
        order.append("enqueue")
        captured.update(kw)
        if enqueue_raises:
            raise RuntimeError("outbox insert failed")

    monkeypatch.setattr(outbox_mod, "enqueue_session_event", _enqueue)

    async def _publish(sid):
        order.append(("publish", sid))

    monkeypatch.setattr(ext_mod, "publish_session_completed", _publish)
    return captured


def test_enqueue_runs_before_commit_and_publish_after(monkeypatch) -> None:
    order: list = []
    captured = _patch(monkeypatch, order)

    ext = _Ext()
    ext._session_id = "sess-1"
    ext._event_log = [{"type": "USER_TURN"}]
    asyncio.run(ext._persist_event_log())

    # UPDATE -> enqueue (in-txn) -> commit -> inline publish (after commit)
    assert order == ["execute", "enqueue", "commit", ("publish", "sess-1")]

    # enqueue args + payload shape match publish_session_completed's payload
    assert captured["event_type"] == "session.completed"
    assert captured["schema_version"] == "v1"
    assert captured["session_id"] == "sess-1"
    payload = captured["payload"]
    assert payload["event_type"] == "session.completed"
    assert payload["schema_version"] == "v1"
    assert payload["session_id"] == "sess-1"
    assert isinstance(payload["created_at"], str) and payload["created_at"]


def test_enqueue_failure_rolls_back_and_skips_publish(monkeypatch) -> None:
    order: list = []
    _patch(monkeypatch, order, enqueue_raises=True)

    ext = _Ext()
    ext._session_id = "sess-2"
    ext._event_log = [{"type": "USER_TURN"}]
    # The exception is caught inside _persist_event_log (Phase 1 FAILED log).
    asyncio.run(ext._persist_event_log())

    # Enqueue failure happens before commit -> no commit, no publish.
    assert "enqueue" in order
    assert "commit" not in order
    assert not any(isinstance(x, tuple) and x[0] == "publish" for x in order)
