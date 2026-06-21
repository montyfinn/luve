"""Diagnostic logging for suppressed STT finals.

Suppression reasons were only sent to the client, never logged server-side, so
the cause of intermittent non-finalization was invisible. These guard the log
formatter: it must surface the reason + acoustic metrics for diagnosis, and it
must NEVER include the raw transcript text (hard project rule).
"""
from __future__ import annotations

from src.ten_ext.luve_extension import LUVEExtension


def test_suppression_log_includes_reason_and_metrics() -> None:
    line = LUVEExtension._format_stt_suppression_log(
        "low_average_logprob",
        is_final=True,
        trigger="vad_silence",
        text_len=17,
        word_count=4,
        avg_logprob=-1.2,
        no_speech_prob=0.31,
        low_conf_ratio=0.12,
        speech_ms=910.0,
    )
    assert "ten.stt.suppressed" in line
    assert "reason=low_average_logprob" in line
    assert "is_final=True" in line
    assert "trigger=vad_silence" in line
    assert "text_len=17" in line
    assert "word_count=4" in line
    assert "avg_logprob=-1.2" in line
    assert "no_speech_prob=0.31" in line
    assert "low_conf_ratio=0.12" in line
    assert "speech_ms=910.0" in line


def test_suppression_log_never_contains_raw_transcript() -> None:
    secret = "I listen to music and play games"
    line = LUVEExtension._format_stt_suppression_log(
        "probable_hallucination",
        is_final=True,
        trigger="vad_silence",
        text_len=len(secret),  # length only; the raw text is never passed in
        word_count=len(secret.split()),
        avg_logprob=-0.4,
        no_speech_prob=0.1,
        low_conf_ratio=0.0,
        speech_ms=1500.0,
    )
    assert secret not in line
    assert f"text_len={len(secret)}" in line


def test_suppression_log_handles_missing_metrics() -> None:
    line = LUVEExtension._format_stt_suppression_log(
        "empty_transcript",
        is_final=False,
        trigger="partial_timer",
        text_len=0,
        word_count=0,
        avg_logprob=None,
        no_speech_prob=None,
        low_conf_ratio=None,
        speech_ms=None,
    )
    assert "avg_logprob=None" in line
    assert "speech_ms=None" in line
