from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: EmailStr
    fluency_level: int
    quota_minutes: int
    is_active: bool
    is_banned: bool
    created_at: datetime
