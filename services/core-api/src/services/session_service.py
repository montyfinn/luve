from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.schemas.session import GradingRead, GradingStatusRead, SessionCreateRequest, SessionRead

logger = logging.getLogger(__name__)


async def create_webrtc_session(
    db: AsyncSession,
    *,
    current_user: User,
    payload: SessionCreateRequest,
) -> SessionRead:
    lesson_id = payload.lesson_id
    if lesson_id is not None:
        lesson_exists = await db.scalar(
            text(
                """
                SELECT 1
                FROM lessons
                WHERE id = :lesson_id
                  AND deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"lesson_id": str(lesson_id)},
        )
        if lesson_exists is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lesson not found",
            )

    metadata = {
        "transport": "webrtc_ten",
        "created_by": "core_api",
        **payload.metadata,
    }

    row = await db.execute(
        text(
            """
            INSERT INTO sessions (user_id, lesson_id, status, metadata)
            VALUES (
                :user_id,
                :lesson_id,
                'ready',
                CAST(:metadata AS jsonb)
            )
            RETURNING
                id,
                user_id,
                lesson_id,
                status,
                metadata,
                raw_backup_json,
                total_tokens,
                manual_stops_count,
                started_at,
                ended_at
            """
        ),
        {
            "user_id": str(current_user.id),
            "lesson_id": str(lesson_id) if lesson_id is not None else None,
            "metadata": json.dumps(metadata),
        },
    )
    await db.commit()
    session_row = row.mappings().one()
    return SessionRead(**session_row)


async def get_user_session(
    db: AsyncSession,
    *,
    session_id: UUID,
    current_user: User,
) -> SessionRead:
    row = await db.execute(
        text(
            """
            SELECT
                id,
                user_id,
                lesson_id,
                status,
                metadata,
                raw_backup_json,
                total_tokens,
                manual_stops_count,
                started_at,
                ended_at
            FROM sessions
            WHERE id = :session_id
              AND user_id = :user_id
              AND deleted_at IS NULL
            LIMIT 1
            """
        ),
        {
            "session_id": str(session_id),
            "user_id": str(current_user.id),
        },
    )
    session_row = row.mappings().first()
    if session_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return SessionRead(**session_row)


async def get_session_grading(
    db: AsyncSession,
    *,
    session_id: UUID,
    user_id: UUID,
) -> GradingRead:
    # Check if the session exists and check its owner
    session_row = await db.execute(
        text(
            """
            SELECT user_id
            FROM sessions
            WHERE id = :session_id
              AND deleted_at IS NULL
            LIMIT 1
            """
        ),
        {"session_id": str(session_id)},
    )
    s_row = session_row.mappings().first()
    if s_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if s_row["user_id"] != str(user_id) and s_row["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This session is not owned by the current account.",
        )

    row = await db.execute(
        text(
            """
            SELECT
                gr.session_id,
                gr.overall_score,
                gr.fluency_score,
                gr.grammar_score,
                gr.vocab_score,
                gr.detailed_corrections,
                gr.ai_summary_feedback,
                gr.graded_at
            FROM grading_results gr
            WHERE gr.session_id = :session_id
            LIMIT 1
            """
        ),
        {"session_id": str(session_id)},
    )
    grading_row = row.mappings().first()
    if grading_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grading result not ready",
        )
    return GradingRead(**grading_row)


def _parse_raw_backup_events(raw_backup_json: Any) -> list[Any]:
    if isinstance(raw_backup_json, list):
        return raw_backup_json
    if isinstance(raw_backup_json, str):
        try:
            parsed = json.loads(raw_backup_json)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _compute_student_word_count(raw_backup_json: Any) -> int | None:
    if raw_backup_json is None:
        return None
    total = 0
    for event in _parse_raw_backup_events(raw_backup_json):
        if isinstance(event, str):
            try:
                event = json.loads(event)
            except (json.JSONDecodeError, ValueError):
                continue
        if not isinstance(event, Mapping):
            continue
        if (event.get("type") or event.get("event")) != "USER_TURN":
            continue
        payload = event.get("payload", {})
        if not isinstance(payload, Mapping):
            payload = {}
        text_value = str(payload.get("text") or "").strip()
        if text_value:
            total += len(text_value.split())
    return total


def _get_min_student_words() -> int:
    try:
        return int(os.getenv("GRADING_MIN_STUDENT_WORDS", "25"))
    except (ValueError, TypeError):
        return 25


async def get_session_grading_status(
    db: AsyncSession,
    *,
    session_id: UUID,
    user_id: UUID,
) -> GradingStatusRead:
    row = await db.execute(
        text(
            """
            SELECT
                s.user_id,
                s.raw_backup_json,
                (gr.session_id IS NOT NULL) AS has_grading
            FROM sessions s
            LEFT JOIN grading_results gr ON gr.session_id = s.id
            WHERE s.id = :session_id
              AND s.deleted_at IS NULL
            LIMIT 1
            """
        ),
        {"session_id": str(session_id)},
    )
    status_row = row.mappings().first()
    if status_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if status_row["user_id"] != str(user_id) and status_row["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This session is not owned by the current account.",
        )

    if status_row["has_grading"]:
        return GradingStatusRead(session_id=session_id, status="graded")

    word_count = _compute_student_word_count(status_row["raw_backup_json"])
    min_words = _get_min_student_words()

    if word_count is not None and word_count < min_words:
        inferred = "insufficient_evidence"
    else:
        inferred = "pending"

    logger.info(
        "grading.status_inferred session_id=%s status=%s student_word_count=%s",
        session_id,
        inferred,
        word_count,
    )
    return GradingStatusRead(
        session_id=session_id,
        status=inferred,
        student_word_count=word_count,
    )

