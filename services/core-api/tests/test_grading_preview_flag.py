from __future__ import annotations

import pytest

from src.services.session_service import _get_min_student_words, _is_dev_preview_grading


@pytest.mark.parametrize(
    ("provider", "grader_version"),
    [
        ("fake", "fake_grader.v1"),
        (" Fake ", "llm_grader.v1"),
        ("llm", "fake_grader.v1"),
        ("llm", " Fake_Grader.V1 "),
        ("llm", "legacy"),
        (None, "llm_grader.v1"),
        ("", "llm_grader.v1"),
        ("unknown", "llm_grader.v1"),
    ],
)
def test_is_dev_preview_grading_marks_fake_legacy_or_unknown_as_preview(
    provider: str | None,
    grader_version: str,
) -> None:
    assert _is_dev_preview_grading(provider, grader_version) is True


@pytest.mark.parametrize(
    ("provider", "grader_version"),
    [
        ("llm", "llm_grader.v1"),
        ("LLM", "llm_grader.v2"),
    ],
)
def test_is_dev_preview_grading_marks_real_llm_grade_as_non_preview(
    provider: str,
    grader_version: str,
) -> None:
    assert _is_dev_preview_grading(provider, grader_version) is False


def test_grading_status_default_min_student_words_allows_beginner_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRADING_MIN_STUDENT_WORDS", raising=False)
    assert _get_min_student_words() == 15
