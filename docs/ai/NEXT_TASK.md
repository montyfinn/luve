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

### Task 15: Patch 7 Audit/Design — Multi-Session Stability and Reproducibility Planning.
* Audited all 10 questions: stability/fallback behavior, score consistency, CUDA reproducibility, API metadata exposure, dead code, publisher shutdown, `.gitignore`, multi-session test plan, prioritized patches.
* Key findings: `grading.llm_failed_fallback` silently upserts fake row; both verified sessions returned identical scores (temperature=0 + similar transcripts likely cause); `requirements.txt` does not pin torch cu126; `SQLSessionStore.persist_event_log` is dead but ten_compat.py must be checked before removal; `close_publisher()` not wired to lifecycle; `.codegraph/` and `.cursor/` not in `.gitignore`.
* Produced prioritized patch list: 7A (.gitignore), 7B (CUDA requirements), 7C (multi-session live test), 7D (grader_version API), 7E (dead code), 7F (publisher shutdown).

### Task 16: Patch 7A — Ignore Local IDE Artifacts (commit `ec94d10`).
* Added `.codegraph/` and `.cursor/` to `.gitignore` under the IDEs section.
* No runtime code changed. Working tree is clean after this commit.

### Task 17: Patch 7B — CUDA/cu126 Reproducibility File.
* Created `services/core-api/requirements-torch-cu126.txt` recording the known-working PyTorch cu126 stack.
* Install order: `requirements-torch-cu126.txt` first, then `requirements.txt`.
* No packages installed/uninstalled. No venv modified. No runtime source changed.
* Fresh-venv rebuild not tested; reproducibility claim is based on recording known-working state.

### Task 18: Patch 7C — Multi-Session Real Groq Grading Stability Test.
* Ran Session A (suffix `f56364d6`, 2 user turns) and Session B (suffix `98a58d10`, 10 user turns) through normal RabbitMQ consume-loop with `GRADING_PROVIDER=llm`. Both returned structurally valid `llm_grader.v1` rows.
* Groq HTTP 200 for both. No `grading.llm_failed_fallback`. Queue drained to `messages=0` after each worker run. Worker started exactly once per session. Exit code 124 (idle timeout) expected and observed.
* Session A scores: `overall=2.95`, `fluency=4.00`, `grammar=2.00`, `vocab=3.00`, `feedback_len=173`.
* Session B scores: `overall=2.95`, `fluency=4.00`, `grammar=3.00`, `vocab=2.00`, `feedback_len=226`.
* Unsafe session `af661bda` (`status=ready`, `ended=False`, `user_turn_count=0`) correctly identified and excluded before any worker run.
* Verdict: INVESTIGATE. Pipeline reliability confirmed across multiple sequential runs. Score sensitivity unresolved — no dimension changed ≥1.5 across any session pair; `overall=2.95` identical across all four graded sessions (Patches 3, 4, 7C-A, 7C-B).
* SRE conclusion: no further Groq calls until prompt/rubric and STT transcript quality are audited in Patch 7D.

### Task 19: Patch 7D-A/B — Grader Calibration and Sanitized Transcript Review.
* **7D-B (synthetic calibration test):** Direct call to `llm_grade_with_client` with a synthetic strong transcript — no DB write, no RabbitMQ, no worker, 1 Groq call. Returned `fluency=8.0`, `grammar=9.0`, `vocab=8.5`, `overall=8.52`. `high_score_pass=True`. Prompt/model can produce high scores; prompt anchoring and model floor ruled out.
* **7D-A (sanitized transcript review):** SELECT-only DB query extracting USER_TURN text for all four live sessions. No `raw_backup_json` printed. Key findings:
  * `a3d35b36`: 15 turns, 74 words — fragmented informal chat, avg 23 chars/turn.
  * `218666a0`: 4 turns, 23 words — very short, clear STT artifact ("first hot. Yes, first hot.").
  * `f56364d6`: 2 turns, 14 words — only partial script captured; "buyed" → "apply" (STT misrecognition).
  * `98a58d10`: 10 turns, 92 words — severe STT noise first half ("last whisker", "first pressed pull and break and break and break"), cleaner second half.
* **Root-cause confirmed:** STT/transcript quality is the primary cause of repeated `overall=2.95`. Grader scored each session correctly for what it received. Prompt calibration and model floor ruled out.
* **Remaining structural gap:** grammar and vocab both weighted 0.35 — g/v swaps produce identical overall. Not root cause, but masks sub-score sensitivity.
* **SRE conclusion:** Do not expand `GRADING_PROVIDER=llm` use until transcript quality gate is implemented (Patch 7E). Sessions with 14 words or severe STT noise currently receive authoritative numeric scores without confidence indication.

### Task 20: Patch 7E Audit/Design — Transcript Quality Gate.
* Conducted 13-section SRE-level audit: gate placement comparison (Options A–E), threshold recommendation, insufficient-evidence behavior comparison, schema constraints, API/UI impact, idempotency, observability plan, mocked test plan, rollback plan, risk register, minimal implementation proposal.
* **Gate placement:** `worker.py` after `has_student_turns` guard (Option B) — single-file change, prevents Groq spend before any network call, testable with `FakeRepository`, no DB changes.
* **Threshold:** `GRADING_MIN_STUDENT_WORDS=25` — captures `f56364d6` (14w) and `218666a0` (23w) as below; `a3d35b36` (74w) and `98a58d10` (92w) pass.
* **Behavior:** early return, no upsert — `GradingRead` requires non-nullable `float` scores; 404 from API already handled by UI as "pending" with retry button.
* **Log event:** `grading.skipped_insufficient_evidence session_id=... user_turn_count=... student_word_count=... min_student_words=...` (no transcript text).
* **No DB schema, API, UI, or migration changes** in the implementation patch.
* Audit/design only — no Groq calls, no worker, no DB writes.

### Task 21: Patch 7E Implementation — Runtime Transcript Quality Gate (commit `8b16c50`).
* Implemented word-count gate in `services/grading-worker/src/worker.py` (+12 lines after `has_student_turns` guard).
* `GRADING_MIN_STUDENT_WORDS` read at call time via `os.getenv()` (not module import) so `monkeypatch.setenv` works in tests.
* Double-safety cast: `int(quality_signals.get("student_word_count", 0) or 0)` guards against `None` or non-numeric values.
* Updated `services/grading-worker/tests/test_worker_patch2a.py`: existing `_SESSION_ROW_WITH_TURNS` fixture text updated to 34 student words; `_SESSION_ROW_SHORT_WORDS` added (4 words); 3 new gate tests added (skip, pass, gate-disabled-at-zero).
* **Verification:** `py_compile` 5 modules passed; 60/60 mocked tests passed (`test_worker_patch2a.py` 21 + `test_llm_grader.py` 17 + `test_grading_provider_client.py` 22). No live services, no Groq, no DB, no RabbitMQ.
* Committed as `8b16c50`. No docs staged in that commit (docs follow in this task).

### Task 22: Patch 7F Audit/Design — Insufficient-Evidence API/UI Status and Operational Visibility.
* Conducted 13-section SRE-level audit: API contract options (new endpoint vs modifying existing `/grading`), DB approach options (new column, separate table, sentinel row, dynamic inference), `GradingRead` non-nullable float constraint analysis, UI state branching, backward compatibility, observability, threshold-change re-evaluation, and idempotency.
* **Key finding:** DB score columns are `NUMERIC(4,2)` without NOT NULL — nullable at DB level, but `GradingRead.overall_score: float` is the binding non-nullable constraint. Adding a null-score "skip" row would require an `Optional[float]` refactor of `GradingRead` or a separate schema — both are high-risk to existing consumers.
* **No `grading_status` column** in `grading_results`. No Alembic or migration runner in repo — only `infrastructure/db-init/01-init.sql`. No `grader_version` DB column — stored only inside `detailed_corrections[0]` JSONB.
* **Recommended Path B:** New read-only `GET /sessions/{id}/grading/status` endpoint computing status dynamically from `grading_results` existence + `raw_backup_json` word count. No DB migration. No worker changes. `GradingRead` untouched.
* Audit/design only — no Groq calls, no worker, no DB writes.

### Task 23: Patch 7F-1 Implementation — Grading Status Endpoint and Insufficient-Evidence UI (commit `ddb46ec`).
* Added `GradingStatusRead` schema to `services/core-api/src/schemas/session.py`: `session_id`, `status` (str), `student_word_count` (int | None).
* Added three pure helpers to `services/core-api/src/services/session_service.py`: `_parse_raw_backup_events`, `_compute_student_word_count`, `_get_min_student_words`. Handle SQLAlchemy (decoded JSONB) and asyncpg (string JSONB) shapes; malformed `GRADING_MIN_STUDENT_WORDS` falls back to 25.
* Added `get_session_grading_status()` service function: LEFT JOIN query, dynamic status inference (graded / insufficient_evidence / pending), logs `grading.status_inferred`.
* Added `GET /{session_id}/grading/status` route to `services/core-api/src/api/v1/sessions.py` before existing `/grading` route.
* Updated `fetchAndShowGrading` in `services/core-api/src/static/index.html` to call `/grading/status` first: `insufficient_evidence` → "Not enough speech to grade. Try a longer session." (no Retry); `pending` → existing Retry flow; `graded` → calls `/grading` and renders score tiles as before.
* **Verification:** `py_compile` OK (3 modules); import smoke OK (routes verified, `GradingRead.overall_score` still `float`, `GradingStatusRead` has `student_word_count`); helper smoke OK (5 assertions, all input shapes); UI grep OK (4 patterns confirmed). No Groq, no worker, no DB writes, no RabbitMQ, no sessions.
* Committed as `ddb46ec`.

### Task 24: Patch 7F-2 — Read-only Smoke Test (PASS).
* Verified Patch 7F-1 endpoint and UI against live core-api using existing DB data. READ-ONLY throughout.
* **Static checks:** `py_compile` OK (3 modules); import smoke confirmed `has_status_route=True`, `has_grading_route=True`, `GradingRead.overall_score` is `float`, `GradingStatusRead` has `student_word_count`.
* **DB candidate discovery (SELECT-only):** graded=`98a58d10` (wc=92, has_grading=True); insufficient_evidence=`3d1eca15` (wc=5, has_grading=False); pending=`49639bde` (wc=None, has_grading=False). Real candidates for all three statuses — no mock needed.
* **API smoke (5/5):** `GET /grading/status` → `graded` (HTTP 200); `GET /grading` → scores numeric, `llm_grader.v1`, feedback_len=226 (HTTP 200); `GET /grading/status` → `insufficient_evidence` wc=5 (HTTP 200); `GET /grading` for insufficient session → 404 (correct, no row); `GET /grading/status` → `pending` wc=None (HTTP 200).
* **UI smoke (13/13 PASS):** Playwright 1.60 + headless Chrome. Port 8080 not running — UI loaded via `file://…/static/index.html` with `luve.control.coreApiUrl` localStorage override to `http://localhost:8000`; API calls hit live core-api. Assertions: graded score tiles rendered; insufficient message "Not enough speech to grade. Try a longer session." visible; no Retry button in insufficient state; no `/grading` call made after `insufficient_evidence`; Retry button present in pending state.
* **Side effects confirmed absent:** no files modified, no Groq calls, no worker started, no TEN sessions, no DB writes, no RabbitMQ operations (queue `messages=0` pre/post), no secrets/raw data printed.
* **SRE conclusions:** `NULL raw_backup_json` → `pending` (no false insufficient_evidence); `/grading` backward compatibility intact; UI branch prevents retry treadmill.

### Task 25: Patch 7G Audit/Design — Production Hardening for Grading Status, Observability, and Migration Strategy.
* Conducted 13-section production hardening audit for the Patch 7E/7F grading status and quality gate system. Audit/design only — no runtime files modified, no Groq calls, no DB writes, no RabbitMQ operations, no sessions.
* **DB persistence:** Recommended separate `grading_skip_log` table (Option D) — additive, no null-score problem, clean rollback, enables SRE queryability and regrade list sourcing. Options A–C ruled out due to schema blast radius or semantic mismatch.
* **Migration strategy:** No Alembic or migration framework found. Only `infrastructure/db-init/01-init.sql`. Proposed numbered SQL migrations directory (`infrastructure/db-migrations/0001_...`) with idempotent scripts and backup/preflight/verify/rollback requirements.
* **Critical drift (word-count helper):** `_compute_student_word_count` in core-api does not handle the `"event"` field alias (worker checks `event.get("type") or event.get("event")`). Risk: worker skips a session; core-api status infers `"pending"` instead of `"insufficient_evidence"`.
* **Reconciliation scanner critical gap:** `_count_user_turns()` counts USER_TURN events but does not enforce `GRADING_MIN_STUDENT_WORDS`. Running `--execute` with `GRADING_PROVIDER=llm` would submit below-threshold sessions to Groq, undoing the Patch 7E safety gate. **Do not run scanner with `--execute` + `GRADING_PROVIDER=llm` until Patch 7G-4 is merged.**
* **Observability:** Current structured logs sufficient for grep-based ops. Medium-term: Prometheus counters for `grading_jobs_total{outcome}`, `grading_status_requests_total{status}`, `grading_fallback_total`, `grading_queue_depth`.
* **Regrade strategy:** Two scenarios (wrong result, threshold lowered). Both require dry-run default, batch-size ≤ 20, rate-limit, `grading_skip_log` as source for skipped candidates.
* **8080/control-center:** No Nginx in docker-compose, no StaticFiles in main.py. Fix planned (Patch 7G-6) must pair with CORS lockdown.
* **API/UI hardening:** `Literal[...]` status type, unknown-status `else` fallback, 401 handling (Patch 7G-3). No `GradingRead` changes.
* **Fake fallback (production blocker):** `grading.llm_failed_fallback` silently upserts fake scores. Fix: `GRADING_FAKE_FALLBACK` env gate + DLQ (Patch 7G-5 + 7G-9).
* **Security/privacy:** CORS `allow_origins=["*"]` is a production blocker; rate limiting on `/grading/status` needed before broader use; transcript data not exposed in `/grading/status` response; session ownership enforced.
* **Production readiness checklist:** 14-item checklist recorded in PROJECT_STATE.md Section 19.
* **Recommended sequence (strictly sequential — do not run in parallel):** commit 7G-1 docs → implement + commit 7G-2 → implement + commit 7G-3 → 7G-4 → 7G-5 → 7G-6 → 7G-7 → 7G-8 → 7G-9. Each patch committed independently to keep blast radius small, rollback simple, and test failures attributable to a single change.

### Task 26: Patch 7G-2 Implementation — Word-Count Parity Fix (commit `24fef0b`).
* Fixed `_compute_student_word_count()` in `services/core-api/src/services/session_service.py` to accept `USER_TURN` events keyed by both `"type"` and `"event"`, matching `evaluation_input_builder` semantics.
* Broadened event and payload type guards from `dict`-only to `Mapping`-compatible (covers `UserDict` and other Mapping subclasses).
* Preserved `raw_backup_json is None` → `None` (conservative "pending" fallback — prevents false `insufficient_evidence` for sessions with no event log).
* No pytest harness found in `services/core-api/` (only STT GPU hardware scripts). Verified via py_compile + 8-case inline helper parity smoke run from within the core-api venv.
* **Verification:** py_compile OK; helper smoke 8/8 PASS — `type_key_user_turn`, `event_key_user_turn`, `mixed_type_and_event`, `json_string_event_key`, `double_encoded_event_key`, `mapping_like_event_payload`, `none_raw`, `invalid_json`.
* No Groq calls, no worker/core-api started, no DB writes, no RabbitMQ operations, no sessions.

### Task 27: Patch 7G-3 Implementation — Status Literal Schema and UI Defensive Handling (commit `55a4d02`).
* Changed `GradingStatusRead.status` from `str` to `Literal["graded", "pending", "insufficient_evidence"]` in `services/core-api/src/schemas/session.py`. Pydantic now raises `ValidationError` on unexpected values.
* Added 401/403 auth guard in `fetchAndShowGrading` in `services/core-api/src/static/index.html` — after the 404 check, before the generic `!statusRes.ok` check. Shows "Session expired or unauthorized. Please refresh your token and try again." and returns before `/grading`.
* Added unknown-status fail-closed guard after the `pending` block — `status !== "graded"` shows "Unknown grading status. Please refresh and try again." and returns before `/grading`.
* `GradingRead`, `student_word_count`, `/grading` endpoint, and all three existing UI branches (`insufficient_evidence`, `pending`, `graded`) preserved unchanged.
* **Verification:** py_compile OK; schema Literal smoke — `schema_literal_smoke_ok`, `grading_score_type_is_float: True`; UI grep confirmed all 5 branches; Playwright route-intercept branch smoke **22/22 PASS** — 6 cases (401, 403, unknown_status, insufficient_evidence, pending, graded), dummy token, `file://` page, no live API calls.
* No Groq calls, no worker/core-api started, no DB writes, no RabbitMQ operations, no sessions.

### Task 28: Patch 7G-4 Audit/Design — Reconciliation Scanner Threshold Parity.
* **Audit/design only — no runtime files modified, no scanner executed, no DB writes, no Groq calls.**
* Confirmed: `_count_user_turns()` in both `reconciliation_scanner.py` and `backfill_completed_sessions.py` has three defects: checks only `"type"` key (not `"event"` alias), uses `isinstance(e, dict)` not `Mapping`, counts turns not words. Neither script enforces `GRADING_MIN_STUDENT_WORDS`.
* Scanner execute path calls `process_session_completed_job()` directly — no RabbitMQ publish. Worker Patch 7E gate fires and prevents Groq calls today. Scanner prints misleading `ok` (worker returns `None` on skip, no exception) and sessions are perpetually re-selected (no grading row = always a candidate).
* Threshold parity matrix documented: worker/`evaluation_input_builder` and core-api (`_compute_student_word_count` after 7G-2) both handle `type`/`event` aliases and Mapping; scanner/backfill do not.
* Shared eligibility helper proposed: `services/grading-worker/src/session_eligibility.py` — pure Python, no DB/RabbitMQ, handles all event-shape variants.
* Recommended sequence: 7G-4A (helper + tests only) → 7G-4B (scanner dry-run wired) → 7G-4C (scanner execute gated) → 7G-4D (backfill parity).
* Full findings recorded in `docs/ai/PROJECT_STATE.md` Section 19 Patch 7G-4 subsection.

### Task 29: Patch 7G-4A Implementation — Session Eligibility Helper and Unit Tests (commit `462f5a4`).
* Added `services/grading-worker/src/session_eligibility.py` — pure Python eligibility helper; stdlib-only imports (`json`, `collections.abc`, `dataclasses`, `typing`); no DB/RabbitMQ/runtime imports.
* Helper exports: `DEFAULT_MIN_STUDENT_WORDS=25`, `GradingEligibility` frozen dataclass (`eligible`, `reason`, `user_turn_count`, `student_word_count`), `parse_raw_backup_events`, `get_event_kind`, `get_event_text`, `count_user_turns`, `count_student_words`, `evaluate_grading_eligibility`. Private helper `_decode_event` handles per-event JSON strings.
* Reason codes: `eligible`, `no_raw_backup`, `invalid_raw_backup`, `no_user_turns`, `insufficient_words`.
* Handles: `type`/`event` aliases, Mapping-like events/payloads (`UserDict`, `asyncpg.Record`), `list[dict]`, JSON array string, per-event JSON object strings, `None`, invalid JSON, below/at/above threshold, `min_student_words=0` gate-disable.
* `GradingEligibility` never exposes transcript text — verified by `test_evaluate_result_has_no_transcript_text`.
* Added `services/grading-worker/tests/test_session_eligibility.py` — 45 unit tests; no DB, no RabbitMQ, no live services.
* **Verification:** py_compile OK; 45/45 targeted tests passed; 105/105 full suite passed (60 pre-existing + 45 new); import smoke `eligibility_import_smoke_ok`; static safety check — `session_eligibility` referenced only in helper file and tests; not wired into scanner, backfill, or worker.
* No Groq calls. No services started. No DB writes. No RabbitMQ operations. No scanner/backfill execution. No sessions.

### Task 30: Patch 7G-4B Implementation — Scanner Dry-Run Categorization (commit `5714ae4`).
* Wired `reconciliation_scanner.py` dry-run path to `evaluate_grading_eligibility` from `src.session_eligibility`.
* Added `_parse_min_student_words_env(value: str | None) -> int` pure helper (None/negative/non-numeric → default; 0 allowed).
* Restructured candidate loop: `if not args.execute: ... continue` short-circuits before `_count_user_turns` — execute path code untouched.
* Added counters: `skipped_invalid_raw`, `skipped_no_user_turns`, `skipped_insufficient_words` (dry-run only).
* Added `--min-student-words N` CLI flag (default: `GRADING_MIN_STUDENT_WORDS` env or 25).
* Updated dry-run `would` output to include `user_turns=` and `student_words=`; updated dry-run summary to include per-reason skip counts.
* Added `services/grading-worker/tests/test_reconciliation_scanner_patch7g4b.py` — 25 mocked unit tests; no DB/RabbitMQ/live services.
* **Verification:** py_compile OK; 25/25 new tests passed; 130/130 full suite passed; execute path behavior confirmed unchanged (structural gap test documents that `_count_user_turns` does not handle event-key alias — Patch 7G-4C scope).
* No Groq calls. No services started. No DB writes. No RabbitMQ operations. No scanner `--execute`. No sessions.

### Task 31: Patch 7G-4C Implementation — Scanner Execute-Path Eligibility Gate (commit `7dcc9e8`).
* Gated scanner execute path: `evaluate_grading_eligibility` called before `process_session_completed_job` for all candidates; ineligible sessions skipped with per-reason counters and `continue`.
* Skip reasons dispatched in execute path: `no_raw_backup`, `invalid_raw_backup`, `no_user_turns`, `insufficient_words`.
* Unified execute and dry-run skip summary bucket naming: `skipped_no_raw_backup`, `skipped_invalid_raw`, `skipped_no_user_turns`, `skipped_insufficient_words`.
* `_count_user_turns` retained but no longer called in the main candidate loop; superseded by `evaluate_grading_eligibility`. Docstring updated.
* Added `test_reconciliation_scanner_patch7g4c.py` — 11 mocked unit tests; no DB/RabbitMQ/Groq/live services.
* **Verification:** py_compile OK; targeted 11 passed; full suite 141 passed; no live scanner/backfill `--execute` run.
* Closes operational gap: scanner no longer prints `ok` for sessions the worker silently skips; prevents ineligible sessions from reaching `process_session_completed_job`.

### Task 32: Patch 7G-4D Implementation — Backfill Execute-Path Eligibility Gate (commit `80d4db7`).
* Gated backfill execute and dry-run paths: `evaluate_grading_eligibility` called before `process_session_completed_job` for all candidates; ineligible sessions skipped with per-reason counters and `continue`.
* Added local `_parse_min_student_words_env` helper (matching scanner; not cross-imported).
* Added `--min-student-words N` CLI flag (default: `GRADING_MIN_STUDENT_WORDS` env or 25).
* Updated `--no-require-user-turn` help text: flag retained for CLI backward compatibility only; eligibility helper now enforces user-turn presence.
* Updated `--include-empty-raw` help text: NULL raw sessions selected by this flag are still gated by `evaluate_grading_eligibility(None)` → `no_raw_backup`.
* Counter names aligned with scanner: `skipped_no_raw_backup`, `skipped_invalid_raw`, `skipped_no_user_turns`, `skipped_insufficient_words`.
* `_count_user_turns` retained with updated docstring (superseded by `evaluate_grading_eligibility` in Patch 7G-4D).
* Added `test_backfill_completed_sessions_patch7g4d.py` — 13 mocked unit tests; no DB/RabbitMQ/Groq/live services.
* **Verification:** py_compile OK; targeted 58/58 passed (`test_session_eligibility.py` + `test_backfill_completed_sessions_patch7g4d.py`); full grading-worker suite 154/154 passed using `services/core-api/venv/bin/python3 -m pytest tests/ -q`. An earlier run via `~/.local/bin/pytest` produced 32 failures due to missing `pytest-asyncio` in that runner — a runner issue, not a code issue. `de6c6d1` corrected the earlier inaccurate verification docs; this approved-env rerun followed. No backfill/scanner `--execute` run.
* Patch 7G-4 series complete and verified.

### Task 34: Patch 7G-6 Implementation — StaticFiles / Control-Center Serving and CORS Lockdown (commit `7d522d9`).
* Extracted CORS origins into standalone `src/core/cors.py` helper: 8-origin local default (no wildcard), `CORS_ALLOW_ORIGINS` env var override, comma-split/trim/drop-empty parsing, explicit `"*"` opt-in.
* Updated `src/main.py`: `allow_origins=get_cors_allow_origins()`, `allow_credentials=False`, `StaticFiles` at `/static`, `/control-center` FileResponse route using `Path(__file__).parent / "static"`.
* Created `tests/__init__.py` and `tests/test_main_patch7g6.py` (15 tests): 8 CORS helper unit tests, 5 StaticFiles/route tests via throwaway app factory, 2 CORS preflight tests.
* Throwaway app factory avoids `get_settings()` ValidationError at import time — `src.main` never imported in tests.
* No new dependencies: Starlette 1.0.0 uses `anyio` (already installed transitively via `uvicorn[standard]`).
* **Verification:** py_compile OK; 15/15 mocked tests passed. No Groq, DB, RabbitMQ, live services.
* **Not claimed:** browser E2E via `/control-center` URL not verified in this patch; TEN gateway CORS not addressed; no HTTPS/production domain origins; no DLQ yet.

### Task 33: Patch 7G-5 Implementation — Fake Fallback Env Gate (commit `dcdf9ba`).
* Audited `process_session_completed_job` fake fallback path: broad `except Exception` silently called `fake_grade()` on every LLM failure, upserted fake scores indistinguishable from real `llm_grader.v1` rows.
* Added `_get_fake_fallback_enabled() -> bool` to `worker.py`: reads `GRADING_FAKE_FALLBACK` env, default false; truthy values: `1`, `true`, `yes`, `on` (case-insensitive).
* Gated `except Exception` block: fallback disabled (default) → logs `grading.llm_failed_no_fallback` at ERROR and re-raises; no `fake_grade()` call, no DB upsert. Fallback enabled (`GRADING_FAKE_FALLBACK=true`) → preserves previous `grading.llm_failed_fallback` WARNING + `fake_grade()` path.
* `GRADING_PROVIDER=fake` and skip gates (insufficient evidence, no user turns) unchanged.
* Added `test_worker_patch7g5.py` — 29 mocked test cases; updated 4 legacy tests in `test_worker_patch2a.py` with `GRADING_FAKE_FALLBACK=true` to preserve their intent.
* **Verification:** py_compile OK; targeted 50/50 passed; full grading-worker suite 183/183 passed. No live Groq, DB, RabbitMQ, services/TEN.
* Queue note: exception escaping `process_session_completed_job` should cause `aio_pika`'s `message.process(requeue=False)` to NACK; actual DLQ delivery depends on RabbitMQ DLX configuration not declared in this codebase.

---

## Current Task
**Patch 7G-7: Migration Strategy Audit/Design — Numbered Migration Directory**

**Status: Not yet started. AUDIT/DESIGN ONLY. Do not implement, modify, stage, or commit during this phase.**

**Recommended model:**
* **Sonnet high:** focused audit of existing DB init structure with clear prior art.
* **Sonnet max:** if output is ambiguous, surprising schema findings, or migration safety analysis requires broader architecture judgment.
* **Opus high/max:** only if broader DB migration framework decisions (Alembic vs. manual) require deeper architectural trade-off analysis.

**Background:**
No Alembic or migration framework exists in the repo. Only `infrastructure/db-init/01-init.sql` (run once by Docker `entrypoint-initdb.d`). No `alembic_version` table. Patch 7G-8 (`grading_skip_log` table) and future schema changes require a safe, auditable migration path before any `CREATE TABLE` or `ALTER TABLE` is applied to the production database.

**Goal:** Audit existing DB initialization structure; design a minimal numbered SQL migration directory proposal; produce an audit/design output before any files are created or modified.

Questions to answer:
* What tables and constraints exist in `infrastructure/db-init/01-init.sql`?
* Is `alembic_version` table absent from the DB (confirm from prior audit)?
* What would `infrastructure/db-migrations/0001_grading_skip_log.sql` contain?
* What preflight/backup/verify/rollback requirements must each migration script satisfy?
* Is any Alembic tooling present or worth adding at this stage?
* What is the safe execution order for `db-migrations/` scripts alongside `db-init/`?

**Hard safety rules for this task:**
* AUDIT/DESIGN ONLY — do not create migration files, modify `db-init/`, modify any service source, stage, or commit.
* Do not run `psql`, `alembic`, or any DB-modifying command.
* Do not start services, run Groq, publish RabbitMQ messages, or touch TEN/browser.
* Do not print secrets, DATABASE_URL values, or DB credentials.
* Allowed read paths: `infrastructure/`, `services/core-api/src/`, `services/grading-worker/src/`, `docs/ai/`. No write paths.

## Out of Scope (requires separate approved prompt)
* Patch 7G-7 implementation (create migration files, modify `db-init/`) — audit/design only in current task.
* Patch 7G-8 (`grading_skip_log` implementation — after 7G-7 approved).
* Patch 7G-9 (DLQ, Prometheus counters, regrade tooling).
* Transactional outbox implementation.
* New DB schema or migration files (blocked until Patch 7G-7 design approved).
* Reconciliation scanner execution or modification.
* Removing `SQLSessionStore.persist_event_log` dead code.
* Removing DEV PREVIEW badge from UI.
* Wiring `close_publisher()` into shutdown.
* Browser E2E smoke of `/control-center` HTTP route (deferred from Patch 7G-6).

## Protected Runtime Files
Protected runtime files and canonical guardrails are maintained in `CLAUDE.md` and `docs/ai/CLAUDE_CODE_HANDOFF.md`. Do not modify runtime files, DB schema/migrations, env files, secret/local payload files, or TEN/VAD/STT/TTS/WebRTC files unless a future prompt explicitly authorizes it.
