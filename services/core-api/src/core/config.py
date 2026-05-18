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
    max_webrtc_sessions: int = Field(default=1, alias="MAX_WEBRTC_SESSIONS")
    enable_legacy_ws_audio: bool = Field(default=True, alias="ENABLE_LEGACY_WS_AUDIO")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    llm_provider: str | None = Field(default=None, alias="LLM_PROVIDER")
    llm_timeout_seconds: float | None = Field(default=None, alias="LLM_TIMEOUT_SECONDS")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    gemini_timeout_seconds: float = Field(default=20.0, alias="GEMINI_TIMEOUT_SECONDS")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groqcloud_api_key: str | None = Field(default=None, alias="GROQCLOUD_API_KEY")
    groq_model: str = Field(default="llama-3.1-8b-instant", alias="GROQ_MODEL")
    tts_enabled: bool = Field(default=True, alias="TTS_ENABLED")
    edge_tts_voice: str = Field(default="en-US-AnaNeural", alias="EDGE_TTS_VOICE")
    tts_phrase_min_chars: int = Field(default=28, alias="TTS_PHRASE_MIN_CHARS")
    tts_queue_maxsize: int = Field(default=24, alias="TTS_QUEUE_MAXSIZE")
    tts_chunk_ms: int = Field(default=120, alias="TTS_CHUNK_MS")
    tts_force_flush_timeout_ms: int = Field(
        default=700, alias="TTS_FORCE_FLUSH_TIMEOUT_MS"
    )
    local_tts_enabled: bool = Field(default=False, alias="LOCAL_TTS_ENABLED")
    piper_model_path: str | None = Field(default=None, alias="PIPER_MODEL_PATH")
    piper_sample_rate: int = Field(default=22050, alias="PIPER_SAMPLE_RATE")
    vad_energy_threshold_db: float = Field(default=-42.0, alias="VAD_ENERGY_THRESHOLD_DB")
    vad_silence_timeout_ms: int = Field(default=900, alias="VAD_SILENCE_TIMEOUT_MS")
    vad_pre_roll_ms: int = Field(default=300, alias="VAD_PRE_ROLL_MS")
    stt_model_size: str = Field(default="small.en", alias="STT_MODEL_SIZE")
    stt_beam_size: int = Field(default=3, alias="STT_BEAM_SIZE")
    stt_partial_beam_size: int = Field(default=1, alias="STT_PARTIAL_BEAM_SIZE")
    stt_final_beam_size: int = Field(default=3, alias="STT_FINAL_BEAM_SIZE")
    stt_partial_emit_interval_ms: int = Field(
        default=700, alias="STT_PARTIAL_EMIT_INTERVAL_MS"
    )
    stt_partial_min_audio_ms: int = Field(default=900, alias="STT_PARTIAL_MIN_AUDIO_MS")
    stt_partial_window_ms: int = Field(default=4000, alias="STT_PARTIAL_WINDOW_MS")
    stt_final_min_audio_ms: int = Field(default=700, alias="STT_FINAL_MIN_AUDIO_MS")
    stt_initial_prompt: str = Field(
        default="This is a spoken English conversation between a learner and an AI tutor.",
        alias="STT_INITIAL_PROMPT",
    )

    @property
    def effective_groq_api_key(self) -> str | None:
        return self.groq_api_key or self.groqcloud_api_key

    @property
    def effective_llm_provider(self) -> str:
        if self.llm_provider:
            return self.llm_provider.strip().lower()
        if self.effective_groq_api_key:
            return "groq"
        return "gemini"

    @property
    def effective_llm_timeout_seconds(self) -> float:
        if self.llm_timeout_seconds is not None:
            return self.llm_timeout_seconds
        return self.gemini_timeout_seconds

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
