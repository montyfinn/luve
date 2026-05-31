"""
Patch 7G-8C-1: Mocked tests for GradingRepository.log_grading_skip().

All tests use unittest.mock to replace asyncpg.connect — no live DB, no
docker, no psql. The repository pattern (open connection, try/finally close)
is tested in isolation.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.grading_repository import GradingRepository, _REQUIRED_GRADING_RESULTS_COLUMNS

DATABASE_URL = "postgresql://user:pass@localhost/testdb"
_SKIP_REASON = "insufficient_words"
_SESSION_ID = uuid4()


def _make_repo() -> GradingRepository:
    return GradingRepository(DATABASE_URL)


def _mock_connection() -> tuple[MagicMock, MagicMock]:
    """Return (mock_connect, mock_conn) with execute and close as AsyncMocks."""
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(return_value=None)
    mock_conn.fetchrow = AsyncMock(return_value={"session_id": _SESSION_ID})
    mock_conn.close = AsyncMock(return_value=None)
    mock_connect = AsyncMock(return_value=mock_conn)
    return mock_connect, mock_conn


def _mock_schema_connection(
    *,
    skip_log_exists: bool,
    present_columns: set[str] | None = None,
) -> tuple[MagicMock, MagicMock]:
    mock_conn = MagicMock()
    mock_conn.fetchval = AsyncMock(return_value=skip_log_exists)
    mock_conn.fetch = AsyncMock(
        return_value=[
            {"column_name": column}
            for column in (present_columns or _REQUIRED_GRADING_RESULTS_COLUMNS)
        ]
    )
    mock_conn.close = AsyncMock(return_value=None)
    mock_connect = AsyncMock(return_value=mock_conn)
    return mock_connect, mock_conn


@pytest.mark.asyncio
async def test_log_grading_skip_inserts_with_expected_params() -> None:
    mock_connect, mock_conn = _mock_connection()
    with patch("src.grading_repository.asyncpg.connect", mock_connect):
        repo = _make_repo()
        await repo.log_grading_skip(
            session_id=_SESSION_ID,
            reason=_SKIP_REASON,
            source="worker",
            student_word_count=12,
            min_words_threshold=25,
        )

    mock_conn.execute.assert_awaited_once()
    call_args = mock_conn.execute.call_args
    sql: str = call_args[0][0]
    assert "INSERT INTO grading_skip_log" in sql
    assert "ON CONFLICT (session_id) DO UPDATE" in sql

    params = call_args[0][1:]
    assert params == (_SESSION_ID, _SKIP_REASON, "worker", 12, 25)
    mock_conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_grading_skip_defaults_source_worker() -> None:
    mock_connect, mock_conn = _mock_connection()
    with patch("src.grading_repository.asyncpg.connect", mock_connect):
        repo = _make_repo()
        await repo.log_grading_skip(
            session_id=_SESSION_ID,
            reason="no_user_turns",
        )

    call_args = mock_conn.execute.call_args
    params = call_args[0][1:]
    assert params[2] == "worker"


@pytest.mark.asyncio
async def test_log_grading_skip_allows_none_counts_for_non_word_reason() -> None:
    mock_connect, mock_conn = _mock_connection()
    with patch("src.grading_repository.asyncpg.connect", mock_connect):
        repo = _make_repo()
        await repo.log_grading_skip(
            session_id=_SESSION_ID,
            reason="no_raw_backup",
            source="scanner",
            student_word_count=None,
            min_words_threshold=None,
        )

    call_args = mock_conn.execute.call_args
    params = call_args[0][1:]
    assert params == (_SESSION_ID, "no_raw_backup", "scanner", None, None)


@pytest.mark.asyncio
async def test_log_grading_skip_closes_connection_on_execute_error() -> None:
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(side_effect=RuntimeError("db error"))
    mock_conn.close = AsyncMock(return_value=None)
    mock_connect = AsyncMock(return_value=mock_conn)

    with patch("src.grading_repository.asyncpg.connect", mock_connect):
        repo = _make_repo()
        with pytest.raises(RuntimeError, match="db error"):
            await repo.log_grading_skip(
                session_id=_SESSION_ID,
                reason=_SKIP_REASON,
            )

    mock_conn.close.assert_awaited_once()


def test_log_grading_skip_does_not_accept_raw_payload_arguments() -> None:
    sig = inspect.signature(GradingRepository.log_grading_skip)
    param_names = list(sig.parameters.keys())

    assert param_names == [
        "self",
        "session_id",
        "reason",
        "source",
        "student_word_count",
        "min_words_threshold",
    ]

    forbidden = {"raw_backup_json", "transcript", "audio", "metadata", "payload"}
    assert not forbidden.intersection(param_names)


@pytest.mark.asyncio
async def test_assert_schema_ready_passes_when_required_objects_exist() -> None:
    mock_connect, mock_conn = _mock_schema_connection(skip_log_exists=True)
    with patch("src.grading_repository.asyncpg.connect", mock_connect):
        repo = _make_repo()
        await repo.assert_schema_ready()

    mock_conn.fetchval.assert_awaited_once()
    mock_conn.fetch.assert_awaited_once()
    mock_conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_assert_schema_ready_fails_when_skip_log_is_missing() -> None:
    mock_connect, _mock_conn = _mock_schema_connection(skip_log_exists=False)
    with patch("src.grading_repository.asyncpg.connect", mock_connect):
        repo = _make_repo()
        with pytest.raises(RuntimeError, match="grading_skip_log"):
            await repo.assert_schema_ready()


@pytest.mark.asyncio
async def test_assert_schema_ready_fails_when_required_column_is_missing() -> None:
    present_columns = set(_REQUIRED_GRADING_RESULTS_COLUMNS)
    present_columns.remove("score_schema_version")
    mock_connect, _mock_conn = _mock_schema_connection(
        skip_log_exists=True,
        present_columns=present_columns,
    )

    with patch("src.grading_repository.asyncpg.connect", mock_connect):
        repo = _make_repo()
        with pytest.raises(RuntimeError, match="score_schema_version"):
            await repo.assert_schema_ready()


@pytest.mark.asyncio
async def test_mark_grading_processing_skips_existing_graded_rows() -> None:
    mock_connect, mock_conn = _mock_connection()
    with patch("src.grading_repository.asyncpg.connect", mock_connect):
        repo = _make_repo()
        result = await repo.mark_grading_processing(
            session_id=_SESSION_ID,
            provider="fake",
        )

    assert result is True
    mock_conn.fetchrow.assert_awaited_once()
    sql: str = mock_conn.fetchrow.call_args[0][0]
    assert "WHERE grading_results.status <> 'graded'" in sql
    assert "RETURNING session_id" in sql
    assert mock_conn.fetchrow.call_args[0][1:] == (_SESSION_ID, "fake")


@pytest.mark.asyncio
async def test_mark_grading_processing_returns_false_when_existing_grade_is_preserved() -> None:
    mock_connect, mock_conn = _mock_connection()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    with patch("src.grading_repository.asyncpg.connect", mock_connect):
        repo = _make_repo()
        result = await repo.mark_grading_processing(
            session_id=_SESSION_ID,
            provider="fake",
        )

    assert result is False


@pytest.mark.asyncio
async def test_mark_grading_failed_skips_existing_graded_rows() -> None:
    mock_connect, mock_conn = _mock_connection()
    with patch("src.grading_repository.asyncpg.connect", mock_connect):
        repo = _make_repo()
        await repo.mark_grading_failed(
            session_id=_SESSION_ID,
            provider="llm",
            error_code="RuntimeError",
            error_message="temporary failure",
        )

    mock_conn.execute.assert_awaited_once()
    sql: str = mock_conn.execute.call_args[0][0]
    assert "WHERE grading_results.status <> 'graded'" in sql
