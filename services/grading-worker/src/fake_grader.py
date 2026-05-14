from __future__ import annotations

from src.contracts import EvaluationInput, GradingResult


def fake_grade(input_data: EvaluationInput) -> GradingResult:
    """Deterministic fake grader for wiring tests; does not call any LLM."""

    student_turns = [turn for turn in input_data.turns if turn.speaker == "student"]
    student_words = sum(len(turn.text.split()) for turn in student_turns)
    ignored_events = int(input_data.quality_signals.get("ignored_events_count") or 0)

    fluency_score = _clamp_score(5.0 + min(len(student_turns), 5) * 0.6)
    grammar_score = _clamp_score(6.0 + min(student_words, 40) / 20.0)
    vocab_score = _clamp_score(5.5 + min(_unique_student_words(student_turns), 30) / 15.0)
    if ignored_events:
        fluency_score = _clamp_score(fluency_score - min(ignored_events, 5) * 0.1)

    overall_score = round((fluency_score + grammar_score + vocab_score) / 3.0, 2)

    return GradingResult(
        session_id=input_data.session_id,
        overall_score=overall_score,
        fluency_score=fluency_score,
        grammar_score=grammar_score,
        vocab_score=vocab_score,
        detailed_corrections=[
            {
                "type": "fake_grader_notice",
                "message": "Deterministic placeholder only; no LLM grading was performed.",
            },
            {
                "type": "input_quality",
                "raw_event_count": input_data.raw_event_count,
                "turn_count": len(input_data.turns),
                "ignored_events_count": ignored_events,
            },
        ],
        ai_summary_feedback=(
            "Fake grading completed. Replace fake_grader.v1 with a real "
            "LLM-backed grader after the worker flow is verified."
        ),
    )


def _unique_student_words(student_turns: list[object]) -> int:
    words: set[str] = set()
    for turn in student_turns:
        text = getattr(turn, "text", "")
        for word in text.lower().split():
            cleaned = "".join(ch for ch in word if ch.isalpha())
            if cleaned:
                words.add(cleaned)
    return len(words)


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 2)
