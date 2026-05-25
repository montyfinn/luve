from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from pydantic import ValidationError

from src.contracts import GradingResult, SessionCompletedJob
from src.evaluation_input_builder import build_evaluation_input
from src.fake_grader import fake_grade
from src.grading_repository import GradingRepository
from src.llm_grader import LLMGraderError, llm_grade_with_client


logger = logging.getLogger(__name__)
QUEUE_NAME = os.getenv("GRADING_QUEUE_NAME", "luve.session.completed")


def _get_grading_provider() -> str:
    raw = os.getenv("GRADING_PROVIDER", "fake").strip().lower()
    if raw not in ("fake", "llm"):
        logger.warning(
            "grading.unknown_provider value=%r — falling back to fake", raw
        )
        return "fake"
    return raw


def _build_grader_client() -> Any:
    from src.grading_provider_client import GroqClient
    llm_provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if llm_provider != "groq":
        raise LLMGraderError(
            f"Unsupported LLM_PROVIDER for grading worker: {llm_provider!r}"
        )
    api_key = os.getenv("GROQCLOUD_API_KEY", "").strip()
    if not api_key:
        raise LLMGraderError("GROQCLOUD_API_KEY is not set — cannot use llm provider")
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
    raw_timeout = os.getenv("GROQ_TIMEOUT_SECONDS") or os.getenv("LLM_TIMEOUT_SECONDS", "20.0")
    try:
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise LLMGraderError(
            f"GROQ_TIMEOUT_SECONDS is not a valid float: {raw_timeout!r}"
        ) from exc
    return GroqClient(api_key=api_key, model=model, timeout_seconds=timeout)


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
    if not evaluation_input.quality_signals.get("has_student_turns"):
        logger.warning("grading.no_user_turns_skip session_id=%s", job.session_id)
        return

    min_student_words = int(os.getenv("GRADING_MIN_STUDENT_WORDS", "25"))
    student_word_count = int(evaluation_input.quality_signals.get("student_word_count", 0) or 0)
    if student_word_count < min_student_words:
        logger.warning(
            "grading.skipped_insufficient_evidence session_id=%s user_turn_count=%d student_word_count=%d min_student_words=%d",
            job.session_id,
            int(evaluation_input.quality_signals.get("user_turn_count", 0) or 0),
            student_word_count,
            min_student_words,
        )
        return

    provider = _get_grading_provider()
    result: GradingResult

    if provider == "llm":
        try:
            client = _build_grader_client()
            result = await llm_grade_with_client(evaluation_input, client)
            result.detailed_corrections = [
                {"type": "grader_info", "grader_version": result.grader_version, "message": ""},
                *result.detailed_corrections,
            ]
        except Exception as exc:
            logger.warning(
                "grading.llm_failed_fallback session_id=%s error=%s: %s",
                job.session_id,
                type(exc).__name__,
                exc,
            )
            result = fake_grade(evaluation_input)
    else:
        result = fake_grade(evaluation_input)

    await repository.upsert_grading_result(result)
    logger.info(
        "grading.completed session_id=%s overall_score=%.2f provider_requested=%s grader_version=%s",
        job.session_id,
        result.overall_score,
        provider,
        result.grader_version,
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
