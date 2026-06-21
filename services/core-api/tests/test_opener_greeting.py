"""Focused tests for the proactive tutor opening greeting on session ready.

Uses the established MockLUVEExtension pattern (override __init__ to set only the
fields the method touches) so no TEN runtime / DB / network is needed.
"""
from __future__ import annotations

import asyncio

from src.services.session_service import (
    _compute_student_word_count,
    _session_has_student_content,
)
from src.ten_ext.luve_extension import LUVEExtension
from src.ten_ext.tutor_opener import OPENERS


class _FakeTTS:
    def __init__(self) -> None:
        self.fed: list[tuple[str, bool]] = []

    async def feed_text(self, text: str, *, is_final: bool) -> None:
        self.fed.append((text, is_final))


class OpenerExtension(LUVEExtension):
    """Minimal LUVEExtension wired only for the opener path."""

    def __init__(self, *, tts: bool = True, rotation: int = 0) -> None:
        self._opener_sent = False
        self._opener_rotation = rotation
        self._opener_lead_in_seconds = 0.0  # no real sleep in tests
        self._session_id = "s1"
        self._stopping = False
        self._stt_only_mode = False
        self._tts_output_enabled = tts
        self._tts_processor = _FakeTTS() if tts else None
        self._dialogue_history = []
        self._event_log = []
        self._tutor_context_turns = 6
        self._is_assistant_speaking = False
        self._tts_feed_started_at = None
        self._tts_first_chunk_logged = False
        self.emitted: list[tuple[str, dict]] = []

    def _emit_json(self, event, payload):  # capture instead of routing to TEN
        self.emitted.append((event, payload))


def _run(ext: OpenerExtension, session_id: str = "s1") -> None:
    asyncio.run(ext._maybe_send_opening_greeting(session_id))


def _finals(ext: OpenerExtension) -> list[dict]:
    return [payload for event, payload in ext.emitted if event == "assistant_final"]


def test_opener_speaks_first_and_feeds_tts() -> None:
    ext = OpenerExtension()

    _run(ext)

    finals = _finals(ext)
    assert len(finals) == 1
    assert finals[0]["response_text"] == OPENERS[0]
    assert finals[0]["source"] == "opener"
    # Greeting goes through the normal TTS feed (text, then final marker).
    assert ext._tts_processor.fed == [(OPENERS[0], False), ("", True)]
    assert ext._opener_sent is True
    # Echo guard is left to the chunk callback; the feed path unblocks the mic.
    assert ext._is_assistant_speaking is False


def test_opener_fires_only_once_per_session() -> None:
    ext = OpenerExtension()

    _run(ext)
    snapshot = list(ext.emitted)
    fed_snapshot = list(ext._tts_processor.fed)

    _run(ext)  # reconnect / retry START must not re-greet

    assert ext.emitted == snapshot
    assert ext._tts_processor.fed == fed_snapshot
    assert len(_finals(ext)) == 1


def test_opener_is_assistant_turn_never_student() -> None:
    ext = OpenerExtension()

    _run(ext)

    types = [event.get("type") for event in ext._event_log]
    assert types == ["AI_TURN"]
    assert "USER_TURN" not in types
    # Seeds the context window as a tutor turn so follow-ups stay coherent.
    assert ext._dialogue_history == [{"speaker": "tutor", "text": OPENERS[0]}]


def test_opener_does_not_pollute_student_word_count() -> None:
    ext = OpenerExtension()

    _run(ext)

    # Reuse the exact grading / saved-session word-count semantics.
    assert _compute_student_word_count(ext._event_log) == 0
    assert _session_has_student_content(ext._event_log) is False


def test_opener_skipped_for_non_active_session() -> None:
    ext = OpenerExtension()
    ext._session_id = "other"  # a different session is active

    _run(ext, "s1")

    assert ext.emitted == []
    assert ext._opener_sent is False


def test_opener_skipped_in_stt_only_mode() -> None:
    ext = OpenerExtension()
    ext._stt_only_mode = True

    _run(ext)

    assert ext.emitted == []
    assert ext._opener_sent is False


def test_opener_text_only_mode_emits_without_tts() -> None:
    ext = OpenerExtension(tts=False)

    _run(ext)

    finals = _finals(ext)
    assert len(finals) == 1
    assert finals[0]["response_text"] == OPENERS[0]
    assert ext._tts_processor is None
    assert ext._opener_sent is True


def test_opener_rotation_advances_and_varies() -> None:
    ext = OpenerExtension(rotation=1)

    _run(ext)

    assert _finals(ext)[0]["response_text"] == OPENERS[1]
    assert ext._opener_rotation == 2
