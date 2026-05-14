from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from src.contracts import EvaluationInput, EvaluationTurn


def build_evaluation_input(
    session_row: Mapping[str, Any],
    raw_backup_json: Any | None = None,
) -> EvaluationInput:
    """Build the deterministic grading input from persisted session data.

    This function is intentionally pure: no DB, network, FastAPI, WebRTC, or TEN
    runtime dependency. It tolerates older/malformed raw backup shapes and only
    converts USER_TURN/AI_TURN entries with non-empty text.
    """

    raw_events = _coerce_event_list(
        raw_backup_json
        if raw_backup_json is not None
        else session_row.get("raw_backup_json")
    )
    ignored_events_count = 0
    empty_text_events_count = 0
    missing_timestamp_count = 0
    turns: list[EvaluationTurn] = []

    for event in raw_events:
        if not isinstance(event, Mapping):
            ignored_events_count += 1
            continue

        source = str(event.get("type") or event.get("event") or "").strip().upper()
        if source not in {"USER_TURN", "AI_TURN"}:
            ignored_events_count += 1
            continue

        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            payload = {}
        text = str(payload.get("text") or event.get("text") or "").strip()
        if not text:
            empty_text_events_count += 1
            ignored_events_count += 1
            continue

        timing = _extract_timing_ms(payload)
        if all(timing.get(key) is None for key in ("start_ms", "end_ms", "duration_ms")):
            missing_timestamp_count += 1

        turns.append(
            EvaluationTurn(
                seq=len(turns),
                speaker="student" if source == "USER_TURN" else "assistant",
                text=text,
                source=source,  # type: ignore[arg-type]
                start_ms=timing["start_ms"],
                end_ms=timing["end_ms"],
                duration_ms=timing["duration_ms"],
            )
        )

    user_turn_count = sum(1 for turn in turns if turn.speaker == "student")
    assistant_turn_count = sum(1 for turn in turns if turn.speaker == "assistant")
    total_student_words = sum(
        len(turn.text.split()) for turn in turns if turn.speaker == "student"
    )

    return EvaluationInput(
        session_id=_coerce_uuid(session_row.get("id") or session_row.get("session_id")),
        user_id=_coerce_optional_uuid(session_row.get("user_id")),
        lesson_id=_coerce_optional_uuid(session_row.get("lesson_id")),
        raw_event_count=len(raw_events),
        turns=turns,
        quality_signals={
            "ignored_events_count": ignored_events_count,
            "empty_text_events_count": empty_text_events_count,
            "missing_timestamp_count": missing_timestamp_count,
            "user_turn_count": user_turn_count,
            "assistant_turn_count": assistant_turn_count,
            "student_word_count": total_student_words,
            "has_student_turns": user_turn_count > 0,
            "has_assistant_turns": assistant_turn_count > 0,
        },
    )


def _coerce_event_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return _coerce_event_list(json.loads(value))
        except json.JSONDecodeError:
            return []
    if isinstance(value, Mapping):
        for key in ("logs", "events", "raw_backup_json"):
            if key not in value:
                continue
            nested = value[key]
            if isinstance(nested, str):
                try:
                    nested = json.loads(nested)
                except json.JSONDecodeError:
                    return []
            return _coerce_event_list(nested)
    return []


def _extract_timing_ms(payload: Mapping[str, Any]) -> dict[str, int | None]:
    start_ms = _coerce_optional_int(payload.get("start_ms"))
    end_ms = _coerce_optional_int(payload.get("end_ms"))
    duration_ms = _coerce_optional_int(payload.get("duration_ms"))

    words = payload.get("word_timestamps")
    if isinstance(words, list) and words:
        starts: list[int] = []
        ends: list[int] = []
        for word in words:
            if not isinstance(word, Mapping):
                continue
            start = _coerce_optional_int(word.get("start_ms", word.get("start")))
            end = _coerce_optional_int(word.get("end_ms", word.get("end")))
            if start is not None:
                starts.append(start)
            if end is not None:
                ends.append(end)
        if start_ms is None and starts:
            start_ms = min(starts)
        if end_ms is None and ends:
            end_ms = max(ends)

    audio = payload.get("audio")
    if isinstance(audio, Mapping) and duration_ms is None:
        duration_ms = _coerce_optional_int(audio.get("audio_ms"))

    if duration_ms is None and start_ms is not None and end_ms is not None:
        duration_ms = max(end_ms - start_ms, 0)

    return {"start_ms": start_ms, "end_ms": end_ms, "duration_ms": duration_ms}


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _coerce_optional_uuid(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    return _coerce_uuid(value)


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    if number < 60 and not float(number).is_integer():
        number *= 1000
    return int(round(number))
