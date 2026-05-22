from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from src.core.config import settings


logger = logging.getLogger(__name__)

GRADING_QUEUE_NAME = "luve.session.completed"
PUBLISH_TIMEOUT_SECONDS = 2.0


class RabbitMQSessionEventPublisher:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._connection: Any | None = None
        self._channel: Any | None = None
        self._aio_pika: Any | None = None
        self._declared_queues: set[str] = set()

    async def publish_json(
        self,
        *,
        queue_name: str,
        payload: dict[str, object],
    ) -> None:
        try:
            await self._publish_json(queue_name=queue_name, payload=payload)
        except Exception:
            await self._reset()
            await self._publish_json(queue_name=queue_name, payload=payload)

    async def close(self) -> None:
        async with self._lock:
            await self._close_unlocked()

    async def _publish_json(
        self,
        *,
        queue_name: str,
        payload: dict[str, object],
    ) -> None:
        async with self._lock:
            aio_pika, channel = await self._ensure_channel(queue_name)
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(payload).encode("utf-8"),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=queue_name,
            )

    async def _ensure_channel(self, queue_name: str) -> tuple[Any, Any]:
        aio_pika = self._get_aio_pika()
        if self._connection is None or self._is_closed(self._connection):
            self._connection = await aio_pika.connect_robust(_build_rabbitmq_url())
            self._channel = None
            self._declared_queues.clear()

        if self._channel is None or self._is_closed(self._channel):
            self._channel = await self._connection.channel()
            self._declared_queues.clear()

        if queue_name not in self._declared_queues:
            await self._channel.declare_queue(queue_name, durable=True)
            self._declared_queues.add(queue_name)

        return aio_pika, self._channel

    def _get_aio_pika(self) -> Any:
        if self._aio_pika is not None:
            return self._aio_pika
        try:
            import aio_pika
        except ImportError as exc:
            raise RuntimeError("aio-pika is required to publish session events") from exc
        self._aio_pika = aio_pika
        return self._aio_pika

    @staticmethod
    def _is_closed(resource: Any) -> bool:
        is_closed = getattr(resource, "is_closed", False)
        return bool(is_closed() if callable(is_closed) else is_closed)

    async def _reset(self) -> None:
        async with self._lock:
            await self._close_unlocked()

    async def _close_unlocked(self) -> None:
        channel = self._channel
        connection = self._connection
        self._channel = None
        self._connection = None
        self._declared_queues.clear()

        if channel is not None and not self._is_closed(channel):
            with contextlib.suppress(Exception):
                await channel.close()
        if connection is not None and not self._is_closed(connection):
            with contextlib.suppress(Exception):
                await connection.close()


_publisher = RabbitMQSessionEventPublisher()


async def publish_session_completed(session_id: str) -> bool:
    payload = {
        "event_type": "session.completed",
        "schema_version": "v1",
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        await asyncio.wait_for(
            _publisher.publish_json(queue_name=GRADING_QUEUE_NAME, payload=payload),
            timeout=PUBLISH_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception(
            "session.completed publish failed session_id=%s queue=%s",
            session_id,
            GRADING_QUEUE_NAME,
        )
        return False

    logger.info(
        "session.completed published session_id=%s queue=%s",
        session_id,
        GRADING_QUEUE_NAME,
    )
    return True


async def close_publisher() -> None:
    await _publisher.close()


async def _publish_json(
    *,
    queue_name: str,
    payload: dict[str, object],
) -> None:
    await _publisher.publish_json(queue_name=queue_name, payload=payload)


def _build_rabbitmq_url() -> str:
    host = settings.rabbitmq_host or "localhost"
    port = settings.rabbitmq_port or 5672
    user = quote(settings.rabbitmq_user or "guest", safe="")
    password = quote(settings.rabbitmq_pass or "guest", safe="")
    return f"amqp://{user}:{password}@{host}:{port}/"
