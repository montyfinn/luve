from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from src.contracts import GradingResult
from src.llm_grader import LLMGraderError
from src.worker import process_session_completed_job


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SESSION_ID = UUID("00000000-0000-0000-0000-000000000099")

_BASE_PAYLOAD: dict[str, Any] = {
    "event_type": "session.completed",
    "schema_version": "v1",
    "session_id": str(SESSION_ID),
    "created_at": "2026-01-01T00:00:00+00:00",
}

# 34 student words — above the default 25-word gate
_SESSION_ROW = {
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

# 4 student words — below default 25-word gate
_SESSION_ROW_SHORT = {
    **_SESSION_ROW,
    "raw_backup_json": [
        {"type": "USER_TURN", "payload": {"text": "Hello how are you"}},
    ],
}


class _FakeRepo:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row if row is not None else _SESSION_ROW
        self.upserted: GradingResult | None = None
        self.upsert_call_count = 0

    async def fetch_session_row(self, session_id: UUID) -> dict[str, Any] | None:
        return self._row

    async def upsert_grading_result(self, result: GradingResult) -> None:
        self.upserted = result
        self.upsert_call_count += 1

    async def log_grading_skip(self, **kwargs: Any) -> None:
        pass


def _llm_result() -> GradingResult:
    return GradingResult(
        session_id=SESSION_ID,
        overall_score=8.0,
        fluency_score=8.0,
        grammar_score=8.0,
        vocab_score=8.0,
        ai_summary_feedback="Good session.",
        detailed_corrections=[],
        grader_version="llm_grader.v1",
    )


# ---------------------------------------------------------------------------
# fake provider path is unaffected by GRADING_FAKE_FALLBACK
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fake_provider_unaffected_when_fallback_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.delenv("GRADING_FAKE_FALLBACK", raising=False)
    repo = _FakeRepo()
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upserted is not None
    assert repo.upserted.grader_version == "fake_grader.v1"


@pytest.mark.asyncio
async def test_fake_provider_unaffected_when_fallback_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.setenv("GRADING_FAKE_FALLBACK", "true")
    repo = _FakeRepo()
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upserted is not None
    assert repo.upserted.grader_version == "fake_grader.v1"


@pytest.mark.asyncio
async def test_fake_provider_unaffected_when_fallback_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    monkeypatch.setenv("GRADING_FAKE_FALLBACK", "false")
    repo = _FakeRepo()
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upserted is not None
    assert repo.upserted.grader_version == "fake_grader.v1"


# ---------------------------------------------------------------------------
# llm success — no fallback, regardless of flag
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_success_writes_llm_result_fallback_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.delenv("GRADING_FAKE_FALLBACK", raising=False)
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(return_value=_llm_result())),
    ):
        repo = _FakeRepo()
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upserted is not None
    assert repo.upserted.grader_version == "llm_grader.v1"
    assert repo.upsert_call_count == 1


# ---------------------------------------------------------------------------
# llm failure + fallback DISABLED (default / false) → raise, no fake upsert
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_failure_fallback_unset_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.delenv("GRADING_FAKE_FALLBACK", raising=False)
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("parse error"))),
    ):
        repo = _FakeRepo()
        with pytest.raises(LLMGraderError):
            await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upsert_call_count == 0


@pytest.mark.asyncio
async def test_llm_failure_fallback_false_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.setenv("GRADING_FAKE_FALLBACK", "false")
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("http 429"))),
    ):
        repo = _FakeRepo()
        with pytest.raises(LLMGraderError):
            await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upsert_call_count == 0


@pytest.mark.asyncio
async def test_llm_timeout_fallback_unset_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.delenv("GRADING_FAKE_FALLBACK", raising=False)
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=asyncio.TimeoutError())),
    ):
        repo = _FakeRepo()
        with pytest.raises(asyncio.TimeoutError):
            await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upsert_call_count == 0


# ---------------------------------------------------------------------------
# llm failure + fallback ENABLED (true) → fake fallback, upsert fake result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_failure_fallback_true_uses_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.setenv("GRADING_FAKE_FALLBACK", "true")
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("timeout"))),
    ):
        repo = _FakeRepo()
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upserted is not None
    assert repo.upserted.grader_version == "fake_grader.v1"
    assert repo.upsert_call_count == 1


# ---------------------------------------------------------------------------
# Truthy / falsey parsing for GRADING_FAKE_FALLBACK
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("truthy_val", ["1", "true", "True", "TRUE", "yes", "YES", "on", "ON"])
async def test_truthy_values_enable_fallback(monkeypatch: pytest.MonkeyPatch, truthy_val: str) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.setenv("GRADING_FAKE_FALLBACK", truthy_val)
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("err"))),
    ):
        repo = _FakeRepo()
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upsert_call_count == 1
    assert repo.upserted.grader_version == "fake_grader.v1"


@pytest.mark.asyncio
@pytest.mark.parametrize("falsey_val", ["0", "false", "no", "off", "bogus", "", "  "])
async def test_falsey_values_disable_fallback(monkeypatch: pytest.MonkeyPatch, falsey_val: str) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.setenv("GRADING_FAKE_FALLBACK", falsey_val)
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("err"))),
    ):
        repo = _FakeRepo()
        with pytest.raises(LLMGraderError):
            await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upsert_call_count == 0


@pytest.mark.asyncio
async def test_fallback_unset_env_disables_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.delenv("GRADING_FAKE_FALLBACK", raising=False)
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("err"))),
    ):
        repo = _FakeRepo()
        with pytest.raises(LLMGraderError):
            await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upsert_call_count == 0


# ---------------------------------------------------------------------------
# Log key verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_disabled_logs_llm_failed_no_fallback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.delenv("GRADING_FAKE_FALLBACK", raising=False)
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("bad json"))),
    ):
        repo = _FakeRepo()
        with caplog.at_level(logging.ERROR, logger="src.worker"):
            with pytest.raises(LLMGraderError):
                await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert any("llm_failed_no_fallback" in r.message for r in caplog.records)
    assert not any("llm_failed_fallback" in r.message and "no_fallback" not in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_fallback_enabled_logs_llm_failed_fallback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.setenv("GRADING_FAKE_FALLBACK", "true")
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("bad json"))),
    ):
        repo = _FakeRepo()
        with caplog.at_level(logging.WARNING, logger="src.worker"):
            await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert any("llm_failed_fallback" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Transcript must not appear in log output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_transcript_in_log_when_fallback_disabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.delenv("GRADING_FAKE_FALLBACK", raising=False)
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("err"))),
    ):
        repo = _FakeRepo()
        with caplog.at_level(logging.DEBUG, logger="src.worker"):
            with pytest.raises(LLMGraderError):
                await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    for record in caplog.records:
        assert "vegetables" not in record.message
        assert "market" not in record.message


@pytest.mark.asyncio
async def test_no_transcript_in_log_when_fallback_enabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.setenv("GRADING_FAKE_FALLBACK", "true")
    mock_client = object()
    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("err"))),
    ):
        repo = _FakeRepo()
        with caplog.at_level(logging.DEBUG, logger="src.worker"):
            await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    for record in caplog.records:
        assert "vegetables" not in record.message
        assert "market" not in record.message


# ---------------------------------------------------------------------------
# Insufficient evidence skips before provider/fallback logic — no raise
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_insufficient_evidence_skips_before_fallback_gate(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    monkeypatch.setenv("GRADING_FAKE_FALLBACK", "false")
    monkeypatch.setenv("GRADING_MIN_STUDENT_WORDS", "25")
    repo = _FakeRepo(row=_SESSION_ROW_SHORT)
    with caplog.at_level(logging.WARNING, logger="src.worker"):
        # must not raise even though fallback is disabled — skip gate fires first
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upsert_call_count == 0
    assert any("session_ineligible" in r.message for r in caplog.records)
