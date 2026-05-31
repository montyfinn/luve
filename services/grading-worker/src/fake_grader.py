from __future__ import annotations

from src.contracts import EvaluationInput, GradingResult, SkillFeedback


def fake_grade(input_data: EvaluationInput) -> GradingResult:
    """Deterministic fake grader for wiring tests; does not call any LLM."""

    student_turns = [turn for turn in input_data.turns if turn.speaker == "student"]
    student_words = sum(len(turn.text.split()) for turn in student_turns)
    ignored_events = int(input_data.quality_signals.get("ignored_events_count") or 0)

    fluency_score = _clamp_score(5.0 + min(len(student_turns), 5) * 0.6)
    grammar_score = _clamp_score(6.0 + min(student_words, 40) / 20.0)
    vocab_score = _clamp_score(5.5 + min(_unique_student_words(student_turns), 30) / 15.0)
    uncertain_turns = int(input_data.quality_signals.get("uncertain_student_turn_count") or 0)
    pronunciation_score = None if not student_turns else _clamp_score(7.0 - min(uncertain_turns, 4) * 0.4)
    if ignored_events:
        fluency_score = _clamp_score(fluency_score - min(ignored_events, 5) * 0.1)

    overall_score = round((fluency_score + grammar_score + vocab_score) / 3.0, 2)

    return GradingResult(
        session_id=input_data.session_id,
        overall_score=overall_score,
        fluency_score=fluency_score,
        grammar_score=grammar_score,
        vocab_score=vocab_score,
        pronunciation_score=pronunciation_score,
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
        provider="fake",
        skill_feedback=_build_fake_skill_feedback(
            fluency_score=fluency_score,
            grammar_score=grammar_score,
            vocab_score=vocab_score,
            pronunciation_score=pronunciation_score,
        ),
        input_quality=dict(input_data.quality_signals),
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


def _build_fake_skill_feedback(
    *,
    fluency_score: float,
    grammar_score: float,
    vocab_score: float,
    pronunciation_score: float | None,
) -> list[SkillFeedback]:
    pronunciation_status = "scored" if pronunciation_score is not None else "insufficient_evidence"
    return [
        SkillFeedback(
            skill="fluency",
            score=fluency_score,
            summary="Basic fluency estimate from turn count and ignored event volume.",
            suggestion="Use the LLM grader before showing this as a learner-facing fluency grade.",
        ),
        SkillFeedback(
            skill="grammar",
            score=grammar_score,
            summary="Basic grammar estimate from transcript length only.",
            suggestion="Use the LLM grader for sentence-level grammar feedback.",
        ),
        SkillFeedback(
            skill="vocabulary",
            score=vocab_score,
            summary="Basic vocabulary estimate from unique word count.",
            suggestion="Use the LLM grader for vocabulary range and word-choice coaching.",
        ),
        SkillFeedback(
            skill="pronunciation_clarity",
            score=pronunciation_score,
            status=pronunciation_status,
            summary=(
                "Estimated from STT uncertainty signals."
                if pronunciation_score is not None
                else "No reliable pronunciation evidence was available."
            ),
            suggestion="Use audio/STT confidence signals only as pronunciation evidence, not grammar text alone.",
        ),
    ]
