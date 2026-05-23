from __future__ import annotations

import json
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.schemas.session import GradingRead, SessionCreateRequest, SessionRead


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
            JOIN sessions s ON s.id = gr.session_id
            WHERE gr.session_id = :session_id
              AND s.user_id = :user_id
              AND s.deleted_at IS NULL
            LIMIT 1
            """
        ),
        {
            "session_id": str(session_id),
            "user_id": str(user_id),
        },
    )
    grading_row = row.mappings().first()
    if grading_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grading result not ready",
        )
    return GradingRead(**grading_row)

