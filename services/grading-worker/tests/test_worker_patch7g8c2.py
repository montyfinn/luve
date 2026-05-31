"""
Patch 7G-8C-2: Worker eligibility refactor + skip-log write tests.

All tests use mocked repository and provider — no live DB, no Groq.
Covers all four ineligible reasons, the eligible path, and skip-log failure.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from src.contracts import GradingResult
from src.worker import process_session_completed_job

SESSION_ID = UUID("00000000-0000-0000-0000-000000000099")

_BASE_PAYLOAD: dict[str, Any] = {
    "event_type": "session.completed",
    "schema_version": "v1",
    "session_id": str(SESSION_ID),
    "created_at": "2026-01-01T00:00:00+00:00",
}

# 34 student words — above default 25-word gate
_SESSION_ROW_ELIGIBLE: dict[str, Any] = {
    "id": str(SESSION_ID),
    "user_id": "00000000-0000-0000-0000-000000000002",
    "lesson_id": None,
    "status": "completed",
    "raw_backup_json": [
        {
            "type": "USER_TURN",
            "payload": {
                "text": (
                    "Hello, how are you today? I would like to practice my English "
                    "conversation skills. Last weekend I visited the local market with "
                    "my family and we had a great time shopping for fresh vegetables."
                )
            },
        },
        {"type": "AI_TURN", "payload": {"text": "That sounds wonderful!"}},
    ],
    "started_at": "2026-01-01T00:00:00+00:00",
    "ended_at": "2026-01-01T00:01:00+00:00",
}


def _make_row(**overrides: Any) -> dict[str, Any]:
    return {**_SESSION_ROW_ELIGIBLE, **overrides}


class _FakeRepo:
    def __init__(
        self,
        row: dict[str, Any] | None = None,
        skip_log_raise: Exception | None = None,
    ) -> None:
        self._row = row if row is not None else _SESSION_ROW_ELIGIBLE
        self.upserted: GradingResult | None = None
        self.upsert_call_count = 0
        self.skip_log_calls: list[dict[str, Any]] = []
        self._skip_log_raise = skip_log_raise

    async def fetch_session_row(self, session_id: UUID) -> dict[str, Any] | None:
        return self._row

    async def upsert_grading_result(self, result: GradingResult) -> None:
        self.upserted = result
        self.upsert_call_count += 1

    async def log_grading_skip(
        self,
        *,
        session_id: UUID,
        reason: str,
        source: str,
        student_word_count: int | None,
        min_words_threshold: int | None,
    ) -> None:
        if self._skip_log_raise is not None:
            raise self._skip_log_raise
        self.skip_log_calls.append(
            {
                "session_id": session_id,
                "reason": reason,
                "source": source,
                "student_word_count": student_word_count,
                "min_words_threshold": min_words_threshold,
            }
        )


# ---------------------------------------------------------------------------
# no_raw_backup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_no_raw_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    repo = _FakeRepo(row=_make_row(raw_backup_json=None))
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert repo.upsert_call_count == 0
    assert len(repo.skip_log_calls) == 1
    call = repo.skip_log_calls[0]
    assert call["reason"] == "no_raw_backup"
    assert call["source"] == "worker"
    assert call["student_word_count"] is None
    assert call["min_words_threshold"] is None


# ---------------------------------------------------------------------------
# invalid_raw_backup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_invalid_raw_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    repo = _FakeRepo(row=_make_row(raw_backup_json="not a list"))
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert repo.upsert_call_count == 0
    assert len(repo.skip_log_calls) == 1
    call = repo.skip_log_calls[0]
    assert call["reason"] == "invalid_raw_backup"
    assert call["source"] == "worker"
    assert call["student_word_count"] is None
    assert call["min_words_threshold"] is None


# ---------------------------------------------------------------------------
# no_user_turns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_no_user_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    repo = _FakeRepo(row=_make_row(raw_backup_json=[]))
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert repo.upsert_call_count == 0
    assert len(repo.skip_log_calls) == 1
    call = repo.skip_log_calls[0]
    assert call["reason"] == "no_user_turns"
    assert call["source"] == "worker"
    assert call["min_words_threshold"] is None


# ---------------------------------------------------------------------------
# insufficient_words
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_insufficient_words(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.setenv("GRADING_MIN_STUDENT_WORDS", "25")
    row = _make_row(
        raw_backup_json=[{"type": "USER_TURN", "payload": {"text": "Hello hi"}}]
    )
    repo = _FakeRepo(row=row)
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert repo.upsert_call_count == 0
    assert len(repo.skip_log_calls) == 1
    call = repo.skip_log_calls[0]
    assert call["reason"] == "insufficient_words"
    assert call["source"] == "worker"
    assert call["student_word_count"] == 2
    assert call["min_words_threshold"] == 25


@pytest.mark.asyncio
async def test_skip_explicitly_excluded_stt_words(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.setenv("GRADING_MIN_STUDENT_WORDS", "25")
    row = _make_row(
        raw_backup_json=[
            {
                "type": "USER_TURN",
                "payload": {
                    "text": " ".join(f"word{i}" for i in range(30)),
                    "stt_quality": "uncertain",
                    "uncertainty_reasons": ["weak_mixed_language_english"],
                    "grading_eligible": False,
                    "excluded_from_grading_reason": "weak_mixed_language_english",
                },
            }
        ]
    )
    repo = _FakeRepo(row=row)
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert repo.upsert_call_count == 0
    assert len(repo.skip_log_calls) == 1
    call = repo.skip_log_calls[0]
    assert call["reason"] == "insufficient_words"
    assert call["source"] == "worker"
    assert call["student_word_count"] == 0
    assert call["min_words_threshold"] == 25


@pytest.mark.asyncio
async def test_uncertain_autocorrection_words_remain_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.setenv("GRADING_MIN_STUDENT_WORDS", "25")
    row = _make_row(
        raw_backup_json=[
            {
                "type": "USER_TURN",
                "payload": {
                    "text": " ".join(f"word{i}" for i in range(30)),
                    "stt_quality": "uncertain",
                    "uncertainty_reasons": ["possible_stt_autocorrection"],
                    "possible_stt_autocorrection": True,
                },
            }
        ]
    )
    repo = _FakeRepo(row=row)
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert len(repo.skip_log_calls) == 0
    assert repo.upsert_call_count == 1


# ---------------------------------------------------------------------------
# eligible — skip-log not called, upsert called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eligible_skips_skip_log_and_upserts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.setenv("GRADING_MIN_STUDENT_WORDS", "25")
    repo = _FakeRepo()  # _SESSION_ROW_ELIGIBLE has 34 student words
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert len(repo.skip_log_calls) == 0
    assert repo.upsert_call_count == 1


# ---------------------------------------------------------------------------
# skip-log failure is retryable — no ACK without durable skip/failure state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_log_failure_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    repo = _FakeRepo(
        row=_make_row(raw_backup_json=None),  # no_raw_backup → ineligible
        skip_log_raise=RuntimeError("db error"),
    )
    with pytest.raises(RuntimeError, match="db error"):
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert repo.upsert_call_count == 0
