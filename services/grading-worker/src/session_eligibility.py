from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DEFAULT_MIN_STUDENT_WORDS = 25
HARD_EXCLUDE_STT_REASONS = frozenset(
    {
        "verification_language_mismatch",
        "non_english_verification_failed",
        "non_target_language",
        "mixed_non_english",
        "hallucination_suspected",
        "empty_transcript",
        "no_speech_detected",
        "background_noise",
        "weak_mixed_language_english",
    }
)


@dataclass(frozen=True)
class GradingEligibility:
    eligible: bool
    reason: str
    user_turn_count: int
    student_word_count: int | None
    reliable_student_word_count: int | None = None


def parse_raw_backup_events(raw_backup_json: Any) -> list[Any] | None:
    """Normalize raw_backup_json to a flat list of events.

    Returns None for None input or inputs not parseable as a JSON array.
    Returns a list (possibly empty) for valid list or JSON-array-string input.
    Per-event strings are not decoded here; callers use _decode_event for that.

    Reason codes produced by evaluate_grading_eligibility:
        no_raw_backup       — input is None
        invalid_raw_backup  — input is present but not a parseable JSON array
    """
    if raw_backup_json is None:
        return None
    if isinstance(raw_backup_json, list):
        return raw_backup_json
    if isinstance(raw_backup_json, str):
        try:
            parsed = json.loads(raw_backup_json)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(parsed, list):
            return None
        return parsed
    return None


def get_event_kind(event: Any) -> str | None:
    """Return normalized event type (e.g. 'USER_TURN'), or None if unavailable.

    Checks 'type' key first, falls back to 'event' key.
    Requires event to be a Mapping; returns None for all other inputs.
    """
    if not isinstance(event, Mapping):
        return None
    raw = event.get("type") or event.get("event")
    if not raw:
        return None
    return str(raw).strip().upper()


def get_event_text(event: Any) -> str:
    """Extract student text from event payload.

    Returns empty string if:
    - event is not a Mapping
    - payload key is absent or not a Mapping
    - payload.text is absent or not a str

    Never returns transcript content in metadata fields; callers use this
    for word counting only.
    """
    if not isinstance(event, Mapping):
        return ""
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return ""
    text = payload.get("text")
    if not isinstance(text, str):
        return ""
    return text.strip()


def get_event_grading_text(event: Any) -> str:
    """Extract the text that should count as grading evidence."""
    if not isinstance(event, Mapping):
        return ""
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return ""
    english_segment = payload.get("english_segment")
    if isinstance(english_segment, str) and english_segment.strip():
        return english_segment.strip()
    return get_event_text(event)


def get_event_payload(event: Any) -> Mapping[str, Any]:
    if not isinstance(event, Mapping):
        return {}
    payload = event.get("payload")
    return payload if isinstance(payload, Mapping) else {}


def _decode_event(event: Any) -> Any:
    """If event is a JSON-encoded Mapping string, decode and return it.

    Returns the original value unchanged for non-strings or non-Mapping JSON.
    Swallows JSON decode errors silently — invalid per-event strings are treated
    as non-Mapping and ignored by kind/text functions.
    """
    if not isinstance(event, str):
        return event
    try:
        decoded = json.loads(event)
    except (json.JSONDecodeError, ValueError):
        return event
    return decoded if isinstance(decoded, Mapping) else event


def count_user_turns(raw_backup_json: Any) -> int | None:
    """Count USER_TURN events in the event log.

    Returns None if raw_backup_json is None or cannot be parsed as a JSON array.
    Returns an int (possibly 0) for all other valid inputs.
    """
    events = parse_raw_backup_events(raw_backup_json)
    if events is None:
        return None
    return sum(
        1 for e in events if get_event_kind(_decode_event(e)) == "USER_TURN"
    )


def count_student_words(raw_backup_json: Any) -> int | None:
    """Sum word counts across USER_TURN event texts.

    Returns None if raw_backup_json is None or cannot be parsed as a JSON array.
    Returns an int (possibly 0) for all other valid inputs.
    AI_TURN events are excluded.
    """
    events = parse_raw_backup_events(raw_backup_json)
    if events is None:
        return None
    total = 0
    for event in events:
        event = _decode_event(event)
        if get_event_kind(event) != "USER_TURN":
            continue
        text = get_event_text(event)
        if text:
            total += len(text.split())
    return total


def is_reliable_student_event(event: Any) -> bool:
    """Return whether a USER_TURN is eligible for grading input.

    The historical name is kept to avoid broad call-site churn. In current
    policy, uncertain learner English is still gradeable unless hard-excluded
    by explicit metadata.
    """
    event = _decode_event(event)
    if get_event_kind(event) != "USER_TURN":
        return False
    if not get_event_grading_text(event):
        return False

    payload = get_event_payload(event)
    raw_reasons = payload.get("uncertainty_reasons")
    reasons = {
        item.strip()
        for item in raw_reasons
        if isinstance(item, str) and item.strip()
    } if isinstance(raw_reasons, list) else set()
    excluded_reason = str(
        payload.get("excluded_from_grading_reason") or ""
    ).strip()
    turn_language_type = str(payload.get("turn_language_type") or "").strip().lower()

    if payload.get("grading_eligible") is False:
        return False
    if excluded_reason:
        return False
    if turn_language_type in {"vietnamese", "noise"}:
        return False
    if reasons.intersection(HARD_EXCLUDE_STT_REASONS):
        return False
    return True


def count_reliable_student_words(raw_backup_json: Any) -> int | None:
    events = parse_raw_backup_events(raw_backup_json)
    if events is None:
        return None
    total = 0
    for event in events:
        event = _decode_event(event)
        if not is_reliable_student_event(event):
            continue
        text = get_event_grading_text(event)
        if text:
            total += len(text.split())
    return total


def evaluate_grading_eligibility(
    raw_backup_json: Any,
    min_student_words: int = DEFAULT_MIN_STUDENT_WORDS,
) -> GradingEligibility:
    """Determine whether a session should be submitted for grading.

    Checks in order:
    1. raw_backup_json is None      → no_raw_backup
    2. raw_backup_json unparseable  → invalid_raw_backup
    3. no USER_TURN events found    → no_user_turns
    4. reliable student words < min → insufficient_words
    5. passes all gates             → eligible

    min_student_words=0 disables the word-count gate; any session with at
    least one reliable USER_TURN and parseable raw data is then eligible.

    GradingEligibility never exposes transcript text.
    """
    if raw_backup_json is None:
        return GradingEligibility(
            eligible=False,
            reason="no_raw_backup",
            user_turn_count=0,
            student_word_count=None,
            reliable_student_word_count=None,
        )

    events = parse_raw_backup_events(raw_backup_json)
    if events is None:
        return GradingEligibility(
            eligible=False,
            reason="invalid_raw_backup",
            user_turn_count=0,
            student_word_count=None,
            reliable_student_word_count=None,
        )

    user_turn_count = 0
    reliable_student_word_count = 0
    reliable_user_turn_count = 0
    for event in events:
        event = _decode_event(event)
        if get_event_kind(event) != "USER_TURN":
            continue
        user_turn_count += 1
        if is_reliable_student_event(event):
            reliable_user_turn_count += 1
            text = get_event_grading_text(event)
            if text:
                reliable_student_word_count += len(text.split())

    if user_turn_count == 0:
        return GradingEligibility(
            eligible=False,
            reason="no_user_turns",
            user_turn_count=0,
            student_word_count=0,
            reliable_student_word_count=0,
        )

    if reliable_user_turn_count == 0 or reliable_student_word_count < min_student_words:
        return GradingEligibility(
            eligible=False,
            reason="insufficient_words",
            user_turn_count=user_turn_count,
            student_word_count=reliable_student_word_count,
            reliable_student_word_count=reliable_student_word_count,
        )

    return GradingEligibility(
        eligible=True,
        reason="eligible",
        user_turn_count=user_turn_count,
        student_word_count=reliable_student_word_count,
        reliable_student_word_count=reliable_student_word_count,
    )
