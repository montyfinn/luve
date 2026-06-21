"""Default saved-session history hides sessions with no student content.

Pure-predicate tests for `_session_has_student_content` (no DB): a session is
useful for history iff it has at least one eligible student word, reusing the
existing `_compute_student_word_count` semantics.
"""

from src.services.session_service import _session_has_student_content


def _user_turn(text: str, *, grading_eligible: bool | None = None) -> dict:
    payload: dict = {"text": text}
    if grading_eligible is not None:
        payload["grading_eligible"] = grading_eligible
    return {"type": "USER_TURN", "payload": payload}


def test_session_with_student_words_is_kept():
    assert _session_has_student_content([_user_turn("I went to Da Nang")]) is True


def test_none_backup_is_hidden():
    assert _session_has_student_content(None) is False


def test_empty_array_backup_is_hidden():
    assert _session_has_student_content([]) is False


def test_user_turn_with_empty_text_is_hidden():
    assert _session_has_student_content([_user_turn("   ")]) is False


def test_grading_ineligible_only_turn_is_hidden():
    assert _session_has_student_content([_user_turn("hi", grading_eligible=False)]) is False


def test_json_string_backup_with_content_is_kept():
    import json

    assert _session_has_student_content(json.dumps([_user_turn("hello there")])) is True
