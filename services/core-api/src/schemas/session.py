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


class SessionListItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID
    lesson_id: UUID | None = None
    status: str
    total_tokens: int
    manual_stops_count: int
    started_at: datetime
    ended_at: datetime | None = None


class SessionListResponse(BaseModel):
    items: list[SessionListItem] = Field(default_factory=list)
    limit: int
    offset: int
    total: int


class GradingRead(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: UUID
    status: str = "graded"
    provider: str | None = None
    grader_version: str | None = None
    score_schema_version: str = "grading.v1"
    overall_score: float
    fluency_score: float
    grammar_score: float
    vocab_score: float
    pronunciation_score: float | None = None
    detailed_corrections: list[dict[str, Any]] = Field(default_factory=list)
    skill_feedback: list[dict[str, Any]] = Field(default_factory=list)
    input_quality: dict[str, Any] = Field(default_factory=dict)
    ai_summary_feedback: str
    error_code: str | None = None
    error_message: str | None = None
    graded_at: datetime
    is_dev_preview: bool = False


class GradingStatusRead(BaseModel):
    session_id: UUID
    status: Literal["graded", "processing", "pending", "insufficient_evidence", "failed"]
    student_word_count: int | None = None
    reason: str | None = None
    error_code: str | None = None
