from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add scripts/ so we can import scanner helpers directly.
_GRADING_WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_GRADING_WORKER_ROOT / "scripts"))

from reconciliation_scanner import (  # noqa: E402
    _count_user_turns,
    _parse_min_student_words_env,
)
from src.session_eligibility import (
    DEFAULT_MIN_STUDENT_WORDS,
    evaluate_grading_eligibility,
)


# ---------------------------------------------------------------------------
# _parse_min_student_words_env — pure helper
# ---------------------------------------------------------------------------

def test_min_words_none_returns_default():
    assert _parse_min_student_words_env(None) == DEFAULT_MIN_STUDENT_WORDS


def test_min_words_valid_int_string():
    assert _parse_min_student_words_env("30") == 30


def test_min_words_zero_allowed():
    assert _parse_min_student_words_env("0") == 0


def test_min_words_invalid_string_returns_default():
    assert _parse_min_student_words_env("not_a_number") == DEFAULT_MIN_STUDENT_WORDS


def test_min_words_negative_returns_default():
    assert _parse_min_student_words_env("-1") == DEFAULT_MIN_STUDENT_WORDS


def test_min_words_float_string_returns_default():
    assert _parse_min_student_words_env("12.5") == DEFAULT_MIN_STUDENT_WORDS


def test_min_words_empty_string_returns_default():
    assert _parse_min_student_words_env("") == DEFAULT_MIN_STUDENT_WORDS


# ---------------------------------------------------------------------------
# dry-run categorization (via evaluate_grading_eligibility — what scanner uses)
# ---------------------------------------------------------------------------

def _user_turn_raw(word_count: int, key: str = "type") -> str:
    text = " ".join(f"w{i}" for i in range(word_count))
    return json.dumps([{key: "USER_TURN", "payload": {"text": text}}])


def test_categorize_no_raw_backup():
    result = evaluate_grading_eligibility(None, min_student_words=25)
    assert not result.eligible
    assert result.reason == "no_raw_backup"


def test_categorize_invalid_raw():
    result = evaluate_grading_eligibility("not json at all", min_student_words=25)
    assert not result.eligible
    assert result.reason == "invalid_raw_backup"


def test_categorize_no_user_turns_ai_only():
    raw = json.dumps([{"type": "AI_TURN", "payload": {"text": "hello world"}}])
    result = evaluate_grading_eligibility(raw, min_student_words=25)
    assert not result.eligible
    assert result.reason == "no_user_turns"


def test_categorize_below_threshold():
    raw = _user_turn_raw(3)  # 3 words < 25
    result = evaluate_grading_eligibility(raw, min_student_words=25)
    assert not result.eligible
    assert result.reason == "insufficient_words"
    assert result.student_word_count == 3


def test_categorize_exactly_threshold_is_eligible():
    raw = _user_turn_raw(25)
    result = evaluate_grading_eligibility(raw, min_student_words=25)
    assert result.eligible
    assert result.reason == "eligible"
    assert result.student_word_count == 25


def test_categorize_above_threshold_is_eligible():
    raw = _user_turn_raw(30)
    result = evaluate_grading_eligibility(raw, min_student_words=25)
    assert result.eligible
    assert result.reason == "eligible"
    assert result.student_word_count == 30


def test_categorize_event_key_alias_eligible():
    raw = _user_turn_raw(25, key="event")
    result = evaluate_grading_eligibility(raw, min_student_words=25)
    assert result.eligible
    assert result.reason == "eligible"


def test_categorize_type_key_alias_eligible():
    raw = _user_turn_raw(25, key="type")
    result = evaluate_grading_eligibility(raw, min_student_words=25)
    assert result.eligible
    assert result.reason == "eligible"


# ---------------------------------------------------------------------------
# Summary counts — mixed candidates produce correct per-reason counts
# ---------------------------------------------------------------------------

def test_summary_counts_all_reasons():
    candidates = [
        None,                                                           # no_raw_backup
        "not json",                                                     # invalid_raw_backup
        json.dumps([{"type": "AI_TURN", "payload": {"text": "hi"}}]),  # no_user_turns
        _user_turn_raw(3),                                              # insufficient_words (< 25)
        _user_turn_raw(25),                                             # eligible (exactly 25)
        _user_turn_raw(30),                                             # eligible (> 25)
    ]

    counts: dict[str, int] = {
        "eligible": 0,
        "no_raw_backup": 0,
        "invalid_raw_backup": 0,
        "no_user_turns": 0,
        "insufficient_words": 0,
    }
    for raw in candidates:
        counts[evaluate_grading_eligibility(raw, min_student_words=25).reason] += 1

    assert counts["eligible"] == 2
    assert counts["no_raw_backup"] == 1
    assert counts["invalid_raw_backup"] == 1
    assert counts["no_user_turns"] == 1
    assert counts["insufficient_words"] == 1


def test_summary_no_transcript_text_in_counts():
    """Aggregated result of categorization must not expose transcript text."""
    candidates = [_user_turn_raw(3), _user_turn_raw(25)]
    reasons = [evaluate_grading_eligibility(r, min_student_words=25).reason for r in candidates]
    summary = str(reasons)
    assert "w0" not in summary
    assert "w1" not in summary


# ---------------------------------------------------------------------------
# Execute path unchanged — _count_user_turns still present and unchanged
# ---------------------------------------------------------------------------

def test_count_user_turns_callable():
    assert callable(_count_user_turns)


def test_count_user_turns_type_key_counted():
    raw = json.dumps([{"type": "USER_TURN", "payload": {"text": "hello"}}])
    assert _count_user_turns(raw) == 1


def test_count_user_turns_event_key_not_counted():
    """Execute path _count_user_turns does NOT recognize event-key alias.

    This is the known Patch 7G-4B limitation: execute path parity is
    Patch 7G-4C scope. This test documents that the defect is preserved
    intentionally in the execute path for now.
    """
    raw = json.dumps([{"event": "USER_TURN", "payload": {"text": "hello"}}])
    assert _count_user_turns(raw) == 0


def test_count_user_turns_none_returns_zero():
    assert _count_user_turns(None) == 0


def test_count_user_turns_invalid_json_returns_zero():
    assert _count_user_turns("not json") == 0


def test_dry_run_recognizes_event_key_execute_path_does_not():
    """Structural gap between dry-run (helper) and execute path (_count_user_turns).

    dry-run: evaluate_grading_eligibility handles event-key alias → eligible
    execute: _count_user_turns does NOT handle event-key alias → returns 0
    """
    raw = _user_turn_raw(25, key="event")
    assert evaluate_grading_eligibility(raw, min_student_words=25).eligible
    assert _count_user_turns(raw) == 0


# ---------------------------------------------------------------------------
# No transcript leakage — GradingEligibility must never expose transcript text
# ---------------------------------------------------------------------------

def test_no_transcript_leakage_in_eligible_result():
    secret = "SECRET TRANSCRIPT WORDS"
    raw = json.dumps([{"type": "USER_TURN", "payload": {"text": secret}}])
    result = evaluate_grading_eligibility(raw, min_student_words=1)
    result_str = str(result)
    assert "SECRET" not in result_str
    assert "TRANSCRIPT" not in result_str
    assert "WORDS" not in result_str
    assert secret not in result_str


def test_no_transcript_leakage_in_ineligible_result():
    secret = "SECRET TRANSCRIPT WORDS"
    raw = json.dumps([{"type": "USER_TURN", "payload": {"text": secret}}])
    result = evaluate_grading_eligibility(raw, min_student_words=100)
    result_str = str(result)
    assert "SECRET" not in result_str
    assert "TRANSCRIPT" not in result_str
    assert secret not in result_str
