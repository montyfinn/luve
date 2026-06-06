from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from typing import Any
from urllib.parse import quote

from pydantic import ValidationError

from src.contracts import GradingResult, SessionCompletedJob
from src.evaluation_input_builder import build_evaluation_input
from src.fake_grader import fake_grade
from src.grading_repository import GradingRepository
from src.llm_grader import LLMGraderError, llm_grade_with_client
from src.outbox_repository import (
    claim_pending_session_events,
    mark_session_event_published,
    mark_session_event_retry_or_failed,
)
from src.session_eligibility import DEFAULT_MIN_STUDENT_WORDS, evaluate_grading_eligibility


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


def _get_fake_fallback_enabled() -> bool:
    value = os.getenv("GRADING_FAKE_FALLBACK", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _get_min_student_words() -> int:
    raw = os.getenv("GRADING_MIN_STUDENT_WORDS", str(DEFAULT_MIN_STUDENT_WORDS))
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "grading.invalid_min_student_words value=%r using_default=%s",
            raw,
            DEFAULT_MIN_STUDENT_WORDS,
        )
        return DEFAULT_MIN_STUDENT_WORDS
    return max(parsed, 0)


def _get_max_attempts() -> int:
    raw = os.getenv("GRADING_MAX_ATTEMPTS", "2")
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        logger.warning("grading.invalid_max_attempts value=%r using_default=2", raw)
        return 2
    return max(parsed, 1)


def _get_retry_delay_seconds() -> float:
    raw = os.getenv("GRADING_RETRY_DELAY_SECONDS", "1.0")
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        logger.warning("grading.invalid_retry_delay_seconds value=%r using_default=1.0", raw)
        return 1.0
    return max(parsed, 0.0)


def _get_requeue_backoff_seconds() -> float:
    # Fixed delay before nack(requeue=True) when terminal state cannot be
    # persisted (DB down), to avoid a tight redeliver loop. 0 disables.
    raw = os.getenv("GRADING_REQUEUE_BACKOFF_SECONDS", "5.0")
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        logger.warning("grading.invalid_requeue_backoff_seconds value=%r using_default=5.0", raw)
        return 5.0
    return max(parsed, 0.0)


def _get_outbox_relay_enabled() -> bool:
    # T7c-2: default OFF. The relay only runs when explicitly enabled.
    return os.getenv("OUTBOX_RELAY_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _get_outbox_relay_poll_interval_seconds() -> float:
    raw = os.getenv("OUTBOX_RELAY_POLL_INTERVAL_SECONDS", "5.0")
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        logger.warning("outbox_relay.invalid_poll_interval value=%r using_default=5.0", raw)
        return 5.0
    return max(parsed, 0.5)


def _get_outbox_relay_batch_size() -> int:
    raw = os.getenv("OUTBOX_RELAY_BATCH_SIZE", "20")
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        logger.warning("outbox_relay.invalid_batch_size value=%r using_default=20", raw)
        return 20
    return max(parsed, 1)


def _get_outbox_relay_max_attempts() -> int:
    raw = os.getenv("OUTBOX_RELAY_MAX_ATTEMPTS", "5")
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        logger.warning("outbox_relay.invalid_max_attempts value=%r using_default=5", raw)
        return 5
    return max(parsed, 1)


def _get_outbox_relay_publish_timeout_seconds() -> float:
    raw = os.getenv("OUTBOX_RELAY_PUBLISH_TIMEOUT_SECONDS", "10.0")
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        logger.warning("outbox_relay.invalid_publish_timeout value=%r using_default=10.0", raw)
        return 10.0
    return max(parsed, 1.0)


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
    payload: Any,
    *,
    repository: GradingRepository,
) -> None:
    job = SessionCompletedJob.model_validate(payload)
    session_row = await repository.fetch_session_row(job.session_id)
    if session_row is None:
        logger.warning("grading.session_missing session_id=%s", job.session_id)
        return

    min_student_words = _get_min_student_words()
    eligibility = evaluate_grading_eligibility(
        session_row["raw_backup_json"],
        min_student_words=min_student_words,
    )
    if not eligibility.eligible:
        logger.warning(
            "grading.session_ineligible session_id=%s reason=%s student_word_count=%s min_words_threshold=%s",
            job.session_id,
            eligibility.reason,
            eligibility.student_word_count,
            min_student_words if eligibility.reason == "insufficient_words" else None,
        )
        await repository.log_grading_skip(
            session_id=job.session_id,
            reason=eligibility.reason,
            source="worker",
            student_word_count=eligibility.student_word_count,
            min_words_threshold=_min_words_threshold_for_skip(
                eligibility.reason,
                min_student_words,
            ),
        )
        return

    evaluation_input = build_evaluation_input(session_row)
    provider = _get_grading_provider()
    if not await _mark_grading_processing_if_supported(
        repository,
        session_id=job.session_id,
        provider=provider,
    ):
        logger.info("grading.already_graded session_id=%s", job.session_id)
        return
    result: GradingResult

    if provider == "llm":
        try:
            client = _build_grader_client()
            result = await llm_grade_with_client(evaluation_input, client)
            result.input_quality = dict(evaluation_input.quality_signals)
            result.detailed_corrections = [
                {"type": "grader_info", "grader_version": result.grader_version, "message": ""},
                *result.detailed_corrections,
            ]
        except Exception as exc:
            if _get_fake_fallback_enabled():
                logger.warning(
                    "grading.llm_failed_fallback session_id=%s error=%s: %s",
                    job.session_id,
                    type(exc).__name__,
                    exc,
                )
                result = fake_grade(evaluation_input)
            else:
                await _mark_grading_failed_if_supported(
                    repository=repository,
                    session_id=job.session_id,
                    provider=provider,
                    exc=exc,
                )
                logger.error(
                    "grading.llm_failed_no_fallback session_id=%s error=%s: %s",
                    job.session_id,
                    type(exc).__name__,
                    exc,
                )
                raise
    else:
        result = fake_grade(evaluation_input)

    if not result.input_quality:
        result.input_quality = dict(evaluation_input.quality_signals)
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
    await repository.open(
        max_size=int(os.getenv("GRADING_DB_POOL_SIZE", "4")),
    )

    try:
        await repository.assert_schema_ready()

        try:
            import aio_pika
        except ImportError as exc:
            raise RuntimeError("aio-pika is required to consume RabbitMQ jobs") from exc

        connection = await aio_pika.connect_robust(rabbitmq_url)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=1)
            queue = await channel.declare_queue(QUEUE_NAME, durable=True)

            logger.info("worker.ready queue=%s prefetch_count=%s", QUEUE_NAME, 1)

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    await _handle_queue_message(message, repository=repository)
    finally:
        await repository.close()


def _outbox_payload_to_body(payload: Any) -> bytes:
    # session_outbox.payload is JSONB. asyncpg returns it as a JSON string (no
    # codec on the relay pool); publish it as-is. Handle dict/bytes defensively.
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload).encode("utf-8")


async def _publish_outbox_message(channel: Any, body: bytes, *, timeout: float) -> None:
    # First RabbitMQ publisher in the worker. Mirrors core-api's
    # session_event_publisher: persistent message to the default exchange,
    # routing_key = queue name. aio-pika channels enable publisher confirms by
    # default, so publish() returns only after the broker acks; the timeout
    # bounds how long an outbox row lock can be held during a stuck publish.
    import aio_pika

    message = aio_pika.Message(
        body=body,
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await asyncio.wait_for(
        channel.default_exchange.publish(message, routing_key=QUEUE_NAME),
        timeout=timeout,
    )


async def _relay_drain_once(
    pool: Any,
    channel: Any,
    *,
    batch_size: int,
    max_attempts: int,
    publish_timeout: float,
) -> int:
    # Claim + publish + mark all inside ONE transaction so the FOR UPDATE
    # SKIP LOCKED row locks are held until the marks commit (T7c-1 contract).
    published = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await claim_pending_session_events(conn, batch_size)
            for row in rows:
                outbox_id = row["id"]
                body = _outbox_payload_to_body(row["payload"])
                try:
                    await _publish_outbox_message(channel, body, timeout=publish_timeout)
                    await mark_session_event_published(conn, outbox_id)
                    published += 1
                except Exception as exc:
                    logger.warning(
                        "outbox_relay.publish_failed outbox_id=%s error=%s",
                        outbox_id,
                        type(exc).__name__,
                    )
                    await mark_session_event_retry_or_failed(
                        conn, outbox_id, f"{type(exc).__name__}: {exc}", max_attempts
                    )
    return published


async def relay_forever() -> None:
    import aio_pika
    import asyncpg

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    poll_interval = _get_outbox_relay_poll_interval_seconds()
    batch_size = _get_outbox_relay_batch_size()
    max_attempts = _get_outbox_relay_max_attempts()
    publish_timeout = _get_outbox_relay_publish_timeout_seconds()

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
    connection = await aio_pika.connect_robust(_build_rabbitmq_url())
    try:
        channel = await connection.channel()
        # Ensure the durable queue exists (idempotent); does not touch the DLX/DLQ.
        await channel.declare_queue(QUEUE_NAME, durable=True)
        logger.info(
            "outbox_relay.ready queue=%s poll_interval_s=%s batch_size=%s max_attempts=%s",
            QUEUE_NAME,
            poll_interval,
            batch_size,
            max_attempts,
        )
        while True:
            try:
                published = await _relay_drain_once(
                    pool,
                    channel,
                    batch_size=batch_size,
                    max_attempts=max_attempts,
                    publish_timeout=publish_timeout,
                )
                if published:
                    logger.info("outbox_relay.drained published=%s", published)
            except Exception:
                logger.exception("outbox_relay.cycle_failed")
            await asyncio.sleep(poll_interval)
    finally:
        with contextlib.suppress(Exception):
            await connection.close()
        with contextlib.suppress(Exception):
            await pool.close()


async def _process_payload_with_retries(
    payload: Any,
    *,
    repository: GradingRepository,
) -> None:
    max_attempts = _get_max_attempts()
    retry_delay = _get_retry_delay_seconds()
    session_id = _payload_session_id_for_logging(payload)
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            await process_session_completed_job(payload, repository=repository)
            return
        except ValidationError:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "grading.job_attempt_failed session_id=%s attempt=%s max_attempts=%s error=%s: %s",
                session_id,
                attempt,
                max_attempts,
                type(exc).__name__,
                exc,
            )
            if attempt < max_attempts and retry_delay > 0:
                await asyncio.sleep(retry_delay * attempt)

    if last_exc is None:
        return
    if session_id is None:
        raise last_exc

    try:
        await repository.mark_grading_failed(
            session_id=session_id,
            provider=_get_grading_provider(),
            error_code=type(last_exc).__name__,
            error_message=str(last_exc),
        )
    except Exception as mark_exc:
        logger.exception(
            "grading.mark_failed_after_retries_failed session_id=%s",
            session_id,
        )
        raise mark_exc from last_exc


async def _handle_queue_message(
    message: Any,
    *,
    repository: GradingRepository,
) -> None:
    try:
        payload = json.loads(message.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.exception("grading.invalid_message")
        await message.reject(requeue=False)
        return

    try:
        await _process_payload_with_retries(payload, repository=repository)
    except ValidationError:
        logger.exception("grading.invalid_message")
        await message.reject(requeue=False)
    except Exception:
        logger.exception("grading.job_requeued")
        backoff = _get_requeue_backoff_seconds()
        if backoff > 0:
            await asyncio.sleep(backoff)
        await message.nack(requeue=True)
    else:
        await message.ack()


async def _mark_grading_processing_if_supported(
    repository: GradingRepository,
    *,
    session_id: Any,
    provider: str,
) -> bool:
    method = getattr(repository, "mark_grading_processing", None)
    if method is None:
        return True

    result = await method(
        session_id=session_id,
        provider=provider,
    )
    return True if result is None else bool(result)


async def _mark_grading_failed_if_supported(
    *,
    repository: GradingRepository,
    session_id: Any,
    provider: str,
    exc: Exception,
) -> None:
    method = getattr(repository, "mark_grading_failed", None)
    if method is None:
        return
    try:
        await method(
            session_id=session_id,
            provider=provider,
            error_code=type(exc).__name__,
            error_message=str(exc),
        )
    except Exception as mark_exc:
        logger.warning(
            "grading.mark_failed_failed session_id=%s error=%s: %s",
            session_id,
            type(mark_exc).__name__,
            mark_exc,
        )


def _payload_session_id_for_logging(payload: Any) -> Any | None:
    try:
        return SessionCompletedJob.model_validate(payload).session_id
    except ValidationError:
        return None


def _min_words_threshold_for_skip(reason: str, min_student_words: int) -> int | None:
    if reason == "insufficient_words":
        return min_student_words
    return None


def _build_rabbitmq_url() -> str:
    host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    port = os.getenv("RABBITMQ_PORT", "5672")
    user = os.getenv("RABBITMQ_USER", "guest")
    password = os.getenv("RABBITMQ_PASS", "guest")
    return f"amqp://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/"


async def _run_consumer_with_relay() -> None:
    await asyncio.gather(consume_forever(), relay_forever())


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    if _get_outbox_relay_enabled():
        logger.info("outbox_relay.enabled=true — starting consumer + relay")
        asyncio.run(_run_consumer_with_relay())
    else:
        asyncio.run(consume_forever())


if __name__ == "__main__":
    main()
