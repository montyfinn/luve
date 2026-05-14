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


QualityValue = int | float | str | bool | None


class EvaluationInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: UUID
    user_id: UUID | None = None
    lesson_id: UUID | None = None
    raw_event_count: int
    turns: list[EvaluationTurn] = Field(default_factory=list)
    quality_signals: dict[str, QualityValue] = Field(default_factory=dict)
    builder_version: Literal["evaluation_input.v1"] = "evaluation_input.v1"


class GradingResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: UUID
    overall_score: float
    fluency_score: float
    grammar_score: float
    vocab_score: float
    detailed_corrections: list[dict[str, Any]] = Field(default_factory=list)
    ai_summary_feedback: str
    grader_version: Literal["fake_grader.v1"] = "fake_grader.v1"
