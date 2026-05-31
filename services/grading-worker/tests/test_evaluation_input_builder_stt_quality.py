from __future__ import annotations

from uuid import UUID

from src.evaluation_input_builder import build_evaluation_input


SESSION_ID = UUID("00000000-0000-0000-0000-000000000123")


def test_builder_keeps_uncertain_student_turns_with_caution_metadata() -> None:
    raw_backup_json = [
        {
            "type": "USER_TURN",
            "payload": {
                "text": "I very like this lesson",
                "stt_quality": "uncertain",
                "uncertainty_reasons": [
                    "low_average_logprob",
                    "possible_stt_autocorrection",
                ],
                "possible_stt_autocorrection": True,
            },
        },
        {"type": "AI_TURN", "payload": {"text": "Good, keep practicing."}},
    ]

    result = build_evaluation_input(
        {"id": SESSION_ID, "user_id": None, "lesson_id": None},
        raw_backup_json=raw_backup_json,
    )

    student_turns = [turn for turn in result.turns if turn.speaker == "student"]
    assert len(student_turns) == 1
    assert student_turns[0].text == "I very like this lesson"
    assert student_turns[0].stt_quality == "uncertain"
    assert student_turns[0].stt_uncertainty_reasons == [
        "low_average_logprob",
        "possible_stt_autocorrection",
    ]
    assert student_turns[0].possible_stt_autocorrection is True
    assert result.quality_signals["unreliable_student_turn_count"] == 0
    assert result.quality_signals["excluded_student_turn_count"] == 0
    assert result.quality_signals["uncertain_student_turn_count"] == 1


def test_builder_uses_english_segment_for_mixed_gradeable_turn() -> None:
    raw_backup_json = [
        {
            "type": "USER_TURN",
            "payload": {
                "text": "I want to practice",
                "english_segment": "I want to practice",
                "original_stt_text": "I want to practice tiếng Anh",
                "stt_quality": "uncertain",
                "uncertainty_reasons": ["mixed_language_filtered"],
                "grading_eligible": True,
            },
        }
    ]

    result = build_evaluation_input(
        {"id": SESSION_ID, "user_id": None, "lesson_id": None},
        raw_backup_json=raw_backup_json,
    )

    student_turns = [turn for turn in result.turns if turn.speaker == "student"]
    assert len(student_turns) == 1
    assert student_turns[0].text == "I want to practice"
    assert student_turns[0].stt_uncertainty_reasons == ["mixed_language_filtered"]
    assert result.quality_signals["student_word_count"] == 4


def test_builder_filters_hard_excluded_student_turns_from_grading_input() -> None:
    raw_backup_json = [
        {
            "type": "USER_TURN",
            "payload": {
                "text": "What is",
                "stt_quality": "uncertain",
                "uncertainty_reasons": ["weak_mixed_language_english"],
                "grading_eligible": False,
                "excluded_from_grading_reason": "weak_mixed_language_english",
            },
        },
        {
            "type": "USER_TURN",
            "payload": {
                "text": "I go school yesterday and I want improve speaking",
                "stt_quality": "confident",
            },
        },
    ]

    result = build_evaluation_input(
        {"id": SESSION_ID, "user_id": None, "lesson_id": None},
        raw_backup_json=raw_backup_json,
    )

    student_turns = [turn for turn in result.turns if turn.speaker == "student"]
    assert len(student_turns) == 1
    assert student_turns[0].text == "I go school yesterday and I want improve speaking"
    assert result.quality_signals["unreliable_student_turn_count"] == 1
    assert result.quality_signals["excluded_student_turn_count"] == 1
    assert result.quality_signals["student_word_count"] == 9


def test_builder_marks_soft_hallucination_as_prompt_caution() -> None:
    raw_backup_json = [
        {
            "type": "USER_TURN",
            "payload": {
                "text": "I want improve speaking because my English not good",
                "stt_quality": "uncertain",
                "uncertainty_reasons": ["low_average_logprob"],
                "possible_hallucination": True,
            },
        }
    ]

    result = build_evaluation_input(
        {"id": SESSION_ID, "user_id": None, "lesson_id": None},
        raw_backup_json=raw_backup_json,
    )

    student_turn = [turn for turn in result.turns if turn.speaker == "student"][0]
    assert "low_average_logprob" in student_turn.stt_uncertainty_reasons
    assert "possible_hallucination_soft" in student_turn.stt_uncertainty_reasons
