"""Transactional outbox SQL primitives (T7a).

This helper operates on a caller-supplied SQLAlchemy ``AsyncSession`` and never
commits on its own. That is deliberate: ``enqueue_session_event`` is meant to be
called inside the same transaction that writes the session state, so the outbox
row becomes durable *iff* that state change commits — closing the publish-side
dual-write gap. The caller owns commit/rollback.

T7a scope: schema + the enqueue (write) primitive only. The relay-side primitives
(claim pending rows, mark published, mark failed/retry) are deferred to T7c, where
they will be implemented in the driver/location the relay actually runs in
(core-api SQLAlchemy vs grading-worker raw asyncpg) once that is decided. Nothing
here publishes to RabbitMQ.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def enqueue_session_event(
    db: AsyncSession,
    *,
    session_id: str,
    event_type: str,
    payload: dict[str, Any],
    schema_version: str = "v1",
) -> None:
    """Insert a pending outbox row on the caller's transaction.

    Idempotent on ``UNIQUE(session_id, event_type)``: a duplicate enqueue is a
    no-op (``ON CONFLICT DO NOTHING``). Does NOT commit.
    """
    await db.execute(
        text(
            """
            INSERT INTO session_outbox (session_id, event_type, schema_version, payload)
            VALUES (:session_id, :event_type, :schema_version, CAST(:payload AS jsonb))
            ON CONFLICT (session_id, event_type) DO NOTHING
            """
        ),
        {
            "session_id": session_id,
            "event_type": event_type,
            "schema_version": schema_version,
            "payload": json.dumps(payload),
        },
    )
