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
from src.schemas.session import (
    GradingRead,
    GradingStatusRead,
    SessionCreateRequest,
    SessionListItem,
    SessionListResponse,
    SessionRead,
)

logger = logging.getLogger(__name__)

SESSION_LIST_DEFAULT_LIMIT = 20
SESSION_LIST_MAX_LIMIT = 100
GRADING_STATUS_DEFAULT_MIN_STUDENT_WORDS = 15


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


async def list_user_sessions(
    db: AsyncSession,
    *,
    current_user: User,
    limit: int = SESSION_LIST_DEFAULT_LIMIT,
    offset: int = 0,
) -> SessionListResponse:
    safe_limit = min(max(limit, 1), SESSION_LIST_MAX_LIMIT)
    safe_offset = max(offset, 0)
    params = {
        "user_id": str(current_user.id),
        "limit": safe_limit,
        "offset": safe_offset,
    }

    total_result = await db.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM sessions
            WHERE user_id = :user_id
              AND deleted_at IS NULL
            """
        ),
        {"user_id": params["user_id"]},
    )
    total = int(total_result.scalar_one())

    rows = await db.execute(
        text(
            """
            SELECT
                id,
                lesson_id,
                status,
                total_tokens,
                manual_stops_count,
                started_at,
                ended_at
            FROM sessions
            WHERE user_id = :user_id
              AND deleted_at IS NULL
            ORDER BY started_at DESC, id DESC
            LIMIT :limit
            OFFSET :offset
            """
        ),
        params,
    )
    items = [SessionListItem(**session_row) for session_row in rows.mappings().all()]
    return SessionListResponse(
        items=items,
        limit=safe_limit,
        offset=safe_offset,
        total=total,
    )


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
                gr.status,
                gr.provider,
                gr.grader_version,
                gr.score_schema_version,
                gr.overall_score,
                gr.fluency_score,
                gr.grammar_score,
                gr.vocab_score,
                gr.pronunciation_score,
                gr.detailed_corrections,
                gr.skill_feedback_json AS skill_feedback,
                gr.input_quality_json AS input_quality,
                gr.ai_summary_feedback,
                gr.error_code,
                gr.error_message,
                gr.graded_at
            FROM grading_results gr
            WHERE gr.session_id = :session_id
              AND gr.status = 'graded'
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

    grading_data = dict(grading_row)
    grading_data["is_dev_preview"] = _is_dev_preview_grading(
        grading_data.get("provider"),
        grading_data.get("grader_version"),
    )
    return GradingRead(**grading_data)


def _is_dev_preview_grading(provider: Any, grader_version: Any) -> bool:
    normalized_provider = str(provider or "").strip().lower()
    normalized_grader_version = str(grader_version or "").strip().lower()

    if normalized_provider == "fake":
        return True
    if normalized_grader_version.startswith("fake_"):
        return True
    if normalized_grader_version == "legacy":
        return True
    if normalized_provider in {"", "unknown"}:
        return True

    return not (
        normalized_provider == "llm"
        and normalized_grader_version
    )


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
        if payload.get("grading_eligible") is False:
            continue
        text_value = str(payload.get("english_segment") or payload.get("text") or "").strip()
        if text_value:
            total += len(text_value.split())
    return total


def _get_min_student_words() -> int:
    try:
        return int(os.getenv("GRADING_MIN_STUDENT_WORDS", str(GRADING_STATUS_DEFAULT_MIN_STUDENT_WORDS)))
    except (ValueError, TypeError):
        return GRADING_STATUS_DEFAULT_MIN_STUDENT_WORDS


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
                gr.status AS grading_status,
                gr.error_code AS grading_error_code,
                gsl.skipped_reason,
                gsl.student_word_count AS skipped_student_word_count
            FROM sessions s
            LEFT JOIN grading_results gr ON gr.session_id = s.id
            LEFT JOIN grading_skip_log gsl ON gsl.session_id = s.id
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

    grading_status = status_row["grading_status"]
    if grading_status == "graded":
        return GradingStatusRead(session_id=session_id, status="graded")
    if grading_status == "processing":
        return GradingStatusRead(session_id=session_id, status="processing")
    if grading_status == "failed":
        return GradingStatusRead(
            session_id=session_id,
            status="failed",
            error_code=status_row["grading_error_code"],
        )

    skipped_reason = status_row["skipped_reason"]
    if skipped_reason is not None:
        return GradingStatusRead(
            session_id=session_id,
            status="insufficient_evidence",
            student_word_count=status_row["skipped_student_word_count"],
            reason=skipped_reason,
        )

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
