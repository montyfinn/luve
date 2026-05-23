from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from src.contracts import EvaluationInput, EvaluationTurn, GradingResult
from src.llm_grader import LLMGraderError
from src.worker import process_session_completed_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")

_BASE_PAYLOAD: dict[str, Any] = {
    "event_type": "session.completed",
    "schema_version": "v1",
    "session_id": str(SESSION_ID),
    "created_at": "2026-01-01T00:00:00+00:00",
}

_SESSION_ROW_WITH_TURNS: dict[str, Any] = {
    "id": str(SESSION_ID),
    "user_id": "00000000-0000-0000-0000-000000000002",
    "lesson_id": None,
    "status": "completed",
    "raw_backup_json": [
        {
            "type": "USER_TURN",
            "payload": {"text": "Hello, how are you?"},
        },
        {
            "type": "AI_TURN",
            "payload": {"text": "I am fine, thanks!"},
        },
    ],
    "started_at": "2026-01-01T00:00:00+00:00",
    "ended_at": "2026-01-01T00:01:00+00:00",
}

_SESSION_ROW_NO_TURNS: dict[str, Any] = {
    **_SESSION_ROW_WITH_TURNS,
    "raw_backup_json": [],
}


class FakeRepository:
    """In-memory repository stub — no DB, no network."""

    def __init__(self, session_row: dict[str, Any] | None = _SESSION_ROW_WITH_TURNS) -> None:
        self._row = session_row
        self.upserted: GradingResult | None = None
        self.upsert_call_count = 0

    async def fetch_session_row(self, session_id: UUID) -> dict[str, Any] | None:
        return self._row

    async def upsert_grading_result(self, result: GradingResult) -> None:
        self.upserted = result
        self.upsert_call_count += 1


def _fake_llm_result() -> GradingResult:
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
# Provider selection + fake path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_default_provider_unset_uses_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRADING_PROVIDER", raising=False)
    repo = FakeRepository()
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upserted is not None
    assert repo.upserted.grader_version == "fake_grader.v1"


@pytest.mark.asyncio
async def test_provider_fake_explicit_uses_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "fake")
    repo = FakeRepository()
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upserted is not None
    assert repo.upserted.grader_version == "fake_grader.v1"


@pytest.mark.asyncio
async def test_unknown_provider_falls_back_to_fake(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "INVALID_PROVIDER")
    repo = FakeRepository()
    with caplog.at_level(logging.WARNING, logger="src.worker"):
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upserted is not None
    assert repo.upserted.grader_version == "fake_grader.v1"
    assert any("unknown_provider" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# No-user-turn skip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_user_turns_skips_upsert(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.delenv("GRADING_PROVIDER", raising=False)
    repo = FakeRepository(session_row=_SESSION_ROW_NO_TURNS)
    with caplog.at_level(logging.WARNING, logger="src.worker"):
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upsert_call_count == 0
    assert any("no_user_turns_skip" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_no_user_turns_skips_even_with_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    repo = FakeRepository(session_row=_SESSION_ROW_NO_TURNS)
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upsert_call_count == 0


# ---------------------------------------------------------------------------
# Missing session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_missing_skips_upsert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRADING_PROVIDER", raising=False)
    repo = FakeRepository(session_row=None)
    await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    assert repo.upsert_call_count == 0


# ---------------------------------------------------------------------------
# LLM provider path — _build_grader_client raises (Patch 2A stub)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_provider_stub_falls_back_to_fake(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    repo = FakeRepository()
    with caplog.at_level(logging.WARNING, logger="src.worker"):
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    # _build_grader_client raises LLMGraderError → fallback
    assert repo.upserted is not None
    assert repo.upserted.grader_version == "fake_grader.v1"
    assert any("llm_failed_fallback" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# LLM provider path — mocked success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_provider_success_upserts_llm_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")

    mock_client = object()
    llm_result = _fake_llm_result()

    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(return_value=llm_result)),
    ):
        repo = FakeRepository()
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert repo.upserted is not None
    assert repo.upserted.grader_version == "llm_grader.v1"


@pytest.mark.asyncio
async def test_llm_provider_success_prepends_grader_info_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")

    mock_client = object()
    llm_result = _fake_llm_result()

    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(return_value=llm_result)),
    ):
        repo = FakeRepository()
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    corrections = repo.upserted.detailed_corrections
    assert len(corrections) >= 1
    marker = corrections[0]
    assert marker["type"] == "grader_info"
    assert marker["grader_version"] == "llm_grader.v1"
    assert marker["message"] == ""


# ---------------------------------------------------------------------------
# LLM provider path — error handling / fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_grade_error_falls_back_to_fake(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    mock_client = object()

    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=LLMGraderError("bad json"))),
    ):
        repo = FakeRepository()
        with caplog.at_level(logging.WARNING, logger="src.worker"):
            await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert repo.upserted is not None
    assert repo.upserted.grader_version == "fake_grader.v1"
    assert any("llm_failed_fallback" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_timeout_error_falls_back_to_fake(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("GRADING_PROVIDER", "llm")
    mock_client = object()

    with (
        patch("src.worker._build_grader_client", return_value=mock_client),
        patch("src.worker.llm_grade_with_client", new=AsyncMock(side_effect=asyncio.TimeoutError())),
    ):
        repo = FakeRepository()
        with caplog.at_level(logging.WARNING, logger="src.worker"):
            await process_session_completed_job(_BASE_PAYLOAD, repository=repo)

    assert repo.upserted is not None
    assert repo.upserted.grader_version == "fake_grader.v1"
    assert any("llm_failed_fallback" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Log safety: raw transcript text must not appear in log output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logs_do_not_include_transcript_text(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.delenv("GRADING_PROVIDER", raising=False)
    repo = FakeRepository()
    with caplog.at_level(logging.DEBUG, logger="src.worker"):
        await process_session_completed_job(_BASE_PAYLOAD, repository=repo)
    for record in caplog.records:
        assert "Hello, how are you?" not in record.message
        assert "I am fine" not in record.message
