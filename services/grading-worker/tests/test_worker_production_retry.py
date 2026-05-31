from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.worker import _handle_queue_message, _process_payload_with_retries, process_session_completed_job


SESSION_ID = UUID("00000000-0000-0000-0000-000000000777")


_PAYLOAD: dict[str, Any] = {
    "event_type": "session.completed",
    "schema_version": "v1",
    "session_id": str(SESSION_ID),
    "created_at": "2026-01-01T00:00:00+00:00",
}


_SESSION_ROW: dict[str, Any] = {
    "id": str(SESSION_ID),
    "user_id": "00000000-0000-0000-0000-000000000002",
    "lesson_id": None,
    "status": "completed",
    "raw_backup_json": [
        {
            "type": "USER_TURN",
            "payload": {
                "text": " ".join(f"word{i}" for i in range(30)),
            },
        },
    ],
    "started_at": "2026-01-01T00:00:00+00:00",
    "ended_at": "2026-01-01T00:01:00+00:00",
}


class _FailingRepo:
    def __init__(self, *, mark_failed_raise: Exception | None = None) -> None:
        self.upsert_attempts = 0
        self.failed_calls: list[dict[str, Any]] = []
        self._mark_failed_raise = mark_failed_raise

    async def fetch_session_row(self, session_id: UUID) -> dict[str, Any]:
        return _SESSION_ROW

    async def upsert_grading_result(self, result: Any) -> None:
        self.upsert_attempts += 1
        raise RuntimeError("db temporarily unavailable")

    async def mark_grading_failed(self, **kwargs: Any) -> None:
        self.failed_calls.append(kwargs)
        if self._mark_failed_raise is not None:
            raise self._mark_failed_raise


class _FakeMessage:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.ack = AsyncMock()
        self.nack = AsyncMock()
        self.reject = AsyncMock()


class _AlreadyGradedRepo:
    def __init__(self) -> None:
        self.processing_calls = 0
        self.upsert_attempts = 0

    async def fetch_session_row(self, session_id: UUID) -> dict[str, Any]:
        return _SESSION_ROW

    async def mark_grading_processing(self, **kwargs: Any) -> bool:
        self.processing_calls += 1
        return False

    async def upsert_grading_result(self, result: Any) -> None:
        self.upsert_attempts += 1


@pytest.mark.asyncio
async def test_retry_wrapper_marks_failed_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.setenv("GRADING_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("GRADING_RETRY_DELAY_SECONDS", "0")

    repo = _FailingRepo()
    await _process_payload_with_retries(_PAYLOAD, repository=repo)  # type: ignore[arg-type]

    assert repo.upsert_attempts == 2
    assert len(repo.failed_calls) == 1
    assert repo.failed_calls[0]["session_id"] == SESSION_ID
    assert repo.failed_calls[0]["error_code"] == "RuntimeError"


@pytest.mark.asyncio
async def test_retry_wrapper_raises_when_failed_state_cannot_be_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.setenv("GRADING_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("GRADING_RETRY_DELAY_SECONDS", "0")

    repo = _FailingRepo(mark_failed_raise=RuntimeError("db still unavailable"))
    with pytest.raises(RuntimeError, match="db still unavailable"):
        await _process_payload_with_retries(_PAYLOAD, repository=repo)  # type: ignore[arg-type]

    assert repo.upsert_attempts == 2
    assert len(repo.failed_calls) == 1


@pytest.mark.asyncio
async def test_queue_message_acks_after_durable_failed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.setenv("GRADING_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("GRADING_RETRY_DELAY_SECONDS", "0")

    repo = _FailingRepo()
    message = _FakeMessage(json.dumps(_PAYLOAD).encode("utf-8"))
    await _handle_queue_message(message, repository=repo)  # type: ignore[arg-type]

    message.ack.assert_awaited_once_with()
    message.nack.assert_not_awaited()
    message.reject.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_message_requeues_when_terminal_state_is_not_durable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.setenv("GRADING_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("GRADING_RETRY_DELAY_SECONDS", "0")

    repo = _FailingRepo(mark_failed_raise=RuntimeError("db still unavailable"))
    message = _FakeMessage(json.dumps(_PAYLOAD).encode("utf-8"))
    await _handle_queue_message(message, repository=repo)  # type: ignore[arg-type]

    message.ack.assert_not_awaited()
    message.nack.assert_awaited_once_with(requeue=True)
    message.reject.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_message_rejects_invalid_json() -> None:
    message = _FakeMessage(b"not-json")
    await _handle_queue_message(message, repository=object())  # type: ignore[arg-type]

    message.ack.assert_not_awaited()
    message.nack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


@pytest.mark.asyncio
async def test_duplicate_completed_job_preserves_existing_grade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")

    repo = _AlreadyGradedRepo()
    await process_session_completed_job(_PAYLOAD, repository=repo)  # type: ignore[arg-type]

    assert repo.processing_calls == 1
    assert repo.upsert_attempts == 0
