#!/usr/bin/env python3
"""
One-shot reconciliation scanner: grade completed sessions missing a grading result.

Runs once and exits. Dry-run by default — pass --execute to write to DB.

Difference from backfill_completed_sessions.py:
  - Applies a grace window (default 5 min) so recently completed sessions are
    skipped, giving the live grading worker time to process them first.
  - Intended to be run periodically (cron / external scheduler) as an automated
    safety net. Does not loop internally.

Safety:
  - Does not publish to RabbitMQ.
  - Does not import from services/core-api.
  - Does not start the consumer loop.
  - grading_results upsert is idempotent via ON CONFLICT(session_id).

Usage examples:
  Dry-run (safe, no DB writes):
    python reconciliation_scanner.py

  Dry-run, show up to 10 candidates:
    python reconciliation_scanner.py --limit 10

  Live: grade all overdue sessions (default grace window: 5 min):
    python reconciliation_scanner.py --execute

  Live: tighter grace window for low-latency env:
    python reconciliation_scanner.py --execute --grace-minutes 2

  Single session:
    python reconciliation_scanner.py --execute --session-id <UUID>

Environment:
  DATABASE_URL  Required. PostgreSQL connection URL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

# Make src.* importable when running from any working directory.
SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

import asyncpg

from src.grading_repository import GradingRepository
from src.worker import process_session_completed_job

# Keep imported-module log noise off; only WARNING+ from asyncpg/asyncio surfacing.
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=logging.WARNING)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _truncate_id(value: Any) -> str:
    """Return last 8 chars of a UUID string for safe log output."""
    return f"...{str(value)[-8:]}"


def _normalize_db_url(url: str) -> str:
    """asyncpg requires postgresql:// not postgresql+asyncpg://."""
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def _count_user_turns(raw_json_text: str | None) -> int:
    """Count USER_TURN events in the event log JSON text.

    Pure Python parse — does not rely on JSONB operators in the DB.
    Returns 0 on any parse failure.
    """
    if not raw_json_text:
        return 0
    try:
        events = json.loads(raw_json_text)
    except json.JSONDecodeError:
        return 0
    if not isinstance(events, list):
        return 0
    return sum(
        1
        for e in events
        if isinstance(e, dict) and str(e.get("type", "")).upper() == "USER_TURN"
    )


# --------------------------------------------------------------------------- #
# Candidate query                                                               #
# --------------------------------------------------------------------------- #

def _build_candidate_sql(
    *,
    grace_threshold: datetime,
    since: date | None,
    session_id: UUID | None,
    limit: int,
) -> tuple[str, list[Any]]:
    """Build the parameterised candidate SELECT and its parameter list."""
    wheres = [
        "s.status = 'completed'",
        "s.deleted_at IS NULL",
        "gr.session_id IS NULL",
        "s.raw_backup_json IS NOT NULL",
    ]
    params: list[Any] = []

    # Grace window: only consider sessions that ended before the threshold.
    params.append(grace_threshold)
    wheres.append(f"s.ended_at < ${len(params)}")

    if since is not None:
        params.append(since)
        wheres.append(f"s.ended_at::date >= ${len(params)}")

    if session_id is not None:
        params.append(session_id)
        wheres.append(f"s.id = ${len(params)}")

    params.append(limit)
    sql = (
        "SELECT"
        "  s.id AS session_id,"
        "  s.ended_at,"
        "  s.raw_backup_json::text AS raw_json"
        " FROM sessions s"
        " LEFT JOIN grading_results gr ON gr.session_id = s.id"
        f" WHERE {' AND '.join(wheres)}"
        " ORDER BY s.ended_at ASC"
        f" LIMIT ${len(params)}"
    )
    return sql, params


# --------------------------------------------------------------------------- #
# Main coroutine                                                                #
# --------------------------------------------------------------------------- #

async def run(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    target_session_id: UUID | None = None
    if args.session_id:
        try:
            target_session_id = UUID(args.session_id)
        except ValueError:
            print("ERROR: --session-id is not a valid UUID.", file=sys.stderr)
            return 1

    since_date: date | None = None
    if args.since:
        try:
            since_date = date.fromisoformat(args.since)
        except ValueError:
            print(f"ERROR: --since '{args.since}' must be YYYY-MM-DD.", file=sys.stderr)
            return 1

    grace_threshold = datetime.now(timezone.utc) - timedelta(minutes=args.grace_minutes)

    mode = "[RECONCILE]" if args.execute else "[DRY-RUN]"
    print(
        f"{mode} execute={args.execute}"
        f"  limit={args.limit}"
        f"  grace_minutes={args.grace_minutes}"
        f"  require_user_turn={args.require_user_turn}"
        + (f"  since={args.since}" if args.since else "")
        + ("  session_id=<provided>" if args.session_id else "")
    )

    sql, params = _build_candidate_sql(
        grace_threshold=grace_threshold,
        since=since_date,
        session_id=target_session_id,
        limit=args.limit,
    )

    conn = await asyncpg.connect(_normalize_db_url(database_url))
    try:
        rows = await conn.fetch(sql, *params)
    finally:
        await conn.close()

    candidates_seen = len(rows)
    would_process = 0
    processed = 0
    skipped_no_raw = 0
    skipped_grace_window = 0
    skipped_no_user_turn = 0
    errors = 0

    repository = GradingRepository(database_url) if args.execute else None

    for row in rows:
        sid = row["session_id"]
        ended_at = row["ended_at"]
        raw_json = row["raw_json"]
        sid_short = _truncate_id(sid)
        ended_fmt = ended_at.isoformat() if ended_at else "unknown"

        # Belt-and-suspenders: SQL already filters, but re-check in Python.
        if not raw_json:
            skipped_no_raw += 1
            print(f"{mode}  skip  {sid_short}  reason=no_raw_backup_json  ended_at={ended_fmt}")
            continue

        if ended_at is not None and ended_at.replace(tzinfo=timezone.utc) >= grace_threshold:
            skipped_grace_window += 1
            print(f"{mode}  skip  {sid_short}  reason=grace_window  ended_at={ended_fmt}")
            continue

        user_turns = _count_user_turns(raw_json)
        if args.require_user_turn and user_turns == 0:
            skipped_no_user_turn += 1
            print(f"{mode}  skip  {sid_short}  reason=no_user_turn  ended_at={ended_fmt}")
            continue

        if not args.execute:
            would_process += 1
            print(f"{mode}  would  {sid_short}  user_turns={user_turns}  ended_at={ended_fmt}")
            continue

        # Live path: use the same code as the grading worker.
        try:
            payload: dict[str, Any] = {
                "event_type": "session.completed",
                "schema_version": "v1",
                "session_id": str(sid),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await process_session_completed_job(payload, repository=repository)
            processed += 1
            print(f"{mode}  ok    {sid_short}  user_turns={user_turns}  ended_at={ended_fmt}")
        except Exception as exc:
            errors += 1
            print(
                f"{mode}  ERR   {sid_short}  error={type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            if target_session_id is not None:
                # Single-session mode: do not attempt further sessions.
                break

        if args.sleep_ms > 0:
            await asyncio.sleep(args.sleep_ms / 1000.0)

    print(f"{mode} ---")
    if args.execute:
        print(
            f"{mode} done"
            f"  candidates_seen={candidates_seen}"
            f"  processed={processed}"
            f"  skipped_no_raw={skipped_no_raw}"
            f"  skipped_grace_window={skipped_grace_window}"
            f"  skipped_no_user_turn={skipped_no_user_turn}"
            f"  errors={errors}"
        )
    else:
        print(
            f"{mode} done"
            f"  candidates_seen={candidates_seen}"
            f"  would_process={would_process}"
            f"  skipped_no_raw={skipped_no_raw}"
            f"  skipped_grace_window={skipped_grace_window}"
            f"  skipped_no_user_turn={skipped_no_user_turn}"
        )

    return 1 if (args.execute and errors > 0) else 0


# --------------------------------------------------------------------------- #
# CLI                                                                           #
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "One-shot reconciliation scanner: grade completed sessions missing a "
            "grading result, respecting a grace window for the live worker. "
            "Dry-run by default. Pass --execute to write to DB."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Write grading results to DB. Without this flag, runs as dry-run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        metavar="N",
        help="Max candidates to process per run (default: 50).",
    )
    parser.add_argument(
        "--grace-minutes",
        type=int,
        default=5,
        metavar="N",
        help=(
            "Skip sessions that completed less than N minutes ago, giving the "
            "live grading worker time to process them first (default: 5)."
        ),
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        default=None,
        help="Only consider sessions ended on or after this date.",
    )
    parser.add_argument(
        "--session-id",
        metavar="UUID",
        default=None,
        help="Scan exactly one session by ID (ignores --limit and --since).",
    )
    parser.add_argument(
        "--no-require-user-turn",
        dest="require_user_turn",
        action="store_false",
        help="Disable the filter requiring at least one accepted USER_TURN event.",
    )
    parser.set_defaults(require_user_turn=True)
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=100,
        metavar="N",
        help="Milliseconds to sleep between sessions in execute mode (default: 100).",
    )

    args = parser.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
