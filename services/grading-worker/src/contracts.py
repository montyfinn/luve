from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SessionCompletedJob(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_type: Literal["session.completed"]
    schema_version: Literal["v1"] = "v1"
    session_id: UUID
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class EvaluationTurn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    seq: int
    speaker: Literal["student", "assistant"]
    text: str
    source: Literal["USER_TURN", "AI_TURN"]
    start_ms: int | None = None
    end_ms: int | None = None
    duration_ms: int | None = None
    stt_quality: Literal["confident", "uncertain"] | None = None
    stt_uncertainty_reasons: list[str] = Field(default_factory=list)
    possible_stt_autocorrection: bool = False


QualityValue = int | float | str | bool | None
GradingSkill = Literal["fluency", "grammar", "vocabulary", "pronunciation_clarity"]
SkillFeedbackStatus = Literal["scored", "insufficient_evidence"]
SCORE_SCHEMA_LEGACY = "grading.v1"
SCORE_SCHEMA_WITH_PRONUNCIATION = "grading.v2"


class EvaluationInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: UUID
    user_id: UUID | None = None
    lesson_id: UUID | None = None
    raw_event_count: int
    turns: list[EvaluationTurn] = Field(default_factory=list)
    quality_signals: dict[str, QualityValue] = Field(default_factory=dict)
    builder_version: Literal["evaluation_input.v1"] = "evaluation_input.v1"


class SkillFeedback(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    skill: GradingSkill
    score: float | None = None
    status: SkillFeedbackStatus = "scored"
    summary: str
    suggestion: str


class GradingResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: UUID
    overall_score: float
    fluency_score: float
    grammar_score: float
    vocab_score: float
    pronunciation_score: float | None = None
    detailed_corrections: list[dict[str, Any]] = Field(default_factory=list)
    ai_summary_feedback: str
    grader_version: str = "fake_grader.v1"
    provider: str = "fake"
    score_schema_version: str = SCORE_SCHEMA_LEGACY
    skill_feedback: list[SkillFeedback] = Field(default_factory=list)
    input_quality: dict[str, QualityValue] = Field(default_factory=dict)
