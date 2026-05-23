from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

from src.contracts import EvaluationInput, EvaluationTurn, GradingResult


class LLMGraderError(Exception):
    """Raised when the LLM response cannot be parsed or validated."""


class GraderClient(Protocol):
    async def grade(self, prompt: str) -> str:
        ...


def build_grading_prompt(input_data: EvaluationInput) -> str:
    student_turns = [t for t in input_data.turns if t.speaker == "student"]
    assistant_turns = [t for t in input_data.turns if t.speaker == "assistant"]

    if not student_turns:
        transcript_section = "No student speech was captured in this session."
    else:
        lines: list[str] = []
        for t in input_data.turns:
            label = "Student" if t.speaker == "student" else "Tutor"
            lines.append(f"[{t.seq}] {label}: {t.text}")
        transcript_section = "\n".join(lines)

    quality_notes: list[str] = []
    quality_notes.append(f"Student turns: {len(student_turns)}")
    quality_notes.append(f"Tutor turns: {len(assistant_turns)}")
    word_count = input_data.quality_signals.get("student_word_count")
    if word_count is not None:
        quality_notes.append(f"Student word count: {word_count}")

    return f"""\
You are an experienced English language teacher evaluating a student's spoken English practice session.

## Transcript
{transcript_section}

## Session quality signals
{chr(10).join(quality_notes)}

## Scoring rubric
Score each dimension from 0.0 to 10.0 (one decimal place is fine):
- fluency_score: naturalness, rhythm, pace, minimal hesitation
- grammar_score: correctness of tenses, agreement, sentence structure
- vocab_score: variety, appropriateness, and precision of vocabulary

## Instructions
Return ONLY a JSON object with these exact keys — no markdown, no prose, no extra keys:
{{
  "fluency_score": <number 0–10>,
  "grammar_score": <number 0–10>,
  "vocab_score": <number 0–10>,
  "summary": "<2–4 sentence overall feedback in English>",
  "corrections": [
    {{
      "turn_seq": <integer>,
      "original": "<student's exact phrase>",
      "corrected": "<corrected phrase>",
      "error_type": "<grammar|vocab|fluency|pronunciation>",
      "explanation": "<brief explanation>"
    }}
  ]
}}
If there are no corrections, return an empty list for "corrections".
Do not include any text before or after the JSON object.
"""


def parse_grading_response(raw_json: str, *, session_id: UUID) -> GradingResult:
    stripped = raw_json.strip()

    # Strip a single markdown code fence if the model ignored the instruction.
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = [
            ln for ln in lines if not ln.startswith("```")
        ]
        stripped = "\n".join(inner).strip()

    try:
        data: dict[str, Any] = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise LLMGraderError(f"LLM returned invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise LLMGraderError("LLM response must be a JSON object")

    required = ("fluency_score", "grammar_score", "vocab_score", "summary", "corrections")
    missing = [k for k in required if k not in data]
    if missing:
        raise LLMGraderError(f"LLM response missing required fields: {missing}")

    fluency = _validate_score(data["fluency_score"], "fluency_score")
    grammar = _validate_score(data["grammar_score"], "grammar_score")
    vocab = _validate_score(data["vocab_score"], "vocab_score")

    summary = str(data["summary"]).strip()
    if not summary:
        raise LLMGraderError("LLM response has empty summary")

    raw_corrections = data["corrections"]
    if not isinstance(raw_corrections, list):
        raise LLMGraderError("LLM response corrections must be a list")

    corrections = _filter_corrections(raw_corrections)
    overall = round(fluency * 0.30 + grammar * 0.35 + vocab * 0.35, 2)

    return GradingResult(
        session_id=session_id,
        overall_score=overall,
        fluency_score=fluency,
        grammar_score=grammar,
        vocab_score=vocab,
        ai_summary_feedback=summary,
        detailed_corrections=corrections,
        grader_version="llm_grader.v1",
    )


async def llm_grade_with_client(
    input_data: EvaluationInput,
    client: GraderClient,
) -> GradingResult:
    student_turns = [t for t in input_data.turns if t.speaker == "student"]
    if not student_turns:
        raise LLMGraderError(
            f"Cannot grade session {input_data.session_id}: zero student turns"
        )

    prompt = build_grading_prompt(input_data)
    raw_response = await client.grade(prompt)
    return parse_grading_response(raw_response, session_id=input_data.session_id)


def _validate_score(value: Any, field: str) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise LLMGraderError(f"{field} is not a number: {value!r}") from exc
    if not (0.0 <= score <= 10.0):
        raise LLMGraderError(
            f"{field} out of range [0, 10]: {score}"
        )
    return score


_CORRECTION_REQUIRED_KEYS = {"turn_seq", "original", "corrected", "error_type", "explanation"}


def _filter_corrections(raw: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not _CORRECTION_REQUIRED_KEYS.issubset(item.keys()):
            continue
        result.append({
            "turn_seq": item["turn_seq"],
            "original": item["original"],
            "corrected": item["corrected"],
            "error_type": item["error_type"],
            "explanation": item["explanation"],
        })
    return result
