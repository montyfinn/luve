from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import asyncpg

from src.contracts import GradingResult


class GradingRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise ValueError("database_url must not be empty")
        self._database_url = _normalize_asyncpg_database_url(database_url.strip())

    async def fetch_session_row(self, session_id: UUID) -> Mapping[str, Any] | None:
        connection = await asyncpg.connect(self._database_url)
        try:
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
        finally:
            await connection.close()

    async def upsert_grading_result(self, result: GradingResult) -> None:
        """Persist fake/real grading output using the current schema.

        The current schema has no columns for evaluation_input_json or grading
        status, so this stores only the final grading fields plus details.
        """

        connection = await asyncpg.connect(self._database_url)
        try:
            await connection.execute(
                """
                INSERT INTO grading_results (
                    session_id,
                    overall_score,
                    fluency_score,
                    grammar_score,
                    vocab_score,
                    detailed_corrections,
                    ai_summary_feedback
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                ON CONFLICT (session_id) DO UPDATE SET
                    overall_score = EXCLUDED.overall_score,
                    fluency_score = EXCLUDED.fluency_score,
                    grammar_score = EXCLUDED.grammar_score,
                    vocab_score = EXCLUDED.vocab_score,
                    detailed_corrections = EXCLUDED.detailed_corrections,
                    ai_summary_feedback = EXCLUDED.ai_summary_feedback,
                    graded_at = CURRENT_TIMESTAMP
                """,
                result.session_id,
                result.overall_score,
                result.fluency_score,
                result.grammar_score,
                result.vocab_score,
                json.dumps(result.detailed_corrections),
                result.ai_summary_feedback,
            )
        finally:
            await connection.close()


def _normalize_asyncpg_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return database_url
