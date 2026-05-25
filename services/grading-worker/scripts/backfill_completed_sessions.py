#!/usr/bin/env python3
"""
Backfill grading_results for completed sessions that are missing a result row.

Dry-run by default — pass --execute to write to DB.

Safety:
  - Does not publish to RabbitMQ.
  - Does not import from services/core-api.
  - Does not start the consumer loop.
  - grading_results upsert is idempotent via ON CONFLICT(session_id).

Usage examples:
  Dry-run (safe, no DB writes):
    python backfill_completed_sessions.py --limit 10

  Single session dry-run:
    python backfill_completed_sessions.py --session-id <UUID>

  Live: grade one session:
    python backfill_completed_sessions.py --execute --limit 1

  Live: grade sessions since a date:
    python backfill_completed_sessions.py --execute --since 2026-01-01

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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

# Make src.* importable when running from any working directory.
SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

import asyncpg

from src.grading_repository import GradingRepository
from src.session_eligibility import DEFAULT_MIN_STUDENT_WORDS, evaluate_grading_eligibility
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


def _parse_min_student_words_env(value: str | None) -> int:
    """Parse GRADING_MIN_STUDENT_WORDS env value; fall back to default on invalid.

    Accepts 0 (disables the word-count gate) and positive integers.
    Returns DEFAULT_MIN_STUDENT_WORDS for None, non-numeric, or negative inputs.
    """
    if value is None:
        return DEFAULT_MIN_STUDENT_WORDS
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        return DEFAULT_MIN_STUDENT_WORDS
    return parsed if parsed >= 0 else DEFAULT_MIN_STUDENT_WORDS


def _count_user_turns(raw_json_text: str | None) -> int:
    """Count USER_TURN events in the event log JSON text.

    Pure Python parse — does not rely on JSONB operators in the DB.
    Returns 0 on any parse failure.

    No longer called in the main candidate loop (superseded by
    evaluate_grading_eligibility in Patch 7G-4D). Retained for tests that
    document the known type-key-only limitation vs. the full helper.
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
    since: date | None,
    session_id: UUID | None,
    include_empty_raw: bool,
    limit: int,
) -> tuple[str, list[Any]]:
    """Build the parameterised candidate SELECT and its parameter list."""
    wheres = [
        "s.status = 'completed'",
        "s.deleted_at IS NULL",
        "gr.session_id IS NULL",
    ]
    params: list[Any] = []

    if not include_empty_raw:
        wheres.append("s.raw_backup_json IS NOT NULL")

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
        " ORDER BY s.ended_at DESC"
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

    mode = "[BACKFILL]" if args.execute else "[DRY-RUN]"
    print(
        f"{mode} execute={args.execute}"
        f"  limit={args.limit}"
        f"  include_empty_raw={args.include_empty_raw}"
        f"  min_student_words={args.min_student_words}"
        + (f"  since={args.since}" if args.since else "")
        + ("  session_id=<provided>" if args.session_id else "")
    )

    sql, params = _build_candidate_sql(
        since=since_date,
        session_id=target_session_id,
        include_empty_raw=args.include_empty_raw,
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
    skipped_no_raw_backup = 0
    skipped_invalid_raw = 0        # both paths: raw_backup_json present but not parseable as JSON array
    skipped_no_user_turns = 0      # both paths: no USER_TURN events found
    skipped_insufficient_words = 0  # both paths: student word count below threshold
    errors = 0

    repository = GradingRepository(database_url) if args.execute else None

    for row in rows:
        sid = row["session_id"]
        ended_at = row["ended_at"]
        raw_json = row["raw_json"]
        sid_short = _truncate_id(sid)
        ended_fmt = ended_at.isoformat() if ended_at else "unknown"

        # Belt-and-suspenders: SQL already filters when include_empty_raw=False,
        # but re-check in Python in case of slippage.
        if not args.include_empty_raw and not raw_json:
            skipped_no_raw_backup += 1
            print(f"{mode}  skip  {sid_short}  reason=no_raw_backup  ended_at={ended_fmt}")
            continue

        # Eligibility gate: prevents ineligible sessions from reaching
        # process_session_completed_job — applies to both dry-run and execute paths.
        result = evaluate_grading_eligibility(raw_json, min_student_words=args.min_student_words)
        if not result.eligible:
            if result.reason == "no_raw_backup":
                skipped_no_raw_backup += 1
            elif result.reason == "invalid_raw_backup":
                skipped_invalid_raw += 1
            elif result.reason == "no_user_turns":
                skipped_no_user_turns += 1
            elif result.reason == "insufficient_words":
                skipped_insufficient_words += 1
            print(
                f"{mode}  skip  {sid_short}"
                f"  reason={result.reason}"
                f"  ended_at={ended_fmt}"
            )
            continue

        if not args.execute:
            would_process += 1
            print(
                f"{mode}  would  {sid_short}"
                f"  user_turns={result.user_turn_count}"
                f"  student_words={result.student_word_count}"
                f"  ended_at={ended_fmt}"
            )
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
            print(f"{mode}  ok    {sid_short}  user_turns={result.user_turn_count}  ended_at={ended_fmt}")
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
            f"  skipped_no_raw_backup={skipped_no_raw_backup}"
            f"  skipped_invalid_raw={skipped_invalid_raw}"
            f"  skipped_no_user_turns={skipped_no_user_turns}"
            f"  skipped_insufficient_words={skipped_insufficient_words}"
            f"  errors={errors}"
        )
    else:
        print(
            f"{mode} done"
            f"  candidates_seen={candidates_seen}"
            f"  would_process={would_process}"
            f"  skipped_no_raw_backup={skipped_no_raw_backup}"
            f"  skipped_invalid_raw={skipped_invalid_raw}"
            f"  skipped_no_user_turns={skipped_no_user_turns}"
            f"  skipped_insufficient_words={skipped_insufficient_words}"
        )

    return 1 if (args.execute and errors > 0) else 0


# --------------------------------------------------------------------------- #
# CLI                                                                           #
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill grading_results for completed sessions missing a result. "
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
        "--since",
        metavar="YYYY-MM-DD",
        default=None,
        help="Only process sessions ended on or after this date.",
    )
    parser.add_argument(
        "--session-id",
        metavar="UUID",
        default=None,
        help="Backfill exactly one session by ID (ignores --limit and --since).",
    )
    parser.add_argument(
        "--include-empty-raw",
        action="store_true",
        default=False,
        help=(
            "Include sessions where raw_backup_json IS NULL in the candidate query. "
            "Selected sessions with NULL raw data are still skipped by the eligibility "
            "gate with reason=no_raw_backup before any grading attempt."
        ),
    )
    parser.add_argument(
        "--no-require-user-turn",
        dest="require_user_turn",
        action="store_false",
        help=(
            "Retained for CLI backward compatibility. The eligibility helper now "
            "enforces user-turn presence; this flag no longer affects execute behavior."
        ),
    )
    parser.set_defaults(require_user_turn=True)
    parser.add_argument(
        "--min-student-words",
        type=int,
        default=_parse_min_student_words_env(os.environ.get("GRADING_MIN_STUDENT_WORDS")),
        metavar="N",
        help=(
            "Minimum student word count for eligibility — applies to both dry-run and "
            "execute paths (default: GRADING_MIN_STUDENT_WORDS env or %(default)s)."
        ),
    )
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
