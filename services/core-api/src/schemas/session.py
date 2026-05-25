from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    lesson_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionRead(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID
    user_id: UUID
    lesson_id: UUID | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_backup_json: dict[str, Any] | list[Any] | None = None
    total_tokens: int
    manual_stops_count: int
    started_at: datetime
    ended_at: datetime | None = None


class GradingRead(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: UUID
    overall_score: float
    fluency_score: float
    grammar_score: float
    vocab_score: float
    detailed_corrections: list[dict[str, Any]] = Field(default_factory=list)
    ai_summary_feedback: str
    graded_at: datetime
    is_dev_preview: bool = True


class GradingStatusRead(BaseModel):
    session_id: UUID
    status: Literal["graded", "pending", "insufficient_evidence"]
    student_word_count: int | None = None

