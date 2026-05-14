from datetime import datetime
from typing import Any
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

