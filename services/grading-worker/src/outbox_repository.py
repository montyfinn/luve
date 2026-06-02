"""Transactional-outbox relay primitives for the grading worker (T7c-1).

asyncpg helpers that operate on a caller-supplied connection (so the caller owns
the transaction / `FOR UPDATE SKIP LOCKED` lock lifetime). These are pure DB
primitives — they do NOT publish to RabbitMQ and are NOT wired into the worker
runtime yet (the relay loop is a later T7c phase). Adding this module changes no
runtime behaviour.

Schema: matches infrastructure/db-migrations/0003_session_outbox.sql exactly —
columns payload, attempt_count, status, last_error, created_at/updated_at/
published_at. There is no payload_json / attempts / available_at.
"""
from __future__ import annotations

from typing import Any

# Bound the stored error text so a large traceback can't bloat the row.
_MAX_LAST_ERROR_LEN = 1000

_CLAIM_PENDING_SQL = """
    SELECT id, session_id, event_type, schema_version, payload, attempt_count
    FROM session_outbox
    WHERE status = 'pending'
    ORDER BY created_at
    LIMIT $1
    FOR UPDATE SKIP LOCKED
"""

_MARK_PUBLISHED_SQL = """
    UPDATE session_outbox
    SET status = 'published',
        published_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = $1
"""

# Atomic decision in SQL: the row goes 'failed' once this attempt reaches
# max_attempts, otherwise it stays 'pending' for the next poll. No available_at
# column exists, so there is no per-row backoff — retries are paced by the
# relay's poll interval, and the attempt cap prevents an unbounded poison loop.
_MARK_RETRY_OR_FAILED_SQL = """
    UPDATE session_outbox
    SET attempt_count = attempt_count + 1,
        last_error = $2,
        status = CASE
            WHEN attempt_count + 1 >= $3 THEN 'failed'
            ELSE 'pending'
        END,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = $1
"""


async def claim_pending_session_events(conn: Any, limit: int) -> list[Any]:
    """Claim up to ``limit`` pending outbox rows, oldest first.

    Uses ``FOR UPDATE SKIP LOCKED`` so concurrent relays never claim the same
    row; the caller must hold an open transaction until it has processed (and
    marked) the returned rows, then commit/rollback.
    """
    return list(await conn.fetch(_CLAIM_PENDING_SQL, limit))


async def mark_session_event_published(conn: Any, outbox_id: Any) -> None:
    """Mark a row published — call only after the broker confirmed the publish."""
    await conn.execute(_MARK_PUBLISHED_SQL, outbox_id)


async def mark_session_event_retry_or_failed(
    conn: Any,
    outbox_id: Any,
    error: str,
    max_attempts: int,
) -> None:
    """Increment attempt_count and record the (bounded) error.

    Stays ``pending`` until the incremented attempt count reaches
    ``max_attempts``, then flips to ``failed``.
    """
    bounded_error = (error or "")[:_MAX_LAST_ERROR_LEN]
    await conn.execute(_MARK_RETRY_OR_FAILED_SQL, outbox_id, bounded_error, max_attempts)
