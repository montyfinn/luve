# LUVE Next Task

This file is a scoped task memo, not the global repo state source of truth.

- Read `PROJECT_STATE.md` first for current baseline and verified status.
- Use this file only for the currently approved task scope at the time it was last updated.
- If this file conflicts with current code, current git history, or `PROJECT_STATE.md`, re-audit before acting.

## Completed Tasks

### Task 1: Audit grading delivery reliability, design and implement backfill script, execute backfill.
* Audited grading delivery gap: `_persist_event_log` commits DB first then publishes best-effort; no durable outbox.
* Designed and implemented `services/grading-worker/scripts/backfill_completed_sessions.py` (commit `c5cf2c3`).
* Executed backfill against local Postgres in controlled increments:
  * `grading_results` total: 2 → **138**
  * `completed_missing_grading`: 216 → **80**
  * Remaining 80 all have `raw_backup_json IS NULL`; excluded by default filter.
* Verified idempotency: rerun on already-graded session produced `candidates_seen=0`, no duplicate row.

### Task 2: Audit why completed sessions have `raw_backup_json IS NULL`.
* Confirmed NULL-producing branch in `luve_extension.py`: `_persist_event_log` has an explicit `if self._event_log: ... else: ...`; the `else` path omits `raw_backup_json` from the UPDATE.
* `_event_log` is only populated when accepted STT finals arrive (`job.is_final and analysis.raw_text.strip()`). Zero accepted finals → empty `_event_log` → NULL.
* The 80 remaining NULL sessions are consistent with empty/noise/rapid-disconnect/silent sessions; no gradeable event log was found. Under the current observed code path, a session with an accepted USER_TURN should write `raw_backup_json`.
* **Policy confirmed:** Do not run `--include-empty-raw`. `fake_grader.v1` produces meaningless fixed scores for 0-turn input; the rows would pollute `grading_results` with no pedagogical value.
* **Apparently unused code identified:** `SQLSessionStore.persist_event_log` in `session_store.py` appears unused by current call-site search; removal should be a separate cleanup with verification.
* **Future patch scoped:** Collapse the `_persist_event_log` if/else to always write `json.dumps(self._event_log)` (empty array `[]` when no turns). Grading input coercion treats NULL and `[]` similarly as zero events, but backfill candidate accounting differs: `[]` satisfies `raw_backup_json IS NOT NULL` and would then be skipped by `user_turns=0`. Requires a separate approved prompt.

### Task 3: Implement [] instead of NULL for empty session event logs.
* Audited proposed patch: collapse `_persist_event_log` if/else into one unconditional `UPDATE` with `raw_backup_json = CAST(:logs AS jsonb)`.
* Implemented in `services/core-api/src/ten_ext/luve_extension.py` (commit `440ff98`).
* Verified: py_compile pass, `run_ten` import smoke pass, DB verification pass with RabbitMQ publish monkeypatched to async no-op.
  * `raw_backup_json::text = '[]'`, `status = 'completed'`, `ended_at IS NOT NULL`, cleanup `deleted_rows=1`.
* Existing 80 NULL sessions are historical data — not migrated, not backfilled.
* `SQLSessionStore.persist_event_log` dead code left in place (separate cleanup required, not urgent).

### Task 4: Implement automated reconciliation scanner for missed grading results.
* Audited durable outbox vs manual backfill safety net; recommended one-shot scanner over full outbox at current dev stage.
* Implemented `services/grading-worker/scripts/reconciliation_scanner.py` (commit `fc18916`).
* Scanner properties: one-shot, dry-run default, `--execute` required for DB writes, 5-minute grace window (configurable), reuses `process_session_completed_job`, no RabbitMQ dependency for recovery.
* Verified: py_compile pass, dry-run `candidates_seen=0` (correct — all eligible sessions already graded by historical backfill).
* Not a daemon; intended for cron or manual execution. Does not loop internally.

### Task 5: Add end-of-session grading analysis API and UI.
* Audited: `grading_results` table was fully populated (138 rows) but no API endpoint exposed the data and the UI had no post-session display.
* Added `GradingRead` Pydantic schema to `schemas/session.py`.
* Added `get_session_grading()` to `session_service.py`: raw SQL JOIN enforcing session ownership via `sessions.user_id`; returns `GradingRead` or HTTP 404 (detail `"Grading result not ready"`). The UI treats HTTP 404 as pending based on status code only — it does not parse the detail string.
* Added `GET /api/v1/sessions/{session_id}/grading` route to `sessions.py`, registered before the `/{session_id}` wildcard to avoid route shadowing.
* Added Session Analysis card to control center UI (`static/index.html`):
  * One-shot `fetchAndShowGrading(sessionId)` with 2s delay, hooked into `session_ended` TEN event and manual `disconnect()`.
  * Renders 4 score tiles, AI summary, corrections list, and graded_at timestamp.
  * 404 path shows pending text + DOM-created Retry button (no inline `onclick`).
  * All server-derived text sanitized via `escapeHtml()` before `innerHTML` insertion.
  * Labeled "DEV PREVIEW — Simulated Grading" (amber badge + disclaimer) because `fake_grader.v1` is not pedagogically valid.
  * Card hidden on `ten_started` for new sessions.
* Committed as `3da235c`. Verified: py_compile OK, import smoke OK, JS syntax OK.
* Not yet manually tested end-to-end in browser.

---

## Current Task
No active task. Awaiting next approved prompt.

## Out of Scope (requires separate approved prompt)
* Transactional outbox implementation.
* New DB schema / migration files.
* Wiring reconciliation scanner as a background daemon or auto-start service.
* Removing `SQLSessionStore.persist_event_log` dead code.
* Replacing `fake_grader.v1` with real pedagogical grader.
* Wiring `close_publisher()` into shutdown.
* Adding `.codegraph/` and `.cursor/` to `.gitignore`.
* Live browser/API end-to-end verification of Session Analysis card (dev-preview grading delivery committed; real grader and browser smoke test remain deferred).

## Protected Runtime Files
Protected runtime files and canonical guardrails are maintained in `CLAUDE.md` and `docs/ai/CLAUDE_CODE_HANDOFF.md`. Do not modify runtime files unless a future prompt explicitly allows it.

## Route Behavior Note
`GET /sessions/{session_id}/grading` and `GET /sessions/{session_id}` match structurally different URL shapes (two segments vs one). They cannot conflict regardless of registration order; FastAPI's UUID path converter also rejects the literal string `"grading"` as a non-UUID. The `/grading` route is registered first for readability only.
