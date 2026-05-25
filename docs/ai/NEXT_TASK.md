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

---

## Current Task
**Mode: CODE / NO GROQ / NO DB WRITES / NO WORKER / NO MIGRATION**

### Patch 7G-3 Implementation: Status Literal Schema and UI Defensive Handling

**Goal:** Harden the grading status API schema and UI against unexpected values. Change `GradingStatusRead.status` from `str` to a constrained `Literal` type, add an unknown-status fallback branch in `fetchAndShowGrading`, and add 401/session-expired error handling for the status call.

**Background:**
`GradingStatusRead.status` is currently typed as `str`. An unexpected value from a bug or future code change would pass Pydantic validation silently and reach the UI with no error. The UI `fetchAndShowGrading` also has no `else` fallback after the `pending` branch — a fourth status string falls through with no user-visible update. An expired auth token currently renders no error to the user.

**Constraints:**
* Do not call Groq.
* Do not start the grading-worker.
* Do not run a new TEN session.
* Do not write DB rows.
* Do not add migration files.
* Do not run scanner/backfill.
* Do not touch `.understand-anything/` or `docs/system-map.md`.
* Do not modify `/grading` endpoint or `GradingRead` schema.
* Do not change response JSON values — `"graded"`, `"pending"`, `"insufficient_evidence"` strings must remain identical.
* Do not print secrets, API keys, `DATABASE_URL`, raw transcript, `raw_backup_json`, or auth tokens.

**Implementation scope:**
1. In `services/core-api/src/schemas/session.py`:
   - Change `GradingStatusRead.status: str` to `status: Literal["graded", "pending", "insufficient_evidence"]`.
   - Keep `session_id` and `student_word_count` fields unchanged.
   - Keep `GradingRead` entirely unchanged.
2. In `services/core-api/src/static/index.html`:
   - Add an `else` fallback branch after the `pending` branch in `fetchAndShowGrading` — show a generic error message if status is unrecognised, then return.
   - Add 401 handling for the `/grading/status` fetch: if `statusRes.status === 401`, show a "Session expired — please reload" message and return early.
   - Do not change the `insufficient_evidence`, `pending`, or `graded` branch logic.
   - Do not add new API calls.
3. No DB schema changes. No new endpoints. No migration.

**Verification:**
* `py_compile` on modified Python files.
* Import smoke: confirm `GradingStatusRead.status` is `Literal` (check annotation, not `str`).
* UI grep: confirm `else` fallback branch present; confirm `=== 401` handling present; confirm `insufficient_evidence`, `pending`, `graded` branches unchanged.
* No Groq calls. No worker started. No DB writes. No RabbitMQ. No sessions.

## Out of Scope (requires separate approved prompt)
* Patch 7G-4 (scanner `--min-words` hardening).
* Patch 7G-5 (fake fallback env gate).
* Patch 7G-6 (`StaticFiles` mount, CORS lockdown).
* Patch 7G-7 (migration strategy docs and numbered migration directory).
* Patch 7G-8 (`grading_skip_log` implementation).
* Patch 7G-9 (DLQ, Prometheus counters, regrade tooling).
* Transactional outbox implementation.
* New DB schema or migration files.
* Reconciliation scanner execution or modification.
* Removing `SQLSessionStore.persist_event_log` dead code.
* Removing DEV PREVIEW badge from UI.
* Wiring `close_publisher()` into shutdown.

## Protected Runtime Files
Protected runtime files and canonical guardrails are maintained in `CLAUDE.md` and `docs/ai/CLAUDE_CODE_HANDOFF.md`. Do not modify runtime files, DB schema/migrations, env files, secret/local payload files, or TEN/VAD/STT/TTS/WebRTC files unless a future prompt explicitly authorizes it.
