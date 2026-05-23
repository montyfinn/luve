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

### Task 6: Patch 1 — Offline LLM grader scaffold.
* Audited and designed real grader rollout: three-patch plan (offline scaffold → env-flag wiring → controlled real-session test).
* Implemented `services/grading-worker/src/llm_grader.py` (commit `675e3a2`):
  * `build_grading_prompt`, `parse_grading_response`, `llm_grade_with_client`, `LLMGraderError`, `GraderClient` Protocol.
  * No external/provider/network imports. No worker wiring.
* Loosened `GradingResult.grader_version` from `Literal["fake_grader.v1"]` to `str` (default unchanged).
* Added `services/grading-worker/tests/` with 22 mocked tests.
* Verified: py_compile pass, 22/22 tests pass, fake_grader regression pass, no external imports.
* Live grading path remains `fake_grader.v1` only — `worker.py` untouched.

### Task 7: Patch 2A — Safe grading provider dispatch skeleton.
* Conducted Patch 2 pre-implementation audit (design-only): confirmed `GraderClient` Protocol, `requirements.txt` baseline, no DB migration needed, provider fallback design.
* Implemented `GRADING_PROVIDER` dispatch in `worker.py` (commit `06acf97`):
  * `_get_grading_provider()` reads env var, validates against `{"fake", "llm"}`, warns + falls back on unknown values.
  * `_build_grader_client()` raises `LLMGraderError` (stub) — `GRADING_PROVIDER=llm` falls back to fake safely; monkeypatchable in tests.
  * `process_session_completed_job` now returns early (no upsert) for sessions without accepted student turns.
  * `grader_info` marker prepended to `detailed_corrections` on LLM success path.
  * Completion log includes `provider_requested=` and `grader_version=`.
* Added 12 mocked worker dispatch tests (`tests/test_worker_patch2a.py`).
* Verified: py_compile pass, 34/34 tests pass, no external provider imports.
* No `httpx`, no provider SDK, no `requirements.txt` change, no `core-api` change, no DB migration, no UI change.
* Live behavior unchanged: `GRADING_PROVIDER` defaults to `"fake"`; `fake_grader.v1` still the only live grader.

### Task 8: Patch 2B — Groq grading provider client.
* Conducted Patch 2B pre-implementation audit (design-only): confirmed Groq as first provider, `httpx` as HTTP client, env var names.
* Implemented `services/grading-worker/src/grading_provider_client.py` (commit `1cae30b`):
  * `GroqClient` using raw `httpx.AsyncClient` POST to `https://api.groq.com/openai/v1/chat/completions`.
  * No Groq SDK, no OpenAI SDK. Constructor validates `api_key`, `model`, `timeout_seconds`. No env reads inside class.
  * `grade(prompt) -> str` extracts `choices[0]["message"]["content"]`; wraps all errors as `LLMGraderError`; no secrets/prompt/response body in messages.
* Updated `_build_grader_client()` in `worker.py` to read `LLM_PROVIDER`/`GROQCLOUD_API_KEY`/`GROQ_MODEL`/`GROQ_TIMEOUT_SECONDS` and return a real `GroqClient`.
* Declared `httpx>=0.27,<1` in `services/grading-worker/requirements.txt`.
* Added 17 mocked `GroqClient` tests (`tests/test_grading_provider_client.py`); updated `tests/test_worker_patch2a.py` with 6 new env-wiring tests (total 26).
* Verified: py_compile pass, 57/57 tests pass, no real API calls in tests, no secrets/prompt/response-body in logs.
* `GRADING_PROVIDER` default/unset remains `"fake"`. Real Groq live test has **not** been run. UI still shows DEV PREVIEW.
* **Security:** A Groq API key was exposed in chat during this task. It must be rotated/revoked before Patch 3. Docs contain env var names only — never values.

---

## Current Task
**Mode: AUDIT / DESIGN ONLY — do not run live test, do not modify runtime files.**

### Patch 3 Pre-Implementation Audit: Controlled Real Groq Grading Test

**Goal of audit:** produce an approved plan for exactly one controlled real Groq grading test before any live path is enabled.

**What this audit must plan (read-only, no execution):**
1. **Key rotation confirmation:** Verify that the previously exposed `GROQCLOUD_API_KEY` has been rotated and revoked. Do not run any live path until a fresh key is confirmed. Do not print or log key values — refer only to env var names.
2. **Exact services to run:** Which processes must be running (core-api, grading-worker, Postgres, RabbitMQ). Confirm no additional services are needed.
3. **Exact env var names only:** `GRADING_PROVIDER=llm`, `LLM_PROVIDER=groq`, `GROQCLOUD_API_KEY` (name only), `GROQ_MODEL` (default or override). Do not print values.
4. **One controlled session only:** Plan for exactly one test session — not a batch scan. Determine whether to trigger via a new UI session or by injecting one known session payload into the worker directly. Do not use the reconciliation scanner `--execute` flag.
5. **How to avoid batch scanner/backfill:** Explicitly confirm the reconciliation scanner will not be run in `--execute` mode during this test.
6. **How to verify `grading_results` row safely:** SQL read-only query (`SELECT`) against local Postgres to confirm a new row exists with `grader_version='llm_grader.v1'` and valid score range `[0,10]`. No `UPDATE`/`DELETE`/`TRUNCATE` during verification.
7. **How to verify `grader_info` marker:** `SELECT detailed_corrections` from `grading_results` and confirm `detailed_corrections[0].type == 'grader_info'` and `detailed_corrections[0].grader_version == 'llm_grader.v1'`.
8. **How to verify UI:** Confirm grading analysis card loads in control center. Confirm UI still shows DEV PREVIEW badge (do not remove it during Patch 3). Verify scores are non-zero and differ from the fake grader floor pattern.
9. **Rollback plan:** Unsetting `GRADING_PROVIDER` or setting `GRADING_PROVIDER=fake` immediately restores fake grader behavior. No DB migration needed to roll back.
10. **UI badge removal:** Keep deferred until after the controlled real Groq test passes. Badge removal (`static/index.html`) requires separate authorization in a Patch 3 implementation prompt.

**Do not in this task:**
* Do not set `GRADING_PROVIDER=llm` or call Groq.
* Do not run the grading worker with a real Groq key.
* Do not write any `grading_results` row via the live path.
* Do not run the reconciliation scanner in `--execute` mode.
* Do not remove the DEV PREVIEW badge or modify `static/index.html`.
* Do not modify any `services/grading-worker/src/` or `services/core-api/src/` files.
* Do not modify DB schema, migrations, or `requirements.txt`.
* Do not print secret values, API keys, or DATABASE_URL credentials.

## Out of Scope (requires separate approved prompt)
* Transactional outbox implementation.
* New DB schema / migration files (including adding `grader_version` column to `grading_results`).
* Wiring reconciliation scanner as a background daemon or auto-start service.
* Removing `SQLSessionStore.persist_event_log` dead code.
* Removing DEV PREVIEW badge from UI (requires Patch 3 approval and `index.html` authorization).
* Wiring `close_publisher()` into shutdown.
* Adding `.codegraph/` and `.cursor/` to `.gitignore`.
* Live browser/API end-to-end verification with real LLM grader (deferred to Patch 3).
* Patch 3: controlled real-session grading test and UI badge removal.

## Protected Runtime Files
Protected runtime files and canonical guardrails are maintained in `CLAUDE.md` and `docs/ai/CLAUDE_CODE_HANDOFF.md`. For the Patch 2 audit/design task, do not modify runtime files, core-api UI/API files, DB schema/migrations, env files, secret/local payload files, or TEN/VAD/STT/TTS/WebRTC files unless a future prompt explicitly authorizes it.

## Route Behavior Note
`GET /sessions/{session_id}/grading` and `GET /sessions/{session_id}` match structurally different URL shapes (two segments vs one). They cannot conflict regardless of registration order; FastAPI's UUID path converter also rejects the literal string `"grading"` as a non-UUID. The `/grading` route is registered first for readability only.
