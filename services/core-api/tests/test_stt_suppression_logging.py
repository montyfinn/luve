from __future__ import annotations

import logging
from types import SimpleNamespace

from src.schemas.ai_logic import STTAnalysis, WordPoint
from src.ten_ext.luve_extension import LUVEExtension

_LOGGER_NAME = "src.ten_ext.luve_extension"


class _LogMock(LUVEExtension):
    """Minimal stand-in: the suppression logger only needs a session id."""

    def __init__(self) -> None:
        self._session_id = "sess-123"


def _job(*, is_final: bool = True, trigger: str = "vad_silence", speech_ms: float = 820.0):
    return SimpleNamespace(
        is_final=is_final,
        trigger=trigger,
        audio_stats={"speech_ms": speech_ms},
    )


def test_logs_reason_and_metrics(caplog) -> None:
    ext = _LogMock()
    confidence = {
        "word_count": 4,
        "avg_logprob": -0.72,
        "no_speech_prob": 0.05,
        "compression_ratio": 0.86,
        "low_confidence_word_ratio": 0.5,
        "segment_count": 1,
    }
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        ext._log_stt_suppression(
            "too_many_low_confidence_words", job=_job(), confidence=confidence
        )
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "stt.result.suppressed" in joined
    assert "reason=too_many_low_confidence_words" in joined
    assert "session_id=sess-123" in joined
    assert "is_final=True" in joined
    assert "trigger=vad_silence" in joined
    assert "speech_ms=820" in joined
    assert "word_count=4" in joined
    assert "avg_logprob=-0.72" in joined
    assert "low_confidence_word_ratio=0.5" in joined
    assert "segment_count=1" in joined


def test_log_never_contains_transcript_text(caplog) -> None:
    ext = _LogMock()
    analysis = STTAnalysis(
        raw_text="I have no job",
        all_words=[
            WordPoint(word="I", confidence=0.20, start_ms=0.0, end_ms=10.0),
            WordPoint(word="have", confidence=0.30, start_ms=10.0, end_ms=20.0),
            WordPoint(word="no", confidence=0.90, start_ms=20.0, end_ms=30.0),
            WordPoint(word="job", confidence=0.95, start_ms=30.0, end_ms=40.0),
        ],
        avg_logprob=-0.70,
        no_speech_prob=0.05,
        compression_ratio=0.86,
        segment_count=1,
    )
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        ext._log_stt_suppression("low_avg_logprob", job=_job(), analysis=analysis)
    joined = " ".join(r.getMessage() for r in caplog.records)
    # No raw transcript text may leak into the log.
    assert "I have no job" not in joined
    assert "have" not in joined
    assert "job" not in joined
    # Derived, non-sensitive metrics still present.
    assert "reason=low_avg_logprob" in joined
    assert "word_count=4" in joined
    assert "low_confidence_word_ratio=0.5" in joined


def test_missing_metrics_do_not_crash(caplog) -> None:
    ext = _LogMock()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        ext._log_stt_suppression("stt_runtime_error", job=None)
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "reason=stt_runtime_error" in joined
    assert "avg_logprob=None" in joined
    assert "speech_ms=None" in joined
