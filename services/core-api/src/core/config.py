from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL")
    db_pool_size: int = Field(default=20, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    secret_key: str = Field(alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    rabbitmq_host: str | None = Field(default=None, alias="RABBITMQ_HOST")
    rabbitmq_port: int | None = Field(default=None, alias="RABBITMQ_PORT")
    rabbitmq_user: str | None = Field(default=None, alias="RABBITMQ_USER")
    rabbitmq_pass: str | None = Field(default=None, alias="RABBITMQ_PASS")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
