from __future__ import annotations

import asyncio
import time
import weakref
from collections import deque
from contextlib import suppress


def _cancel_monitor_task(buffer_ref: "weakref.ReferenceType[AudioBuffer]") -> None:
    buffer = buffer_ref()
    if buffer is None:
        return
    monitor_task = buffer._monitor_task
    if monitor_task is not None and not monitor_task.done():
        monitor_task.cancel()


class AudioBuffer:
    def __init__(
        self,
        *,
        silence_ttl_seconds: float = 5.0,
        sweep_interval_seconds: float = 0.5,
    ) -> None:
        if silence_ttl_seconds <= 0:
            raise ValueError("silence_ttl_seconds must be > 0")
        if sweep_interval_seconds <= 0:
            raise ValueError("sweep_interval_seconds must be > 0")

        self._silence_ttl_seconds = silence_ttl_seconds
        self._sweep_interval_seconds = min(sweep_interval_seconds, silence_ttl_seconds)

        self._ordered_chunks: deque[memoryview] = deque()
        self._pending_by_sequence: dict[int, memoryview] = {}
        self._next_expected_sequence: int | None = None

        self._total_bytes = 0
        self._flat_cache: bytes | None = None
        self._last_activity = time.monotonic()

        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._monitor_task: asyncio.Task[None] | None = None
        self._closed = False

        # Weak finalizer avoids strong-reference cycles between GC and task cleanup.
        self._finalizer = weakref.finalize(self, _cancel_monitor_task, weakref.ref(self))

    async def start(self) -> None:
        async with self._lock:
            self._ensure_open_unlocked()
            self._ensure_monitor_started_unlocked()

    async def close(self) -> None:
        monitor_task: asyncio.Task[None] | None
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop_event.set()
            monitor_task = self._monitor_task
            self._monitor_task = None
            self._clear_unlocked()

        if monitor_task is not None and not monitor_task.done():
            monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await monitor_task

        self._finalizer.detach()

    async def __aenter__(self) -> "AudioBuffer":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def add_chunk(self, sequence_number: int, chunk: bytes | bytearray | memoryview) -> None:
        if sequence_number < 0:
            raise ValueError("sequence_number must be >= 0")

        normalized_chunk = self._normalize_chunk(chunk)
        if not normalized_chunk:
            return

        async with self._lock:
            self._ensure_open_unlocked()
            self._ensure_monitor_started_unlocked()
            self._last_activity = time.monotonic()

            if self._next_expected_sequence is None:
                self._next_expected_sequence = sequence_number

            if sequence_number < self._next_expected_sequence:
                return

            if sequence_number in self._pending_by_sequence:
                return

            self._pending_by_sequence[sequence_number] = normalized_chunk
            self._flush_contiguous_unlocked()

    async def push(self, sequence_number: int, chunk: bytes | bytearray | memoryview) -> None:
        await self.add_chunk(sequence_number, chunk)

    async def get_flat_audio(self) -> bytes:
        async with self._lock:
            self._ensure_open_unlocked()

            if self._flat_cache is not None:
                return self._flat_cache

            if self._total_bytes == 0:
                self._flat_cache = b""
                return self._flat_cache

            # One pre-allocation + one pass copy; avoids repeated N^2 concatenation.
            merged = bytearray(self._total_bytes)
            offset = 0
            for chunk in self._ordered_chunks:
                chunk_end = offset + len(chunk)
                merged[offset:chunk_end] = chunk
                offset = chunk_end

            self._flat_cache = bytes(merged)
            return self._flat_cache

    async def clear(self) -> None:
        async with self._lock:
            self._clear_unlocked()

    async def stats(self) -> dict[str, int | float | None]:
        async with self._lock:
            return {
                "ordered_chunk_count": len(self._ordered_chunks),
                "pending_chunk_count": len(self._pending_by_sequence),
                "total_bytes": self._total_bytes,
                "next_expected_sequence": self._next_expected_sequence,
                "silence_ttl_seconds": self._silence_ttl_seconds,
            }

    async def _check_silence_timeout(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._sweep_interval_seconds,
                )
                break
            except asyncio.TimeoutError:
                pass

            async with self._lock:
                if self._closed:
                    return

                is_idle = (time.monotonic() - self._last_activity) >= self._silence_ttl_seconds
                has_audio = bool(self._ordered_chunks or self._pending_by_sequence)
                if is_idle and has_audio:
                    self._clear_unlocked()

    @staticmethod
    def _normalize_chunk(chunk: bytes | bytearray | memoryview) -> memoryview:
        if isinstance(chunk, bytes):
            return memoryview(chunk)
        if isinstance(chunk, bytearray):
            # bytearray may be mutable by caller; freeze to keep deterministic audio ordering.
            return memoryview(bytes(chunk))
        if isinstance(chunk, memoryview):
            # memoryview may be backed by a mutable/reused buffer; freeze it on enqueue.
            return memoryview(chunk.tobytes())
        raise TypeError("chunk must be bytes-like (bytes, bytearray, memoryview)")

    def _flush_contiguous_unlocked(self) -> None:
        if self._next_expected_sequence is None:
            return

        while True:
            chunk = self._pending_by_sequence.pop(self._next_expected_sequence, None)
            if chunk is None:
                break
            self._ordered_chunks.append(chunk)
            self._total_bytes += len(chunk)
            self._flat_cache = None
            self._next_expected_sequence += 1

    def _clear_unlocked(self) -> None:
        self._ordered_chunks.clear()
        self._pending_by_sequence.clear()
        self._next_expected_sequence = None
        self._total_bytes = 0
        self._flat_cache = b""
        self._last_activity = time.monotonic()

    def _ensure_open_unlocked(self) -> None:
        if self._closed:
            raise RuntimeError("AudioBuffer is closed")

    def _ensure_monitor_started_unlocked(self) -> None:
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(
                self._check_silence_timeout(),
                name="audio-buffer-silence-monitor",
            )
