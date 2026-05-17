from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from urllib.parse import quote

from src.core.config import settings


logger = logging.getLogger(__name__)

GRADING_QUEUE_NAME = "luve.session.completed"
PUBLISH_TIMEOUT_SECONDS = 2.0


async def publish_session_completed(session_id: str) -> bool:
    payload = {
        "event_type": "session.completed",
        "schema_version": "v1",
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        await asyncio.wait_for(
            _publish_json(queue_name=GRADING_QUEUE_NAME, payload=payload),
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


async def _publish_json(
    *,
    queue_name: str,
    payload: dict[str, object],
) -> None:
    try:
        import aio_pika
    except ImportError as exc:
        raise RuntimeError("aio-pika is required to publish session events") from exc

    connection = await aio_pika.connect_robust(_build_rabbitmq_url())
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue(queue_name, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=queue.name,
        )


def _build_rabbitmq_url() -> str:
    host = settings.rabbitmq_host or "localhost"
    port = settings.rabbitmq_port or 5672
    user = quote(settings.rabbitmq_user or "guest", safe="")
    password = quote(settings.rabbitmq_pass or "guest", safe="")
    return f"amqp://{user}:{password}@{host}:{port}/"
