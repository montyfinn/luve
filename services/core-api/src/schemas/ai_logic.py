from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


DEFAULT_LOW_CONFIDENCE_WORD_THRESHOLD = 0.55


class WordPoint(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    word: str = Field(min_length=1)
    confidence: float
    start_ms: int
    end_ms: int

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: object) -> float:
        if isinstance(value, bool):
            raise ValueError("confidence must be a number in [0, 1]")
        try:
            confidence = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence must be a number in [0, 1]") from exc
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in range [0, 1]")
        return confidence

    @model_validator(mode="before")
    @classmethod
    def normalize_time_unit(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        payload = dict(data)

        if "start" in payload and "start_ms" not in payload:
            payload["start_ms"] = payload.pop("start")
        if "end" in payload and "end_ms" not in payload:
            payload["end_ms"] = payload.pop("end")

        if "start_ms" in payload:
            payload["start_ms"] = cls._to_milliseconds(payload["start_ms"])
        if "end_ms" in payload:
            payload["end_ms"] = cls._to_milliseconds(payload["end_ms"])

        return payload

    @staticmethod
    def _to_milliseconds(value: object) -> int:
        if isinstance(value, bool):
            raise ValueError("timestamps must be numeric")
        if isinstance(value, int):
            if value < 0:
                raise ValueError("timestamps must be non-negative")
            return value

        try:
            seconds = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("timestamps must be numeric") from exc

        if seconds < 0:
            raise ValueError("timestamps must be non-negative")
        return int(round(seconds * 1000))

    @model_validator(mode="after")
    def validate_time_range(self) -> "WordPoint":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class STTAnalysis(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    raw_text: str
    all_words: list[WordPoint] = Field(default_factory=list)
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    compression_ratio: float | None = None
    segment_count: int = 0

    @computed_field
    @property
    def suspicious_count(self) -> int:
        return sum(1 for item in self.all_words if item.confidence < 0.6)

    @computed_field
    @property
    def low_confidence_word_count(self) -> int:
        return sum(
            1
            for item in self.all_words
            if item.confidence < DEFAULT_LOW_CONFIDENCE_WORD_THRESHOLD
        )

    @computed_field
    @property
    def low_confidence_word_ratio(self) -> float:
        if not self.all_words:
            return 0.0
        return self.low_confidence_word_count / len(self.all_words)


class AIReview(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: UUID
    original_stt: STTAnalysis
    grammar_score: int
    feedback_text: str
