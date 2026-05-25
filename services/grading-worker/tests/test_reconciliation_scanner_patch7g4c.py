from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add scripts/ so we can import scanner helpers directly.
_GRADING_WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_GRADING_WORKER_ROOT / "scripts"))

from reconciliation_scanner import run  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _args(
    execute: bool = True,
    min_student_words: int = 25,
    limit: int = 50,
    grace_minutes: int = 60,  # large so test rows are never grace-window skipped
    since: str | None = None,
    session_id: str | None = None,
    sleep_ms: int = 0,
) -> argparse.Namespace:
    return argparse.Namespace(
        execute=execute,
        min_student_words=min_student_words,
        limit=limit,
        grace_minutes=grace_minutes,
        since=since,
        session_id=session_id,
        sleep_ms=sleep_ms,
    )


class _Row:
    """Minimal asyncpg-like record for scanner tests."""
    _SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeee001"

    def __init__(self, raw_json: str | None, hours_ago: int = 2):
        self._raw = raw_json
        self._ended = datetime.now(timezone.utc) - timedelta(hours=hours_ago)

    def __getitem__(self, key: str):
        if key == "session_id":
            return self._SID
        if key == "ended_at":
            return self._ended
        if key == "raw_json":
            return self._raw
        raise KeyError(key)


def _eligible_raw(words: int = 25, key: str = "type") -> str:
    text = " ".join(f"w{i}" for i in range(words))
    return json.dumps([{key: "USER_TURN", "payload": {"text": text}}])


def _run_scanner(args: argparse.Namespace, rows: list, mock_job: AsyncMock) -> int:
    """Run scanner against fake rows with mocked DB and process_session_completed_job."""
    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=rows)
    mock_conn.close = AsyncMock()

    with patch("reconciliation_scanner.asyncpg.connect", AsyncMock(return_value=mock_conn)), \
         patch("reconciliation_scanner.GradingRepository"), \
         patch("reconciliation_scanner.process_session_completed_job", mock_job), \
         patch.dict("os.environ", {"DATABASE_URL": "postgresql://fake/testdb"}):
        return asyncio.run(run(args))


# ---------------------------------------------------------------------------
# Execute path: ineligible candidates must NOT call process_session_completed_job
# ---------------------------------------------------------------------------

def test_execute_skips_no_raw_backup():
    mock_job = AsyncMock()
    _run_scanner(_args(execute=True), [_Row(None)], mock_job)
    assert mock_job.call_count == 0


def test_execute_skips_invalid_raw_backup():
    mock_job = AsyncMock()
    _run_scanner(_args(execute=True), [_Row("not-valid-json")], mock_job)
    assert mock_job.call_count == 0


def test_execute_skips_no_user_turns():
    raw = json.dumps([{"type": "AI_TURN", "payload": {"text": "hello world"}}])
    mock_job = AsyncMock()
    _run_scanner(_args(execute=True), [_Row(raw)], mock_job)
    assert mock_job.call_count == 0


def test_execute_skips_insufficient_words():
    raw = _eligible_raw(words=3)  # 3 < 25
    mock_job = AsyncMock()
    _run_scanner(_args(execute=True, min_student_words=25), [_Row(raw)], mock_job)
    assert mock_job.call_count == 0


# ---------------------------------------------------------------------------
# Execute path: eligible candidates must call process_session_completed_job
# ---------------------------------------------------------------------------

def test_execute_processes_exactly_threshold():
    raw = _eligible_raw(words=25)  # exactly at threshold
    mock_job = AsyncMock()
    _run_scanner(_args(execute=True, min_student_words=25), [_Row(raw)], mock_job)
    assert mock_job.call_count == 1


def test_execute_processes_above_threshold():
    raw = _eligible_raw(words=30)  # 30 > 25
    mock_job = AsyncMock()
    _run_scanner(_args(execute=True, min_student_words=25), [_Row(raw)], mock_job)
    assert mock_job.call_count == 1


def test_execute_processes_event_key_alias():
    # "event" key alias handled by the helper — execute path now recognizes it.
    raw = _eligible_raw(words=25, key="event")
    mock_job = AsyncMock()
    _run_scanner(_args(execute=True, min_student_words=25), [_Row(raw)], mock_job)
    assert mock_job.call_count == 1


# ---------------------------------------------------------------------------
# Dry-run must never call process_session_completed_job for any candidate
# ---------------------------------------------------------------------------

def test_dryrun_never_calls_job_for_eligible():
    raw = _eligible_raw(words=30)
    mock_job = AsyncMock()
    _run_scanner(_args(execute=False, min_student_words=25), [_Row(raw)], mock_job)
    assert mock_job.call_count == 0


# ---------------------------------------------------------------------------
# Summary counts with mixed candidates + no transcript leakage
# ---------------------------------------------------------------------------

def test_execute_summary_counts_mixed_candidates(capsys):
    ai_only = json.dumps([{"type": "AI_TURN", "payload": {"text": "hello world"}}])
    candidates = [
        _Row(None),                     # no_raw_backup (belt-and-suspenders)
        _Row("not-valid-json"),         # invalid_raw_backup
        _Row(ai_only),                  # no_user_turns
        _Row(_eligible_raw(words=3)),   # insufficient_words (3 < 25)
        _Row(_eligible_raw(words=25)),  # eligible
        _Row(_eligible_raw(words=30)),  # eligible
    ]
    mock_job = AsyncMock()
    _run_scanner(_args(execute=True, min_student_words=25), candidates, mock_job)

    assert mock_job.call_count == 2

    out = capsys.readouterr().out
    assert "candidates_seen=6" in out
    assert "processed=2" in out
    assert "skipped_no_raw_backup=1" in out
    assert "skipped_invalid_raw=1" in out
    assert "skipped_no_user_turns=1" in out
    assert "skipped_insufficient_words=1" in out
    # No transcript text in output
    assert "w0" not in out
    assert "w1" not in out
    assert "hello world" not in out


# ---------------------------------------------------------------------------
# min-student-words override affects execute path
# ---------------------------------------------------------------------------

def test_execute_min_words_high_threshold_skips():
    raw = _eligible_raw(words=10)  # 10 < 50 threshold
    mock_job = AsyncMock()
    _run_scanner(_args(execute=True, min_student_words=50), [_Row(raw)], mock_job)
    assert mock_job.call_count == 0


def test_execute_min_words_low_threshold_allows():
    raw = _eligible_raw(words=10)  # 10 >= 5 threshold
    mock_job = AsyncMock()
    _run_scanner(_args(execute=True, min_student_words=5), [_Row(raw)], mock_job)
    assert mock_job.call_count == 1
