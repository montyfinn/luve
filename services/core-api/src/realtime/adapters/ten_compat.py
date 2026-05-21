from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Awaitable, Callable

import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError, MediaStreamTrack
from aiortc.sdp import candidate_from_sdp
from av import AudioFrame
from av.audio.resampler import AudioResampler
from fastapi import HTTPException, status
from jose import JWTError, jwt

from src.core.config import settings
from src.media.audio_frame_utils import audio_frame_to_pcm16le_bytes
from src.realtime.contracts import IceRequest, OfferRequest, OfferResponse
from src.realtime.session_store import (
    SQLSessionStore,
    SessionStore,
    SessionStoreError,
)
from src.ten_ext.luve_extension import LUVEExtension


logger = logging.getLogger(__name__)

TEN_SINGLE_SESSION_CAPACITY = 1


class OutboundAudioTrack(MediaStreamTrack):
    kind = "audio"
    # Browsers/WebRTC/Opus operate most predictably at 48 kHz. The extension can
    # still emit 16 kHz PCM; this track owns the final playout resample boundary.
    _target_sample_rate = 48000
    _frame_duration_ms = 20

    def __init__(self) -> None:
        super().__init__()
        self._queue: asyncio.Queue[AudioFrame | None] = asyncio.Queue(maxsize=128)
        self._enqueue_lock = asyncio.Lock()
        self._closed = False
        self._next_pts = 0
        self._time_base = Fraction(1, self._target_sample_rate)
        self._playout_base_time: float | None = None
        self._resync_playout = False
        self._frame_samples = int(
            self._target_sample_rate * self._frame_duration_ms / 1000
        )

    async def enqueue_pcm(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        if not pcm_bytes:
            return
        if self._closed:
            return

        if sample_rate <= 0:
            sample_rate = self._target_sample_rate
        if channels <= 0:
            channels = 1

        async with self._enqueue_lock:
            if self._closed:
                return
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            if samples.size == 0:
                return

            if channels > 1:
                usable = samples[: (samples.size // channels) * channels]
                if usable.size == 0:
                    return
                mono = usable.reshape(-1, channels).mean(axis=1).astype(
                    np.int16,
                    copy=False,
                )
            else:
                mono = samples

            if sample_rate != self._target_sample_rate:
                mono = self._resample_pcm16_mono(
                    mono,
                    sample_rate,
                    self._target_sample_rate,
                )
                if mono.size == 0:
                    return

            for offset in range(0, mono.size, self._frame_samples):
                packet = mono[offset : offset + self._frame_samples]
                if packet.size == 0:
                    continue
                frame = AudioFrame(format="s16", layout="mono", samples=packet.size)
                frame.planes[0].update(packet.tobytes())
                frame.sample_rate = self._target_sample_rate
                await self._queue.put(frame)

    async def close(self) -> None:
        self._closed = True
        self._drain_queue()
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(None)

    async def clear(self) -> None:
        self._drain_queue()
        self._resync_playout = True

    @property
    def queued_frames(self) -> int:
        return self._queue.qsize()

    @property
    def closed(self) -> bool:
        return self._closed

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    async def recv(self) -> AudioFrame:
        if self._closed and self._queue.empty():
            raise MediaStreamError

        try:
            frame = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            frame = self._make_silence_frame()

        if frame is None:
            raise MediaStreamError

        loop = asyncio.get_running_loop()
        now = loop.time()

        if self._playout_base_time is None or self._resync_playout:
            self._playout_base_time = now - (
                self._next_pts / float(self._target_sample_rate)
            )
            self._resync_playout = False

        target_time = self._playout_base_time + (
            self._next_pts / float(self._target_sample_rate)
        )
        sleep_for = target_time - now
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)

        frame.pts = self._next_pts
        frame.time_base = self._time_base
        self._next_pts += frame.samples
        return frame

    def _make_silence_frame(self) -> AudioFrame:
        frame = AudioFrame(format="s16", layout="mono", samples=self._frame_samples)
        frame.planes[0].update(bytes(self._frame_samples * 2))
        frame.sample_rate = self._target_sample_rate
        return frame

    @staticmethod
    def _resample_pcm16_mono(
        pcm_samples: np.ndarray,
        source_rate: int,
        target_rate: int,
    ) -> np.ndarray:
        if source_rate == target_rate or pcm_samples.size == 0:
            return pcm_samples

        source_frame = AudioFrame(format="s16", layout="mono", samples=pcm_samples.size)
        source_frame.planes[0].update(pcm_samples.tobytes())
        source_frame.sample_rate = source_rate
        resampler = AudioResampler(format="s16", layout="mono", rate=target_rate)
        output = bytearray()

        converted = resampler.resample(source_frame)
        frames = converted if isinstance(converted, list) else [converted]
        for frame in frames:
            if frame is not None:
                output.extend(audio_frame_to_pcm16le_bytes(frame))

        flushed = resampler.resample(None)
        flush_frames = flushed if isinstance(flushed, list) else [flushed]
        for frame in flush_frames:
            if frame is not None:
                output.extend(audio_frame_to_pcm16le_bytes(frame))

        return np.frombuffer(bytes(output), dtype=np.int16)


@dataclass
class SessionState:
    session_id: str
    pc: RTCPeerConnection
    outbound_audio_track: OutboundAudioTrack
    created_at: float = field(default_factory=time.monotonic)
    data_channels: set[Any] = field(default_factory=set)
    tasks: set[asyncio.Task[None]] = field(default_factory=set)


class WebRTCGatewayManager:
    def __init__(
        self,
        extension: LUVEExtension,
        *,
        session_store: SessionStore | None = None,
    ) -> None:
        self._extension = extension
        self._session_store = session_store or SQLSessionStore()
        self._sessions: dict[str, SessionState] = {}
        self._closed_sessions_total = 0
        self._last_close_summary: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def create_session(self, request: OfferRequest) -> OfferResponse:
        if not request.session_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "session_id is required. Create a session via "
                    "POST /api/v1/sessions on the Core API before WebRTC offer."
                ),
            )

        session_id = request.session_id
        pc = RTCPeerConnection()
        outbound_track = OutboundAudioTrack()
        pc.addTrack(outbound_track)
        session = SessionState(
            session_id=session_id,
            pc=pc,
            outbound_audio_track=outbound_track,
        )

        async with self._lock:
            effective_capacity = min(
                settings.max_webrtc_sessions,
                TEN_SINGLE_SESSION_CAPACITY,
            )
            if len(self._sessions) >= effective_capacity:
                with contextlib.suppress(Exception):
                    await outbound_track.close()
                with contextlib.suppress(Exception):
                    await pc.close()
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "WebRTC capacity reached on this node. This gateway "
                        "currently supports one active TEN session."
                    ),
                )
            try:
                await self._session_store.reserve_persisted_session(session_id)
            except SessionStoreError as exc:
                with contextlib.suppress(Exception):
                    await outbound_track.close()
                with contextlib.suppress(Exception):
                    await pc.close()
                self._raise_session_store_error(exc)
            self._sessions[session_id] = session

        self._extension.on_cmd(
            {
                "session_id": session_id,
                "command": "START",
                "stt_only": request.stt_only,
                "tts_enabled": request.tts_enabled,
            }
        )

        @pc.on("datachannel")
        def _on_datachannel(channel: Any) -> None:
            session.data_channels.add(channel)

            @channel.on("message")
            def _on_message(message: Any) -> None:
                if isinstance(message, bytes):
                    with contextlib.suppress(Exception):
                        message = message.decode("utf-8")
                if not isinstance(message, str):
                    return
                with contextlib.suppress(Exception):
                    payload = json.loads(message)
                    payload.setdefault("session_id", session_id)
                    cmd = str(
                        payload.get("cmd") or payload.get("command") or ""
                    ).strip().upper()
                    if cmd:
                        if cmd == "BARGE_IN":
                            asyncio.create_task(self.flush_outbound_audio(session_id))
                        self._extension.on_cmd(payload)

            @channel.on("close")
            def _on_close() -> None:
                session.data_channels.discard(channel)

        @pc.on("track")
        def _on_track(track: MediaStreamTrack) -> None:
            if track.kind != "audio":
                return
            task = asyncio.create_task(
                self._consume_incoming_audio(session_id, track),
                name=f"in-audio-{session_id}",
            )
            session.tasks.add(task)
            task.add_done_callback(session.tasks.discard)

        @pc.on("connectionstatechange")
        async def _on_connectionstatechange() -> None:
            if pc.connectionState in {"failed", "closed", "disconnected"}:
                await self.close_session(session_id)

        try:
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=request.sdp, type=request.type)
            )
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
        except Exception:
            async with self._lock:
                self._sessions.pop(session_id, None)
            with contextlib.suppress(Exception):
                await self._session_store.mark_session_status(session_id, "ready")
            with contextlib.suppress(Exception):
                await outbound_track.close()
            with contextlib.suppress(Exception):
                await pc.close()
            raise

        logger.info("webrtc.session.created session_id=%s", session_id)
        return OfferResponse(
            session_id=session_id,
            answer={"type": pc.localDescription.type, "sdp": pc.localDescription.sdp},
        )

    async def add_ice_candidate(self, request: IceRequest) -> None:
        async with self._lock:
            session = self._sessions.get(request.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_id not found")

        cand = request.candidate
        sdp_candidate = cand.get("candidate")
        if not sdp_candidate:
            raise HTTPException(status_code=400, detail="missing ICE candidate string")
        candidate = candidate_from_sdp(str(sdp_candidate))
        candidate.sdpMid = cand.get("sdpMid")
        candidate.sdpMLineIndex = cand.get("sdpMLineIndex")
        await session.pc.addIceCandidate(candidate)

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False)
        target_session_id = self._extract_session_id_from_payload(payload)
        async with self._lock:
            sessions = self._select_output_sessions_locked(target_session_id)
        for session in sessions:
            for channel in list(session.data_channels):
                if getattr(channel, "readyState", "") == "open":
                    with contextlib.suppress(Exception):
                        channel.send(body)

    async def broadcast_audio_frame(self, frame_obj: Any) -> None:
        pcm_bytes, sample_rate, channels, target_session_id = (
            self._extract_pcm_payload(frame_obj)
        )
        if not pcm_bytes:
            return

        async with self._lock:
            sessions = self._select_output_sessions_locked(target_session_id)
        for session in sessions:
            with contextlib.suppress(Exception):
                await session.outbound_audio_track.enqueue_pcm(
                    pcm_bytes,
                    sample_rate=sample_rate,
                    channels=channels,
                )

    async def close_session(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            remaining_sessions = len(self._sessions)
        if session is None:
            return

        queued_frames = session.outbound_audio_track.queued_frames
        for task in list(session.tasks):
            task.cancel()
        if session.tasks:
            await asyncio.gather(*session.tasks, return_exceptions=True)

        with contextlib.suppress(Exception):
            await session.outbound_audio_track.clear()
        with contextlib.suppress(Exception):
            await session.outbound_audio_track.close()
        with contextlib.suppress(Exception):
            await session.pc.close()

        self._extension.on_cmd({"session_id": session_id, "command": "END_SESSION"})

        logger.info(
            "webrtc.session.closed session_id=%s remaining_sessions=%s queued_frames=%s",
            session_id,
            remaining_sessions,
            queued_frames,
        )
        async with self._lock:
            self._closed_sessions_total += 1
            self._last_close_summary = {
                "session_id": session_id,
                "remaining_sessions": remaining_sessions,
                "queued_frames": queued_frames,
                "closed_total": self._closed_sessions_total,
            }

    async def assert_session_owner(
        self,
        session_id: str,
        authorization: str | None,
    ) -> None:
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")

        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token is required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = authorization.split(" ", 1)[1].strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token is required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.algorithm],
            )
            user_id = str(payload.get("sub") or "")
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            owner_id = await self._session_store.get_session_owner(session_id)
        except SessionStoreError as exc:
            self._raise_session_store_error(exc)

        if owner_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="session does not belong to token owner",
            )

    async def close_all(self) -> None:
        async with self._lock:
            session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id)

    async def get_runtime_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        async with self._lock:
            sessions = list(self._sessions.values())
            closed_sessions_total = self._closed_sessions_total
            last_close_summary = (
                dict(self._last_close_summary)
                if self._last_close_summary is not None
                else None
            )

        session_snapshots: list[dict[str, Any]] = []
        for session in sessions:
            pc = session.pc
            session_snapshots.append(
                {
                    "session_id": session.session_id,
                    "age_seconds": round(max(now - session.created_at, 0.0), 2),
                    "connection_state": getattr(pc, "connectionState", None),
                    "ice_connection_state": getattr(pc, "iceConnectionState", None),
                    "queued_frames": session.outbound_audio_track.queued_frames,
                    "outbound_track_closed": session.outbound_audio_track.closed,
                    "data_channels": len(session.data_channels),
                    "tasks": len(session.tasks),
                }
            )

        max_session_age_seconds = max(
            (item["age_seconds"] for item in session_snapshots),
            default=0.0,
        )
        return {
            "status": "ok",
            "active_sessions": len(session_snapshots),
            "max_session_age_seconds": max_session_age_seconds,
            "closed_sessions_total": closed_sessions_total,
            "last_close": last_close_summary,
            "sessions": session_snapshots,
        }

    async def flush_outbound_audio(self, session_id: str | None = None) -> None:
        async with self._lock:
            if session_id is None:
                sessions = list(self._sessions.values())
            else:
                session = self._sessions.get(session_id)
                sessions = [session] if session is not None else []

        for session in sessions:
            with contextlib.suppress(Exception):
                await session.outbound_audio_track.clear()

    async def _consume_incoming_audio(
        self,
        session_id: str,
        track: MediaStreamTrack,
    ) -> None:
        resampler = AudioResampler(format="s16", layout="mono", rate=16000)
        sequence_number = 0
        try:
            while True:
                frame = await track.recv()
                resampled = resampler.resample(frame)
                frames = resampled if isinstance(resampled, list) else [resampled]
                for item in frames:
                    if item is None:
                        continue
                    pcm = audio_frame_to_pcm16le_bytes(item)
                    if not pcm:
                        continue
                    self._extension.on_audio_frame(
                        {
                            "session_id": session_id,
                            "sequence_number": sequence_number,
                            "data": pcm,
                        }
                    )
                    sequence_number += 1
        except MediaStreamError:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("webrtc.inbound.failed session_id=%s", session_id)
        finally:
            self._extension.on_cmd(
                {
                    "session_id": session_id,
                    "command": "FLUSH",
                    "suppress_response": True,
                }
            )

    @staticmethod
    def _extract_session_id_from_payload(payload: dict[str, Any]) -> str | None:
        value = payload.get("session_id")
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def _select_output_sessions_locked(
        self,
        target_session_id: str | None,
    ) -> list[SessionState]:
        if target_session_id is not None:
            session = self._sessions.get(target_session_id)
            return [session] if session is not None else []
        if len(self._sessions) <= 1:
            return list(self._sessions.values())
        logger.warning("dropping unscoped TEN output while multiple sessions are active")
        return []

    @staticmethod
    def _extract_pcm_payload(frame_obj: Any) -> tuple[bytes, int, int, str | None]:
        sample_rate = 16000
        channels = 1
        payload: bytes | bytearray | memoryview | None = None
        session_id: str | None = None

        if isinstance(frame_obj, dict):
            payload = (
                frame_obj.get("data")
                or frame_obj.get("buffer")
                or frame_obj.get("payload")
            )
            sample_rate = int(frame_obj.get("sample_rate", 16000))
            channels = int(frame_obj.get("channels", 1))
            session_id = WebRTCGatewayManager._normalize_optional_session_id(
                frame_obj.get("session_id")
            )
        else:
            payload = (
                getattr(frame_obj, "data", None)
                or getattr(frame_obj, "buffer", None)
                or getattr(frame_obj, "payload", None)
            )
            sample_rate = int(getattr(frame_obj, "sample_rate", 16000) or 16000)
            channels = int(getattr(frame_obj, "channels", 1) or 1)
            session_id = WebRTCGatewayManager._normalize_optional_session_id(
                getattr(frame_obj, "session_id", None)
            )

        if payload is None:
            return b"", sample_rate, channels, session_id
        if isinstance(payload, memoryview):
            return payload.tobytes(), sample_rate, channels, session_id
        if isinstance(payload, bytearray):
            return bytes(payload), sample_rate, channels, session_id
        if isinstance(payload, bytes):
            return payload, sample_rate, channels, session_id
        return b"", sample_rate, channels, session_id

    @staticmethod
    def _normalize_optional_session_id(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _raise_session_store_error(exc: SessionStoreError) -> None:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


class TenEnvAdapter:
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        gateway: WebRTCGatewayManager,
        properties: dict[str, Any],
    ) -> None:
        self._loop = loop
        self._gateway = gateway
        self._properties = properties

    def get_property(self, key: str) -> Any:
        return self._properties.get(key)

    def map_ports(self, _mapping: dict[str, str]) -> None:
        return None

    def bind_ports(self, _mapping: dict[str, str]) -> None:
        return None

    def configure_ports(self, _mapping: dict[str, str]) -> None:
        return None

    def register_port_mapping(self, _mapping: dict[str, str]) -> None:
        return None

    def send_audio_frame(self, *args: Any) -> None:
        frame = self._extract_payload_from_args(args)
        self._schedule(lambda: self._gateway.broadcast_audio_frame(frame))

    def push_audio_frame(self, *args: Any) -> None:
        self.send_audio_frame(*args)

    def emit_audio_frame(self, *args: Any) -> None:
        self.send_audio_frame(*args)

    def send_json(self, *args: Any) -> None:
        payload = self._extract_payload_from_args(args)
        if not isinstance(payload, dict):
            payload = {"event": "raw_json", "data": str(payload)}
        self._schedule(lambda: self._gateway.broadcast_json(payload))

    def push_json(self, *args: Any) -> None:
        self.send_json(*args)

    def emit_json(self, *args: Any) -> None:
        self.send_json(*args)

    def send_text(self, *args: Any) -> None:
        payload = self._extract_payload_from_args(args)
        self._schedule(
            lambda: self._gateway.broadcast_json(
                {"event": "log", "message": str(payload)}
            )
        )

    def send_log(self, *args: Any) -> None:
        self.send_text(*args)

    def emit_text(self, *args: Any) -> None:
        self.send_text(*args)

    def send_data(self, *args: Any) -> None:
        payload = self._extract_payload_from_args(args)
        if isinstance(payload, dict):
            self.send_json(payload)
        else:
            self.send_text(payload)

    def _schedule(self, factory: Callable[[], Awaitable[None]]) -> None:
        def _dispatch() -> None:
            asyncio.create_task(factory())

        self._loop.call_soon_threadsafe(_dispatch)

    @staticmethod
    def _extract_payload_from_args(args: tuple[Any, ...]) -> Any:
        if len(args) == 1:
            return args[0]
        if len(args) >= 2:
            if isinstance(args[0], str):
                return args[1]
            return args[0]
        raise TypeError("Expected at least one argument")
