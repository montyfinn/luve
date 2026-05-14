from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from pydantic import ValidationError

from src.contracts import SessionCompletedJob
from src.evaluation_input_builder import build_evaluation_input
from src.fake_grader import fake_grade
from src.grading_repository import GradingRepository


logger = logging.getLogger(__name__)
QUEUE_NAME = os.getenv("GRADING_QUEUE_NAME", "luve.session.completed")


async def process_session_completed_job(
    payload: dict[str, Any],
    *,
    repository: GradingRepository,
) -> None:
    job = SessionCompletedJob.model_validate(payload)
    session_row = await repository.fetch_session_row(job.session_id)
    if session_row is None:
        logger.warning("grading.session_missing session_id=%s", job.session_id)
        return

    evaluation_input = build_evaluation_input(session_row)
    if not evaluation_input.turns:
        logger.warning("grading.no_turns session_id=%s", job.session_id)

    result = fake_grade(evaluation_input)
    await repository.upsert_grading_result(result)
    logger.info(
        "grading.completed session_id=%s overall_score=%.2f fake_grader=true",
        job.session_id,
        result.overall_score,
    )


async def consume_forever() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    rabbitmq_url = _build_rabbitmq_url()
    repository = GradingRepository(database_url)

    try:
        import aio_pika
    except ImportError as exc:
        raise RuntimeError("aio-pika is required to consume RabbitMQ jobs") from exc

    connection = await aio_pika.connect_robust(rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process(requeue=False):
                    try:
                        payload = json.loads(message.body.decode("utf-8"))
                        await process_session_completed_job(
                            payload,
                            repository=repository,
                        )
                    except (json.JSONDecodeError, ValidationError):
                        logger.exception("grading.invalid_message")
                    except Exception:
                        logger.exception("grading.job_failed")
                        raise


def _build_rabbitmq_url() -> str:
    host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    port = os.getenv("RABBITMQ_PORT", "5672")
    user = os.getenv("RABBITMQ_USER", "guest")
    password = os.getenv("RABBITMQ_PASS", "guest")
    return f"amqp://{user}:{password}@{host}:{port}/"


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(consume_forever())


if __name__ == "__main__":
    main()
