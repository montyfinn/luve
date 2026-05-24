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
* `GRADING_PROVIDER` default/unset remains `"fake"`. Real Groq live test deferred to Patch 3.
* **Security:** A Groq API key was exposed in chat during this task. It must be rotated/revoked before Patch 3. Docs contain env var names only — never values.

### Task 9: Patch 3 Pre-Implementation Audit — Controlled Real Groq Grading Test.
* Produced approved plan for one controlled live Groq grading test: key rotation gate, services to run, exact env var names, one-session-only approach, scanner avoidance, DB SELECT verification queries, rollback plan, UI badge deferral.
* Confirmed all 10 audit questions answered (audit/design only — no live call, no runtime changes).

### Task 10: Patch 3 — CUDA/STT Stabilization + Controlled One-Shot Groq Grading Test.
* **CUDA stabilization (prerequisite):** STT was falling back to CPU due to `torch+cu118` / system CUDA 12.1 / `ctranslate2 4.7.1` mixed-runtime conflict. Upgraded torch to `2.7.1+cu126` (venv-only, no source changes). Removed 24 orphan nvidia packages. Resolved pip namespace corruption via second force-reinstall. NVIDIA kernel module bad state required system reboot; after reboot `cuInit(0) → CUDA_SUCCESS`, `torch.cuda.is_available() → True`, `ctranslate2.get_cuda_device_count() → 1`, faster-whisper tiny CUDA load passed.
* **New TEN session (suffix `...a3d35b36`):** STT GPU path active (`device=cuda`, `compute_type=int8_float16`). 30 events persisted, 15 `USER_TURN` events. `session.completed` published. Grading-worker consume loop was NOT running.
* **One-shot direct Groq grading:** Pre-live DB check confirmed `has_grading=False`. Exactly one `process_session_completed_job` call with `GRADING_PROVIDER=llm LLM_PROVIDER=groq GROQCLOUD_API_KEY` set. Groq call succeeded. `grading_results` row created.
* **Verified DB result (SELECT-only):** `marker_type=grader_info`, `marker_grader_version=llm_grader.v1`, `is_fake_text=False`, `feedback_len=252`, `overall_score=2.95`, `fluency_score=4.00`, `grammar_score=2.00`, `vocab_score=3.00`, all score range checks passed.
* No scanner/backfill `--execute`, no worker consume loop, no RabbitMQ publish, no source files modified, no secrets printed.
* UI still shows DEV PREVIEW. Normal RabbitMQ consume-loop path with `GRADING_PROVIDER=llm` not yet tested.

### Task 11: Patch 4 Audit/Design — Normal Grading-Worker Consume-Loop Test.
* Audited consume-loop structure: `consume_forever()` has no `--consume-once` flag; `prefetch_count=1`; `message.process(requeue=False)`.
* Identified 4 stale messages in `luve.session.completed` queue — starting worker immediately would risk 4 Groq calls and overwrites.
* Recommended strategy: purge stale messages (separate approval gate), run fresh TEN session, use OS `timeout 60` to bound worker without code changes.
* Confirmed `RABBITMQ_HOST=localhost` override required for local worker execution (default `"rabbitmq"` is Docker-internal hostname).
* Confirmed all 10 audit questions answered (audit/design only — no live call, no runtime changes, no messages consumed/purged).

### Task 12: Patch 4 — Normal RabbitMQ Consume-Loop Groq Grading Test.
* **Queue preparation:** 4 stale messages purged via `rabbitmqctl purge_queue luve.session.completed`. Queue confirmed `messages=0`.
* **Fresh TEN session:** Session suffix `...218666a0`, `event_count=8`, `USER_TURN count=4`. Queue confirmed `messages=1` before worker start.
* **Worker:** Started exactly once with `timeout 60 python -m src.worker` with `GRADING_PROVIDER=llm`, `LLM_PROVIDER=groq`, `RABBITMQ_HOST=localhost`. No code changes required.
* **Worker log:** `grading.completed provider_requested=llm grader_version=llm_grader.v1`. No `grading.llm_failed_fallback`. Exit code 124 (timeout-after-idle) expected.
* **Queue after:** `messages=0`.
* **Verified DB result (SELECT-only):** `marker_type=grader_info`, `marker_grader_version=llm_grader.v1`, `is_fake_text=False`, `feedback_len=168`, `overall_score=2.95`, `fluency_score=4.00`, `grammar_score=2.00`, `vocab_score=3.00`, all score range checks passed.
* No scanner/backfill `--execute`, no manual RabbitMQ publish, no second worker, no source files modified, no secrets printed.
* UI still shows DEV PREVIEW. Browser UI verification deferred to Patch 5.

### Task 13: Patch 5 — Browser UI Verification of Real llm_grader.v1 Session Analysis Row.
* **Target session:** `9de7a1e3-e374-487e-af91-4d0b218666a0` (suffix `...218666a0`); same session graded in Patch 4.
* **Correct UI URL confirmed:** `http://localhost:8080/control-center` (HTTP 200). `http://localhost:8000/static/index.html` returns 404 — not a valid route.
* **Method:** Temporary Playwright automation in `/tmp/luve-playwright-ui-check/` (outside repo) using system Chrome `/usr/bin/google-chrome`. Token injected from `/tmp/luve_token` (file-based, not printed; deleted immediately after run).
* **API response verified (HTTP 200):** `overall_score=2.95`, `fluency_score=4.00`, `grammar_score=2.00`, `vocab_score=3.00`, `detailed_corrections[0].type=grader_info`, `detailed_corrections[0].grader_version=llm_grader.v1`, `ai_summary_feedback` non-empty, no fake placeholder.
* **Rendered UI verified (Playwright DOM):** Session Analysis card visible, Overall=3.0 (toFixed(1)), Fluency=4.0, Grammar=2.0, Vocab=3.0, summary non-empty, `Graded at:` visible, Retry button absent, DEV PREVIEW badge visible, `fake_grader.v1` disclaimer visible.
* **Semantic issue confirmed:** Badge says "Simulated Grading"; disclaimer says `fake_grader.v1` — both are inaccurate for real `llm_grader.v1` rows. Static HTML, not introduced by Patch 5. Requires Patch 6 to fix.
* No Groq calls, no worker started, no DB writes, no new sessions, no repo files modified, no secrets printed.

### Task 14: Patch 6 — UI Label/Disclaimer Cleanup for Session Analysis Card.
* Implemented two static text-only changes in `services/core-api/src/static/index.html`:
  * Badge text: `"DEV PREVIEW — Simulated Grading"` → `"DEV PREVIEW"`.
  * Disclaimer: `"Dev preview: current scores are generated by fake_grader.v1 and are not final pedagogical grading."` → `"Dev preview: scores are automatically generated and are not final pedagogical grading."`.
* No JS, backend, schema, worker, DB, or API changes.
* Static grep verified: old strings absent; new strings present.
* Browser Playwright re-run not completed (token namespace issue); not required for a text-only static change.
* DEV PREVIEW badge retained; production readiness not claimed.
* `is_dev_preview` field and top-level `grader_version` exposure left for future scope.

---

## Current Task
**Mode: AUDIT / DESIGN ONLY — do not call Groq, do not run worker, do not run new sessions, do not write DB, do not change DB schema.**

### Patch 7 Audit/Design: Multi-Session Real Grading Stability and Reproducibility Planning

**Goal of audit:** Design a minimal plan to verify that real Groq grading (`GRADING_PROVIDER=llm`) is stable and reproducible across multiple sessions, and identify any remaining gaps or cleanup items before wider use. Do not implement in this audit.

**Do not in this task:**
* Do not call Groq without explicit approval.
* Do not start the grading-worker consume loop.
* Do not run a new TEN session.
* Do not write DB.
* Do not change DB schema or add migrations.
* Do not touch CUDA dependencies — reproducibility audit only.
* Do not print secrets, API keys, DATABASE_URL credentials, raw transcript text, or auth tokens.

**What this audit must answer:**
1. **Stability:** What conditions (Groq rate limits, network timeouts, empty transcript edge cases) could cause `llm_grader.v1` to fail silently? Is the `grading.llm_failed_fallback` log path exercised and safe?
2. **Score consistency:** Are the fixed scores (`overall=2.95`, `fluency=4.00`, etc.) appearing across sessions a coincidence or an artifact of the prompt/model? What would a multi-session comparison reveal?
3. **CUDA reproducibility:** Is the current `torch 2.7.1+cu126` venv state captured anywhere (requirements or lock file) so that it can be reproduced after a clean install?
4. **Grader version exposure:** Should `GradingRead` expose a top-level `grader_version` field so the UI can display which grader was used? Minimal schema change if any.
5. **`is_dev_preview` wiring:** Should `GradingRead.is_dev_preview: bool = True` remain hardcoded or be wired to a DB column or env flag? What is the minimal change?
6. **Dead code removal:** `SQLSessionStore.persist_event_log` is dead code (identified in Task 2). Should it be removed now or left until a broader cleanup? What verification is needed?
7. **`close_publisher()` shutdown wiring:** Risk of not wiring it vs complexity. Should this be a separate patch?
8. **`.gitignore` additions:** `.codegraph/` and `.cursor/` appear as untracked in every `git status`. Should they be added to `.gitignore`?
9. **Multi-session test plan:** Propose a concrete minimal test plan (how many sessions, what inputs, what checks) that would give confidence in `llm_grader.v1` stability without excessive Groq spend.
10. **Prioritized next patches:** Produce a prioritized list of the smallest next patches (Patch 7A, 7B, …) for future approved prompts.

## Out of Scope (requires separate approved prompt)
* Transactional outbox implementation.
* New DB schema / migration files (including adding `grader_version` column to `grading_results`).
* Wiring reconciliation scanner as a background daemon or auto-start service.
* Removing `SQLSessionStore.persist_event_log` dead code.
* Removing DEV PREVIEW badge from UI (requires Patch 4 success + separate authorization).
* Wiring `close_publisher()` into shutdown.
* Adding `.codegraph/` and `.cursor/` to `.gitignore`.
* Real grading stability verification over multiple sessions.
* Scanner/backfill with `GRADING_PROVIDER=llm` (not approved).

## Protected Runtime Files
Protected runtime files and canonical guardrails are maintained in `CLAUDE.md` and `docs/ai/CLAUDE_CODE_HANDOFF.md`. Do not modify runtime files, core-api UI/API files, DB schema/migrations, env files, secret/local payload files, or TEN/VAD/STT/TTS/WebRTC files unless a future prompt explicitly authorizes it.

## Route Behavior Note
`GET /sessions/{session_id}/grading` and `GET /sessions/{session_id}` match structurally different URL shapes (two segments vs one). They cannot conflict regardless of registration order; FastAPI's UUID path converter also rejects the literal string `"grading"` as a non-UUID. The `/grading` route is registered first for readability only.
