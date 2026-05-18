from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

import numpy as np

from src.media.brain import LLMProcessor, PedagogicalReply
from src.media.stt_postprocess import sanitize_transcript
from src.media.stt_worker import WhisperInference
from src.media.tts import TTSAudioChunk, TTSProcessor
from src.schemas.ai_logic import STTAnalysis


logger = logging.getLogger(__name__)

PCM16_MONO_16KHZ_BYTES_PER_SECOND = 32000


@dataclass(frozen=True)
class InferenceJob:
    is_final: bool
    trigger: str
    created_at: float
    pcm_bytes: bytes


class SubtitleSender(Protocol):
    async def send_json(
        self, connection_id: str, payload: dict[str, object]
    ) -> None: ...


class StreamCoordinator:
    def __init__(
        self,
        *,
        session_id: UUID,
        connection_id: str,
        sender: SubtitleSender,
        stt_inference: WhisperInference,
        llm_processor: LLMProcessor | None = None,
        tts_processor: TTSProcessor | None = None,
        tts_force_flush_timeout_ms: int = 600,
        vad_energy_threshold_db: float = -42.0,
        vad_silence_timeout_ms: int = 800,
        vad_pre_roll_ms: int = 250,
        stt_partial_emit_interval_ms: int = 300,
        stt_partial_min_audio_ms: int = 450,
        stt_partial_window_ms: int = 15000,
        stt_final_min_audio_ms: int = 250,
        stt_partial_beam_size: int = 1,
        stt_final_beam_size: int = 3,
        stt_initial_prompt: str = (
            "This is a spoken English conversation between a learner and an AI tutor."
        ),
    ) -> None:
        if tts_force_flush_timeout_ms <= 0:
            raise ValueError("tts_force_flush_timeout_ms must be > 0")
        if vad_pre_roll_ms <= 0:
            raise ValueError("vad_pre_roll_ms must be > 0")
        if vad_silence_timeout_ms <= 0:
            raise ValueError("vad_silence_timeout_ms must be > 0")
        if stt_partial_emit_interval_ms <= 0:
            raise ValueError("stt_partial_emit_interval_ms must be > 0")
        if stt_partial_min_audio_ms <= 0:
            raise ValueError("stt_partial_min_audio_ms must be > 0")
        if stt_partial_window_ms < stt_partial_min_audio_ms:
            raise ValueError(
                "stt_partial_window_ms must be >= stt_partial_min_audio_ms"
            )
        if stt_final_min_audio_ms <= 0:
            raise ValueError("stt_final_min_audio_ms must be > 0")
        if stt_partial_beam_size <= 0:
            raise ValueError("stt_partial_beam_size must be > 0")
        if stt_final_beam_size <= 0:
            raise ValueError("stt_final_beam_size must be > 0")

        self._session_id = session_id
        self._connection_id = connection_id
        self._sender = sender
        self._stt_inference = stt_inference
        self._llm_processor = llm_processor
        self._tts_processor = tts_processor
        self._tts_force_flush_timeout_seconds = tts_force_flush_timeout_ms / 1000.0

        self._vad_energy_threshold_db = vad_energy_threshold_db
        self._vad_silence_timeout_seconds = vad_silence_timeout_ms / 1000.0
        self._vad_pre_roll_bytes = int(
            vad_pre_roll_ms / 1000.0 * PCM16_MONO_16KHZ_BYTES_PER_SECOND
        )
        self._stt_partial_emit_interval_seconds = stt_partial_emit_interval_ms / 1000.0
        self._stt_partial_min_audio_bytes = int(
            stt_partial_min_audio_ms / 1000.0 * PCM16_MONO_16KHZ_BYTES_PER_SECOND
        )
        self._stt_partial_window_bytes = int(
            stt_partial_window_ms / 1000.0 * PCM16_MONO_16KHZ_BYTES_PER_SECOND
        )
        self._stt_final_min_audio_bytes = int(
            stt_final_min_audio_ms / 1000.0 * PCM16_MONO_16KHZ_BYTES_PER_SECOND
        )
        self._stt_partial_beam_size = stt_partial_beam_size
        self._stt_final_beam_size = stt_final_beam_size
        self._stt_initial_prompt = stt_initial_prompt.strip()

        self._inference_queue: asyncio.Queue[InferenceJob] = asyncio.Queue(maxsize=1)
        self._inference_task: asyncio.Task[None] | None = None
        self._llm_tasks: set[asyncio.Task[None]] = set()
        self._closed = False

        # Blackbox Logger: Event-based conversation history
        self._event_log: list[dict[str, object]] = []

        self._utterance_pcm = bytearray()
        self._pre_roll_pcm = bytearray()
        self._is_speaking = False
        self._silence_duration_seconds = 0.0
        self._last_partial_emit_at = 0.0

        # Context carry for STT: store previous final text to improve transcription accuracy
        self._previous_stt_text: str = ""

    async def start(self) -> None:
        if self._inference_task is not None and not self._inference_task.done():
            return
        if self._tts_processor is not None:
            await self._tts_processor.start(self._emit_tts_chunk)
        self._inference_task = asyncio.create_task(
            self._inference_loop(),
            name=f"inference-loop-{self._session_id}",
        )

    async def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._reset_turn_state()
        await self._inference_queue.put(
            InferenceJob(
                is_final=True,
                trigger="stop",
                created_at=time.perf_counter(),
                pcm_bytes=b"",
            )
        )

        if self._inference_task is not None:
            await self._inference_task
            self._inference_task = None

        await self._cancel_llm_tasks()

        if self._tts_processor is not None:
            await self._tts_processor.stop(flush=False)

    async def notify_audio_chunk(
        self, sequence_number: int, payload_bytes: bytes
    ) -> None:
        _ = sequence_number
        if self._closed or not payload_bytes:
            return

        self._append_to_pre_roll(payload_bytes)
        frame_duration_s = len(payload_bytes) / PCM16_MONO_16KHZ_BYTES_PER_SECOND
        now = time.perf_counter()
        is_speech = self._is_speech_frame(payload_bytes)

        if is_speech:
            if not self._is_speaking:
                self._is_speaking = True
                self._silence_duration_seconds = 0.0
                if self._pre_roll_pcm and not self._utterance_pcm:
                    self._utterance_pcm.extend(self._pre_roll_pcm)
                await self._on_user_turn_started()

            self._utterance_pcm.extend(payload_bytes)
            self._silence_duration_seconds = 0.0

            if (
                len(self._utterance_pcm) >= self._stt_partial_min_audio_bytes
                and (now - self._last_partial_emit_at)
                >= self._stt_partial_emit_interval_seconds
            ):
                self._last_partial_emit_at = now
                partial_pcm = bytes(
                    self._utterance_pcm[-self._stt_partial_window_bytes :]
                )
                await self._enqueue_inference_job(
                    is_final=False,
                    trigger="partial_timer",
                    pcm_bytes=partial_pcm,
                )
            return

        if not self._is_speaking:
            return

        self._utterance_pcm.extend(payload_bytes)
        self._silence_duration_seconds += frame_duration_s
        if self._silence_duration_seconds < self._vad_silence_timeout_seconds:
            return

        await self._finalize_current_utterance(trigger="vad_silence")

    async def notify_silence(self) -> None:
        if self._closed:
            return
        await self._finalize_current_utterance(trigger="silence")

    async def _finalize_current_utterance(self, *, trigger: str) -> None:
        final_pcm = bytes(self._utterance_pcm)
        self._reset_turn_state()
        if final_pcm:
            await self._enqueue_inference_job(
                is_final=True,
                trigger=trigger,
                pcm_bytes=final_pcm,
            )

    def _reset_turn_state(self) -> None:
        self._utterance_pcm.clear()
        self._pre_roll_pcm.clear()
        self._is_speaking = False
        self._silence_duration_seconds = 0.0
        self._last_partial_emit_at = 0.0

    async def _on_user_turn_started(self) -> None:
        if (
            self._tts_processor is not None
            and await self._tts_processor.has_pending_output()
        ):
            await self._tts_processor.stop_immediately()
            await self._sender.send_json(
                self._connection_id,
                {
                    "event": "assistant_audio_aborted",
                    "session_id": str(self._session_id),
                    "reason": "barge_in",
                },
            )

        if self._llm_tasks:
            for task in list(self._llm_tasks):
                task.cancel()
            await self._sender.send_json(
                self._connection_id,
                {
                    "event": "assistant_generation_aborted",
                    "session_id": str(self._session_id),
                    "reason": "barge_in",
                },
            )

    def _append_to_pre_roll(self, payload_bytes: bytes) -> None:
        self._pre_roll_pcm.extend(payload_bytes)
        if len(self._pre_roll_pcm) > self._vad_pre_roll_bytes:
            overshoot = len(self._pre_roll_pcm) - self._vad_pre_roll_bytes
            del self._pre_roll_pcm[:overshoot]

    def _is_speech_frame(self, payload_bytes: bytes) -> bool:
        samples = np.frombuffer(payload_bytes, dtype=np.int16)
        if samples.size == 0:
            return False
        rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float32)))))
        if rms <= 0.0:
            return False
        dbfs = 20.0 * np.log10(rms / 32768.0 + 1e-12)
        return dbfs >= self._vad_energy_threshold_db

    async def _enqueue_inference_job(
        self, *, is_final: bool, trigger: str, pcm_bytes: bytes
    ) -> None:
        if not pcm_bytes or self._closed:
            return

        if self._inference_queue.full():
            if not is_final:
                return
            with contextlib.suppress(asyncio.QueueEmpty):
                self._inference_queue.get_nowait()

        if self._inference_queue.full():
            return

        await self._inference_queue.put(
            InferenceJob(
                is_final=is_final,
                trigger=trigger,
                created_at=time.perf_counter(),
                pcm_bytes=pcm_bytes,
            )
        )

    async def _inference_loop(self) -> None:
        while True:
            job = await self._inference_queue.get()
            if self._closed and job.trigger == "stop":
                return

            min_audio_bytes = (
                self._stt_final_min_audio_bytes
                if job.is_final
                else self._stt_partial_min_audio_bytes
            )
            if len(job.pcm_bytes) < min_audio_bytes:
                continue

            # Build contextual initial prompt: combine base prompt with previous STT text for context carry
            contextual_prompt = self._stt_initial_prompt
            if self._previous_stt_text.strip() and not job.is_final:
                # For partial results, add previous text as context (but limit length to avoid overwhelming)
                contextual_prompt += (
                    f" Previous context: {self._previous_stt_text[-200:]}"
                )

            started = time.perf_counter()
            analysis = await self._stt_inference.transcribe_audio_bytes(
                job.pcm_bytes,
                initial_prompt=contextual_prompt,
                beam_size=self._stt_final_beam_size
                if job.is_final
                else self._stt_partial_beam_size,
                word_timestamps=False,
                vad_filter=False,
                condition_on_previous_text=False,
            )

            logger.info(f"STT Output (final={job.is_final}): '{analysis.raw_text}'")
            analysis.raw_text = sanitize_transcript(analysis.raw_text)
            if job.is_final and analysis.raw_text.strip():
                self._previous_stt_text = analysis.raw_text.strip()

            inference_ms = (time.perf_counter() - started) * 1000
            await self.broadcast_subtitle(
                is_final=job.is_final,
                analysis=analysis,
                trigger=job.trigger,
                inference_ms=inference_ms,
                queued_at=job.created_at,
            )

            if job.is_final and analysis.raw_text.strip():
                # Record User Turn in Blackbox
                self._event_log.append(
                    {
                        "type": "USER_TURN",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": {
                            "text": analysis.raw_text,
                            "confidence": float(
                                np.mean([w.confidence for w in analysis.all_words])
                            )
                            if analysis.all_words
                            else 0.0,
                            "word_timestamps": [
                                w.model_dump() for w in analysis.all_words
                            ],
                            "stt_inference_ms": round(inference_ms, 2),
                        },
                    }
                )
                self._spawn_llm_task(analysis)

    async def broadcast_subtitle(
        self,
        *,
        is_final: bool,
        analysis: STTAnalysis,
        trigger: str,
        inference_ms: float,
        queued_at: float,
    ) -> None:
        coordination_ms = max(
            (time.perf_counter() - queued_at) * 1000 - inference_ms, 0.0
        )
        total_latency_ms = inference_ms + coordination_ms
        payload = {
            "event": "subtitle",
            "session_id": str(self._session_id),
            "absolute_timestamp": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "is_final": is_final,
            "trigger": trigger,
            "latency_ms": {
                "inference": round(inference_ms, 2),
                "coordination": round(coordination_ms, 2),
                "total": round(total_latency_ms, 2),
            },
            "within_budget": total_latency_ms < 800.0,
            "stt": analysis.model_dump(),
        }
        await self._sender.send_json(self._connection_id, payload)

    def _spawn_llm_task(self, analysis: STTAnalysis) -> None:
        if not analysis.raw_text.strip():
            return

        runner = (
            self._emit_local_fallback_reply
            if self._llm_processor is None
            else self._run_llm_pipeline
        )
        task = asyncio.create_task(
            runner(analysis),
            name=f"assistant-loop-{self._session_id}",
        )
        self._llm_tasks.add(task)
        task.add_done_callback(self._llm_tasks.discard)

    async def _emit_local_fallback_reply(self, analysis: STTAnalysis) -> None:
        result = LLMProcessor.build_fallback_reply(analysis)

        if result.response_text and not self._is_speaking:
            await self._sender.send_json(
                self._connection_id,
                {
                    "event": "assistant_stream",
                    "session_id": str(self._session_id),
                    "delta": result.response_text,
                    "source": "local_fallback",
                },
            )
            if self._tts_processor is not None:
                await self._tts_processor.feed_text(
                    result.response_text, is_final=False
                )

        if self._tts_processor is not None:
            await self._tts_processor.feed_text("", is_final=True)

        if self._is_speaking:
            return

        await self._sender.send_json(
            self._connection_id,
            {
                "event": "assistant_final",
                "session_id": str(self._session_id),
                "response_text": result.response_text,
                "pedagogical_feedback": result.pedagogical_feedback,
                "source": "local_fallback",
            },
        )

        # Record Fallback Turn in Blackbox
        self._event_log.append(
            {
                "type": "AI_TURN",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "text": result.response_text,
                    "pedagogical_feedback": result.pedagogical_feedback,
                    "source": "local_fallback",
                },
            }
        )

    def get_event_log(self) -> list[dict[str, object]]:
        """Retrieve the captured conversation history."""
        return list(self._event_log)

    async def _run_llm_pipeline(self, analysis: STTAnalysis) -> None:
        if self._llm_processor is None:
            return

        llm_raw_buffer = ""
        streamed_response_buffer = ""
        force_flush_task: asyncio.Task[None] | None = None

        async def reset_force_flush_timer() -> None:
            nonlocal force_flush_task
            if self._tts_processor is None:
                return
            if force_flush_task is not None:
                force_flush_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await force_flush_task
            force_flush_task = asyncio.create_task(
                self._force_flush_after_idle_timeout(),
                name=f"tts-force-flush-{self._session_id}",
            )

        async def on_token(delta: str) -> None:
            nonlocal llm_raw_buffer
            nonlocal streamed_response_buffer
            if not delta or self._is_speaking:
                return
            llm_raw_buffer += delta
            current_response_text = self._extract_response_text(llm_raw_buffer)
            response_delta = self._diff_streamed_text(
                streamed_response_buffer, current_response_text
            )
            if not response_delta:
                return
            streamed_response_buffer += response_delta
            await self._sender.send_json(
                self._connection_id,
                {
                    "event": "assistant_stream",
                    "session_id": str(self._session_id),
                    "delta": response_delta,
                    "source": self._llm_processor.source,
                },
            )
            if self._tts_processor is not None:
                await self._tts_processor.feed_text(response_delta, is_final=False)
                await reset_force_flush_timer()

        try:
            result = await self._llm_processor.stream_response(
                session_id=self._session_id,
                stt=analysis,
                on_token=on_token,
            )
        except asyncio.CancelledError:
            if force_flush_task is not None:
                force_flush_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await force_flush_task
            raise
        except Exception:
            logger.exception("llm.pipeline.failed session_id=%s", self._session_id)
            # Notify frontend of LLM error for quota/exceeded cases
            try:
                await self._sender.send_json(
                    self._connection_id,
                    {
                        "event": "llm_error",
                        "session_id": str(self._session_id),
                        "message": "LLM quota exceeded or unavailable. Using fallback responses.",
                    },
                )
            except Exception:
                # Avoid raising secondary exceptions during error handling
                pass
            result = PedagogicalReply(
                response_text="Let's keep going. Can you try saying it one more time?",
                pedagogical_feedback="",
                source="local_fallback",
            )

        final_tail = self._diff_streamed_text(
            streamed_response_buffer, result.response_text
        )
        if final_tail and not self._is_speaking:
            await self._sender.send_json(
                self._connection_id,
                {
                    "event": "assistant_stream",
                    "session_id": str(self._session_id),
                    "delta": final_tail,
                    "source": result.source,
                },
            )
            if self._tts_processor is not None:
                await self._tts_processor.feed_text(final_tail, is_final=False)

        if force_flush_task is not None:
            force_flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await force_flush_task

        if self._tts_processor is not None:
            await self._tts_processor.feed_text("", is_final=True)

        if self._is_speaking:
            return

        await self._sender.send_json(
            self._connection_id,
            {
                "event": "assistant_final",
                "session_id": str(self._session_id),
                "response_text": result.response_text,
                "pedagogical_feedback": result.pedagogical_feedback,
                "source": result.source,
            },
        )

        # Record AI Turn in Blackbox
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

    async def _cancel_llm_tasks(self) -> None:
        if not self._llm_tasks:
            return
        for task in list(self._llm_tasks):
            task.cancel()
        await asyncio.gather(*self._llm_tasks, return_exceptions=True)
        self._llm_tasks.clear()

    async def _force_flush_after_idle_timeout(self) -> None:
        if self._tts_processor is None:
            return
        try:
            await asyncio.sleep(self._tts_force_flush_timeout_seconds)
            await self._tts_processor.force_flush()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("tts.force_flush.failed session_id=%s", self._session_id)

    async def _emit_tts_chunk(self, chunk: TTSAudioChunk) -> None:
        await self._sender.send_json(
            self._connection_id,
            {
                "event": "assistant_audio",
                "session_id": str(self._session_id),
                "phrase_id": chunk.phrase_id,
                "chunk_index": chunk.chunk_index,
                "sequence_number": chunk.sequence_number,
                "is_last_chunk": chunk.is_last_chunk,
                "audio_format": "pcm_s16le",
                "sample_rate": 16000,
                "channels": 1,
                "synthesis_ms": round(chunk.synthesis_ms, 2),
                "audio_b64": base64.b64encode(chunk.pcm16_mono_16khz).decode("ascii"),
            },
        )

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
