from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

from src.contracts import (
    SCORE_SCHEMA_LEGACY,
    SCORE_SCHEMA_WITH_PRONUNCIATION,
    EvaluationInput,
    EvaluationTurn,
    GradingResult,
    SkillFeedback,
)


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
            lines.extend(_format_turn_for_prompt(t))
        transcript_section = "\n".join(lines)

    quality_notes: list[str] = []
    quality_notes.append(f"Student turns: {len(student_turns)}")
    quality_notes.append(f"Tutor turns: {len(assistant_turns)}")
    word_count = input_data.quality_signals.get("student_word_count")
    if word_count is not None:
        quality_notes.append(f"Student word count: {word_count}")
    uncertain_turns = input_data.quality_signals.get("uncertain_student_turn_count")
    if uncertain_turns:
        quality_notes.append(f"Uncertain student turns: {uncertain_turns}")

    return f"""\
You are an experienced English language teacher giving approximate practice feedback for one short spoken English practice session.
These scores are not a CEFR/IELTS score and not a validated proficiency assessment.
Use only the evidence in this session. If evidence is limited, be conservative and say in Vietnamese that the feedback is based on limited session evidence.

## Transcript
{transcript_section}

## Session quality signals
{chr(10).join(quality_notes)}

## Evidence boundaries
- Treat all top-level scores as approximate practice feedback from this session only.
- Do not infer broad English ability from one or two short sentences.
- For very few student turns or very low student word count, keep fluency_score, grammar_score, and vocab_score conservative and mention limited evidence in the Vietnamese summary or suggestions.
- Do not over-penalize possible STT errors. If a phrase may be an STT artifact, skip the correction.
- Do not make grammar or vocabulary corrections from uncertain turns unless the error is obvious and high-confidence.
- Do not claim exact pronunciation errors from the plain transcript.

## Score anchors for fluency_score, grammar_score, and vocab_score
Score each dimension from 0.0 to 10.0 (one decimal place is fine):
- 0-2: no reliable evidence or mostly unusable evidence
- 3-4: very limited output, frequent issues, hard to sustain communication
- 5-6: basic communication with noticeable limitations
- 7-8: generally clear communication with minor issues
- 9-10: strong, consistent, rich evidence across multiple turns

## Skill-specific guidance
- fluency_score: naturalness, rhythm, pace, ability to sustain answers; be conservative for short sessions.
- grammar_score: correctness of tenses, agreement, and sentence structure; skip uncertain STT artifacts.
- vocab_score: variety, appropriateness, and precision of vocabulary; do not reward broad vocabulary without enough evidence.
- pronunciation_clarity_score: use null unless STT confidence/timing notes provide reliable evidence. Use skill_feedback status "insufficient_evidence" for pronunciation_clarity when the transcript alone is the evidence.

## Instructions
When a student turn has an STT note marked uncertain, treat the transcript as possibly imperfect.
Avoid overconfident grammar or pronunciation judgments based only on uncertain STT turns.
Write learner-facing summary, observations, and suggestions in concise Vietnamese.
Keep original and corrected phrases in English.
Return ONLY a JSON object with these exact keys - no markdown, no prose, no extra keys:
{{
  "fluency_score": <number 0–10>,
  "grammar_score": <number 0–10>,
  "vocab_score": <number 0–10>,
  "pronunciation_clarity_score": <number 0–10 or null>,
  "summary": "<2–4 sentence overall feedback in Vietnamese>",
  "skill_feedback": [
    {{
      "skill": "<fluency|grammar|vocabulary|pronunciation_clarity>",
      "score": <number 0–10 or null>,
      "status": "<scored|insufficient_evidence>",
      "summary": "<one concise learner-facing observation in Vietnamese>",
      "suggestion": "<one concrete next practice action in Vietnamese>"
    }}
  ],
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
Corrections rules:
- Return at most 3 corrections.
- Prefer high-impact, high-confidence corrections.
- Keep "original" and "corrected" in English.
- Keep the Vietnamese explanation brief.
- Do not correct every minor phrase in a very short session.
- If there are no corrections, return an empty list for "corrections".
JSON robustness rules:
- Return exactly one skill_feedback item for each skill: fluency, grammar, vocabulary, pronunciation_clarity.
- All four skill_feedback items must appear exactly once.
- For pronunciation_clarity, use status "insufficient_evidence" and score null when STT confidence/timing notes do not provide reliable pronunciation evidence.
- Return valid JSON with no trailing commas.
Do not include any text before or after the JSON object.
"""


def _format_turn_for_prompt(turn: EvaluationTurn) -> list[str]:
    label = "Student" if turn.speaker == "student" else "Tutor"
    lines = [f"[{turn.seq}] {label}: {turn.text}"]
    if turn.speaker != "student" or turn.stt_quality != "uncertain":
        return lines

    reasons = ", ".join(turn.stt_uncertainty_reasons) or "uncertain_transcript"
    lines.append(f"    STT note: uncertain ({reasons})")
    return lines


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
    pronunciation = _validate_optional_score(
        data.get("pronunciation_clarity_score", data.get("pronunciation_score")),
        "pronunciation_clarity_score",
    )

    summary = str(data["summary"]).strip()
    if not summary:
        raise LLMGraderError("LLM response has empty summary")

    raw_corrections = data["corrections"]
    if not isinstance(raw_corrections, list):
        raise LLMGraderError("LLM response corrections must be a list")

    corrections = _filter_corrections(raw_corrections)
    skill_feedback = _filter_skill_feedback(
        data.get("skill_feedback"),
        fluency=fluency,
        grammar=grammar,
        vocab=vocab,
        pronunciation=pronunciation,
    )
    overall = _weighted_overall_score(
        fluency=fluency,
        grammar=grammar,
        vocab=vocab,
        pronunciation=pronunciation,
    )

    return GradingResult(
        session_id=session_id,
        overall_score=overall,
        fluency_score=fluency,
        grammar_score=grammar,
        vocab_score=vocab,
        pronunciation_score=pronunciation,
        ai_summary_feedback=summary,
        detailed_corrections=corrections,
        grader_version="llm_grader.v1",
        provider="llm",
        score_schema_version=(
            SCORE_SCHEMA_WITH_PRONUNCIATION
            if pronunciation is not None
            else SCORE_SCHEMA_LEGACY
        ),
        skill_feedback=skill_feedback,
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


def _validate_optional_score(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    return _validate_score(value, field)


def _weighted_overall_score(
    *,
    fluency: float,
    grammar: float,
    vocab: float,
    pronunciation: float | None,
) -> float:
    if pronunciation is None:
        return round(fluency * 0.30 + grammar * 0.35 + vocab * 0.35, 2)
    return round(
        fluency * 0.25
        + grammar * 0.30
        + vocab * 0.25
        + pronunciation * 0.20,
        2,
    )


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


_SKILL_LABELS: dict[str, str] = {
    "fluency": "Keep answers flowing in complete thoughts.",
    "grammar": "Focus on one recurring grammar pattern in the next session.",
    "vocabulary": "Add more precise words instead of repeating safe words.",
    "pronunciation_clarity": "Practice short phrases clearly and compare the transcript confidence.",
}


def _filter_skill_feedback(
    raw: Any,
    *,
    fluency: float,
    grammar: float,
    vocab: float,
    pronunciation: float | None,
) -> list[SkillFeedback]:
    scores = {
        "fluency": fluency,
        "grammar": grammar,
        "vocabulary": vocab,
        "pronunciation_clarity": pronunciation,
    }
    result_by_skill: dict[str, SkillFeedback] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            skill = str(item.get("skill") or "").strip().lower()
            if skill == "vocab":
                skill = "vocabulary"
            if skill not in scores:
                continue
            score = scores[skill]
            status = "insufficient_evidence" if score is None else "scored"
            summary = str(item.get("summary") or "").strip()
            suggestion = str(item.get("suggestion") or "").strip()
            result_by_skill[skill] = SkillFeedback(
                skill=skill,  # type: ignore[arg-type]
                score=score,
                status=status,  # type: ignore[arg-type]
                summary=summary or _default_summary(skill, score),
                suggestion=suggestion or _SKILL_LABELS[skill],
            )

    for skill, score in scores.items():
        if skill in result_by_skill:
            continue
        result_by_skill[skill] = SkillFeedback(
            skill=skill,  # type: ignore[arg-type]
            score=score,
            status="insufficient_evidence" if score is None else "scored",
            summary=_default_summary(skill, score),
            suggestion=_SKILL_LABELS[skill],
        )

    return [
        result_by_skill["fluency"],
        result_by_skill["grammar"],
        result_by_skill["vocabulary"],
        result_by_skill["pronunciation_clarity"],
    ]


def _default_summary(skill: str, score: float | None) -> str:
    if score is None:
        return f"{skill.replace('_', ' ').title()} could not be scored reliably from this session."
    return f"{skill.replace('_', ' ').title()} scored {score:.1f}/10."
