import asyncio
import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, WebSocketException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp, Receive, Scope, Send

from src.api.deps import get_current_user
from src.core.config import settings
from src.core.db import get_db
from src.media.brain import LLMProcessor
from src.media.coordinator import StreamCoordinator
from src.media.stt_worker import WhisperInference
from src.media.tts import TTSProcessor
from src.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])


class WebSocketHandshakeTimingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "websocket" or not scope.get("path", "").startswith("/ws/chat/"):
            await self.app(scope, receive, send)
            return

        started_at = time.perf_counter()
        accepted = False

        async def send_wrapper(message: dict) -> None:
            nonlocal accepted
            if message["type"] == "websocket.accept":
                accepted = True
                handshake_ms = (time.perf_counter() - started_at) * 1000
                logger.info(
                    "ws.handshake.accepted path=%s handshake_ms=%.2f",
                    scope.get("path", ""),
                    handshake_ms,
                )
            elif message["type"] == "websocket.close" and not accepted:
                handshake_ms = (time.perf_counter() - started_at) * 1000
                logger.warning(
                    "ws.handshake.rejected path=%s code=%s handshake_ms=%.2f",
                    scope.get("path", ""),
                    message.get("code"),
                    handshake_ms,
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)


class ConnectionManager:
    def __init__(self) -> None:
        self._active_connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, connection_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._active_connections[connection_id] = websocket

    async def disconnect(self, connection_id: str) -> None:
        async with self._lock:
            self._active_connections.pop(connection_id, None)

    async def send_json(self, connection_id: str, payload: dict[str, object]) -> None:
        websocket = self._active_connections.get(connection_id)
        if websocket is not None:
            await websocket.send_json(payload)

    @property
    def active_count(self) -> int:
        return len(self._active_connections)


connection_manager = ConnectionManager()


def _extract_websocket_token(websocket: WebSocket) -> str | None:
    token = websocket.query_params.get("token")
    if token:
        return token

    cookie_token = websocket.cookies.get("access_token")
    if cookie_token:
        parts = cookie_token.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        return cookie_token

    return None


def _build_redis_client() -> Redis:
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is not configured")
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def _is_session_registered(redis_client: Redis, session_id: UUID) -> bool:
    session_key = f"session:{session_id}"
    return bool(await redis_client.exists(session_key))


async def _is_session_owner(db: AsyncSession, session_id: UUID, user_id: UUID) -> bool:
    ownership_query = text(
        """
        SELECT 1
        FROM sessions
        WHERE id = :session_id
          AND user_id = :user_id
          AND deleted_at IS NULL
        LIMIT 1
        """
    )
    found = await db.scalar(
        ownership_query,
        {
            "session_id": str(session_id),
            "user_id": str(user_id),
        },
    )
    return found is not None


async def get_current_user_ws(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_websocket_token(websocket)
    if token is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing authentication token",
        )
    try:
        return await get_current_user(db=db, token=token)
    except HTTPException as exc:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=str(exc.detail),
        ) from exc


@router.websocket("/ws/chat/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_ws),
) -> None:
    try:
        redis_client = _build_redis_client()
    except RuntimeError:
        raise WebSocketException(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Redis not configured",
        ) from None

    connection_id: str | None = None
    coordinator: StreamCoordinator | None = None
    stt_worker: WhisperInference | None = None
    llm_processor: LLMProcessor | None = None
    tts_processor: TTSProcessor | None = None
    audio_sequence = 0
    pipeline_started = False
    try:
        if not await _is_session_registered(redis_client, session_id):
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid session_id",
            )

        if not await _is_session_owner(db, session_id, current_user.id):
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Forbidden session access",
            )

        connection_id = f"{session_id}:{current_user.id}"
        await connection_manager.connect(connection_id, websocket)
        await connection_manager.send_json(
            connection_id,
            {
                "event": "handshake_ready",
                "message": "Connected. Waiting for 'START_AUDIO'.",
            },
        )

        stt_worker = await WhisperInference.get_instance(
            model_size=settings.stt_model_size,
            preferred_device="cuda",
            preferred_compute_type="float16",
            beam_size=settings.stt_beam_size,
        )
        llm_provider = settings.effective_llm_provider
        llm_api_key = (
            settings.effective_groq_api_key
            if llm_provider == "groq"
            else settings.gemini_api_key
        )
        llm_model = settings.groq_model if llm_provider == "groq" else settings.gemini_model
        if llm_api_key:
            llm_processor = LLMProcessor(
                api_key=llm_api_key,
                model_name=llm_model,
                provider=llm_provider,
                timeout_seconds=settings.effective_llm_timeout_seconds,
            )
        if settings.tts_enabled:
            tts_processor = TTSProcessor(
                edge_voice=settings.edge_tts_voice,
                phrase_min_chars=settings.tts_phrase_min_chars,
                queue_maxsize=settings.tts_queue_maxsize,
                chunk_ms=settings.tts_chunk_ms,
                local_fallback_enabled=settings.local_tts_enabled,
                piper_model_path=settings.piper_model_path,
                piper_sample_rate=settings.piper_sample_rate,
            )
        coordinator = StreamCoordinator(
            session_id=session_id,
            connection_id=connection_id,
            sender=connection_manager,
            stt_inference=stt_worker,
            llm_processor=llm_processor,
            tts_processor=tts_processor,
            tts_force_flush_timeout_ms=settings.tts_force_flush_timeout_ms,
            vad_energy_threshold_db=settings.vad_energy_threshold_db,
            vad_silence_timeout_ms=settings.vad_silence_timeout_ms,
            vad_pre_roll_ms=settings.vad_pre_roll_ms,
            stt_partial_emit_interval_ms=settings.stt_partial_emit_interval_ms,
            stt_partial_min_audio_ms=settings.stt_partial_min_audio_ms,
            stt_partial_window_ms=settings.stt_partial_window_ms,
            stt_final_min_audio_ms=settings.stt_final_min_audio_ms,
            stt_partial_beam_size=settings.stt_partial_beam_size,
            stt_final_beam_size=settings.stt_final_beam_size,
            stt_initial_prompt=settings.stt_initial_prompt,
        )

        while True:
            incoming = await websocket.receive()
            if incoming["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(incoming.get("code", 1000))

            text_payload = incoming.get("text")
            bytes_payload = incoming.get("bytes")

            if text_payload is not None:
                command = text_payload.strip().upper()
                if command == "START_AUDIO":
                    if coordinator is None:
                        raise WebSocketException(
                            code=status.WS_1011_INTERNAL_ERROR,
                            reason="Coordinator unavailable",
                        )
                    if not pipeline_started:
                        await coordinator.start()
                        pipeline_started = True
                    await connection_manager.send_json(
                        connection_id,
                        {
                            "event": "streaming_started",
                            "session_id": str(session_id),
                        },
                    )
                elif command == "SILENCE":
                    if coordinator is not None and pipeline_started:
                        await coordinator.notify_silence()
                elif command == "STOP_AUDIO":
                    if coordinator is not None and pipeline_started:
                        await coordinator.notify_silence()
                    await connection_manager.send_json(
                        connection_id,
                        {
                            "event": "streaming_stopped",
                            "session_id": str(session_id),
                        },
                    )
                else:
                    await connection_manager.send_json(
                        connection_id,
                        {
                            "event": "unknown_command",
                            "message": "Expected START_AUDIO, SILENCE, or STOP_AUDIO",
                        },
                    )
                continue

            if bytes_payload is not None:
                if not pipeline_started or coordinator is None:
                    await connection_manager.send_json(
                        connection_id,
                        {
                            "event": "pipeline_not_started",
                            "message": "Send START_AUDIO before audio chunks.",
                        },
                    )
                    continue
                await coordinator.notify_audio_chunk(audio_sequence, bytes_payload)
                audio_sequence += 1
                continue

            await connection_manager.send_json(
                connection_id,
                {
                    "event": "invalid_payload",
                    "message": "WebSocket message must contain text or binary data",
                },
            )

    except WebSocketDisconnect:
        logger.info("ws.disconnected session_id=%s", session_id)
    finally:
        if coordinator is not None:
            await coordinator.stop()

        if connection_id is not None:
            await connection_manager.disconnect(connection_id)

        await redis_client.aclose()

        if stt_worker is not None and connection_manager.active_count == 0:
            await stt_worker.unload_model()


# Backward-compatible alias for earlier imports/tests.
websocket_chat = websocket_endpoint
