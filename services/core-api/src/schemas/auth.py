from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=3, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    fluency_level: int = Field(default=1, ge=1, le=3)
    quota_minutes: int = Field(default=60, ge=0)


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class GoogleExchangeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    google_code: str = Field(min_length=1, max_length=512)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    sub: str | None = None
