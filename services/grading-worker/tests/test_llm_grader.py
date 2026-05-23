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


# ---------------------------------------------------------------------------
# parse_grading_response tests
# ---------------------------------------------------------------------------

def test_parse_valid_response_returns_grading_result():
    result = parse_grading_response(_valid_response(), session_id=SESSION_ID)
    assert isinstance(result, GradingResult)
    assert result.grader_version == "llm_grader.v1"
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
    assert isinstance(result.overall_score, float)
