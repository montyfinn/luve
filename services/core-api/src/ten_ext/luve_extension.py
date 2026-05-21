from __future__ import annotations

import asyncio
import contextlib
import json
import logging
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
            model_size=str(self._properties.get("stt_model_size", "small")),
            preferred_device="cuda",
            preferred_compute_type="float16",
            beam_size=int(self._properties.get("stt_beam_size", 5)),
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
                    if job.is_final:
                        self._reset_current_utterance()
                    continue
                finally:
                    self._stt_inference_busy = False

                analysis.raw_text = sanitize_transcript(analysis.raw_text)
                if self._is_probable_stt_hallucination(
                    analysis.raw_text,
                    is_final=job.is_final,
                    audio_stats=job.audio_stats,
                    pcm_bytes=len(job.pcm_bytes),
                ):
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

                stt_rejection = self._stt_rejection_reason(
                    analysis,
                    is_final=job.is_final,
                    audio_stats=job.audio_stats,
                )
                if stt_rejection is not None:
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

                # Update context only after the final text survives cleanup.
                if job.is_final and analysis.raw_text.strip():
                    self._previous_stt_text = analysis.raw_text.strip()

                logger.info(
                    f"TEN STT Output (final={job.is_final}): '{analysis.raw_text}'"
                )

                hop_ms = max((time.perf_counter() - job.queued_at) * 1000, 0.0)
                inference_ms = (time.perf_counter() - started) * 1000
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
                                "confidence": 1.0,  # Faster-Whisper confidence is tricky to average here without all_words
                                "stt_inference_ms": round(inference_ms, 2),
                                "audio": job.audio_stats,
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
                        await self._spawn_llm_for_final(analysis)
            except Exception:
                logger.exception("ten-inference-loop error")
                await asyncio.sleep(1.0)
            finally:
                if acquired_job and self._inference_queue is not None:
                    self._inference_queue.task_done()

    async def _spawn_llm_for_final(self, analysis: STTAnalysis) -> None:
        if not self._responses_enabled():
            return
        self._reset_tts_timing()
        if self._llm_processor is None:
            await self._emit_local_fallback_reply(analysis)
            return

        task = asyncio.create_task(
            self._run_llm_pipeline(analysis), name="ten-llm-pipeline"
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

    async def _run_llm_pipeline(self, analysis: STTAnalysis) -> None:
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
    def _normalize_stt_text(text: str) -> str:
        return " ".join(
            "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text).split()
        )

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

        short_fillers = {
            "thank you",
            "thanks",
            "thank you thank you",
            "please subscribe",
            "thanks for watching",
        }
        audio_ms = pcm_bytes / PCM16_MONO_16KHZ_BYTES_PER_SECOND * 1000
        audio_seconds = audio_ms / 1000.0
        speech_ms = None
        if audio_stats is not None:
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)

        if normalized in short_fillers:
            if not is_final:
                return audio_ms < 3500

            # A real "thank you" is possible, so only suppress finals when live VAD
            # evidence says this was too little speech to be a reliable turn.
            return speech_ms is not None and speech_ms < 900

        # Whisper hallucinations on noise often produce far more words than the
        # captured audio could plausibly contain. Keep this conservative so a
        # fast real speaker is not filtered.
        word_count = len(normalized.split())
        max_plausible_words = max(7, int(audio_seconds * 4.8) + 4)
        if word_count > max_plausible_words:
            return True

        if not is_final and audio_seconds < 1.5 and word_count > 5:
            return True

        return False

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
            return None

        speech_ms = None
        if audio_stats is not None:
            value = audio_stats.get("speech_ms")
            if isinstance(value, (int, float)):
                speech_ms = float(value)

        word_count = len(normalized.split())
        if speech_ms is not None and speech_ms < settings.stt_min_speech_ms_for_final:
            return "low_speech_duration"
        if word_count < settings.stt_min_words_for_llm:
            return "too_few_words"
        if (
            analysis.no_speech_prob is not None
            and analysis.no_speech_prob > settings.stt_max_no_speech_prob
        ):
            return "high_no_speech_probability"
        if (
            analysis.avg_logprob is not None
            and analysis.avg_logprob < settings.stt_min_avg_logprob
        ):
            return "low_average_logprob"
        if (
            analysis.compression_ratio is not None
            and analysis.compression_ratio > settings.stt_max_compression_ratio
        ):
            return "high_compression_ratio"

        confidence = self._stt_confidence_metrics(analysis)
        if (
            confidence["word_count"] > 0
            and confidence["low_confidence_word_ratio"]
            > settings.stt_max_low_confidence_word_ratio
        ):
            return "too_many_low_confidence_words"

        return None

    @staticmethod
    def _stt_confidence_metrics(analysis: STTAnalysis) -> dict[str, object]:
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
            "avg_logprob": analysis.avg_logprob,
            "no_speech_prob": analysis.no_speech_prob,
            "compression_ratio": analysis.compression_ratio,
            "segment_count": analysis.segment_count,
            "word_count": word_count,
            "low_confidence_word_count": low_confidence_word_count,
            "low_confidence_word_ratio": round(low_confidence_word_ratio, 4),
            "min_word_confidence": settings.stt_min_word_confidence,
        }

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
                if self._event_log:
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
                else:
                    await session.execute(
                        text(
                            "UPDATE SESSIONS "
                            "SET status = 'completed', ended_at = CURRENT_TIMESTAMP "
                            "WHERE id = :sid"
                        ),
                        {
                            "sid": session_id,
                        },
                    )
                await session.commit()
                logger.info(
                    "Phase 1: SUCCESS - Blackbox logs saved to DB for session %s",
                    session_id,
                )
                await publish_session_completed(session_id)
        except Exception:
            logger.exception("Phase 1: FAILED - Could not save logs to DB")

    def _reset_session_runtime_state(self) -> None:
        self._session_id = None
        self._audio_sequence = 0
        self._is_assistant_speaking = False
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
