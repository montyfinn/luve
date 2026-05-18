from __future__ import annotations

import asyncio
import contextlib
import io
import inspect
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import av
import numpy as np
from av.audio.resampler import AudioResampler

from src.media.audio_frame_utils import extend_pcm16le_from_frames


logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000
TARGET_LAYOUT = "mono"
TARGET_FORMAT = "s16"
PCM16_MONO_16KHZ_BYTES_PER_SECOND = 32000

AudioChunkCallback = Callable[["TTSAudioChunk"], Awaitable[None]]
_PUNCTUATION_PATTERN = re.compile(r"[,.!?;:](?:\s|$)")


@dataclass(frozen=True)
class PhraseJob:
    phrase_id: int
    text: str
    queued_at: float


@dataclass(frozen=True)
class TTSAudioChunk:
    phrase_id: int
    chunk_index: int
    sequence_number: int
    is_last_chunk: bool
    synthesis_ms: float
    pcm16_mono_16khz: bytes


class TTSProcessor:
    def __init__(
        self,
        *,
        edge_voice: str = "en-US-AnaNeural",
        phrase_min_chars: int = 28,
        queue_maxsize: int = 24,
        chunk_ms: int = 120,
        local_fallback_enabled: bool = False,
        piper_model_path: str | None = None,
        piper_sample_rate: int = 22050,
    ) -> None:
        if phrase_min_chars <= 0:
            raise ValueError("phrase_min_chars must be > 0")
        if queue_maxsize <= 0:
            raise ValueError("queue_maxsize must be > 0")
        if chunk_ms <= 0:
            raise ValueError("chunk_ms must be > 0")
        if piper_sample_rate <= 0:
            raise ValueError("piper_sample_rate must be > 0")

        self._edge_voice = edge_voice
        self._phrase_min_chars = phrase_min_chars
        self._chunk_ms = chunk_ms
        self._local_fallback_enabled = local_fallback_enabled
        self._piper_model_path = piper_model_path
        self._piper_sample_rate = piper_sample_rate

        self._phrase_buffer = ""
        self._phrase_queue: asyncio.Queue[PhraseJob | None] = asyncio.Queue(maxsize=queue_maxsize)
        self._worker_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._closed = False

        self._next_phrase_id = 0
        self._next_audio_sequence = 0
        self._on_audio_chunk: AudioChunkCallback | None = None
        self._active_synthesis_task: asyncio.Task[bytearray] | None = None
        self._active_communicator: object | None = None

    async def start(self, on_audio_chunk: AudioChunkCallback) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._on_audio_chunk = on_audio_chunk
        self._closed = False
        self._worker_task = asyncio.create_task(self._worker_loop(), name="tts-worker")

    async def stop(self, *, flush: bool = True) -> None:
        if self._worker_task is None:
            return
        if flush:
            await self.feed_text("", is_final=True)
        self._closed = True
        await self._phrase_queue.put(None)
        await self._worker_task
        self._worker_task = None
        async with self._lock:
            self._phrase_buffer = ""

    async def stop_immediately(self) -> None:
        if self._closed:
            return
        async with self._lock:
            self._phrase_buffer = ""
            self._clear_phrase_queue_unlocked()
            active_task = self._active_synthesis_task
            active_communicator = self._active_communicator
            self._active_synthesis_task = None
            self._active_communicator = None

        if active_communicator is not None:
            await self._close_streaming_object(active_communicator)

        if active_task is not None:
            active_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await active_task

    async def has_pending_output(self) -> bool:
        async with self._lock:
            return bool(
                self._phrase_buffer.strip()
                or not self._phrase_queue.empty()
                or self._active_synthesis_task is not None
                or self._active_communicator is not None
            )

    async def feed_text(self, delta: str, *, is_final: bool) -> None:
        if self._closed:
            return
        async with self._lock:
            if delta:
                self._phrase_buffer += delta
            ready_phrases = self._drain_ready_phrases(is_final=is_final)

        for phrase in ready_phrases:
            await self._enqueue_phrase(phrase)

    async def force_flush(self) -> None:
        if self._closed:
            return
        async with self._lock:
            pending = self._phrase_buffer.strip()
            self._phrase_buffer = ""
        if pending:
            await self._enqueue_phrase(pending)

    def estimate_first_chunk_latency_ms(self) -> tuple[int, int]:
        # Edge-TTS network + first decode/resample + first 120ms chunk framing.
        return (90, 180)

    def _drain_ready_phrases(self, *, is_final: bool) -> list[str]:
        pending = self._phrase_buffer
        phrases: list[str] = []

        while True:
            cut_index = self._find_phrase_break(pending)
            if cut_index < 0:
                break
            phrase = pending[:cut_index].strip()
            if phrase:
                phrases.append(phrase)
            pending = pending[cut_index:]

        if is_final and pending.strip():
            phrases.append(pending.strip())
            pending = ""

        self._phrase_buffer = pending
        return phrases

    def _find_phrase_break(self, text: str) -> int:
        punctuation_match = _PUNCTUATION_PATTERN.search(text)
        if punctuation_match:
            return punctuation_match.end()

        compact = text.strip()
        if len(compact) < self._phrase_min_chars:
            return -1

        last_space = text.rfind(" ")
        if last_space <= 0:
            return -1
        return last_space + 1

    async def _enqueue_phrase(self, phrase: str) -> None:
        normalized = " ".join(phrase.split())
        if not normalized:
            return
        job = PhraseJob(
            phrase_id=self._next_phrase_id,
            text=normalized,
            queued_at=time.perf_counter(),
        )
        self._next_phrase_id += 1
        await self._phrase_queue.put(job)

    async def _worker_loop(self) -> None:
        while True:
            job = await self._phrase_queue.get()
            if job is None:
                return

            synth_started = time.perf_counter()
            synth_task = asyncio.create_task(self._synthesize_phrase(job.text), name="tts-synthesis")
            async with self._lock:
                self._active_synthesis_task = synth_task
            try:
                pcm = await synth_task
            except asyncio.CancelledError:
                if self._closed:
                    return
                continue
            finally:
                async with self._lock:
                    if self._active_synthesis_task is synth_task:
                        self._active_synthesis_task = None
            synthesis_ms = (time.perf_counter() - synth_started) * 1000
            if not pcm:
                continue

            try:
                await self._emit_audio_chunks(job.phrase_id, pcm, synthesis_ms=synthesis_ms)
            finally:
                pcm.clear()

    async def _emit_audio_chunks(self, phrase_id: int, pcm: bytearray, *, synthesis_ms: float) -> None:
        callback = self._on_audio_chunk
        if callback is None:
            return

        chunk_size = max(int((self._chunk_ms / 1000) * PCM16_MONO_16KHZ_BYTES_PER_SECOND), 640)
        total_len = len(pcm)
        chunk_index = 0
        offset = 0

        while offset < total_len:
            end = min(offset + chunk_size, total_len)
            chunk_bytes = bytes(pcm[offset:end])
            is_last_chunk = end >= total_len

            chunk = TTSAudioChunk(
                phrase_id=phrase_id,
                chunk_index=chunk_index,
                sequence_number=self._next_audio_sequence,
                is_last_chunk=is_last_chunk,
                synthesis_ms=synthesis_ms,
                pcm16_mono_16khz=chunk_bytes,
            )
            self._next_audio_sequence += 1
            chunk_index += 1
            offset = end
            await callback(chunk)

    async def _synthesize_phrase(self, text: str) -> bytearray:
        try:
            return await self._synthesize_with_edge_tts(text)
        except Exception:
            logger.warning("tts.edge.failed phrase=%r", text, exc_info=True)

        if self._local_fallback_enabled:
            try:
                return await self._synthesize_with_piper(text)
            except Exception:
                logger.warning("tts.local_fallback.failed phrase=%r", text, exc_info=True)

        return bytearray()

    async def _synthesize_with_edge_tts(self, text: str) -> bytearray:
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError("edge-tts package is required for TTSProcessor") from exc

        encoded_audio = bytearray()
        try:
            communicator = edge_tts.Communicate(text=text, voice=self._edge_voice)
            await self._set_active_communicator(communicator)
            async for event in communicator.stream():
                if event.get("type") != "audio":
                    continue
                data = event.get("data")
                if isinstance(data, (bytes, bytearray)):
                    encoded_audio.extend(data)

            if not encoded_audio:
                raise RuntimeError("Edge-TTS returned empty audio")

            encoded_bytes = bytes(encoded_audio)
            # Keep PyAV decode/resample fully off the event loop.
            return await asyncio.to_thread(self._decode_edge_audio_to_target_pcm, encoded_bytes)
        finally:
            await self._clear_active_communicator(communicator if "communicator" in locals() else None)
            encoded_audio.clear()

    def _decode_edge_audio_to_target_pcm(self, encoded_audio: bytes) -> bytearray:
        output = bytearray()
        try:
            resampler = AudioResampler(
                format=TARGET_FORMAT,
                layout=TARGET_LAYOUT,
                rate=TARGET_SAMPLE_RATE,
            )
            with av.open(io.BytesIO(encoded_audio), mode="r") as container:
                for frame in container.decode(audio=0):
                    converted = resampler.resample(frame)
                    frames = converted if isinstance(converted, list) else [converted]
                    extend_pcm16le_from_frames(output, frames)

                flushed = resampler.resample(None)
                flush_frames = flushed if isinstance(flushed, list) else [flushed]
                extend_pcm16le_from_frames(output, flush_frames)

            return output
        except Exception:
            output.clear()
            raise

    async def _synthesize_with_piper(self, text: str) -> bytearray:
        if not self._piper_model_path:
            raise RuntimeError("PIPER_MODEL_PATH is required when local fallback is enabled")

        process = await asyncio.create_subprocess_exec(
            "piper",
            "--model",
            self._piper_model_path,
            "--output_raw",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(text.encode("utf-8"))
        if process.returncode != 0:
            raise RuntimeError(f"Piper failed: {stderr.decode('utf-8', errors='replace').strip()}")
        if not stdout:
            raise RuntimeError("Piper returned empty audio")

        resampled = await asyncio.to_thread(
            self._resample_raw_pcm16_mono,
            stdout,
            self._piper_sample_rate,
            TARGET_SAMPLE_RATE,
        )
        return bytearray(resampled)

    @staticmethod
    def _resample_raw_pcm16_mono(audio_bytes: bytes, source_rate: int, target_rate: int) -> bytes:
        samples = np.frombuffer(audio_bytes, dtype=np.int16)
        if samples.size == 0:
            return b""
        if source_rate == target_rate:
            return samples.tobytes()

        source_positions = np.arange(samples.size, dtype=np.float32)
        target_len = max(int(round(samples.size * target_rate / float(source_rate))), 1)
        target_positions = np.linspace(0, samples.size - 1, num=target_len, dtype=np.float32)

        resampled = np.interp(target_positions, source_positions, samples.astype(np.float32, copy=False))
        pcm16 = np.clip(resampled, -32768, 32767).astype(np.int16)
        return pcm16.tobytes()

    @staticmethod
    async def _close_streaming_object(candidate: object) -> None:
        for closer_name in ("aclose", "close"):
            closer = getattr(candidate, closer_name, None)
            if closer is None:
                continue
            result = closer()
            if inspect.isawaitable(result):
                await result
            return

    async def _set_active_communicator(self, communicator: object) -> None:
        async with self._lock:
            self._active_communicator = communicator

    async def _clear_active_communicator(self, communicator: object | None) -> None:
        if communicator is None:
            return
        async with self._lock:
            if self._active_communicator is communicator:
                self._active_communicator = None

    def _clear_phrase_queue_unlocked(self) -> None:
        while True:
            try:
                self._phrase_queue.get_nowait()
            except asyncio.QueueEmpty:
                return
