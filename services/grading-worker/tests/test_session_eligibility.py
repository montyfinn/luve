from __future__ import annotations

import json
from collections import UserDict

from src.session_eligibility import (
    DEFAULT_MIN_STUDENT_WORDS,
    GradingEligibility,
    count_reliable_student_words,
    count_student_words,
    count_user_turns,
    evaluate_grading_eligibility,
    get_event_kind,
    get_event_text,
    is_reliable_student_event,
    parse_raw_backup_events,
)


# ---------------------------------------------------------------------------
# parse_raw_backup_events
# ---------------------------------------------------------------------------

def test_parse_none_returns_none():
    assert parse_raw_backup_events(None) is None


def test_parse_list_of_dicts_accepted():
    events = [{"type": "USER_TURN"}, {"type": "AI_TURN"}]
    assert parse_raw_backup_events(events) is events


def test_parse_valid_json_array_string():
    raw = json.dumps([{"type": "USER_TURN"}])
    result = parse_raw_backup_events(raw)
    assert isinstance(result, list)
    assert result[0]["type"] == "USER_TURN"


def test_parse_invalid_json_string_returns_none():
    assert parse_raw_backup_events("not json at all") is None


def test_parse_non_list_json_returns_none():
    assert parse_raw_backup_events('{"type": "USER_TURN"}') is None


def test_parse_per_event_json_string_list_returned_unchanged():
    # parse_raw normalises the outer container only; per-event strings are
    # left as strings — _decode_event handles them in counting functions.
    inner = json.dumps({"type": "USER_TURN", "payload": {"text": "hello"}})
    raw = [inner]
    result = parse_raw_backup_events(raw)
    assert result == [inner]


# ---------------------------------------------------------------------------
# get_event_kind
# ---------------------------------------------------------------------------

def test_get_event_kind_type_key():
    assert get_event_kind({"type": "USER_TURN"}) == "USER_TURN"


def test_get_event_kind_event_key():
    assert get_event_kind({"event": "USER_TURN"}) == "USER_TURN"


def test_get_event_kind_type_wins_over_event():
    assert get_event_kind({"type": "USER_TURN", "event": "AI_TURN"}) == "USER_TURN"


def test_get_event_kind_non_mapping_returns_none():
    assert get_event_kind("USER_TURN") is None
    assert get_event_kind(None) is None
    assert get_event_kind(42) is None


def test_get_event_kind_mapping_subclass():
    event = UserDict({"type": "USER_TURN"})
    assert get_event_kind(event) == "USER_TURN"


# ---------------------------------------------------------------------------
# get_event_text
# ---------------------------------------------------------------------------

def test_get_event_text_from_payload():
    event = {"type": "USER_TURN", "payload": {"text": "hello world"}}
    assert get_event_text(event) == "hello world"


def test_get_event_text_non_str_returns_empty():
    event = {"type": "USER_TURN", "payload": {"text": 42}}
    assert get_event_text(event) == ""


def test_get_event_text_missing_payload_returns_empty():
    assert get_event_text({"type": "USER_TURN"}) == ""


def test_get_event_text_non_mapping_payload_returns_empty():
    event = {"type": "USER_TURN", "payload": "raw_text_not_mapping"}
    assert get_event_text(event) == ""


def test_get_event_text_non_mapping_event_returns_empty():
    assert get_event_text("not a mapping") == ""


# ---------------------------------------------------------------------------
# count_user_turns
# ---------------------------------------------------------------------------

def test_count_user_turns_type_key():
    raw = [{"type": "USER_TURN", "payload": {"text": "hi"}}]
    assert count_user_turns(raw) == 1


def test_count_user_turns_event_key():
    raw = [{"event": "USER_TURN", "payload": {"text": "hi"}}]
    assert count_user_turns(raw) == 1


def test_count_user_turns_ai_ignored():
    raw = [{"type": "AI_TURN", "payload": {"text": "hi"}}]
    assert count_user_turns(raw) == 0


def test_count_user_turns_mixed_aliases():
    raw = [
        {"type": "USER_TURN", "payload": {"text": "a"}},
        {"event": "USER_TURN", "payload": {"text": "b"}},
        {"type": "AI_TURN", "payload": {"text": "c"}},
    ]
    assert count_user_turns(raw) == 2


def test_count_user_turns_mapping_like_event():
    event = UserDict({"type": "USER_TURN", "payload": UserDict({"text": "hello"})})
    assert count_user_turns([event]) == 1


def test_count_user_turns_per_event_json_string():
    inner = {"type": "USER_TURN", "payload": {"text": "hello"}}
    raw = [json.dumps(inner)]
    assert count_user_turns(raw) == 1


def test_count_user_turns_none_returns_none():
    assert count_user_turns(None) is None


def test_count_user_turns_invalid_json_returns_none():
    assert count_user_turns("not json") is None


def test_count_user_turns_valid_no_user_turns():
    raw = [{"type": "AI_TURN", "payload": {"text": "hello"}}]
    assert count_user_turns(raw) == 0


# ---------------------------------------------------------------------------
# count_student_words
# ---------------------------------------------------------------------------

def test_count_student_words_type_key():
    raw = [{"type": "USER_TURN", "payload": {"text": "one two three"}}]
    assert count_student_words(raw) == 3


def test_count_student_words_event_key():
    raw = [{"event": "USER_TURN", "payload": {"text": "one two three"}}]
    assert count_student_words(raw) == 3


def test_count_student_words_ai_excluded():
    raw = [
        {"type": "USER_TURN", "payload": {"text": "one two"}},
        {"type": "AI_TURN", "payload": {"text": "three four five six seven"}},
    ]
    assert count_student_words(raw) == 2


def test_count_student_words_multi_turn_sum():
    raw = [
        {"type": "USER_TURN", "payload": {"text": "one two three"}},
        {"type": "USER_TURN", "payload": {"text": "four five"}},
    ]
    assert count_student_words(raw) == 5


def test_count_student_words_none_returns_none():
    assert count_student_words(None) is None


def test_count_student_words_invalid_json_returns_none():
    assert count_student_words("bad json") is None


def test_count_student_words_valid_no_user_turns():
    raw = [{"type": "AI_TURN", "payload": {"text": "hello world"}}]
    assert count_student_words(raw) == 0


# ---------------------------------------------------------------------------
# evaluate_grading_eligibility
# ---------------------------------------------------------------------------

def test_evaluate_none_raw():
    result = evaluate_grading_eligibility(None)
    assert result.eligible is False
    assert result.reason == "no_raw_backup"
    assert result.user_turn_count == 0
    assert result.student_word_count is None


def test_evaluate_invalid_raw():
    result = evaluate_grading_eligibility("not json")
    assert result.eligible is False
    assert result.reason == "invalid_raw_backup"
    assert result.user_turn_count == 0
    assert result.student_word_count is None


def test_evaluate_no_user_turns():
    result = evaluate_grading_eligibility([{"type": "AI_TURN", "payload": {"text": "hi"}}])
    assert result.eligible is False
    assert result.reason == "no_user_turns"
    assert result.user_turn_count == 0
    assert result.student_word_count == 0


def test_evaluate_below_threshold():
    raw = [{"type": "USER_TURN", "payload": {"text": "one two three"}}]
    result = evaluate_grading_eligibility(raw, min_student_words=10)
    assert result.eligible is False
    assert result.reason == "insufficient_words"
    assert result.user_turn_count == 1
    assert result.student_word_count == 3


def test_evaluate_exactly_threshold():
    raw = [{"type": "USER_TURN", "payload": {"text": "one two three four five"}}]
    result = evaluate_grading_eligibility(raw, min_student_words=5)
    assert result.eligible is True
    assert result.reason == "eligible"
    assert result.student_word_count == 5


def test_evaluate_above_threshold():
    words = " ".join(f"w{i}" for i in range(30))
    raw = [{"type": "USER_TURN", "payload": {"text": words}}]
    result = evaluate_grading_eligibility(raw, min_student_words=25)
    assert result.eligible is True
    assert result.reason == "eligible"
    assert result.student_word_count == 30


def test_evaluate_min_words_zero_allows_short_session():
    raw = [{"type": "USER_TURN", "payload": {"text": "hi"}}]
    result = evaluate_grading_eligibility(raw, min_student_words=0)
    assert result.eligible is True
    assert result.reason == "eligible"


def test_evaluate_result_has_no_transcript_text():
    raw = [{"type": "USER_TURN", "payload": {"text": "secret transcript content here"}}]
    result = evaluate_grading_eligibility(raw, min_student_words=3)
    # GradingEligibility fields must never expose transcript text
    result_str = str(result)
    assert "secret" not in result_str
    assert "transcript" not in result_str
    assert "content" not in result_str


def test_evaluate_event_key_alias():
    raw = [{"event": "USER_TURN", "payload": {"text": "one two three four five"}}]
    result = evaluate_grading_eligibility(raw, min_student_words=5)
    assert result.eligible is True
    assert result.reason == "eligible"


def test_evaluate_mapping_subclass_event():
    event = UserDict({"type": "USER_TURN", "payload": UserDict({"text": "one two three four five"})})
    result = evaluate_grading_eligibility([event], min_student_words=5)
    assert result.eligible is True
    assert result.reason == "eligible"


def test_evaluate_per_event_json_string():
    inner = {"type": "USER_TURN", "payload": {"text": "one two three four five"}}
    raw = [json.dumps(inner)]
    result = evaluate_grading_eligibility(raw, min_student_words=5)
    assert result.eligible is True
    assert result.reason == "eligible"
    assert result.user_turn_count == 1
    assert result.student_word_count == 5


def test_uncertain_caution_stt_turns_count_for_grading():
    raw = [
        {
            "type": "USER_TURN",
            "payload": {
                "text": " ".join(f"word{i}" for i in range(30)),
                "stt_quality": "uncertain",
                "uncertainty_reasons": [
                    "low_average_logprob",
                    "many_low_confidence_words",
                    "possible_stt_autocorrection",
                    "possible_hallucination_soft",
                ],
                "possible_stt_autocorrection": True,
                "possible_hallucination": True,
            },
        }
    ]

    assert is_reliable_student_event(raw[0]) is True
    assert count_student_words(raw) == 30
    assert count_reliable_student_words(raw) == 30

    result = evaluate_grading_eligibility(raw, min_student_words=25)
    assert result.eligible is True
    assert result.reason == "eligible"
    assert result.user_turn_count == 1
    assert result.student_word_count == 30
    assert result.reliable_student_word_count == 30


def test_explicit_hard_exclusion_metadata_blocks_grading():
    hard_payloads = [
        {"text": "one two three", "grading_eligible": False},
        {"text": "one two three", "excluded_from_grading_reason": "non_target_language"},
        {"text": "one two three", "turn_language_type": "vietnamese"},
        {"text": "one two three", "turn_language_type": "noise"},
        {"text": "one two three", "uncertainty_reasons": ["verification_language_mismatch"]},
        {"text": "one two three", "uncertainty_reasons": ["non_english_verification_failed"]},
        {"text": "one two three", "uncertainty_reasons": ["hallucination_suspected"]},
        {"text": "one two three", "uncertainty_reasons": ["empty_transcript"]},
        {"text": "one two three", "uncertainty_reasons": ["background_noise"]},
        {"text": "one two three", "uncertainty_reasons": ["weak_mixed_language_english"]},
    ]

    for payload in hard_payloads:
        event = {"type": "USER_TURN", "payload": payload}
        assert is_reliable_student_event(event) is False, payload


def test_empty_exclusion_reason_and_missing_metadata_do_not_block_grading():
    raw = [
        {
            "type": "USER_TURN",
            "payload": {
                "text": "one two three four five",
                "excluded_from_grading_reason": "",
                "stt_quality": "uncertain",
                "uncertainty_reasons": ["verification_unavailable"],
            },
        }
    ]

    assert is_reliable_student_event(raw[0]) is True
    assert count_reliable_student_words(raw) == 5


def test_english_segment_counts_for_grading_when_present():
    raw = [
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

    assert is_reliable_student_event(raw[0]) is True
    assert count_reliable_student_words(raw) == 4


def test_legacy_turn_without_stt_metadata_counts_as_reliable():
    raw = [{"type": "USER_TURN", "payload": {"text": "one two three four five"}}]

    assert is_reliable_student_event(raw[0]) is True
    assert count_reliable_student_words(raw) == 5
    result = evaluate_grading_eligibility(raw, min_student_words=5)
    assert result.eligible is True
    assert result.student_word_count == 5
    assert result.reliable_student_word_count == 5


def test_default_min_student_words_constant():
    assert DEFAULT_MIN_STUDENT_WORDS == 25


def test_evaluate_returns_grading_eligibility_dataclass():
    result = evaluate_grading_eligibility(None)
    assert isinstance(result, GradingEligibility)
