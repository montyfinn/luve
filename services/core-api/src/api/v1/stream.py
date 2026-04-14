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

    async def send_json(self, connection_id: str, payload: dict[str, str]) -> None:
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
async def websocket_chat(
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
                "message": "Connected. Waiting for 'Start Streaming'.",
            },
        )

        while True:
            command = (await websocket.receive_text()).strip().lower()
            if command == "start streaming":
                await connection_manager.send_json(
                    connection_id,
                    {
                        "event": "streaming_started",
                        "session_id": str(session_id),
                    },
                )
            else:
                await connection_manager.send_json(
                    connection_id,
                    {
                        "event": "unknown_command",
                        "message": "Expected command: Start Streaming",
                    },
                )
    except WebSocketDisconnect:
        logger.info("ws.disconnected session_id=%s", session_id)
    finally:
        if connection_id is not None:
            await connection_manager.disconnect(connection_id)
        await redis_client.aclose()
