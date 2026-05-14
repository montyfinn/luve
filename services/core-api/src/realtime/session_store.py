from __future__ import annotations

import json
from typing import Any, Protocol

from sqlalchemy import text

from src.core.db import AsyncSessionLocal


class SessionStoreError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SessionStore(Protocol):
    async def reserve_persisted_session(self, session_id: str) -> None: ...

    async def mark_session_status(self, session_id: str, status_value: str) -> None: ...

    async def get_session_owner(self, session_id: str) -> str: ...

    async def persist_event_log(
        self,
        session_id: str,
        event_log: list[dict[str, object]],
    ) -> None: ...


class SQLSessionStore:
    async def reserve_persisted_session(self, session_id: str) -> None:
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text(
                    """
                    SELECT status
                    FROM sessions
                    WHERE id = :session_id
                      AND deleted_at IS NULL
                    LIMIT 1
                    """
                ),
                {"session_id": session_id},
            )
            session_row = row.mappings().first()
            if session_row is None:
                raise SessionStoreError(404, "Persisted session_id not found")

            current_status = str(session_row["status"] or "").lower()
            if current_status not in {"ready", "streaming"}:
                raise SessionStoreError(
                    409,
                    f"Session is not joinable from status '{current_status}'",
                )

            await db.execute(
                text(
                    """
                    UPDATE sessions
                    SET status = 'streaming'
                    WHERE id = :session_id
                      AND deleted_at IS NULL
                    """
                ),
                {"session_id": session_id},
            )
            await db.commit()

    async def mark_session_status(self, session_id: str, status_value: str) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    """
                    UPDATE sessions
                    SET status = :status_value
                    WHERE id = :session_id
                      AND deleted_at IS NULL
                    """
                ),
                {
                    "session_id": session_id,
                    "status_value": status_value,
                },
            )
            await db.commit()

    async def get_session_owner(self, session_id: str) -> str:
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text(
                    """
                    SELECT user_id
                    FROM sessions
                    WHERE id = :session_id
                      AND deleted_at IS NULL
                    LIMIT 1
                    """
                ),
                {"session_id": session_id},
            )
            session_row = row.mappings().first()

        if session_row is None:
            raise SessionStoreError(404, "session_id not found")
        return str(session_row["user_id"])

    async def persist_event_log(
        self,
        session_id: str,
        event_log: list[dict[str, object]],
    ) -> None:
        async with AsyncSessionLocal() as db:
            payload: dict[str, Any] = {"sid": session_id}
            if event_log:
                payload["logs"] = json.dumps(event_log)
                await db.execute(
                    text(
                        "UPDATE SESSIONS "
                        "SET raw_backup_json = CAST(:logs AS jsonb), status = 'completed', ended_at = CURRENT_TIMESTAMP "
                        "WHERE id = :sid"
                    ),
                    payload,
                )
            else:
                await db.execute(
                    text(
                        "UPDATE SESSIONS "
                        "SET status = 'completed', ended_at = CURRENT_TIMESTAMP "
                        "WHERE id = :sid"
                    ),
                    payload,
                )
            await db.commit()
