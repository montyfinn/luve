from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import threading
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

import numpy as np
from sqlalchemy import text
from src.core.db import engine

from src.core.config import settings
from src.media.brain import LLMProcessor
from src.media.stt_postprocess import sanitize_transcript
from src.media.stt_worker import STTProcessingError, WhisperInference
from src.media.tts import TTSAudioChunk, TTSProcessor
from src.schemas.ai_logic import STTAnalysis
from src.services.session_event_publisher import publish_session_completed
from src.ten_ext.tutor_opener import OPENERS, pick_opener

try:
    import ten  # type: ignore
except ImportError:

    class _FallbackExtension:
        pass

    class _FallbackTen:
        Extension = _FallbackExtension

    ten = _FallbackTen()


logger = logging.getLogger(__name__)
PCM16_MONO_16KHZ_BYTES_PER_SECOND = 32000

# Small lead-in before the proactive opening greeting so the client's WebRTC
# audio/data channel is ready to receive it once the session becomes ready.
OPENER_LEAD_IN_SECONDS = 0.4


# Adaptive STT Rejection thresholds for learner English attempts
LEARNER_PHRASE_MIN_SPEECH_MS = 500.0
LEARNER_SHORT_ANSWER_MIN_SPEECH_MS = 350.0
CONTROLLED_SHORT_ENGLISH_MIN_SPEECH_MS = 300.0
RELAXED_STT_MIN_AVG_LOGPROB = -1.15
RELAXED_STT_MAX_LOW_CONFIDENCE_WORD_RATIO = 0.75
RELAXED_STT_MAX_NO_SPEECH_PROB = 0.80
NON_ENGLISH_VERIFICATION_TIMEOUT_SECONDS = 1.5
NON_ENGLISH_VERIFICATION_MIN_PROBABILITY = 0.60
VIETNAMESE_ACCENTED_CHARS = "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
STT_LANGUAGE_MODES = {"forced_en", "auto", "auto_en_vi"}
INCOMPLETE_SHORT_ENGLISH_FRAGMENTS = {
    "are you",
    "can you",
    "did you",
    "do you",
    "how is",
    "i am",
    "i need",
    "i want",
    "it is",
    "this is",
    "what are",
    "what do",
    "what does",
    "what is",
    "where is",
    "who is",
    "you are",
}
CANNED_STT_HALLUCINATION_PHRASES = {
    "go home now everyone",
    "have a good day",
    "i don t know what to say",
    "i dont know what to say",
    "don t ask me to speak english",
    "dont ask me to speak english",
    "thank you very much",
    "today is a club night",
}
# A set of core pronouns, verbs, prepositions, and high-frequency classroom/speech terms
COMMON_ENGLISH_WORDS = {
    # Pronouns
    "i", "you", "he", "she", "it", "we", "they", "my", "your", "his", "her", "our", "their", "me", "him", "us", "them", "this", "that", "these", "those",
    # Verbs
    "be", "am", "is", "are", "was", "were", "been", "have", "has", "had", "do", "does", "did", "go", "went", "gone", "going", "like", "likes", "liked", "want", "wants", "wanted", "can", "could", "will", "would", "should", "say", "said", "make", "made", "get", "got", "know", "think", "thought", "take", "took", "see", "saw", "come", "came", "find", "found", "use", "used", "tell", "told", "work", "call", "try", "ask", "need", "feel", "become", "leave", "put", "mean", "keep", "let", "begin", "run", "show", "hear", "play", "write", "speak", "spoke", "spoken", "saying", "speaking", "learning", "learn", "learned", "study", "studied", "improve", "improving", "improved",
    # Articles / Prepositions / Conjunctions
    "the", "a", "an", "to", "in", "on", "at", "for", "with", "of", "and", "but", "or", "so", "because", "about", "up", "out", "into", "over", "after", "before", "between", "under", "through", "during", "without",
    # Adjectives / Adverbs / Nouns / Common Helpers
    "not", "no", "yes", "ok", "okay", "good", "bad", "new", "old", "first", "last", "right", "wrong", "well", "very", "just", "more", "most", "some", "any", "other", "all", "what", "where", "when", "why", "how", "who", "which", "there", "here", "then", "now", "always", "never", "sometimes", "often", "people", "time", "year", "day", "way", "thing", "world", "life", "school", "english", "teacher", "student", "class", "lesson", "coffee", "rice", "market", "yesterday", "today", "tomorrow", "please", "thank", "thanks", "name", "live", "help", "friend", "understand", "question", "grammar", "practice"
}

CONTROLLED_SHORT_ENGLISH_UTTERANCES = {
    "hello",
    "hi",
    "hey",
    "what",
    "where",
    "when",
    "why",
    "who",
    "how",
    "yes",
    "no",
    "ok",
    "okay",
    "pardon",
    "sorry",
}

LOW_INFORMATION_SHORT_TOKENS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "for",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "you",
}

# Unaccented Vietnamese phonetic tokens that are ALSO extremely common standalone
# English words. Real Vietnamese forms (thế, ít, hệ) carry accents and are still
# caught by VIETNAMESE_ACCENTED_CHARS; only the bare homograph forms are excluded
# from single-token phonetic matching so normal English finals are not corrupted.
AMBIGUOUS_ENGLISH_HOMOGRAPHS = {"the", "it", "he", "on", "bay", "chin"}

VIETNAMESE_PHONETIC_TOKENS = {
    # Unaccented Vietnamese words/phonemes
    "toi", "toy", "di", "dee", "hoc", "xin", "chao", "ban", "hom", "nay", "troi", "dep", "qua",
    "tuan", "thuy", "minh", "anh", "co", "viet", "nam", "tieng", "nha", "giao", "vien", "sinh",
    "la", "gi", "sao", "the", "cung", "duoc", "khong", "biet", "chua", "roi", "va", "nhieu", "it",
    "dang", "kiem", "tra", "he", "thong", "dong", "noi", "nghe", "nguoi", "lam",
    "mot", "hai", "ba", "bon", "nam", "sau", "bay", "tam", "chin", "muoi", "cam", "on",
    # Accented Vietnamese words
    "tôi", "đi", "học", "xin", "chào", "bạn", "hôm", "nay", "trời", "đẹp", "quá", "tuấn", "thuỷ", "thủy", "minh", "anh", "cô", "việt", "nam", "tiếng", "nhà", "giáo", "viên", "sinh", "là", "gì", "sao", "thế", "cũng", "được", "không", "biết", "chưa", "rồi", "và", "nhiều", "ít", "đang", "kiểm", "tra", "hệ", "thống", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười", "cảm", "ơn"
}




@dataclass(frozen=True)
class InferenceJob:
    is_final: bool
    trigger: str
    queued_at: float
    pcm_bytes: bytes
    session_id: str | None = None
    audio_stats: dict[str, object] | None = None
    suppress_response: bool = False


@dataclass
class UtteranceStats:
    started_at: float
    frames: int = 0
    speech_frames: int = 0
    silence_frames: int = 0
    dbfs_sum: float = 0.0
    dbfs_min: float | None = None
    dbfs_max: float | None = None
    assistant_speech_frames: int = 0

    def add_frame(self, dbfs: float | None, *, is_speech: bool, assistant_speaking: bool) -> None:
        self.frames += 1
        if is_speech:
            self.speech_frames += 1
        else:
            self.silence_frames += 1
        if assistant_speaking:
            self.assistant_speech_frames += 1
        if dbfs is None:
            return
        self.dbfs_sum += dbfs
        self.dbfs_min = dbfs if self.dbfs_min is None else min(self.dbfs_min, dbfs)
        self.dbfs_max = dbfs if self.dbfs_max is None else max(self.dbfs_max, dbfs)

    def snapshot(
        self,
        *,
        pcm_bytes: int,
        trigger: str,
        noise_floor_db: float,
        effective_threshold_db: float,
    ) -> dict[str, object]:
        audio_ms = pcm_bytes / PCM16_MONO_16KHZ_BYTES_PER_SECOND * 1000
        avg_dbfs = self.dbfs_sum / self.frames if self.frames else None
        avg_frame_ms = audio_ms / self.frames if self.frames else 0.0
        speech_ms = self.speech_frames * avg_frame_ms
        return {
            "audio_ms": round(audio_ms, 2),
            "speech_ms": round(speech_ms, 2),
            "trigger": trigger,
            "frames": self.frames,
            "speech_frames": self.speech_frames,
            "silence_frames": self.silence_frames,
            "assistant_speech_frames": self.assistant_speech_frames,
            "dbfs_min": round(self.dbfs_min, 2) if self.dbfs_min is not None else None,
            "dbfs_avg": round(avg_dbfs, 2) if avg_dbfs is not None else None,
            "dbfs_max": round(self.dbfs_max, 2) if self.dbfs_max is not None else None,
            "noise_floor_db": round(noise_floor_db, 2),
            "effective_threshold_db": round(effective_threshold_db, 2),
        }


class LUVEExtension(ten.Extension):
    def __init__(self) -> None:
        super().__init__()
        self._state_lock = threading.Lock()

        self._runtime_loop: asyncio.AbstractEventLoop | None = None
        self._runtime_thread: threading.Thread | None = None

        self._started = False
        self._stopping = False

        self._ten_env: Any = None
        self._properties: dict[str, Any] = {}

        self._audio_sequence = 0
        self._audio_sequence_lock = threading.Lock()

        self._stt_worker: WhisperInference | None = None
        self._llm_processor: LLMProcessor | None = None
        self._tts_processor: TTSProcessor | None = None

        self._inference_queue: asyncio.Queue[InferenceJob] | None = None
        self._inference_task: asyncio.Task[None] | None = None
        self._stt_inference_busy = False
        self._llm_tasks: set[asyncio.Task[None]] = set()
        self._force_flush_task: asyncio.Task[None] | None = None
        self._assistant_speech_release_task: asyncio.Task[None] | None = None
        self._tts_feed_started_at: float | None = None
        self._tts_first_chunk_logged = False
        self._cleanup_lock: asyncio.Lock | None = None
        self._event_log: list[dict[str, object]] = []
        # Bounded conversation context window for the realtime tutor: a sliding
        # list of recent {"speaker": learner|tutor, "text": ...} turns passed to
        # the LLM so replies stay coherent across turns. 0 disables it.
        self._dialogue_history: list[dict[str, str]] = []
        self._tutor_context_turns = 6
        # Proactive opening greeting: the tutor (Lucy) speaks first once the
        # session is ready so the learner does not have to start. One-shot per
        # session (reset in _reset_session_runtime_state); the rotation index
        # persists across sessions (random start) so successive openers vary.
        self._opener_sent = False
        self._opener_rotation = random.randrange(len(OPENERS))
        self._opener_lead_in_seconds = OPENER_LEAD_IN_SECONDS
        self._session_id: str | None = None

        self._utterance_pcm = bytearray()
        self._pre_roll_pcm = bytearray()
        self._is_speaking = False
        self._is_assistant_speaking = False  # Echo protection flag
        self._stt_only_mode = False
        self._tts_output_enabled = True
        self._silence_duration_seconds = 0.0
        self._last_partial_emit_at = 0.0
        self._previous_stt_text = ""  # For context carry between chunks
        self._current_utterance_stats: UtteranceStats | None = None

        self._vad_energy_threshold_db = -38.0  # Balanced sensitivity
        self._vad_noise_floor_db = -55.0
        self._vad_adaptive_margin_db = 10.0
        self._vad_hysteresis_db = 4.0
        self._vad_speech_start_frames = 2
        self._pending_speech_frames = 0
        self._stt_final_min_speech_ms = 180
        self._stt_partial_min_speech_ms = 900
        self._stt_max_utterance_seconds = 16.0
        self._assistant_barge_in_enabled = True
        self._vad_silence_timeout_seconds = 0.8
        self._vad_pre_roll_bytes = int(0.25 * PCM16_MONO_16KHZ_BYTES_PER_SECOND)
        self._stt_partial_emit_interval_seconds = 0.3  # Smooth partial updates
        self._stt_partial_min_audio_bytes = int(
            0.45 * PCM16_MONO_16KHZ_BYTES_PER_SECOND
        )
        self._stt_partial_window_bytes = int(15.0 * PCM16_MONO_16KHZ_BYTES_PER_SECOND)
        self._stt_final_min_audio_bytes = int(0.25 * PCM16_MONO_16KHZ_BYTES_PER_SECOND)
        self._stt_partial_beam_size = 1
        self._stt_final_beam_size = 3
        self._stt_language_mode = "forced_en"
        self._stt_transcribe_language: str | None = "en"
        self._stt_second_pass_verification_enabled = False
        self._stt_model_size = "small.en"
        self._stt_initial_prompt = (
            "This is a spoken English conversation between a learner and an AI tutor."
        )

        self._force_flush_timeout_seconds = 0.6
        self._tts_echo_guard_tail_seconds = 0.9

        self._audio_output_port = "audio_out"
        self._json_output_port = "json_out"
        self._log_output_port = "log_out"

    # TEN lifecycle
    async def start_async(self, ten_env: Any) -> None:
        with self._state_lock:
            if not self._prepare_start_locked(ten_env):
                return
            self._runtime_loop = asyncio.get_running_loop()
            self._runtime_thread = None

        try:
            await self._async_start()
        except Exception:
            with self._state_lock:
                self._reset_runtime_state_locked()
            raise

    def on_start(self, ten_env: Any) -> None:
        with self._state_lock:
            if not self._prepare_start_locked(ten_env):
                return
            self._ensure_runtime_loop_locked()

        try:
            self._submit(self._async_start()).result()
        except Exception:
            with self._state_lock:
                self._reset_runtime_state_locked()
            raise

    async def stop_async(self) -> None:
        with self._state_lock:
            if not self._started or self._stopping:
                return
            self._stopping = True

        try:
            await self._async_stop()
        finally:
            with self._state_lock:
                self._reset_runtime_state_locked()

    def on_audio_frame(self, audio_frame: Any) -> None:
        payload_view = self._extract_audio_payload(audio_frame)
        if payload_view is None or not payload_view:
            return

        # Copy at ingress to avoid memoryview lifetime hazards from TEN-owned buffers.
        payload_bytes = payload_view.tobytes()

        sequence_number = self._extract_sequence_number(audio_frame)
        if sequence_number is None:
            with self._audio_sequence_lock:
                sequence_number = self._audio_sequence
                self._audio_sequence += 1

        self._schedule_on_runtime(
            lambda: self._ingest_audio_frame(sequence_number, payload_bytes),
            label="on_audio_frame",
        )

    def on_cmd(self, cmd: Any) -> None:
        command = self._extract_command_name(cmd)
        requested_session_id = self._extract_session_id(cmd)
        self._emit_log(f"TEN command received: {command}")
        if command == "START":
            session_id = requested_session_id or str(uuid4())
            if self._session_id and self._session_id != session_id:
                self._emit_json(
                    "ten_busy",
                    {
                        "status": "busy",
                        "active_session_id": self._session_id,
                        "requested_session_id": session_id,
                    },
                )
                self._emit_log(
                    "TEN START rejected because another session is active: "
                    f"{self._session_id}"
                )
                return

            self._session_id = session_id
            self._stt_only_mode = self._extract_bool(cmd, "stt_only", default=False)
            self._tts_output_enabled = self._extract_bool(
                cmd, "tts_enabled", default=True
            )
            if self._stt_only_mode or not self._tts_output_enabled:
                self._is_assistant_speaking = False
                self._schedule_on_runtime(
                    lambda: self._disable_tts_for_stt_only(),
                    label="on_cmd:START:disable_tts",
                )
            self._emit_json(
                "ten_started",
                {
                    "status": "ok",
                    "session_id": session_id,
                    "stt_only": self._stt_only_mode,
                    "tts_enabled": self._tts_output_enabled,
                },
            )
            self._schedule_on_runtime(
                lambda: self._ensure_stt_ready_for_session(session_id),
                label="on_cmd:START:stt_ready",
            )
            self._emit_log(f"TEN command START accepted, session_id={session_id}")
            return

        if command in {"END_SESSION", "SESSION_ENDED", "DISCONNECT"}:
            self._schedule_on_runtime(
                lambda: self._handle_session_end(requested_session_id),
                label=f"on_cmd:{command}",
            )
            return

        if command == "FLUSH":
            self._schedule_on_runtime(
                lambda: self._handle_flush(cmd), label="on_cmd:FLUSH"
            )
            return

        if command == "BARGE_IN":
            self._schedule_on_runtime(
                lambda: self._handle_barge_in(), label="on_cmd:BARGE_IN"
            )
            return

        if command == "STOP":
            self._emit_log("TEN command STOP accepted")
            self.on_stop()
            return

        self._emit_json(
            "ten_cmd_unknown",
            {
                "received": command,
            },
        )
        self._emit_log(f"TEN unknown command: {command or '<empty>'}")

    def on_stop(self) -> None:
        with self._state_lock:
            if not self._started or self._stopping:
                return
            self._stopping = True

        with contextlib.suppress(Exception):
            self._submit(self._async_stop()).result()

        with self._state_lock:
            if self._runtime_loop is not None and self._runtime_thread is not None:
                self._runtime_loop.call_soon_threadsafe(self._runtime_loop.stop)
            runtime_thread = self._runtime_thread
            self._reset_runtime_state_locked()

        if runtime_thread is not None and runtime_thread.is_alive():
            runtime_thread.join(timeout=2)

    # Internal async runtime
    async def _async_start(self) -> None:
        self._cleanup_lock = asyncio.Lock()

        self._stt_worker = await WhisperInference.get_instance(
            model_size=self._stt_model_size,
            preferred_device="cuda",
            preferred_compute_type="float16",
            beam_size=int(self._properties.get("stt_beam_size", 5)),
        )
        logger.info(
            "ten.stt.language_config mode=%s model=%s transcribe_language=%s second_pass_verification=%s",
            self._stt_language_mode,
            self._stt_model_size,
            self._stt_transcribe_language,
            self._stt_second_pass_verification_enabled,
        )

        llm_provider = str(
            self._properties.get("llm_provider") or settings.effective_llm_provider
        ).strip().lower()
        llm_api_key = str(
            self._properties.get(f"{llm_provider}_api_key")
            or (
                settings.effective_groq_api_key
                if llm_provider == "groq"
                else settings.gemini_api_key
            )
            or ""
        ).strip()
        llm_model = str(
            self._properties.get(f"{llm_provider}_model")
            or (settings.groq_model if llm_provider == "groq" else settings.gemini_model)
        )
        if llm_api_key:
            self._llm_processor = LLMProcessor(
                api_key=llm_api_key,
                model_name=llm_model,
                provider=llm_provider,
                timeout_seconds=float(
                    self._properties.get(
                        "llm_timeout_seconds",
                        self._properties.get(
                            "gemini_timeout_seconds",
                            settings.effective_llm_timeout_seconds,
                        ),
                    )
                ),
            )
        else:
            self._llm_processor = None

        tts_enabled = bool(self._properties.get("tts_enabled", True))
        if tts_enabled:
            self._tts_processor = TTSProcessor(
                edge_voice=str(
                    self._properties.get("tts_voice", settings.edge_tts_voice)
                ),
                phrase_min_chars=int(
                    self._properties.get(
                        "tts_phrase_min_chars", settings.tts_phrase_min_chars
                    )
                ),
                queue_maxsize=int(
                    self._properties.get(
                        "tts_queue_maxsize", settings.tts_queue_maxsize
                    )
                ),
                chunk_ms=int(
                    self._properties.get("tts_chunk_ms", settings.tts_chunk_ms)
                ),
                local_fallback_enabled=bool(
                    self._properties.get(
                        "tts_local_fallback_enabled", settings.local_tts_enabled
                    )
                ),
                piper_model_path=str(
                    self._properties.get(
                        "tts_piper_model_path", settings.piper_model_path or ""
                    )
                )
                or None,
                piper_sample_rate=int(
                    self._properties.get(
                        "tts_piper_sample_rate", settings.piper_sample_rate
                    )
                ),
            )
            await self._tts_processor.start(self._on_tts_chunk_ready)

        self._inference_queue = asyncio.Queue(maxsize=1)
        self._inference_task = asyncio.create_task(
            self._inference_loop(), name="ten-inference-loop"
        )

    async def _ensure_stt_ready_for_session(self, session_id: str) -> None:
        if self._stt_worker is None:
            self._emit_json(
                "stt_ready_error",
                {
                    "status": "error",
                    "session_id": session_id,
                    "reason": "stt_worker_unavailable",
                },
            )
            return

        was_loaded = self._stt_worker.is_model_loaded
        try:
            await self._stt_worker.load_model()
        except Exception as exc:
            logger.exception("ten.stt.ready_failed session_id=%s", session_id)
            if self._session_id != session_id:
                return
            self._emit_json(
                "stt_ready_error",
                {
                    "status": "error",
                    "session_id": session_id,
                    "reason": "stt_model_load_failed",
                    "detail": type(exc).__name__,
                },
            )
            return

        if self._session_id != session_id:
            return

        runtime = self._stt_worker.runtime
        self._emit_json(
            "stt_ready",
            {
                "status": "ok",
                "session_id": session_id,
                "already_loaded": was_loaded,
                "device": runtime.device if runtime is not None else None,
                "compute_type": runtime.compute_type if runtime is not None else None,
                "language_mode": self._stt_language_mode,
                "transcribe_language": self._stt_transcribe_language,
                "model_size": self._stt_model_size,
            },
        )

        try:
            await self._maybe_send_opening_greeting(session_id)
        except Exception:
            logger.exception("ten.opener.failed session_id=%s", session_id)

    async def _async_stop(self) -> None:
        async with self._cleanup_lock or asyncio.Lock():
            await self._persist_event_log()

            await self._stop_tts_pipeline()

            if self._inference_queue is not None:
                await self._inference_queue.put(
                    InferenceJob(
                        is_final=True,
                        trigger="__stop__",
                        queued_at=time.perf_counter(),
                        pcm_bytes=b"",
                    )
                )
            if self._inference_task is not None:
                await self._inference_task
                self._inference_task = None

            if self._llm_tasks:
                for task in list(self._llm_tasks):
                    task.cancel()
                await asyncio.gather(*self._llm_tasks, return_exceptions=True)
                self._llm_tasks.clear()

            release_stt = bool(self._properties.get("release_stt_model_on_stop", True))
            if release_stt and self._stt_worker is not None:
                await self._stt_worker.unload_model()
            self._stt_worker = None
            self._llm_processor = None
            self._inference_queue = None
            self._reset_session_runtime_state()

    async def _finalize_utterance(
        self,
        trigger: str,
        *,
        suppress_response: bool = False,
    ) -> None:
        if not self._is_speaking or not self._utterance_pcm:
            return

        final_pcm = bytes(self._utterance_pcm)
        audio_stats = self._snapshot_utterance_stats(
            pcm_bytes=len(final_pcm),
            trigger=trigger,
        )
        self._reset_current_utterance()

        await self._enqueue_inference_job(
            is_final=True,
            trigger=trigger,
            pcm_bytes=final_pcm,
            session_id=self._session_id,
            audio_stats=audio_stats,
            suppress_response=suppress_response,
        )

    async def _ingest_audio_frame(
        self, sequence_number: int, payload_bytes: bytes
    ) -> None:
        _ = sequence_number
        if not payload_bytes:
            return

        self._append_to_pre_roll(payload_bytes)
        frame_duration_s = len(payload_bytes) / PCM16_MONO_16KHZ_BYTES_PER_SECOND
        now = time.perf_counter()
        dbfs = self._measure_dbfs(payload_bytes)
        is_speech = self._is_speech_frame(payload_bytes, dbfs=dbfs)

        if self._is_assistant_speaking and self._assistant_barge_in_enabled:
            if not is_speech:
                self._update_noise_floor(dbfs)
                return
            await self._handle_barge_in()
        elif self._is_assistant_speaking:
            return

        if is_speech:
            self._pending_speech_frames += 1
            if not self._is_speaking:
                if self._pending_speech_frames < self._vad_speech_start_frames:
                    return
                self._is_speaking = True
                self._current_utterance_stats = UtteranceStats(started_at=now)
                self._silence_duration_seconds = 0.0
                if self._pre_roll_pcm and not self._utterance_pcm:
                    self._utterance_pcm.extend(self._pre_roll_pcm)
            self._utterance_pcm.extend(payload_bytes)
            self._silence_duration_seconds = 0.0
            self._record_utterance_frame(
                dbfs,
                is_speech=True,
                assistant_speaking=self._is_assistant_speaking,
            )

            if (
                len(self._utterance_pcm) >= self._stt_partial_min_audio_bytes
                and self._current_speech_ms() >= self._stt_partial_min_speech_ms
                and (now - self._last_partial_emit_at)
                >= self._stt_partial_emit_interval_seconds
            ):
                self._last_partial_emit_at = now
                partial_pcm = bytes(
                    self._utterance_pcm[-self._stt_partial_window_bytes :]
                )
                audio_stats = self._snapshot_utterance_stats(
                    pcm_bytes=len(partial_pcm),
                    trigger="partial_timer",
                )
                await self._enqueue_inference_job(
                    is_final=False,
                    trigger="partial_timer",
                    pcm_bytes=partial_pcm,
                    session_id=self._session_id,
                    audio_stats=audio_stats,
                )
            if len(self._utterance_pcm) >= int(
                self._stt_max_utterance_seconds * PCM16_MONO_16KHZ_BYTES_PER_SECOND
            ):
                await self._finalize_utterance(trigger="max_utterance")
            return

        self._pending_speech_frames = 0
        if not self._is_speaking:
            self._update_noise_floor(dbfs)
            return

        self._utterance_pcm.extend(payload_bytes)
        self._silence_duration_seconds += frame_duration_s
        self._record_utterance_frame(
            dbfs,
            is_speech=False,
            assistant_speaking=self._is_assistant_speaking,
        )
        if self._silence_duration_seconds < self._vad_silence_timeout_seconds:
            return

        if self._current_speech_ms() < self._stt_final_min_speech_ms:
            self._log_stt_suppression(
                "too_short_for_final",
                is_final=True,
                trigger="vad_silence",
                audio_stats={"speech_ms": self._current_speech_ms()},
            )
            self._emit_json(
                "stt_vad_ignored",
                {
                    "reason": "too_short_for_final",
                    "speech_ms": round(self._current_speech_ms(), 2),
                    "min_speech_ms": self._stt_final_min_speech_ms,
                    "noise_floor_db": round(self._vad_noise_floor_db, 2),
                    "effective_threshold_db": round(self._effective_vad_threshold_db(), 2),
                },
            )
            self._reset_current_utterance()
            return

        await self._finalize_utterance(trigger="vad_silence")

    async def _handle_flush(self, cmd: Any | None = None) -> None:
        suppress_response = self._extract_bool(
            cmd,
            "suppress_response",
            default=False,
        )
        final_pcm = bytes(self._utterance_pcm)
        audio_stats = self._snapshot_utterance_stats(
            pcm_bytes=len(final_pcm),
            trigger="flush",
        )
        self._reset_current_utterance()
        if final_pcm:
            await self._enqueue_inference_job(
                is_final=True,
                trigger="flush",
                pcm_bytes=final_pcm,
                session_id=self._session_id,
                audio_stats=audio_stats,
                suppress_response=suppress_response,
            )
        self._emit_json(
            "flush_ack",
            {
                "status": "ok",
            },
        )

    async def _disable_tts_for_stt_only(self) -> None:
        await self._stop_tts_pipeline()

    async def _stop_tts_pipeline(self) -> None:
        if self._force_flush_task is not None:
            self._force_flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._force_flush_task
            self._force_flush_task = None
        if self._assistant_speech_release_task is not None:
            self._assistant_speech_release_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._assistant_speech_release_task
            self._assistant_speech_release_task = None
        self._is_assistant_speaking = False
        if self._tts_processor is not None:
            await self._tts_processor.stop_immediately()

    async def _handle_barge_in(self) -> None:
        # Unblock mic immediately instead of waiting for TTS/LLM cleanup to settle.
        had_tts = self._tts_processor is not None or self._is_assistant_speaking
        await self._stop_tts_pipeline()
        if had_tts:
            self._emit_json(
                "assistant_audio_aborted",
                {
                    "reason": "barge_in",
                },
            )
        if self._llm_tasks:
            for task in list(self._llm_tasks):
                task.cancel()
            self._emit_json(
                "assistant_generation_aborted",
                {
                    "reason": "barge_in",
                },
            )
        self._emit_json(
            "barge_in_ack",
            {
                "status": "ok",
                "tts_state": "silent",
            },
        )

    async def _handle_session_end(self, requested_session_id: str | None) -> None:
        active_session_id = self._session_id
        if active_session_id is None:
            return
        if requested_session_id and requested_session_id != active_session_id:
            self._emit_log(
                "Ignoring END_SESSION for non-active session "
                f"{requested_session_id}; active session is {active_session_id}"
            )
            return

        await self._finalize_utterance(
            trigger="session_end",
            suppress_response=True,
        )

        if self._inference_queue is not None:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._inference_queue.join(), timeout=5.0)

        await self._stop_tts_pipeline()

        if self._llm_tasks:
            for task in list(self._llm_tasks):
                task.cancel()
            await asyncio.gather(*self._llm_tasks, return_exceptions=True)
            self._llm_tasks.clear()

        await self._persist_event_log()
        self._emit_json(
            "session_ended",
            {
                "status": "ok",
                "session_id": active_session_id,
            },
        )
        self._reset_session_runtime_state()

    def _append_to_pre_roll(self, payload_bytes: bytes) -> None:
        self._pre_roll_pcm.extend(payload_bytes)
        if len(self._pre_roll_pcm) > self._vad_pre_roll_bytes:
            overshoot = len(self._pre_roll_pcm) - self._vad_pre_roll_bytes
            del self._pre_roll_pcm[:overshoot]

    def _measure_dbfs(self, payload_bytes: bytes) -> float | None:
        samples = np.frombuffer(payload_bytes, dtype=np.int16)
        if samples.size == 0:
            return None
        rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float32)))))
        if rms <= 0.0:
            return None
        return float(20.0 * np.log10(rms / 32768.0 + 1e-12))

    def _is_speech_frame(self, payload_bytes: bytes, *, dbfs: float | None) -> bool:
        _ = payload_bytes
        if dbfs is None:
            return False
        threshold = self._effective_vad_threshold_db()
        if self._is_speaking:
            threshold -= self._vad_hysteresis_db
        return dbfs >= threshold

    def _effective_vad_threshold_db(self) -> float:
        adaptive_threshold = self._vad_noise_floor_db + self._vad_adaptive_margin_db
        return max(self._vad_energy_threshold_db, adaptive_threshold)

    def _update_noise_floor(self, dbfs: float | None) -> None:
        if dbfs is None:
            return
        if dbfs >= self._effective_vad_threshold_db():
            return
        # Slow EWMA avoids sudden threshold jumps while still tracking room noise.
        self._vad_noise_floor_db = (self._vad_noise_floor_db * 0.97) + (dbfs * 0.03)

    def _record_utterance_frame(
        self,
        dbfs: float | None,
        *,
        is_speech: bool,
        assistant_speaking: bool,
    ) -> None:
        if self._current_utterance_stats is None:
            self._current_utterance_stats = UtteranceStats(started_at=time.perf_counter())
        self._current_utterance_stats.add_frame(
            dbfs,
            is_speech=is_speech,
            assistant_speaking=assistant_speaking,
        )

    def _snapshot_utterance_stats(
        self,
        *,
        pcm_bytes: int,
        trigger: str,
    ) -> dict[str, object] | None:
        if self._current_utterance_stats is None:
            return None
        return self._current_utterance_stats.snapshot(
            pcm_bytes=pcm_bytes,
            trigger=trigger,
            noise_floor_db=self._vad_noise_floor_db,
            effective_threshold_db=self._effective_vad_threshold_db(),
        )

    def _current_speech_ms(self) -> float:
        if self._current_utterance_stats is None or not self._utterance_pcm:
            return 0.0
        audio_ms = len(self._utterance_pcm) / PCM16_MONO_16KHZ_BYTES_PER_SECOND * 1000
        if self._current_utterance_stats.frames <= 0:
            return 0.0
        avg_frame_ms = audio_ms / self._current_utterance_stats.frames
        return self._current_utterance_stats.speech_frames * avg_frame_ms

    def _reset_current_utterance(self) -> None:
        self._utterance_pcm.clear()
        self._is_speaking = False
        self._silence_duration_seconds = 0.0
        self._last_partial_emit_at = 0.0
        self._pending_speech_frames = 0
        self._current_utterance_stats = None

    async def _enqueue_inference_job(
        self,
        *,
        is_final: bool,
        trigger: str,
        pcm_bytes: bytes,
        session_id: str | None = None,
        audio_stats: dict[str, object] | None = None,
        suppress_response: bool = False,
    ) -> None:
        if not pcm_bytes:
            return
        if self._inference_queue is None:
            return

        if not is_final:
            if self._stt_inference_busy or self._has_queued_final_inference():
                return

        if is_final:
            self._drop_queued_partial_inference()
            if self._has_queued_final_inference():
                return

        if self._inference_queue.full():
            if not is_final:
                return
            self._drop_one_queued_inference()

        if self._inference_queue.full():
            if is_final:
                # A final could not be enqueued (queue still full) — the
                # utterance is lost. Surface it so finalization gaps are visible.
                logger.warning(
                    "ten.stt.final_dropped_queue_full session_id=%s trigger=%s",
                    self._session_id,
                    trigger,
                )
            return

        await self._inference_queue.put(
            InferenceJob(
                is_final=is_final,
                trigger=trigger,
                queued_at=time.perf_counter(),
                pcm_bytes=pcm_bytes,
                session_id=session_id,
                audio_stats=audio_stats,
                suppress_response=suppress_response,
            )
        )

    def _has_queued_final_inference(self) -> bool:
        if self._inference_queue is None:
            return False
        return any(job.is_final for job in list(self._inference_queue._queue))

    def _drop_queued_partial_inference(self) -> None:
        if self._inference_queue is None or self._inference_queue.empty():
            return

        queued_jobs = list(self._inference_queue._queue)
        kept_jobs = [job for job in queued_jobs if job.is_final]
        dropped_partials = len(queued_jobs) - len(kept_jobs)
        if not dropped_partials:
            return

        self._inference_queue._queue.clear()
        self._inference_queue._queue.extend(kept_jobs)

        # Dropped jobs will never be consumed by _inference_loop.
        for _ in range(dropped_partials):
            with contextlib.suppress(ValueError):
                self._inference_queue.task_done()

        logger.info(
            "ten.stt.partial_dropped_for_final count=%s",
            dropped_partials,
        )

    def _drop_one_queued_inference(self) -> None:
        if self._inference_queue is None:
            return
        with contextlib.suppress(asyncio.QueueEmpty):
            self._inference_queue.get_nowait()
            with contextlib.suppress(ValueError):
                self._inference_queue.task_done()

    async def _inference_loop(self) -> None:
        if self._inference_queue is None:
            return

        while True:
            acquired_job = False
            try:
                job = await self._inference_queue.get()
                acquired_job = True
                if job.trigger == "__stop__":
                    return

                if self._stt_worker is None:
                    continue

                min_audio_bytes = (
                    self._stt_final_min_audio_bytes
                    if job.is_final
                    else self._stt_partial_min_audio_bytes
                )
                if len(job.pcm_bytes) < min_audio_bytes:
                    continue

                # Keep live STT decode stateless. Carrying previous text into
                # partials can amplify one bad final into repeated hallucinated
                # partials on background audio.
                contextual_prompt = self._stt_initial_prompt

                queued_ms = max((time.perf_counter() - job.queued_at) * 1000, 0.0)
                stt_log = logger.info if job.is_final else logger.debug
                stt_log(
                    "ten.stt.job_started is_final=%s trigger=%s queued_ms=%.2f",
                    job.is_final,
                    job.trigger,
                    queued_ms,
                )
                started = time.perf_counter()
                try:
                    self._stt_inference_busy = True
                    analysis = await self._stt_worker.transcribe_audio_bytes(
                        job.pcm_bytes,
                        language=self._stt_transcribe_language,
                        initial_prompt=contextual_prompt,
                        beam_size=self._stt_final_beam_size
                        if job.is_final
                        else self._stt_partial_beam_size,
                        word_timestamps=bool(
                            job.is_final and settings.stt_final_word_timestamps
                        ),
                        # Live VAD already owns utterance boundaries. Running
                        # Whisper's internal VAD again on finals can trim/mutate
                        # the same audio that partials recognized correctly.
                        vad_filter=False,
                        condition_on_previous_text=False,
                    )
                except STTProcessingError as exc:
                    self._emit_json(
                        "stt_error",
                        {
                            "reason": "stt_runtime_error",
                            "is_final": job.is_final,
                            "trigger": job.trigger,
                            "audio": job.audio_stats,
                        },
                    )
                    self._emit_json(
                        "stt_result_suppressed",
                        {
                            "reason": "stt_runtime_error",
                            "is_final": job.is_final,
                            "trigger": job.trigger,
                            "audio": job.audio_stats,
                        },
                    )
                    logger.warning("ten.stt.runtime_error reason=%s", exc)
                    self._log_stt_suppression(
                        "stt_runtime_error",
                        is_final=job.is_final,
                        trigger=job.trigger,
                        audio_stats=job.audio_stats,
                    )
                    if job.is_final:
                        self._reset_current_utterance()
                    continue
                finally:
                    self._stt_inference_busy = False

                analysis.raw_text = sanitize_transcript(analysis.raw_text)
                original_stt_text = analysis.raw_text
                mixed_language_filtered = False
                mixed_language_reasons: list[str] = []
                if job.is_final and original_stt_text.strip():
                    prepared_text, mixed_reasons = self._split_mixed_language_transcript(
                        original_stt_text
                    )
                    mixed_language_reasons = mixed_reasons
                    if "mixed_non_english" in mixed_reasons:
                        self._log_stt_suppression(
                            "mixed_non_english",
                            is_final=job.is_final,
                            trigger=job.trigger,
                            analysis=analysis,
                            audio_stats=job.audio_stats,
                        )
                        self._emit_json(
                            "stt_result_suppressed",
                            {
                                "reason": "mixed_non_english",
                                "is_final": job.is_final,
                                "trigger": job.trigger,
                                "text": original_stt_text,
                                "audio": job.audio_stats,
                                "stt": analysis.model_dump(),
                                "confidence": self._stt_confidence_metrics(analysis),
                            },
                        )
                        if job.is_final:
                            self._reset_current_utterance()
                        continue
                    if prepared_text and prepared_text != original_stt_text:
                        analysis = analysis.model_copy(update={"raw_text": prepared_text})
                        mixed_language_filtered = True

                if self._is_probable_stt_hallucination(
                    analysis.raw_text,
                    is_final=job.is_final,
                    audio_stats=job.audio_stats,
                    pcm_bytes=len(job.pcm_bytes),
                ):
                    self._log_stt_suppression(
                        "probable_hallucination",
                        is_final=job.is_final,
                        trigger=job.trigger,
                        analysis=analysis,
                        audio_stats=job.audio_stats,
                    )
                    self._emit_json(
                        "stt_result_suppressed",
                        {
                            "reason": "probable_hallucination",
                            "is_final": job.is_final,
                            "trigger": job.trigger,
                            "text": analysis.raw_text,
                            "audio": job.audio_stats,
                        },
                    )
                    if job.is_final:
                        self._reset_current_utterance()
                    continue

                verification_status = "skipped"
                verification_analysis: STTAnalysis | None = None
                confidence = self._stt_confidence_metrics(analysis)
                if (
                    job.is_final
                    and analysis.raw_text.strip()
                    and not mixed_language_filtered
                ):
                    verification_status, verification_analysis = (
                        await self._verify_non_english_if_suspicious(
                            analysis=analysis,
                            pcm_bytes=job.pcm_bytes,
                            audio_stats=job.audio_stats,
                            confidence=confidence,
                        )
                    )
                    if verification_status == "suppressed":
                        self._log_stt_suppression(
                            "non_english_verification_failed",
                            is_final=job.is_final,
                            trigger=job.trigger,
                            analysis=analysis,
                            audio_stats=job.audio_stats,
                            confidence=confidence,
                        )
                        self._emit_json(
                            "stt_result_suppressed",
                            {
                                "reason": "non_english_verification_failed",
                                "is_final": job.is_final,
                                "trigger": job.trigger,
                                "text": analysis.raw_text,
                                "audio": job.audio_stats,
                                "stt": analysis.model_dump(),
                                "confidence": confidence,
                                "verification": (
                                    verification_analysis.model_dump()
                                    if verification_analysis is not None
                                    else None
                                ),
                            },
                        )
                        if job.is_final:
                            self._reset_current_utterance()
                        continue

                stt_rejection = self._stt_rejection_reason(
                    analysis,
                    is_final=job.is_final,
                    audio_stats=job.audio_stats,
                )
                if stt_rejection is not None:
                    self._log_stt_suppression(
                        stt_rejection,
                        is_final=job.is_final,
                        trigger=job.trigger,
                        analysis=analysis,
                        audio_stats=job.audio_stats,
                        confidence=confidence,
                    )
                    self._emit_json(
                        "stt_result_suppressed",
                        {
                            "reason": stt_rejection,
                            "is_final": job.is_final,
                            "trigger": job.trigger,
                            "text": analysis.raw_text,
                            "audio": job.audio_stats,
                            "stt": analysis.model_dump(),
                            "confidence": self._stt_confidence_metrics(analysis),
                        },
                    )
                    if job.is_final:
                        self._reset_current_utterance()
                    continue

                hop_ms = max((time.perf_counter() - job.queued_at) * 1000, 0.0)
                inference_ms = (time.perf_counter() - started) * 1000
                turn_metadata = self._stt_quality_assessment(
                    analysis,
                    audio_stats=job.audio_stats,
                    inference_ms=inference_ms,
                    verification_status=verification_status,
                    original_text=original_stt_text,
                    mixed_language_filtered=mixed_language_filtered,
                    mixed_language_reasons=mixed_language_reasons,
                ) if job.is_final and analysis.raw_text.strip() else None

                if job.is_final and turn_metadata is not None:
                    final_rejection = self._final_stt_acceptance_rejection_reason(
                        analysis,
                        trigger=job.trigger,
                        audio_stats=job.audio_stats,
                        turn_metadata=turn_metadata,
                        mixed_language_filtered=mixed_language_filtered,
                    )
                    if final_rejection is not None:
                        self._log_stt_suppression(
                            final_rejection,
                            is_final=job.is_final,
                            trigger=job.trigger,
                            analysis=analysis,
                            audio_stats=job.audio_stats,
                            confidence=confidence,
                        )
                        self._emit_json(
                            "stt_result_suppressed",
                            {
                                "reason": final_rejection,
                                "is_final": job.is_final,
                                "trigger": job.trigger,
                                "text": analysis.raw_text,
                                "audio": job.audio_stats,
                                "stt": analysis.model_dump(),
                                "confidence": self._stt_confidence_metrics(analysis),
                                "turn_metadata": turn_metadata,
                                "latency": {
                                    "graph_hop_ms": round(hop_ms, 2),
                                    "stt_inference_ms": round(inference_ms, 2),
                                },
                            },
                        )
                        self._reset_current_utterance()
                        continue

                # Update context only after the final text survives cleanup.
                if job.is_final and analysis.raw_text.strip():
                    self._previous_stt_text = analysis.raw_text.strip()

                logger.info(
                    "TEN STT output processed final=%s text_len=%d avg_logprob=%s no_speech_prob=%s",
                    job.is_final,
                    len(analysis.raw_text),
                    analysis.avg_logprob,
                    analysis.no_speech_prob,
                )
                stt_log(
                    "ten.stt.job_finished is_final=%s trigger=%s inference_ms=%.2f total_ms=%.2f",
                    job.is_final,
                    job.trigger,
                    inference_ms,
                    hop_ms,
                )
                self._emit_json(
                    "stt_result",
                    {
                        "is_final": job.is_final,
                        "trigger": job.trigger,
                        "decode": {
                            "beam_size": self._stt_final_beam_size
                            if job.is_final
                            else self._stt_partial_beam_size,
                            "vad_filter": False,
                            "condition_on_previous_text": False,
                        },
                        "audio": job.audio_stats,
                        "latency": {
                            "graph_hop_ms": round(hop_ms, 2),
                            "stt_inference_ms": round(inference_ms, 2),
                            "within_50ms_hop_target": hop_ms < 50.0,
                        },
                        "stt": analysis.model_dump(),
                    },
                )

                if job.is_final and analysis.raw_text.strip():
                    self._event_log.append(
                        {
                            "type": "USER_TURN",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "payload": {
                                "text": analysis.raw_text,
                                **(turn_metadata or {}),
                            },
                        }
                    )
                    if self._stt_only_mode or job.suppress_response:
                        self._emit_json(
                            "stt_only_final",
                            {
                                "status": "ok",
                                "text": analysis.raw_text,
                                "suppress_response": job.suppress_response,
                            },
                        )
                    else:
                        await self._spawn_llm_for_final(analysis, turn_metadata or {})
            except Exception:
                logger.exception("ten-inference-loop error")
                await asyncio.sleep(1.0)
            finally:
                if acquired_job and self._inference_queue is not None:
                    self._inference_queue.task_done()

    async def _spawn_llm_for_final(
        self,
        analysis: STTAnalysis,
        stt_metadata: dict[str, object],
    ) -> None:
        if not self._responses_enabled():
            return
        self._reset_tts_timing()
        if self._llm_processor is None:
            await self._emit_local_fallback_reply(analysis)
            return

        task = asyncio.create_task(
            self._run_llm_pipeline(analysis, stt_metadata), name="ten-llm-pipeline"
        )
        self._llm_tasks.add(task)
        task.add_done_callback(self._llm_tasks.discard)

    async def _emit_local_fallback_reply(self, analysis: STTAnalysis) -> None:
        if not self._responses_enabled():
            return
        if not analysis.raw_text.strip():
            return

        started = time.perf_counter()
        logger.info("ten.llm.started source=local_fallback")
        try:
            result = LLMProcessor.build_fallback_reply(analysis)
            if not self._responses_enabled():
                return
            if result.response_text:
                if self._tts_output_enabled:
                    self._is_assistant_speaking = True  # Block mic only for audible output.
                self._emit_json(
                    "assistant_stream",
                    {
                        "delta": result.response_text,
                        "source": "local_fallback",
                    },
                )
                if self._tts_processor is not None and self._tts_output_enabled:
                    self._mark_tts_feed_started()
                    await self._tts_processor.feed_text(
                        result.response_text, is_final=False
                    )

            if self._tts_processor is not None and self._tts_output_enabled:
                await self._tts_processor.feed_text("", is_final=True)

            self._emit_json(
                "assistant_final",
                {
                    "response_text": result.response_text,
                    "pedagogical_feedback": result.pedagogical_feedback,
                    "source": "local_fallback",
                },
            )
        finally:
            logger.info(
                "ten.llm.finished source=local_fallback duration_ms=%.2f",
                (time.perf_counter() - started) * 1000,
            )
            self._is_assistant_speaking = False  # ALWAYS unblock mic input

    async def _maybe_send_opening_greeting(self, session_id: str) -> None:
        """Have the tutor (Lucy) greet first, once, when the session is ready.

        Fires at most once per session (``_opener_sent`` one-shot, reset in
        ``_reset_session_runtime_state``) so reconnect/retry STARTs do not
        repeat it. Reuses the normal assistant/TTS emit path so echo protection
        applies, records the greeting only as an assistant turn (never a
        USER_TURN, so grading and the student word count are untouched), and
        seeds the dialogue history so the first learner reply stays coherent and
        Lucy does not greet again.
        """
        if self._opener_sent:
            return
        if not self._responses_enabled() or self._session_id != session_id:
            return
        # Claim the one-shot before awaiting so a concurrent START cannot
        # double-fire while we wait for the client to settle.
        self._opener_sent = True

        if self._opener_lead_in_seconds > 0:
            await asyncio.sleep(self._opener_lead_in_seconds)
        if not self._responses_enabled() or self._session_id != session_id:
            return

        opener = pick_opener(self._opener_rotation)
        self._opener_rotation += 1

        self._reset_tts_timing()
        try:
            if self._tts_output_enabled:
                self._is_assistant_speaking = True  # Block mic only for audible output.
            self._emit_json(
                "assistant_stream",
                {"delta": opener, "source": "opener"},
            )
            if self._tts_processor is not None and self._tts_output_enabled:
                self._mark_tts_feed_started()
                await self._tts_processor.feed_text(opener, is_final=False)
                await self._tts_processor.feed_text("", is_final=True)
            self._emit_json(
                "assistant_final",
                {
                    "response_text": opener,
                    "pedagogical_feedback": None,
                    "source": "opener",
                },
            )
            # Assistant turn only: never a USER_TURN, so the student word count
            # and saved-session filter still treat an opener-only session as empty.
            self._event_log.append(
                {
                    "type": "AI_TURN",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "text": opener,
                        "pedagogical_feedback": None,
                        "source": "opener",
                    },
                }
            )
            if self._tutor_context_turns > 0:
                self._dialogue_history.append(
                    {"speaker": "tutor", "text": opener}
                )
            logger.info(
                "ten.opener.sent session_id=%s rotation=%s",
                session_id,
                self._opener_rotation - 1,
            )
        finally:
            self._is_assistant_speaking = False  # ALWAYS unblock mic input

    async def _run_llm_pipeline(
        self,
        analysis: STTAnalysis,
        stt_metadata: dict[str, object],
    ) -> None:
        if not self._responses_enabled():
            return
        if self._llm_processor is None:
            return

        llm_started = time.perf_counter()
        llm_source = self._llm_processor.source
        logger.info("ten.llm.started source=%s", llm_source)
        try:
            llm_raw_buffer = ""
            streamed_response_buffer = ""

            async def restart_force_flush() -> None:
                if (
                    self._tts_processor is None
                    or not self._tts_output_enabled
                    or not self._responses_enabled()
                ):
                    return
                if self._force_flush_task is not None:
                    self._force_flush_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._force_flush_task
                self._force_flush_task = asyncio.create_task(
                    self._force_flush_timeout(),
                    name="ten-tts-force-flush",
                )

            async def on_token(delta: str) -> None:
                nonlocal llm_raw_buffer
                nonlocal streamed_response_buffer

                if not delta:
                    return
                if not self._responses_enabled():
                    return
                llm_raw_buffer += delta
                current_response_text = self._extract_response_text(llm_raw_buffer)
                response_delta = self._diff_streamed_text(
                    streamed_response_buffer, current_response_text
                )
                if not response_delta:
                    return
                streamed_response_buffer += response_delta

                self._emit_json(
                    "assistant_stream",
                    {
                        "delta": response_delta,
                        "source": self._llm_processor.source,
                    },
                )

                if self._tts_processor is not None and self._tts_output_enabled:
                    self._mark_tts_feed_started()
                    await self._tts_processor.feed_text(response_delta, is_final=False)
                    await restart_force_flush()

            result = await self._llm_processor.stream_response(
                session_id=uuid4(),
                stt=analysis,
                on_token=on_token,
                stt_metadata=stt_metadata,
                history=(
                    self._dialogue_history[-self._tutor_context_turns:]
                    if self._tutor_context_turns > 0
                    else None
                ),
            )
            if not self._responses_enabled():
                return

            final_tail = self._diff_streamed_text(
                streamed_response_buffer, result.response_text
            )
            if final_tail:
                if not self._responses_enabled():
                    return
                self._emit_json(
                    "assistant_stream",
                    {
                        "delta": final_tail,
                        "source": result.source,
                    },
                )
                if self._tts_processor is not None and self._tts_output_enabled:
                    self._mark_tts_feed_started()
                    await self._tts_processor.feed_text(final_tail, is_final=False)

            if self._force_flush_task is not None:
                self._force_flush_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._force_flush_task
                self._force_flush_task = None

            if self._tts_processor is not None and self._tts_output_enabled:
                await self._tts_processor.feed_text("", is_final=True)

            self._emit_json(
                "assistant_final",
                {
                    "response_text": result.response_text,
                    "pedagogical_feedback": result.pedagogical_feedback,
                    "source": result.source,
                },
            )
            self._event_log.append(
                {
                    "type": "AI_TURN",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "text": result.response_text,
                        "pedagogical_feedback": result.pedagogical_feedback,
                        "source": result.source,
                    },
                }
            )
            if self._tutor_context_turns > 0:
                learner_text = (analysis.raw_text or "").strip()
                tutor_text = (result.response_text or "").strip()
                if learner_text:
                    self._dialogue_history.append(
                        {"speaker": "learner", "text": learner_text}
                    )
                if tutor_text:
                    self._dialogue_history.append(
                        {"speaker": "tutor", "text": tutor_text}
                    )
                max_keep = max(self._tutor_context_turns * 2, 12)
                if len(self._dialogue_history) > max_keep:
                    self._dialogue_history = self._dialogue_history[-max_keep:]
            logger.info(
                "ten.llm.finished source=%s duration_ms=%.2f response_chars=%s",
                result.source,
                (time.perf_counter() - llm_started) * 1000,
                len(result.response_text or ""),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "ten.llm.pipeline_failed source=%s duration_ms=%.2f",
                llm_source,
                (time.perf_counter() - llm_started) * 1000,
            )
            if self._responses_enabled():
                self._emit_json(
                    "llm_error",
                    {
                        "message": "Assistant response failed. Please try again.",
                    },
                )
        finally:
            self._is_assistant_speaking = False  # ALWAYS unblock mic input

    async def _force_flush_timeout(self) -> None:
        if (
            self._tts_processor is None
            or not self._tts_output_enabled
            or not self._responses_enabled()
        ):
            return
        await asyncio.sleep(self._force_flush_timeout_seconds)
        if not self._responses_enabled():
            return
        await self._tts_processor.force_flush()

    async def _on_tts_chunk_ready(self, chunk: TTSAudioChunk) -> None:
        if not self._tts_output_enabled or not self._responses_enabled():
            self._is_assistant_speaking = False
            return
        # Echo Protection: Block mic only while audio is actually playing
        if self._assistant_speech_release_task is not None:
            self._assistant_speech_release_task.cancel()
            self._assistant_speech_release_task = None
        self._is_assistant_speaking = True

        audio_frame = self._build_ten_audio_frame(chunk)
        self._emit_audio(audio_frame)
        self._emit_json(
            "assistant_audio_meta",
            {
                "phrase_id": chunk.phrase_id,
                "chunk_index": chunk.chunk_index,
                "sequence_number": chunk.sequence_number,
                "is_last_chunk": chunk.is_last_chunk,
                "sample_rate": 16000,
                "channels": 1,
                "audio_format": "pcm_s16le",
                "echo_guard_tail_ms": round(self._tts_echo_guard_tail_seconds * 1000),
            },
        )

        if chunk.is_last_chunk:
            self._assistant_speech_release_task = asyncio.create_task(
                self._release_assistant_speaking_after_tail(),
                name="ten-assistant-speech-release",
            )

        if not self._tts_first_chunk_logged:
            self._tts_first_chunk_logged = True
            feed_started_at = self._tts_feed_started_at
            first_chunk_ms = (
                (time.perf_counter() - feed_started_at) * 1000
                if feed_started_at is not None
                else None
            )
            logger.info(
                "ten.tts.first_chunk phrase_id=%s chunk_index=%s sequence_number=%s first_chunk_ms=%s",
                chunk.phrase_id,
                chunk.chunk_index,
                chunk.sequence_number,
                round(first_chunk_ms, 2) if first_chunk_ms is not None else None,
            )

    async def _release_assistant_speaking_after_tail(self) -> None:
        await asyncio.sleep(self._tts_echo_guard_tail_seconds)
        self._is_assistant_speaking = False

    def _reset_tts_timing(self) -> None:
        self._tts_feed_started_at = None
        self._tts_first_chunk_logged = False

    def _mark_tts_feed_started(self) -> None:
        if self._tts_feed_started_at is None:
            self._tts_feed_started_at = time.perf_counter()
            logger.info("ten.tts.started")

    # TEN output helpers
    def _responses_enabled(self) -> bool:
        return (
            self._session_id is not None
            and not self._stopping
            and not self._stt_only_mode
        )

    def _build_ten_audio_frame(self, chunk: TTSAudioChunk) -> Any:
        payload_view = memoryview(chunk.pcm16_mono_16khz)
        audio_frame_cls = getattr(ten, "AudioFrame", None)
        if audio_frame_cls is None:
            return {
                "data": payload_view,
                "sample_rate": 16000,
                "channels": 1,
                "sample_format": "s16le",
                "sequence_number": chunk.sequence_number,
                "session_id": self._session_id,
                "timestamp_ms": int(time.time() * 1000),
            }

        frame = audio_frame_cls()
        for attr, value in (
            ("sample_rate", 16000),
            ("channels", 1),
            ("sample_format", "s16le"),
            ("sequence_number", chunk.sequence_number),
        ):
            if hasattr(frame, attr):
                setattr(frame, attr, value)
        with contextlib.suppress(Exception):
            setattr(frame, "session_id", self._session_id)

        if hasattr(frame, "set_buffer") and callable(getattr(frame, "set_buffer")):
            frame.set_buffer(payload_view)
        elif hasattr(frame, "buffer"):
            frame.buffer = payload_view
        elif hasattr(frame, "data"):
            frame.data = payload_view
        return frame

    def _emit_audio(self, frame: Any) -> None:
        if self._ten_env is None:
            return
        for method_name in ("send_audio_frame", "push_audio_frame", "emit_audio_frame"):
            method = getattr(self._ten_env, method_name, None)
            if callable(method):
                for args in (
                    (self._audio_output_port, frame),
                    (frame, self._audio_output_port),
                    (frame,),
                ):
                    try:
                        method(*args)
                        return
                    except TypeError:
                        continue

    def _emit_json(self, event: str, payload: dict[str, Any]) -> None:
        if self._ten_env is None:
            return
        # Automatically include session_id in all JSON messages if available
        if self._session_id is not None:
            payload = {**payload, "session_id": self._session_id}
        message = {"event": event, **payload}
        for method_name in ("send_json", "push_json", "emit_json", "send_data"):
            method = getattr(self._ten_env, method_name, None)
            if callable(method):
                for args in (
                    (self._json_output_port, message),
                    (message, self._json_output_port),
                    (message,),
                ):
                    try:
                        method(*args)
                        return
                    except TypeError:
                        continue

    def _emit_log(self, text: str) -> None:
        if self._ten_env is None:
            return
        for method_name in ("send_text", "send_log", "emit_text", "send_data"):
            method = getattr(self._ten_env, method_name, None)
            if callable(method):
                for args in (
                    (self._log_output_port, text),
                    (text, self._log_output_port),
                    (text,),
                ):
                    try:
                        method(*args)
                        return
                    except TypeError:
                        continue

    # Utilities
    def _schedule_on_runtime(
        self, coroutine_factory: Callable[[], Awaitable[Any]], *, label: str
    ) -> None:
        with self._state_lock:
            loop = self._runtime_loop
        if loop is None:
            self._emit_log(f"Runtime loop unavailable for {label}")
            return

        def _dispatch() -> None:
            task = asyncio.create_task(
                coroutine_factory(), name=f"ten-dispatch:{label}"
            )
            task.add_done_callback(self._log_background_task_result)

        # OS-thread safe handoff from TEN callback thread to Python event loop.
        loop.call_soon_threadsafe(_dispatch)

    def _log_background_task_result(self, task: asyncio.Task[Any]) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            exc = task.exception()
            if exc is not None:
                logger.exception(
                    "ten.runtime.task_failed name=%s", task.get_name(), exc_info=exc
                )
                self._emit_log(f"TEN runtime task failed: {task.get_name()}")

    def _ensure_runtime_loop_locked(self) -> None:
        if self._runtime_loop is not None:
            return

        loop_ready = threading.Event()
        loop_holder: dict[str, asyncio.AbstractEventLoop] = {}

        def _runner() -> None:
            runtime_loop = asyncio.new_event_loop()
            loop_holder["loop"] = runtime_loop
            asyncio.set_event_loop(runtime_loop)
            loop_ready.set()
            try:
                runtime_loop.run_forever()
            finally:
                runtime_loop.close()

        runtime_thread = threading.Thread(
            target=_runner, name="luve-ten-runtime", daemon=True
        )
        runtime_thread.start()

        if not loop_ready.wait(timeout=2):
            raise RuntimeError("TEN runtime loop failed to initialize")
        runtime_loop = loop_holder.get("loop")
        if runtime_loop is None:
            raise RuntimeError("TEN runtime loop was not created")

        self._runtime_loop = runtime_loop
        self._runtime_thread = runtime_thread

    def _prepare_start_locked(self, ten_env: Any) -> bool:
        if self._started:
            return False

        self._started = True
        self._stopping = False
        self._ten_env = ten_env
        self._properties = self._load_properties(ten_env)
        self._utterance_pcm.clear()
        self._pre_roll_pcm.clear()
        self._is_speaking = False
        self._silence_duration_seconds = 0.0
        self._last_partial_emit_at = 0.0

        self._vad_energy_threshold_db = float(
            self._properties.get(
                "vad_energy_threshold_db", self._vad_energy_threshold_db
            )
        )
        self._vad_adaptive_margin_db = max(
            float(self._properties.get("vad_adaptive_margin_db", 10.0)),
            3.0,
        )
        self._vad_noise_floor_db = float(
            self._properties.get(
                "vad_initial_noise_floor_db",
                self._vad_energy_threshold_db - self._vad_adaptive_margin_db,
            )
        )
        self._vad_hysteresis_db = max(
            float(self._properties.get("vad_hysteresis_db", 4.0)),
            0.0,
        )
        self._vad_speech_start_frames = max(
            int(self._properties.get("vad_speech_start_frames", 2)),
            1,
        )
        self._assistant_barge_in_enabled = bool(
            self._properties.get("assistant_barge_in_enabled", True)
        )
        self._vad_silence_timeout_seconds = max(
            float(self._properties.get("vad_silence_timeout_ms", 650)) / 1000.0,
            0.2,
        )
        self._vad_pre_roll_bytes = max(
            int(
                float(self._properties.get("vad_pre_roll_ms", 250))
                / 1000.0
                * PCM16_MONO_16KHZ_BYTES_PER_SECOND
            ),
            0,
        )
        self._stt_partial_emit_interval_seconds = max(
            float(self._properties.get("stt_partial_emit_interval_ms", 300)) / 1000.0,
            0.1,
        )
        self._stt_partial_min_audio_bytes = max(
            int(
                float(self._properties.get("stt_partial_min_audio_ms", 450))
                / 1000.0
                * PCM16_MONO_16KHZ_BYTES_PER_SECOND
            ),
            640,
        )
        self._stt_partial_window_bytes = max(
            int(
                float(self._properties.get("stt_partial_window_ms", 3000))
                / 1000.0
                * PCM16_MONO_16KHZ_BYTES_PER_SECOND
            ),
            self._stt_partial_min_audio_bytes,
        )
        self._stt_final_min_audio_bytes = max(
            int(
                float(self._properties.get("stt_final_min_audio_ms", 250))
                / 1000.0
                * PCM16_MONO_16KHZ_BYTES_PER_SECOND
            ),
            640,
        )
        self._stt_final_min_speech_ms = max(
            int(float(self._properties.get("stt_final_min_speech_ms", 180))),
            80,
        )
        self._stt_partial_min_speech_ms = max(
            int(float(self._properties.get("stt_partial_min_speech_ms", 900))),
            300,
        )
        self._stt_max_utterance_seconds = max(
            float(self._properties.get("stt_max_utterance_ms", 16000)) / 1000.0,
            2.0,
        )
        self._stt_partial_beam_size = max(
            int(self._properties.get("stt_partial_beam_size", 1)), 1
        )
        self._stt_final_beam_size = max(
            int(
                self._properties.get(
                    "stt_final_beam_size", self._properties.get("stt_beam_size", 5)
                )
            ),
            1,
        )
        self._stt_initial_prompt = str(
            self._properties.get(
                "stt_initial_prompt",
                self._stt_initial_prompt,
            )
        )
        configured_model_size = str(
            self._properties.get("stt_model_size", settings.stt_model_size)
        )
        if settings.stt_model_size != "small.en":
            configured_model_size = settings.stt_model_size
        configured_language_mode = self._properties.get(
            "stt_language_mode", settings.stt_language_mode
        )
        if self._normalize_stt_language_mode(settings.stt_language_mode) != "forced_en":
            configured_language_mode = settings.stt_language_mode
        self._stt_language_mode = self._normalize_stt_language_mode(
            configured_language_mode
        )
        self._stt_transcribe_language = self._stt_transcription_language(
            self._stt_language_mode
        )
        property_second_pass_enabled = self._coerce_bool(
            self._properties.get(
                "stt_enable_second_pass_verification",
                settings.stt_enable_second_pass_verification,
            ),
            default=False,
        )
        self._stt_second_pass_verification_enabled = (
            property_second_pass_enabled
            or settings.stt_enable_second_pass_verification
        )
        self._stt_model_size = self._select_stt_model_size(
            configured_model_size,
            self._stt_language_mode,
        )

        self._force_flush_timeout_seconds = max(
            float(self._properties.get("tts_force_flush_timeout_ms", 600)) / 1000.0,
            0.1,
        )
        self._tts_echo_guard_tail_seconds = max(
            float(self._properties.get("tts_echo_guard_tail_ms", 900)) / 1000.0,
            0.0,
        )
        self._audio_output_port = str(
            self._properties.get("audio_output_port", "audio_out")
        )
        self._json_output_port = str(
            self._properties.get("json_output_port", "json_out")
        )
        self._log_output_port = str(self._properties.get("log_output_port", "log_out"))
        self._tutor_context_turns = max(
            0, int(self._properties.get("tutor_context_turns", 6))
        )
        self._auto_map_ports_locked()
        return True

    def _reset_runtime_state_locked(self) -> None:
        self._runtime_thread = None
        self._runtime_loop = None
        self._started = False
        self._stopping = False
        self._ten_env = None
        self._properties = {}
        self._reset_session_runtime_state()
        logger.info("Extension state reset complete. Ready for new session.")

    def _auto_map_ports_locked(self) -> None:
        if self._ten_env is None:
            return

        mapping_payload = {
            "audio_in": self._properties.get("audio_input_port", "audio_in"),
            "audio_out": self._audio_output_port,
            "json_out": self._json_output_port,
            "log_out": self._log_output_port,
        }

        # Best-effort auto wiring with multiple TEN runtime variants.
        for method_name in (
            "map_ports",
            "bind_ports",
            "register_port_mapping",
            "configure_ports",
        ):
            method = getattr(self._ten_env, method_name, None)
            if callable(method):
                with contextlib.suppress(Exception):
                    method(mapping_payload)
                    self._emit_log(
                        f"TEN port mapping applied via {method_name}: {mapping_payload}"
                    )
                    return

        self._emit_log(
            f"TEN port mapping fallback (manifest-driven): {mapping_payload}"
        )

    def _submit(self, coroutine: Any):
        with self._state_lock:
            if self._runtime_loop is None:
                raise RuntimeError("TEN runtime loop is not started")
            loop = self._runtime_loop
        return asyncio.run_coroutine_threadsafe(coroutine, loop)

    def _load_properties(self, ten_env: Any) -> dict[str, Any]:
        property_path = Path(__file__).with_name("property.json")
        loaded: dict[str, Any] = json.loads(property_path.read_text(encoding="utf-8"))

        # TEN runtime properties can override property.json defaults if available.
        for accessor_name in ("get_property", "property", "get"):
            accessor = getattr(ten_env, accessor_name, None)
            if not callable(accessor):
                continue
            for key in list(loaded.keys()):
                with contextlib.suppress(Exception):
                    value = accessor(key)
                    if value is not None:
                        loaded[key] = value
            break
        return loaded

    @staticmethod
    def _extract_command_name(cmd: Any) -> str:
        if isinstance(cmd, str):
            return cmd.strip().upper()
        if isinstance(cmd, dict):
            value = cmd.get("cmd") or cmd.get("command") or cmd.get("name")
            if isinstance(value, str):
                return value.strip().upper()
            return ""
        for attr in ("cmd", "command", "name"):
            value = getattr(cmd, attr, None)
            if isinstance(value, str):
                return value.strip().upper()
        return ""

    @staticmethod
    def _extract_session_id(cmd: Any) -> str | None:
        if isinstance(cmd, dict):
            value = cmd.get("session_id")
            return value.strip() if isinstance(value, str) and value.strip() else None
        value = getattr(cmd, "session_id", None)
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return None

    @staticmethod
    def _extract_bool(cmd: Any, key: str, *, default: bool) -> bool:
        if isinstance(cmd, dict) and key in cmd:
            value = cmd[key]
        else:
            value = getattr(cmd, key, None)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _extract_sequence_number(audio_frame: Any) -> int | None:
        for attr in ("sequence_number", "seq", "seq_no", "index"):
            value = getattr(audio_frame, attr, None)
            if isinstance(value, int):
                return value
        if isinstance(audio_frame, dict):
            for key in ("sequence_number", "seq", "seq_no", "index"):
                value = audio_frame.get(key)
                if isinstance(value, int):
                    return value
        return None

    @staticmethod
    def _extract_audio_payload(audio_frame: Any) -> memoryview | None:
        candidates: list[Any] = []
        for attr in ("data", "buffer", "payload", "audio", "bytes"):
            value = getattr(audio_frame, attr, None)
            if value is not None:
                candidates.append(value)
        for method_name in ("get_data", "get_buffer", "to_bytes"):
            method = getattr(audio_frame, method_name, None)
            if callable(method):
                with contextlib.suppress(Exception):
                    value = method()
                    if value is not None:
                        candidates.append(value)
        if isinstance(audio_frame, dict):
            for key in ("data", "buffer", "payload", "audio", "bytes"):
                if key in audio_frame:
                    candidates.append(audio_frame[key])

        for value in candidates:
            if isinstance(value, memoryview):
                return value
            if isinstance(value, (bytes, bytearray)):
                return memoryview(value)
        return None

    @staticmethod
    def _append_text(previous: str, new_piece: str) -> str:
        cleaned = new_piece.strip()
        if not cleaned:
            return previous
        if not previous:
            return cleaned
        return f"{previous} {cleaned}"

    @staticmethod
    def _normalize_stt_language_mode(value: object) -> str:
        mode = str(value or "forced_en").strip().lower()
        if mode in STT_LANGUAGE_MODES:
            return mode
        logger.warning(
            "ten.stt.invalid_language_mode mode=%r fallback=forced_en",
            value,
        )
        return "forced_en"

    @staticmethod
    def _stt_transcription_language(language_mode: str) -> str | None:
        mode = LUVEExtension._normalize_stt_language_mode(language_mode)
        return "en" if mode == "forced_en" else None

    @staticmethod
    def _select_stt_model_size(configured_model: object, language_mode: str) -> str:
        model = str(configured_model or "").strip() or settings.stt_model_size
        mode = LUVEExtension._normalize_stt_language_mode(language_mode)
        if mode == "forced_en":
            return model

        if model.endswith(".en"):
            multilingual_model = model[:-3]
            logger.warning(
                "ten.stt.auto_language_requires_multilingual_model configured=%s selected=%s mode=%s",
                model,
                multilingual_model,
                mode,
            )
            return multilingual_model
        return model

    @staticmethod
    def _coerce_bool(value: object, *, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    @staticmethod
    def _normalize_stt_text(text: str) -> str:
        return " ".join(
            "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text).split()
        )

    def _english_token_count(self, text: str) -> int:
        normalized = self._normalize_stt_text(text)
        if not normalized:
            return 0
        return len(normalized.split())

    def _has_learner_english_evidence(self, text: str) -> bool:
        normalized = self._normalize_stt_text(text)
        if not normalized:
            return False
        words = normalized.split()
        if len(words) < 2:
            return False

        if self._contains_vietnamese_text(text):
            return False

        english_tokens = [w for w in words if w in COMMON_ENGLISH_WORDS]
        count_english = len(english_tokens)

        # Require at least 2 English evidence tokens
        if count_english >= 2:
            return True

        # Ratio of English evidence tokens >= 0.45 for short phrases
        ratio_english = count_english / len(words)
        if len(words) <= 5 and ratio_english >= 0.45:
            # Enforce: Do NOT classify "English-like" from only one common token in a forced-English decode
            return count_english >= 2

        return False

    def _has_strong_learner_english_attempt(self, text: str) -> bool:
        normalized = self._normalize_stt_text(text)
        if not normalized:
            return False
        if self._contains_vietnamese_text(text):
            return False

        words = normalized.split()
        if len(words) < 3:
            return False

        english_tokens = [w for w in words if w in COMMON_ENGLISH_WORDS]
        content_tokens = [
            w
            for w in words
            if len(w) >= 3 and w not in LOW_INFORMATION_SHORT_TOKENS
        ]
        english_ratio = len(english_tokens) / len(words)

        if len(english_tokens) >= 3:
            return True
        if len(english_tokens) >= 2 and len(content_tokens) >= 2:
            return True
        if len(words) >= 6 and len(english_tokens) >= 2 and english_ratio >= 0.30 and len(content_tokens) >= 4:
            return True

        return False

    def _is_controlled_short_english_candidate(self, text: str) -> bool:
        normalized = self._normalize_stt_text(text)
        if not normalized or self._contains_vietnamese_text(text):
            return False
        words = normalized.split()
        if len(words) == 0 or len(words) > 2:
            return False
        return any(word in CONTROLLED_SHORT_ENGLISH_UTTERANCES for word in words)

    def _contains_vietnamese_text(self, text: str) -> bool:
        normalized = self._normalize_stt_text(text)
        if not normalized:
            return False

        raw_lower = text.lower()
        if any(char in raw_lower for char in VIETNAMESE_ACCENTED_CHARS):
            return True

        return any(
            word in VIETNAMESE_PHONETIC_TOKENS
            and word not in AMBIGUOUS_ENGLISH_HOMOGRAPHS
            for word in normalized.split()
        )

    def _is_incomplete_short_english_fragment(self, text: str) -> bool:
        normalized = self._normalize_stt_text(text)
        if not normalized:
            return False
        return normalized in INCOMPLETE_SHORT_ENGLISH_FRAGMENTS

    def _token_contains_vietnamese_marker(self, token: str) -> bool:
        lowered = token.lower()
        if any(char in lowered for char in VIETNAMESE_ACCENTED_CHARS):
            return True
        normalized = self._normalize_stt_text(token)
        if not normalized:
            return False
        return any(
            word in VIETNAMESE_PHONETIC_TOKENS
            and word not in AMBIGUOUS_ENGLISH_HOMOGRAPHS
            for word in normalized.split()
        )

    def _is_plausible_short_english_text(self, text: str) -> bool:
        normalized = self._normalize_stt_text(text)
        if not normalized or self._contains_vietnamese_text(text):
            return False
        if not text.isascii():
            return False

        words = normalized.split()
        if len(words) == 0 or len(words) > 2:
            return False
        if self._is_incomplete_short_english_fragment(text):
            return False
        if any(not word.isalpha() for word in words):
            return False
        if len(words) == 1 and words[0] in LOW_INFORMATION_SHORT_TOKENS:
            return False
        if len(words) == 2 and all(word in LOW_INFORMATION_SHORT_TOKENS for word in words):
            return False

        boosted = self._is_controlled_short_english_candidate(text)
        anchor_count = sum(
            1
            for word in words
            if word in COMMON_ENGLISH_WORDS or word in CONTROLLED_SHORT_ENGLISH_UTTERANCES
        )
        has_content_word = any(len(word) >= 4 for word in words)
        if len(words) == 1:
            return (
                boosted
                or (words[0] in COMMON_ENGLISH_WORDS and len(words[0]) >= 4)
                or len(words[0]) >= 5
            )
        return anchor_count >= 1 and has_content_word

    def _mixed_english_runs(self, text: str) -> list[str]:
        runs: list[str] = []
        current_tokens: list[str] = []
        for raw_token in text.split():
            if self._token_contains_vietnamese_marker(raw_token):
                if current_tokens:
                    runs.append(" ".join(current_tokens).strip(" ,.;:!?"))
                    current_tokens = []
                continue
            current_tokens.append(raw_token)

        if current_tokens:
            runs.append(" ".join(current_tokens).strip(" ,.;:!?"))

        return runs

    def _english_segment_from_mixed_text(self, text: str) -> str | None:
        if not self._contains_vietnamese_text(text):
            return None

        best_segment: str | None = None
        best_score: tuple[int, int, int] = (-1, -1, -1)
        for segment in self._mixed_english_runs(text):
            normalized = self._normalize_stt_text(segment)
            words = normalized.split()
            if not words:
                continue
            if self._contains_vietnamese_text(segment):
                continue
            if len(words) < 3:
                continue
            if self._is_incomplete_short_english_fragment(segment):
                continue
            if not (
                self._has_learner_english_evidence(segment)
                or self._has_strong_learner_english_attempt(segment)
            ):
                continue

            anchor_count = sum(
                1
                for word in words
                if word in COMMON_ENGLISH_WORDS or word in CONTROLLED_SHORT_ENGLISH_UTTERANCES
            )
            score = (anchor_count, len(words), len(segment))
            if score > best_score:
                best_segment = segment
                best_score = score

        return best_segment

    def _weak_english_fragment_from_mixed_text(self, text: str) -> str | None:
        if not self._contains_vietnamese_text(text):
            return None

        best_fragment: str | None = None
        best_score: tuple[int, int, int] = (-1, -1, -1)
        for segment in self._mixed_english_runs(text):
            normalized = self._normalize_stt_text(segment)
            words = normalized.split()
            if not words or len(words) > 2:
                continue
            if self._contains_vietnamese_text(segment) or not segment.isascii():
                continue
            if any(not word.isalpha() for word in words):
                continue
            if len(words) == 1 and words[0] in LOW_INFORMATION_SHORT_TOKENS:
                continue
            if len(words) == 2 and all(word in LOW_INFORMATION_SHORT_TOKENS for word in words):
                continue

            anchor_count = sum(
                1
                for word in words
                if word in COMMON_ENGLISH_WORDS or word in CONTROLLED_SHORT_ENGLISH_UTTERANCES
            )
            if anchor_count == 0:
                continue
            has_content_word = any(len(word) >= 4 for word in words)
            if len(words) == 2 and not has_content_word:
                continue
            score = (anchor_count, len(words), len(segment))
            if score > best_score:
                best_fragment = segment
                best_score = score

        return best_fragment

    def _split_mixed_language_transcript(self, text: str) -> tuple[str, list[str]]:
        if not self._contains_vietnamese_text(text):
            return text, []

        extracted = self._english_segment_from_mixed_text(text)
        if extracted:
            return extracted, ["mixed_language_filtered"]
        weak_fragment = self._weak_english_fragment_from_mixed_text(text)
        if weak_fragment:
            return weak_fragment, ["weak_mixed_language_english"]
        return "", ["mixed_non_english"]

    def _is_plausible_short_english_utterance(
        self,
        analysis: STTAnalysis,
        audio_stats: dict[str, object] | None,
        confidence: dict[str, object],
    ) -> bool:
        if not self._is_plausible_short_english_text(analysis.raw_text):
            return False
        boosted = self._is_controlled_short_english_candidate(analysis.raw_text)

        speech_ms = None
        if audio_stats is not None:
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)

        if speech_ms is not None and speech_ms < CONTROLLED_SHORT_ENGLISH_MIN_SPEECH_MS:
            return False

        max_no_speech_prob = 0.35 if boosted else 0.30
        if (
            analysis.no_speech_prob is not None
            and analysis.no_speech_prob > max_no_speech_prob
        ):
            return False

        min_avg_logprob = -0.78 if boosted else -0.70
        if (
            analysis.avg_logprob is not None
            and analysis.avg_logprob < min_avg_logprob
        ):
            return False

        max_low_conf_ratio = 0.45 if boosted else 0.35
        if (
            confidence.get("word_count", 0) > 0
            and confidence.get("low_confidence_word_ratio", 0.0) > max_low_conf_ratio
        ):
            return False

        if (
            analysis.compression_ratio is not None
            and analysis.compression_ratio > settings.stt_max_compression_ratio
        ):
            return False

        return True

    def _is_acoustically_plausible_incomplete_fragment(
        self,
        analysis: STTAnalysis,
        audio_stats: dict[str, object] | None,
        confidence: dict[str, object],
    ) -> bool:
        if not self._is_incomplete_short_english_fragment(analysis.raw_text):
            return False
        if self._contains_vietnamese_text(analysis.raw_text) or not analysis.raw_text.isascii():
            return False
        if any(canned in self._normalize_stt_text(analysis.raw_text) for canned in CANNED_STT_HALLUCINATION_PHRASES):
            return False

        speech_ms = None
        if audio_stats is not None:
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)
        if speech_ms is not None and speech_ms < CONTROLLED_SHORT_ENGLISH_MIN_SPEECH_MS:
            return False
        if analysis.no_speech_prob is not None and analysis.no_speech_prob > 0.35:
            return False
        if analysis.avg_logprob is not None and analysis.avg_logprob < -0.80:
            return False
        if (
            confidence.get("word_count", 0) > 0
            and float(confidence.get("low_confidence_word_ratio", 0.0) or 0.0) > 0.45
        ):
            return False
        return True

    def _should_run_non_english_verification(
        self,
        analysis: STTAnalysis,
        *,
        audio_stats: dict[str, object] | None,
        confidence: dict[str, object],
    ) -> bool:
        normalized = self._normalize_stt_text(analysis.raw_text)
        if not normalized or self._contains_vietnamese_text(analysis.raw_text):
            return False
        if not analysis.raw_text.isascii():
            return False

        words = normalized.split()
        if len(words) == 0 or len(words) > 6:
            return False

        has_phrase_evidence = self._has_learner_english_evidence(analysis.raw_text)
        has_strong_learner_attempt = self._has_strong_learner_english_attempt(
            analysis.raw_text
        )
        is_plausible_short = self._is_plausible_short_english_utterance(
            analysis,
            audio_stats,
            confidence,
        )
        possible_stt_autocorrection = self._is_possible_stt_autocorrection(
            analysis,
            confidence=confidence,
            has_phrase_evidence=has_phrase_evidence,
            is_strong_short=is_plausible_short,
        )

        speech_ms = None
        if audio_stats is not None:
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)

        if (
            len(words) <= 2
            and is_plausible_short
            and (speech_ms is None or speech_ms >= 450)
            and (analysis.no_speech_prob is None or analysis.no_speech_prob <= 0.18)
            and (analysis.avg_logprob is None or analysis.avg_logprob >= -0.45)
            and float(confidence.get("low_confidence_word_ratio", 0.0) or 0.0) <= 0.20
        ):
            return False
        if (
            len(words) > 2
            and has_strong_learner_attempt
            and has_phrase_evidence
            and not possible_stt_autocorrection
            and (speech_ms is None or speech_ms >= 1000)
            and (analysis.no_speech_prob is None or analysis.no_speech_prob <= 0.22)
            and (analysis.avg_logprob is None or analysis.avg_logprob >= -0.60)
            and float(confidence.get("low_confidence_word_ratio", 0.0) or 0.0) <= 0.40
        ):
            return False

        suspicious_signals = 0
        if not has_phrase_evidence and not has_strong_learner_attempt:
            suspicious_signals += 1
        if analysis.avg_logprob is not None and analysis.avg_logprob < -0.55:
            suspicious_signals += 1
        if analysis.no_speech_prob is not None and analysis.no_speech_prob > 0.20:
            suspicious_signals += 1
        if analysis.compression_ratio is not None and analysis.compression_ratio > 1.6:
            suspicious_signals += 1
        if (
            confidence["word_count"] > 0
            and float(confidence.get("low_confidence_word_ratio", 0.0) or 0.0) > 0.25
        ):
            suspicious_signals += 1
        if possible_stt_autocorrection:
            suspicious_signals += 1
        if len(words) <= 2 and not is_plausible_short:
            suspicious_signals += 1
        if speech_ms is not None and speech_ms < 700:
            suspicious_signals += 1

        if len(words) <= 2:
            return suspicious_signals >= 1
        return suspicious_signals >= 2

    @staticmethod
    def _verification_indicates_non_english(verification: STTAnalysis) -> bool:
        language = str(verification.detected_language or "").strip().lower()
        probability = verification.detected_language_probability
        if not language or language == "en":
            return False
        if probability is None:
            return False
        return float(probability) >= NON_ENGLISH_VERIFICATION_MIN_PROBABILITY

    async def _verify_non_english_if_suspicious(
        self,
        *,
        analysis: STTAnalysis,
        pcm_bytes: bytes,
        audio_stats: dict[str, object] | None,
        confidence: dict[str, object],
    ) -> tuple[str, STTAnalysis | None]:
        if not getattr(self, "_stt_second_pass_verification_enabled", False):
            return "skipped", None
        if self._stt_worker is None:
            return "skipped", None
        if not self._should_run_non_english_verification(
            analysis,
            audio_stats=audio_stats,
            confidence=confidence,
        ):
            return "skipped", None

        try:
            verification = await asyncio.wait_for(
                self._stt_worker.transcribe_audio_bytes(
                    pcm_bytes,
                    language=None,
                    initial_prompt=None,
                    beam_size=1,
                    word_timestamps=False,
                    vad_filter=False,
                    condition_on_previous_text=False,
                ),
                timeout=NON_ENGLISH_VERIFICATION_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, STTProcessingError, RuntimeError):
            return "unavailable", None
        except Exception:
            logger.warning("ten.stt.non_english_verification_failed", exc_info=True)
            return "unavailable", None

        analysis.verification_language = verification.detected_language
        analysis.verification_language_probability = (
            verification.detected_language_probability
        )

        if self._verification_indicates_non_english(verification):
            return "suppressed", verification
        return "verified", verification

    def _is_probable_stt_hallucination(
        self,
        text: str,
        *,
        is_final: bool,
        audio_stats: dict[str, object] | None,
        pcm_bytes: int,
    ) -> bool:
        normalized = self._normalize_stt_text(text)
        if not normalized:
            return False

        audio_ms = pcm_bytes / PCM16_MONO_16KHZ_BYTES_PER_SECOND * 1000
        audio_seconds = audio_ms / 1000.0
        speech_ms = None
        if audio_stats is not None:
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)

        # 1. Repeated phrase/ngram guard (consecutive repeated 3+ word sequences)
        words = normalized.split()
        n = len(words)
        for k in range(3, n // 2 + 1):
            for i in range(n - 2 * k + 1):
                if words[i : i + k] == words[i + k : i + 2 * k]:
                    return True

        # 2. Suspicious canned Whisper hallucination phrases guard
        if any(canned in normalized for canned in CANNED_STT_HALLUCINATION_PHRASES):
            # Suppress canned phrases when speech/audio duration is not exceptionally long,
            # indicating it's a forced-English hallucination from shorter audio/Vietnamese speech.
            if "thank you very much" in normalized:
                min_speech = 1500
                min_audio = 2.0
            elif (
                "have a good day" in normalized
                or "i don t know what to say" in normalized
                or "i dont know what to say" in normalized
                or "don t ask me to speak english" in normalized
                or "dont ask me to speak english" in normalized
            ):
                min_speech = 1800
                min_audio = 2.5
            else:
                min_speech = 3000
                min_audio = 3.5

            if speech_ms is not None and speech_ms < min_speech:
                return True
            if audio_seconds < min_audio:
                return True

        short_fillers = {
            "thank you",
            "thanks",
            "thank you thank you",
            "please subscribe",
            "thanks for watching",
        }
        if normalized in short_fillers:
            if not is_final:
                return audio_ms < 3500

            # A real "thank you" is possible, so only suppress finals when live VAD
            # evidence says this was too little speech to be a reliable turn.
            return speech_ms is not None and speech_ms < 900

        # Whisper hallucinations on noise often produce far more words than the
        # captured audio could plausibly contain. Keep this conservative so a
        # fast real speaker is not filtered.
        word_count = len(words)
        max_plausible_words = max(7, int(audio_seconds * 4.8) + 4)
        if word_count > max_plausible_words:
            return True

        if not is_final and audio_seconds < 1.5 and word_count > 5:
            return True

        return False

    @staticmethod
    def _format_stt_suppression_log(
        reason: str,
        *,
        is_final: bool,
        trigger: str,
        text_len: int,
        word_count: int,
        avg_logprob: float | None,
        no_speech_prob: float | None,
        low_conf_ratio: float | None,
        speech_ms: float | None,
        session_id: str | None = None,
    ) -> str:
        """Build a server-side diagnostic line for a suppressed/ignored final.

        Logs only safe acoustic metrics and the transcript LENGTH — never the
        raw transcript text — so we can see WHICH gate dropped a real utterance
        without leaking user content.
        """
        return (
            "ten.stt.suppressed "
            f"session_id={session_id} "
            f"reason={reason} "
            f"is_final={is_final} "
            f"trigger={trigger} "
            f"text_len={text_len} "
            f"word_count={word_count} "
            f"avg_logprob={avg_logprob} "
            f"no_speech_prob={no_speech_prob} "
            f"low_conf_ratio={low_conf_ratio} "
            f"speech_ms={speech_ms}"
        )

    def _log_stt_suppression(
        self,
        reason: str,
        *,
        is_final: bool,
        trigger: str,
        analysis: STTAnalysis | None = None,
        audio_stats: dict[str, object] | None = None,
        confidence: dict[str, object] | None = None,
        text_len: int | None = None,
        word_count: int | None = None,
    ) -> None:
        text = (analysis.raw_text if analysis is not None else "") or ""
        speech_ms = None
        if isinstance(audio_stats, dict):
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)
        low_conf_ratio = None
        if isinstance(confidence, dict):
            value = confidence.get("low_confidence_word_ratio")
            if isinstance(value, (int, float)):
                low_conf_ratio = float(value)
        logger.info(
            self._format_stt_suppression_log(
                reason,
                is_final=is_final,
                trigger=trigger,
                text_len=text_len if text_len is not None else len(text),
                word_count=word_count if word_count is not None else len(text.split()),
                avg_logprob=analysis.avg_logprob if analysis is not None else None,
                no_speech_prob=analysis.no_speech_prob if analysis is not None else None,
                low_conf_ratio=low_conf_ratio,
                speech_ms=speech_ms,
                session_id=self._session_id,
            )
        )

    def _stt_rejection_reason(
        self,
        analysis: STTAnalysis,
        *,
        is_final: bool,
        audio_stats: dict[str, object] | None,
    ) -> str | None:
        if not is_final or not settings.stt_reject_low_confidence:
            return None

        normalized = self._normalize_stt_text(analysis.raw_text)
        if not normalized:
            return "empty_transcript"
        confidence = self._stt_confidence_metrics(analysis)
        if (
            self._is_incomplete_short_english_fragment(analysis.raw_text)
            and not self._is_acoustically_plausible_incomplete_fragment(
                analysis,
                audio_stats,
                confidence,
            )
        ):
            return "incomplete_short_fragment"

        # 3. Check suspicious canned/filler forced-English hallucinations
        if any(canned in normalized for canned in CANNED_STT_HALLUCINATION_PHRASES):
            # Require strong acoustic confidence to keep genuine learner attempts
            if (
                analysis.avg_logprob is not None
                and analysis.avg_logprob < -0.45
            ) or (
                confidence.get("word_count", 0) > 0
                and confidence.get("low_confidence_word_ratio", 0.0) > 0.15
            ):
                return "probable_hallucination"

        is_short_with_boost = self._is_controlled_short_english_candidate(
            analysis.raw_text
        )
        is_plausible_short = self._is_plausible_short_english_utterance(
            analysis,
            audio_stats,
            confidence,
        )
        is_plausible_incomplete_fragment = (
            self._is_acoustically_plausible_incomplete_fragment(
                analysis,
                audio_stats,
                confidence,
            )
        )
        has_phrase_evidence = self._has_learner_english_evidence(analysis.raw_text)
        has_strong_learner_attempt = self._has_strong_learner_english_attempt(
            analysis.raw_text
        )

        speech_ms = None
        if audio_stats is not None:
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)

        is_exceptionally_high_confidence = (
            analysis.avg_logprob is not None
            and analysis.avg_logprob >= -0.40
            and confidence.get("low_confidence_word_ratio", 0.0) <= 0.15
            and (speech_ms is None or speech_ms >= LEARNER_PHRASE_MIN_SPEECH_MS)
        )

        # Check for strong acoustic confidence AND transcript has ASCII/English-like structure
        is_strong_acoustic_ascii = False
        has_vietnamese = False
        if normalized:
            words = normalized.split()
            has_vietnamese = self._contains_vietnamese_text(analysis.raw_text)
            if not has_vietnamese and analysis.raw_text.isascii():
                if (
                    analysis.avg_logprob is not None
                    and analysis.avg_logprob >= -0.50
                    and confidence.get("low_confidence_word_ratio", 0.0) <= 0.20
                ):
                    is_strong_acoustic_ascii = True

        is_eligible_learner_english = (
            (
                is_plausible_short
                or is_plausible_incomplete_fragment
                or has_phrase_evidence
                or has_strong_learner_attempt
                or is_exceptionally_high_confidence
                or is_strong_acoustic_ascii
            )
            and not has_vietnamese
        )

        word_count = len(normalized.split())

        # 1. Check speech duration.
        # For strong short answers, minimum duration is LEARNER_SHORT_ANSWER_MIN_SPEECH_MS (350ms)
        # For learner phrase attempts, minimum is max(self._stt_final_min_speech_ms, LEARNER_PHRASE_MIN_SPEECH_MS) (500ms)
        # Otherwise, enforce strict configured minimum (typically 1000ms).
        if is_plausible_short or is_plausible_incomplete_fragment:
            min_speech_ms = CONTROLLED_SHORT_ENGLISH_MIN_SPEECH_MS
        elif is_eligible_learner_english:
            min_speech_ms = max(self._stt_final_min_speech_ms, LEARNER_PHRASE_MIN_SPEECH_MS)
        else:
            min_speech_ms = settings.stt_min_speech_ms_for_final

        if speech_ms is not None and speech_ms < min_speech_ms:
            return "low_speech_duration"

        # 2. Check word count.
        # Strong short responses bypass settings.stt_min_words_for_llm (which might be >= 2)
        # Otherwise, we enforce settings.stt_min_words_for_llm
        expected_min_words = (
            1
            if is_plausible_short or is_plausible_incomplete_fragment
            else settings.stt_min_words_for_llm
        )
        if word_count < expected_min_words:
            return "too_few_words"

        # 3. Check compression ratio (filters repetitive Whisper hallucinations).
        if (
            analysis.compression_ratio is not None
            and analysis.compression_ratio > settings.stt_max_compression_ratio
        ):
            return "high_compression_ratio"

        # 4. Check confidence thresholds.
        # If it is eligible learner English, we apply relaxed thresholds.
        # Otherwise, keep strict thresholds to block environmental hums/Vietnamese speech.
        max_no_speech = RELAXED_STT_MAX_NO_SPEECH_PROB if is_eligible_learner_english else settings.stt_max_no_speech_prob
        min_avg_logprob = RELAXED_STT_MIN_AVG_LOGPROB if is_eligible_learner_english else settings.stt_min_avg_logprob
        max_low_conf_ratio = RELAXED_STT_MAX_LOW_CONFIDENCE_WORD_RATIO if is_eligible_learner_english else settings.stt_max_low_confidence_word_ratio

        if is_short_with_boost and not has_phrase_evidence:
            max_no_speech = max(max_no_speech, 0.35)
            min_avg_logprob = min(min_avg_logprob, -0.78)
            max_low_conf_ratio = max(max_low_conf_ratio, 0.45)
        if has_strong_learner_attempt:
            max_no_speech = max(max_no_speech, 0.90)
            min_avg_logprob = min(min_avg_logprob, -1.30)
            max_low_conf_ratio = max(max_low_conf_ratio, 0.85)

        if (
            analysis.no_speech_prob is not None
            and analysis.no_speech_prob > max_no_speech
        ):
            return "high_no_speech_probability"

        if (
            analysis.avg_logprob is not None
            and analysis.avg_logprob < min_avg_logprob
        ):
            return "low_average_logprob"

        if (
            confidence["word_count"] > 0
            and confidence["low_confidence_word_ratio"] > max_low_conf_ratio
        ):
            return "too_many_low_confidence_words"

        # 5. Semantic Gate: If it contains absolutely zero English evidence, reject it.
        if not is_eligible_learner_english:
            return "no_english_evidence"

        return None

    @staticmethod
    def _stt_confidence_summary(analysis: STTAnalysis) -> dict[str, object]:
        word_count = len(analysis.all_words)
        low_confidence_word_count = sum(
            1
            for word in analysis.all_words
            if word.confidence < settings.stt_min_word_confidence
        )
        low_confidence_word_ratio = (
            low_confidence_word_count / word_count if word_count else 0.0
        )
        return {
            "confidence_score": None,
            "avg_logprob": analysis.avg_logprob,
            "no_speech_prob": analysis.no_speech_prob,
            "compression_ratio": analysis.compression_ratio,
            "segment_count": analysis.segment_count,
            "word_count": word_count,
            "low_confidence_word_count": low_confidence_word_count,
            "low_confidence_word_ratio": round(low_confidence_word_ratio, 4),
            "min_word_confidence": settings.stt_min_word_confidence,
            "detected_language": analysis.detected_language,
            "detected_language_probability": analysis.detected_language_probability,
            "verification_language": analysis.verification_language,
            "verification_language_probability": analysis.verification_language_probability,
        }

    @classmethod
    def _stt_confidence_metrics(cls, analysis: STTAnalysis) -> dict[str, object]:
        return cls._stt_confidence_summary(analysis)

    def _stt_uncertainty_reasons(
        self,
        analysis: STTAnalysis,
        *,
        audio_stats: dict[str, object] | None,
        confidence: dict[str, object],
        is_strong_short: bool,
        has_phrase_evidence: bool,
        is_strong_acoustic_ascii: bool,
        possible_stt_autocorrection: bool,
        verification_status: str,
        mixed_language_filtered: bool,
    ) -> list[str]:
        reasons: list[str] = []

        if analysis.avg_logprob is not None and analysis.avg_logprob < -0.55:
            reasons.append("low_average_logprob")
        if analysis.no_speech_prob is not None and analysis.no_speech_prob > 0.25:
            reasons.append("high_no_speech_probability")
        if (
            confidence["word_count"] > 0
            and confidence["low_confidence_word_ratio"] > 0.25
        ):
            reasons.append("many_low_confidence_words")

        speech_ms = None
        if audio_stats is not None:
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)
        if (
            not is_strong_short
            and speech_ms is not None
            and speech_ms < LEARNER_PHRASE_MIN_SPEECH_MS
        ):
            reasons.append("short_utterance")

        if (
            not has_phrase_evidence
            and not is_strong_short
            and is_strong_acoustic_ascii
            and reasons
        ):
            reasons.append("borderline_learner_english")

        if possible_stt_autocorrection:
            reasons.append("possible_stt_autocorrection")
        if mixed_language_filtered:
            reasons.append("mixed_language_filtered")
        if verification_status == "unavailable":
            reasons.append("verification_unavailable")
        elif (
            verification_status == "verified"
            and analysis.verification_language
            and analysis.verification_language.lower() != "en"
            and analysis.verification_language_probability is not None
            and float(analysis.verification_language_probability) >= 0.35
        ):
            reasons.append("verification_language_mismatch")

        return reasons

    def _is_possible_stt_autocorrection(
        self,
        analysis: STTAnalysis,
        *,
        confidence: dict[str, object],
        has_phrase_evidence: bool,
        is_strong_short: bool,
    ) -> bool:
        if is_strong_short or not has_phrase_evidence:
            return False
        if not analysis.raw_text.isascii():
            return False
        if len(self._normalize_stt_text(analysis.raw_text).split()) < 3:
            return False

        low_conf_ratio = float(confidence.get("low_confidence_word_ratio", 0.0) or 0.0)
        has_clean_word_confidence = confidence.get("word_count", 0) == 0 or low_conf_ratio <= 0.25
        return (
            has_clean_word_confidence
            and analysis.avg_logprob is not None
            and analysis.avg_logprob < -0.55
        )

    def _stt_quality_assessment(
        self,
        analysis: STTAnalysis,
        *,
        audio_stats: dict[str, object] | None,
        inference_ms: float,
        verification_status: str = "skipped",
        original_text: str | None = None,
        mixed_language_filtered: bool = False,
        mixed_language_reasons: list[str] | None = None,
    ) -> dict[str, object]:
        confidence = self._stt_confidence_summary(analysis)
        normalized = self._normalize_stt_text(analysis.raw_text)
        words = normalized.split() if normalized else []

        is_plausible_short = self._is_plausible_short_english_utterance(
            analysis,
            audio_stats,
            confidence,
        )
        is_plausible_incomplete_fragment = (
            self._is_acoustically_plausible_incomplete_fragment(
                analysis,
                audio_stats,
                confidence,
            )
        )
        has_phrase_evidence = self._has_learner_english_evidence(analysis.raw_text)
        has_vietnamese = self._contains_vietnamese_text(analysis.raw_text)
        mixed_reason_set = set(mixed_language_reasons or [])

        speech_ms = None
        if audio_stats is not None:
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)

        is_strong_acoustic_ascii = (
            not has_vietnamese
            and analysis.raw_text.isascii()
            and analysis.avg_logprob is not None
            and analysis.avg_logprob >= -0.50
            and float(confidence.get("low_confidence_word_ratio", 0.0) or 0.0) <= 0.20
        )
        is_exceptionally_high_confidence = (
            analysis.avg_logprob is not None
            and analysis.avg_logprob >= -0.40
            and float(confidence.get("low_confidence_word_ratio", 0.0) or 0.0) <= 0.15
            and (speech_ms is None or speech_ms >= LEARNER_PHRASE_MIN_SPEECH_MS)
        )
        possible_stt_autocorrection = self._is_possible_stt_autocorrection(
            analysis,
            confidence=confidence,
            has_phrase_evidence=has_phrase_evidence,
            is_strong_short=is_plausible_short,
        )
        uncertainty_reasons = self._stt_uncertainty_reasons(
            analysis,
            audio_stats=audio_stats,
            confidence=confidence,
            is_strong_short=is_plausible_short,
            has_phrase_evidence=has_phrase_evidence,
            is_strong_acoustic_ascii=is_strong_acoustic_ascii,
            possible_stt_autocorrection=possible_stt_autocorrection,
            verification_status=verification_status,
            mixed_language_filtered=mixed_language_filtered,
        )
        if (
            not uncertainty_reasons
            and not is_plausible_short
            and not is_exceptionally_high_confidence
            and not has_phrase_evidence
            and is_strong_acoustic_ascii
        ):
            uncertainty_reasons.append("borderline_learner_english")
        if is_plausible_incomplete_fragment:
            if "short_utterance" not in uncertainty_reasons:
                uncertainty_reasons.append("short_utterance")
            if "incomplete_fragment" not in uncertainty_reasons:
                uncertainty_reasons.append("incomplete_fragment")

        payload: dict[str, object] = {
            "confidence": 1.0,
            "stt_quality": "uncertain" if uncertainty_reasons else "confident",
            "stt_confidence": confidence,
            "uncertainty_reasons": uncertainty_reasons,
            "possible_hallucination": False,
            "possible_stt_autocorrection": possible_stt_autocorrection,
            "tutor_visible": True,
            "grading_eligible": True,
            "turn_language_type": "mixed" if mixed_language_filtered else "english",
            "stt_inference_ms": round(inference_ms, 2),
            "audio": audio_stats,
        }
        if is_plausible_incomplete_fragment:
            payload["grading_eligible"] = False
        if mixed_language_filtered and original_text and original_text != analysis.raw_text:
            payload["original_stt_text"] = original_text
            payload["english_segment"] = analysis.raw_text
            payload["mixed_language"] = True
            payload["removed_non_english"] = True
            if "weak_mixed_language_english" in mixed_reason_set:
                payload["english_segment"] = ""
                payload["grading_eligible"] = False
                payload["excluded_from_grading_reason"] = "weak_mixed_language_english"
                if "weak_mixed_language_english" not in uncertainty_reasons:
                    uncertainty_reasons.append("weak_mixed_language_english")
        if analysis.all_words:
            payload["words"] = [
                {
                    "word": item.word,
                    "probability": item.confidence,
                    "start_ms": item.start_ms,
                    "end_ms": item.end_ms,
                }
                for item in analysis.all_words
            ]
        return payload

    def _mixed_english_segment_has_final_evidence(
        self,
        analysis: STTAnalysis,
        *,
        audio_stats: dict[str, object] | None,
        confidence: dict[str, object],
    ) -> bool:
        normalized = self._normalize_stt_text(analysis.raw_text)
        words = normalized.split() if normalized else []
        if len(words) < 3:
            return False
        if self._is_incomplete_short_english_fragment(analysis.raw_text):
            return False
        if self._contains_vietnamese_text(analysis.raw_text):
            return False
        if not analysis.raw_text.isascii():
            return False
        if not (
            self._has_learner_english_evidence(analysis.raw_text)
            or self._has_strong_learner_english_attempt(analysis.raw_text)
        ):
            return False

        speech_ms = None
        if audio_stats is not None:
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)
        if speech_ms is not None and speech_ms < 700:
            return False
        if analysis.no_speech_prob is not None and analysis.no_speech_prob > 0.35:
            return False
        if analysis.avg_logprob is not None and analysis.avg_logprob < -0.80:
            return False
        if (
            confidence.get("word_count", 0) > 0
            and float(confidence.get("low_confidence_word_ratio", 0.0) or 0.0) > 0.45
        ):
            return False
        return True

    def _final_stt_acceptance_rejection_reason(
        self,
        analysis: STTAnalysis,
        *,
        trigger: str,
        audio_stats: dict[str, object] | None,
        turn_metadata: dict[str, object],
        mixed_language_filtered: bool,
    ) -> str | None:
        if not analysis.raw_text.strip():
            return "empty_transcript"

        raw_reasons = turn_metadata.get("uncertainty_reasons")
        reasons = {
            item.strip()
            for item in raw_reasons
            if isinstance(item, str) and item.strip()
        } if isinstance(raw_reasons, list) else set()

        if "verification_language_mismatch" in reasons:
            return "verification_language_mismatch"

        return None

    @staticmethod
    def _extract_response_text(raw_stream: str) -> str:
        marker = "RESPONSE_TEXT:"
        marker_index = raw_stream.upper().find(marker)
        if marker_index < 0:
            return ""
        text = raw_stream[marker_index + len(marker) :]
        feedback_marker = "PEDAGOGICAL_FEEDBACK:"
        feedback_index = text.upper().find(feedback_marker)
        if feedback_index >= 0:
            text = text[:feedback_index]
        return text.replace("\r", "").replace("\n", " ").strip()

    @staticmethod
    def _diff_streamed_text(previous: str, current: str) -> str:
        if not current:
            return ""
        if current.startswith(previous):
            return current[len(previous) :]
        return current

    async def _persist_event_log(self) -> None:
        if not self._session_id:
            return

        session_id = self._session_id
        logger.info(
            "Phase 1: Attempting to save %d events to DB", len(self._event_log)
        )
        try:
            from sqlalchemy import text

            from src.core.db import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                await session.execute(
                    text(
                        "UPDATE SESSIONS "
                        "SET raw_backup_json = CAST(:logs AS jsonb), status = 'completed', ended_at = CURRENT_TIMESTAMP "
                        "WHERE id = :sid"
                    ),
                    {
                        "logs": json.dumps(self._event_log),
                        "sid": session_id,
                    },
                )

                # T7b: shadow transactional outbox. Write the session.completed
                # event in the SAME transaction as the completion UPDATE (before
                # commit) so the outbox row is durable iff completion commits. The
                # inline publish below is unchanged; the relay (T7c) drains the
                # outbox later. Enqueue failure is intentionally fatal -> rollback.
                from src.services.outbox_repository import enqueue_session_event

                await enqueue_session_event(
                    session,
                    session_id=session_id,
                    event_type="session.completed",
                    schema_version="v1",
                    payload={
                        "event_type": "session.completed",
                        "schema_version": "v1",
                        "session_id": session_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                await session.commit()
                logger.info(
                    "Phase 1: SUCCESS - Blackbox logs saved to DB for session %s",
                    session_id,
                )
                published = await publish_session_completed(session_id)
                if not published:
                    logger.warning(
                        "session.completed inline publish failed session_id=%s — "
                        "completion committed and durable session_outbox row persisted; "
                        "use the outbox relay/manual recovery to deliver grading",
                        session_id,
                    )
        except Exception:
            logger.exception("Phase 1: FAILED - Could not save logs to DB")

    def _reset_session_runtime_state(self) -> None:
        self._session_id = None
        self._audio_sequence = 0
        self._is_assistant_speaking = False
        self._opener_sent = False
        self._reset_tts_timing()
        self._stt_inference_busy = False
        self._stt_only_mode = False
        self._tts_output_enabled = True
        self._assistant_speech_release_task = None
        self._event_log.clear()
        self._utterance_pcm.clear()
        self._pre_roll_pcm.clear()
        self._is_speaking = False
        self._silence_duration_seconds = 0.0
        self._last_partial_emit_at = 0.0
        self._previous_stt_text = ""
        self._pending_speech_frames = 0
        self._current_utterance_stats = None
