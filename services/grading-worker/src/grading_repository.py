from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import asyncpg

from src.contracts import GradingResult


_REQUIRED_GRADING_RESULTS_COLUMNS = frozenset(
    {
        "session_id",
        "status",
        "provider",
        "grader_version",
        "score_schema_version",
        "overall_score",
        "fluency_score",
        "grammar_score",
        "vocab_score",
        "pronunciation_score",
        "detailed_corrections",
        "ai_summary_feedback",
        "skill_feedback_json",
        "input_quality_json",
        "error_code",
        "error_message",
        "attempt_count",
        "graded_at",
        "updated_at",
    }
)


class GradingRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise ValueError("database_url must not be empty")
        self._database_url = _normalize_asyncpg_database_url(database_url.strip())
        self._pool: asyncpg.Pool | None = None

    async def open(self, *, min_size: int = 1, max_size: int = 4) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            self._database_url,
            min_size=min_size,
            max_size=max_size,
        )

    async def close(self) -> None:
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None

    @asynccontextmanager
    async def _acquire(self):
        if self._pool is not None:
            async with self._pool.acquire() as connection:
                yield connection
            return

        connection = await asyncpg.connect(self._database_url)
        try:
            yield connection
        finally:
            await connection.close()

    async def fetch_session_row(self, session_id: UUID) -> Mapping[str, Any] | None:
        async with self._acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT id, user_id, lesson_id, status, raw_backup_json, started_at, ended_at
                FROM sessions
                WHERE id = $1
                  AND deleted_at IS NULL
                LIMIT 1
                """,
                session_id,
            )
            return dict(row) if row is not None else None

    async def assert_schema_ready(self) -> None:
        """Fail fast when the worker is started before grading migrations."""

        async with self._acquire() as connection:
            skip_log_exists = await connection.fetchval(
                "SELECT to_regclass('public.grading_skip_log') IS NOT NULL"
            )
            rows = await connection.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'grading_results'
                  AND column_name = ANY($1::text[])
                """,
                list(_REQUIRED_GRADING_RESULTS_COLUMNS),
            )

        present_columns = {str(row["column_name"]) for row in rows}
        missing_parts: list[str] = []
        if not skip_log_exists:
            missing_parts.append("table public.grading_skip_log")

        missing_columns = sorted(_REQUIRED_GRADING_RESULTS_COLUMNS - present_columns)
        if missing_columns:
            missing_parts.append(
                "columns public.grading_results."
                + ", public.grading_results.".join(missing_columns)
            )

        if missing_parts:
            raise RuntimeError(
                "grading schema is not ready; apply "
                "infrastructure/db-migrations/0001_grading_skip_log.sql and "
                "infrastructure/db-migrations/0002_grading_results_production_fields.sql "
                "before starting the grading worker. Missing: "
                + "; ".join(missing_parts)
            )

    async def log_grading_skip(
        self,
        session_id: UUID,
        reason: str,
        source: str = "worker",
        student_word_count: int | None = None,
        min_words_threshold: int | None = None,
    ) -> None:
        async with self._acquire() as connection:
            await connection.execute(
                """
                INSERT INTO grading_skip_log (
                    session_id,
                    skipped_reason,
                    source,
                    student_word_count,
                    min_words_threshold
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (session_id) DO UPDATE SET
                    skipped_reason      = EXCLUDED.skipped_reason,
                    source              = EXCLUDED.source,
                    student_word_count  = EXCLUDED.student_word_count,
                    min_words_threshold = EXCLUDED.min_words_threshold,
                    updated_at          = CURRENT_TIMESTAMP
                """,
                session_id,
                reason,
                source,
                student_word_count,
                min_words_threshold,
            )

    async def mark_grading_processing(
        self,
        *,
        session_id: UUID,
        provider: str,
    ) -> bool:
        async with self._acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO grading_results (
                    session_id,
                    status,
                    provider,
                    attempt_count,
                    skill_feedback_json,
                    input_quality_json,
                    detailed_corrections,
                    ai_summary_feedback
                )
                VALUES ($1, 'processing', $2, 1, '[]'::jsonb, '{}'::jsonb, '[]'::jsonb, '')
                ON CONFLICT (session_id) DO UPDATE SET
                    status = 'processing',
                    provider = EXCLUDED.provider,
                    attempt_count = grading_results.attempt_count + 1,
                    error_code = NULL,
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE grading_results.status <> 'graded'
                RETURNING session_id
                """,
                session_id,
                provider,
            )
            return row is not None

    async def mark_grading_failed(
        self,
        *,
        session_id: UUID,
        provider: str,
        error_code: str,
        error_message: str,
    ) -> None:
        async with self._acquire() as connection:
            await connection.execute(
                """
                INSERT INTO grading_results (
                    session_id,
                    status,
                    provider,
                    attempt_count,
                    skill_feedback_json,
                    input_quality_json,
                    detailed_corrections,
                    ai_summary_feedback,
                    error_code,
                    error_message
                )
                VALUES ($1, 'failed', $2, 1, '[]'::jsonb, '{}'::jsonb, '[]'::jsonb, '', $3, $4)
                ON CONFLICT (session_id) DO UPDATE SET
                    status = 'failed',
                    provider = EXCLUDED.provider,
                    error_code = EXCLUDED.error_code,
                    error_message = EXCLUDED.error_message,
                    updated_at = CURRENT_TIMESTAMP
                WHERE grading_results.status <> 'graded'
                """,
                session_id,
                provider,
                error_code,
                error_message[:500],
            )

    async def upsert_grading_result(self, result: GradingResult) -> None:
        """Persist fake/real grading output using the current schema.

        Stores the final grading fields plus structured skill feedback. Raw
        transcript/audio content must stay out of this row.
        """

        async with self._acquire() as connection:
            await connection.execute(
                """
                INSERT INTO grading_results (
                    session_id,
                    status,
                    provider,
                    grader_version,
                    score_schema_version,
                    overall_score,
                    fluency_score,
                    grammar_score,
                    vocab_score,
                    pronunciation_score,
                    detailed_corrections,
                    ai_summary_feedback,
                    skill_feedback_json,
                    input_quality_json,
                    error_code,
                    error_message
                )
                VALUES (
                    $1,
                    'graded',
                    $2,
                    $3,
                    $4,
                    $5,
                    $6,
                    $7,
                    $8,
                    $9,
                    $10::jsonb,
                    $11,
                    $12::jsonb,
                    $13::jsonb,
                    NULL,
                    NULL
                )
                ON CONFLICT (session_id) DO UPDATE SET
                    status                = 'graded',
                    provider              = EXCLUDED.provider,
                    grader_version        = EXCLUDED.grader_version,
                    score_schema_version  = EXCLUDED.score_schema_version,
                    overall_score         = EXCLUDED.overall_score,
                    fluency_score         = EXCLUDED.fluency_score,
                    grammar_score         = EXCLUDED.grammar_score,
                    vocab_score           = EXCLUDED.vocab_score,
                    pronunciation_score   = EXCLUDED.pronunciation_score,
                    detailed_corrections  = EXCLUDED.detailed_corrections,
                    ai_summary_feedback   = EXCLUDED.ai_summary_feedback,
                    skill_feedback_json   = EXCLUDED.skill_feedback_json,
                    input_quality_json    = EXCLUDED.input_quality_json,
                    error_code            = NULL,
                    error_message         = NULL,
                    graded_at             = CURRENT_TIMESTAMP,
                    updated_at            = CURRENT_TIMESTAMP
                """,
                result.session_id,
                result.provider,
                result.grader_version,
                result.score_schema_version,
                result.overall_score,
                result.fluency_score,
                result.grammar_score,
                result.vocab_score,
                result.pronunciation_score,
                json.dumps(result.detailed_corrections),
                result.ai_summary_feedback,
                json.dumps([item.model_dump(mode="json") for item in result.skill_feedback]),
                json.dumps(result.input_quality),
            )


def _normalize_asyncpg_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return database_url
