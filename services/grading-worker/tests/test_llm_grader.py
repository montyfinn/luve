from __future__ import annotations

import json
import pytest

from src.contracts import EvaluationInput, EvaluationTurn, GradingResult
from src.fake_grader import fake_grade
from src.llm_grader import LLMGraderError, build_grading_prompt, llm_grade_with_client, parse_grading_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SESSION_ID = "00000000-0000-0000-0000-000000000001"


def _make_input(
    student_texts: list[str] | None = None,
    assistant_texts: list[str] | None = None,
) -> EvaluationInput:
    turns: list[EvaluationTurn] = []
    seq = 0
    for text in (student_texts or []):
        turns.append(EvaluationTurn(seq=seq, speaker="student", text=text, source="USER_TURN"))
        seq += 1
    for text in (assistant_texts or []):
        turns.append(EvaluationTurn(seq=seq, speaker="assistant", text=text, source="AI_TURN"))
        seq += 1
    return EvaluationInput(
        session_id=SESSION_ID,
        raw_event_count=len(turns),
        turns=turns,
    )


def _valid_response(**overrides: object) -> str:
    data = {
        "fluency_score": 7.5,
        "grammar_score": 8.0,
        "vocab_score": 6.5,
        "summary": "Good overall session with some vocabulary gaps.",
        "corrections": [
            {
                "turn_seq": 0,
                "original": "I am go to school",
                "corrected": "I am going to school",
                "error_type": "grammar",
                "explanation": "Use the present continuous form 'going'.",
            }
        ],
    }
    data.update(overrides)
    return json.dumps(data)


class MockClient:
    def __init__(self, response: str) -> None:
        self._response = response

    async def grade(self, prompt: str) -> str:
        return self._response


def _skill_feedback(result: GradingResult, skill: str):
    return next(item for item in result.skill_feedback if item.skill == skill)


# ---------------------------------------------------------------------------
# build_grading_prompt tests
# ---------------------------------------------------------------------------

def test_prompt_includes_student_turns():
    ei = _make_input(student_texts=["Hello, how are you?", "My name is Monty."])
    prompt = build_grading_prompt(ei)
    assert "Hello, how are you?" in prompt
    assert "My name is Monty." in prompt
    assert "Student" in prompt


def test_prompt_includes_assistant_turns():
    ei = _make_input(
        student_texts=["Hello."],
        assistant_texts=["Hi! How can I help?"],
    )
    prompt = build_grading_prompt(ei)
    assert "Hi! How can I help?" in prompt
    assert "Tutor" in prompt


def test_prompt_no_student_turns_says_so():
    ei = _make_input()
    prompt = build_grading_prompt(ei)
    assert "No student speech" in prompt


def test_prompt_contains_rubric_fields():
    ei = _make_input(student_texts=["Hello."])
    prompt = build_grading_prompt(ei)
    assert "fluency_score" in prompt
    assert "grammar_score" in prompt
    assert "vocab_score" in prompt


def test_prompt_contains_evidence_boundaries_and_score_anchors():
    ei = _make_input(student_texts=["Hello."])
    prompt = build_grading_prompt(ei)
    lower = prompt.lower()

    assert "approximate practice feedback" in lower
    assert "not a cefr" in lower
    assert "ielts" in lower
    assert "not a validated proficiency assessment" in lower
    assert "limited evidence" in lower
    assert "do not infer broad english ability" in lower
    assert "0-2: no reliable evidence" in lower
    assert "3-4: very limited" in lower
    assert "5-6: basic communication" in lower
    assert "7-8: generally clear" in lower
    assert "9-10: strong" in lower


def test_prompt_contains_stt_pronunciation_and_correction_safety_rules():
    ei = _make_input(student_texts=["Hello."])
    prompt = build_grading_prompt(ei)
    lower = prompt.lower()

    assert "do not over-penalize possible stt errors" in lower
    assert "skip the correction" in lower
    assert "uncertain turns" in lower
    assert "pronunciation_clarity_score: use null unless" in lower
    assert "insufficient_evidence" in prompt
    assert "do not claim exact pronunciation errors" in lower
    assert "return at most 3 corrections" in lower
    assert "high-impact, high-confidence corrections" in lower


def test_prompt_requires_evidence_based_skill_feedback():
    ei = _make_input(student_texts=["I play game."])
    prompt = build_grading_prompt(ei)
    lower = prompt.lower()

    assert "every skill_feedback summary must mention one concrete basis" in lower
    assert "observed phrase" in lower
    assert "observed pattern" in lower
    assert "amount of evidence" in lower
    assert "clear reason why evidence is insufficient" in lower
    assert "without naming what evidence supports that view" in lower
    assert "bạn có một số lỗi về ngữ pháp" in lower


def test_prompt_requires_concrete_micro_practice_and_bans_generic_advice():
    ei = _make_input(student_texts=["I play game."])
    prompt = build_grading_prompt(ei)
    lower = prompt.lower()

    assert "concrete micro-practice task" in lower
    assert "phrase frame" in lower
    assert "small repetition count" in lower
    assert "tập luyện ngữ pháp tiếng anh để cải thiện" in lower
    assert "tập luyện từ vựng tiếng anh để cải thiện" in lower
    assert "tập luyện nói tiếng anh trong thời gian dài hơn" in lower
    assert "tập luyện phát âm tiếng anh để cải thiện" in lower
    assert "cố gắng sử dụng từ vựng tốt hơn" in lower
    assert "hãy nói 4-5 câu" in lower
    assert "i like..." in lower


def test_prompt_handles_short_sessions_and_pronunciation_insufficiency_carefully():
    ei = _make_input(student_texts=["Hello."])
    prompt = build_grading_prompt(ei)
    lower = prompt.lower()

    assert "for short sessions" in lower
    assert "evidence is limited" in lower
    assert "producing more usable evidence next time" in lower
    assert "transcript alone is not enough to judge pronunciation reliably" in lower
    assert "reading 3-5 clear sentences in a quiet place" in lower
    assert "align relevant skill feedback" in lower


def test_prompt_contains_json_robustness_rules():
    ei = _make_input(student_texts=["Hello."])
    prompt = build_grading_prompt(ei)
    lower = prompt.lower()

    assert "return only a json object" in lower
    assert "no markdown" in lower
    assert "no extra keys" in lower
    assert "all four skill_feedback items must appear exactly once" in lower
    assert "valid json with no trailing commas" in lower


def test_prompt_includes_uncertain_stt_note_but_preserves_transcript_text():
    ei = EvaluationInput(
        session_id=SESSION_ID,
        raw_event_count=1,
        turns=[
            EvaluationTurn(
                seq=0,
                speaker="student",
                text="I very like this lesson",
                source="USER_TURN",
                stt_quality="uncertain",
                stt_uncertainty_reasons=[
                    "low_average_logprob",
                    "possible_stt_autocorrection",
                ],
                possible_stt_autocorrection=True,
            )
        ],
        quality_signals={
            "student_word_count": 5,
            "uncertain_student_turn_count": 1,
        },
    )
    prompt = build_grading_prompt(ei)
    assert "[0] Student: I very like this lesson" in prompt
    assert "STT note: uncertain (low_average_logprob, possible_stt_autocorrection)" in prompt
    assert "Uncertain student turns: 1" in prompt


def test_prompt_omits_stt_note_for_confident_turn():
    ei = EvaluationInput(
        session_id=SESSION_ID,
        raw_event_count=1,
        turns=[
            EvaluationTurn(
                seq=0,
                speaker="student",
                text="Hello guys",
                source="USER_TURN",
                stt_quality="confident",
            )
        ],
        quality_signals={"student_word_count": 2},
    )
    prompt = build_grading_prompt(ei)
    assert "[0] Student: Hello guys" in prompt
    assert "STT note:" not in prompt


def test_prompt_includes_soft_hallucination_caution_reason():
    ei = EvaluationInput(
        session_id=SESSION_ID,
        raw_event_count=1,
        turns=[
            EvaluationTurn(
                seq=0,
                speaker="student",
                text="I want improve speaking because my English not good",
                source="USER_TURN",
                stt_quality="uncertain",
                stt_uncertainty_reasons=[
                    "low_average_logprob",
                    "possible_hallucination_soft",
                ],
            )
        ],
        quality_signals={
            "student_word_count": 9,
            "uncertain_student_turn_count": 1,
        },
    )
    prompt = build_grading_prompt(ei)
    assert "possible_hallucination_soft" in prompt


# ---------------------------------------------------------------------------
# parse_grading_response tests
# ---------------------------------------------------------------------------

def test_parse_valid_response_returns_grading_result():
    result = parse_grading_response(_valid_response(), session_id=SESSION_ID)
    assert isinstance(result, GradingResult)
    assert result.grader_version == "llm_grader.v1"
    assert result.score_schema_version == "grading.v1"
    assert result.fluency_score == 7.5
    assert result.grammar_score == 8.0
    assert result.vocab_score == 6.5


def test_parse_overall_score_uses_python_weighting():
    result = parse_grading_response(_valid_response(), session_id=SESSION_ID)
    expected = round(7.5 * 0.30 + 8.0 * 0.35 + 6.5 * 0.35, 2)
    assert result.overall_score == expected


def test_parse_valid_corrections_preserved():
    result = parse_grading_response(_valid_response(), session_id=SESSION_ID)
    assert len(result.detailed_corrections) == 1
    assert result.detailed_corrections[0]["error_type"] == "grammar"


def test_parse_production_skill_feedback_and_pronunciation_score():
    response = _valid_response(
        pronunciation_clarity_score=6.0,
        skill_feedback=[
            {
                "skill": "fluency",
                "score": 7.5,
                "status": "scored",
                "summary": "You answered without long pauses.",
                "suggestion": "Practice linking short answers into two-sentence responses.",
            },
            {
                "skill": "grammar",
                "score": 8.0,
                "status": "scored",
                "summary": "Your basic sentence structure is clear.",
                "suggestion": "Review present continuous forms.",
            },
            {
                "skill": "vocabulary",
                "score": 6.5,
                "status": "scored",
                "summary": "Vocabulary was understandable but repetitive.",
                "suggestion": "Prepare three stronger adjectives before the next session.",
            },
            {
                "skill": "pronunciation_clarity",
                "score": 6.0,
                "status": "scored",
                "summary": "The transcript showed some clarity uncertainty.",
                "suggestion": "Repeat key phrases slowly, then again at natural speed.",
            },
        ],
    )
    result = parse_grading_response(response, session_id=SESSION_ID)

    assert result.provider == "llm"
    assert result.score_schema_version == "grading.v2"
    assert result.pronunciation_score == 6.0
    assert len(result.skill_feedback) == 4
    assert result.skill_feedback[3].skill == "pronunciation_clarity"
    assert result.skill_feedback[3].score == 6.0
    assert result.skill_feedback[3].status == "scored"
    assert result.overall_score == round(7.5 * 0.25 + 8.0 * 0.30 + 6.5 * 0.25 + 6.0 * 0.20, 2)


def test_parse_normalizes_nested_pronunciation_score_from_top_level_null():
    response = _valid_response(
        pronunciation_clarity_score=None,
        skill_feedback=[
            {
                "skill": "pronunciation_clarity",
                "score": 7.0,
                "status": "scored",
                "summary": "Nested pronunciation summary is preserved.",
                "suggestion": "Nested pronunciation suggestion is preserved.",
            }
        ],
    )
    result = parse_grading_response(response, session_id=SESSION_ID)
    pronunciation = _skill_feedback(result, "pronunciation_clarity")

    assert result.pronunciation_score is None
    assert pronunciation.score is None
    assert pronunciation.status == "insufficient_evidence"
    assert pronunciation.summary == "Nested pronunciation summary is preserved."
    assert pronunciation.suggestion == "Nested pronunciation suggestion is preserved."


def test_parse_normalizes_nested_skill_score_and_ignores_raw_status():
    response = _valid_response(
        fluency_score=6.0,
        skill_feedback=[
            {
                "skill": "fluency",
                "score": 9.0,
                "status": "insufficient_evidence",
                "summary": "Fluency summary is preserved.",
                "suggestion": "Fluency suggestion is preserved.",
            }
        ],
    )
    result = parse_grading_response(response, session_id=SESSION_ID)
    fluency = _skill_feedback(result, "fluency")

    assert result.fluency_score == 6.0
    assert fluency.score == 6.0
    assert fluency.status == "scored"
    assert fluency.summary == "Fluency summary is preserved."
    assert fluency.suggestion == "Fluency suggestion is preserved."


def test_parse_invalid_json_raises():
    with pytest.raises(LLMGraderError, match="invalid JSON"):
        parse_grading_response("not json at all", session_id=SESSION_ID)


def test_parse_missing_field_raises():
    data = json.loads(_valid_response())
    del data["grammar_score"]
    with pytest.raises(LLMGraderError, match="missing required fields"):
        parse_grading_response(json.dumps(data), session_id=SESSION_ID)


def test_parse_score_out_of_range_raises():
    with pytest.raises(LLMGraderError, match="out of range"):
        parse_grading_response(_valid_response(fluency_score=11.0), session_id=SESSION_ID)


def test_parse_negative_score_raises():
    with pytest.raises(LLMGraderError, match="out of range"):
        parse_grading_response(_valid_response(grammar_score=-1.0), session_id=SESSION_ID)


def test_parse_non_number_score_raises():
    with pytest.raises(LLMGraderError, match="not a number"):
        parse_grading_response(_valid_response(vocab_score="high"), session_id=SESSION_ID)


def test_parse_malformed_correction_dropped_valid_kept():
    corrections = [
        # valid
        {
            "turn_seq": 0,
            "original": "I go",
            "corrected": "I went",
            "error_type": "grammar",
            "explanation": "Past tense needed.",
        },
        # missing explanation — should be dropped
        {
            "turn_seq": 1,
            "original": "bad",
            "corrected": "better",
            "error_type": "vocab",
        },
        # not a dict — should be dropped
        "not a dict",
    ]
    response = _valid_response(corrections=corrections)
    result = parse_grading_response(response, session_id=SESSION_ID)
    assert len(result.detailed_corrections) == 1
    assert result.detailed_corrections[0]["original"] == "I go"


def test_parse_corrections_not_list_raises():
    with pytest.raises(LLMGraderError, match="corrections must be a list"):
        parse_grading_response(_valid_response(corrections={"bad": "shape"}), session_id=SESSION_ID)


def test_parse_empty_summary_raises():
    with pytest.raises(LLMGraderError, match="empty summary"):
        parse_grading_response(_valid_response(summary=""), session_id=SESSION_ID)


def test_parse_strips_markdown_fence():
    inner = json.loads(_valid_response())
    fenced = f"```json\n{json.dumps(inner)}\n```"
    result = parse_grading_response(fenced, session_id=SESSION_ID)
    assert result.grader_version == "llm_grader.v1"


def test_parse_response_is_not_object_raises():
    with pytest.raises(LLMGraderError, match="must be a JSON object"):
        parse_grading_response(json.dumps([1, 2, 3]), session_id=SESSION_ID)


# ---------------------------------------------------------------------------
# llm_grade_with_client tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_grade_with_mock_client_returns_result():
    ei = _make_input(student_texts=["Hello, my name is Monty."])
    client = MockClient(_valid_response())
    result = await llm_grade_with_client(ei, client)
    assert isinstance(result, GradingResult)
    assert result.grader_version == "llm_grader.v1"
    assert result.session_id == ei.session_id


@pytest.mark.asyncio
async def test_llm_grade_zero_student_turns_raises():
    ei = _make_input()
    client = MockClient(_valid_response())
    with pytest.raises(LLMGraderError, match="zero student turns"):
        await llm_grade_with_client(ei, client)


@pytest.mark.asyncio
async def test_llm_grade_only_assistant_turns_raises():
    ei = _make_input(assistant_texts=["Hello! Ready to practice?"])
    client = MockClient(_valid_response())
    with pytest.raises(LLMGraderError, match="zero student turns"):
        await llm_grade_with_client(ei, client)


@pytest.mark.asyncio
async def test_llm_grade_propagates_parse_error():
    ei = _make_input(student_texts=["Hi."])
    client = MockClient("this is not json")
    with pytest.raises(LLMGraderError, match="invalid JSON"):
        await llm_grade_with_client(ei, client)


# ---------------------------------------------------------------------------
# Regression: fake_grader still works after Literal loosened
# ---------------------------------------------------------------------------

def test_fake_grader_still_produces_fake_grader_v1():
    ei = EvaluationInput(
        session_id=SESSION_ID,
        raw_event_count=1,
        turns=[EvaluationTurn(seq=0, speaker="student", text="Hello", source="USER_TURN")],
    )
    result = fake_grade(ei)
    assert result.grader_version == "fake_grader.v1"
    assert result.score_schema_version == "grading.v1"
    assert isinstance(result.overall_score, float)
