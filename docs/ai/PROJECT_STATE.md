# LUVE Project State

This file is the current source of truth for mutable repo state in `docs/ai`.

- Read this file first for current baseline, verified evidence, and known limitations.
- Treat `NEXT_TASK.md` as a scoped task memo, not as global repo state.
- Treat `CLAUDE_CODE_HANDOFF.md` as architecture/historical onboarding context, not mutable state.

## 1. Current Expected Git State

* **Worktree:** No tracked modifications; only untracked IDE artifacts (`.codegraph/`, `.cursor/`).
* **Latest runtime/tooling baseline:** `1cae30b` — feat(grading-worker): add Groq grading provider client.
* **Source of Truth:** All python services runtime files in `services/core-api/` and `services/grading-worker/` are committed and match the local baseline.

## 2. Latest Important Commits

* `1cae30b` - feat(grading-worker): add Groq grading provider client (`GroqClient` via raw `httpx` REST; `_build_grader_client()` reads `LLM_PROVIDER`/`GROQCLOUD_API_KEY`/`GROQ_MODEL`/`GROQ_TIMEOUT_SECONDS`; `httpx` declared in `requirements.txt`; 57/57 mocked tests pass; real Groq live test not yet run).
* `06acf97` - feat(grading-worker): add safe grading provider dispatch (`GRADING_PROVIDER` env-flag dispatch with fake default; `GRADING_PROVIDER=llm` falls back to fake until real provider client exists; no-user-turn sessions skip without upsert; 34/34 mocked tests pass).
* `675e3a2` - feat(grading-worker): add offline LLM grader scaffold (loosen `grader_version` Literal, add `llm_grader.py` prompt builder + response parser/validator, add 22 mocked tests; worker still uses `fake_grader.v1` only).
* `3da235c` - feat(core-api): add end-of-session grading analysis API and UI (`GradingRead` schema, `GET /api/v1/sessions/{session_id}/grading` endpoint, Session Analysis card in control center UI with dev-preview badge and `escapeHtml` sanitization).
* `fc18916` - feat(grading-worker): add completed session reconciliation scanner (one-shot, dry-run default, `--grace-minutes` grace window, no RabbitMQ dependency for recovery).
* `440ff98` - fix(core-api): persist empty event logs as arrays (`_persist_event_log` always writes `raw_backup_json`; empty event logs now store `[]` instead of NULL).
* `da4a0d9` - docs(ai): record raw_backup_json NULL audit findings.
* `c5cf2c3` - test(grading-worker): add completed session backfill script (dry-run-first, USER_TURN filter, idempotent upsert).
* `9ec6c05` - docs(ai): add Claude coding guardrails (CLAUDE.md with LUVE-specific priority header).
* `aa8a9e9` - docs(ai): add Claude Code handoff state.
* `795fafe` - fix(core-api): reuse RabbitMQ session event publisher (Lazy connection/channel caching).
* `0c09f5b` - test(core-api): improve stress harness cooldown checks (Adds cooldown snapshots before CPU idle verification).
* `bddfa10` - test(core-api): add realtime WebRTC stress harness (Adds `scripts/realtime_stress.py`).
* `ff5d316` - chore(core-api): add TEN runtime health diagnostics (Adds `GET /rtc/health`).

## 3. Verified Reliability Evidence (Local/Dev)

* **`noise` STT-only (no TTS):** 10/10 runs successfully passed.
* **`short_english` LLM (no TTS):** 10/10 runs successfully passed.
* **`short_english` LLM+TTS:** 5/5 runs successfully passed.
* **TTS long-drain:** 5/5 runs successfully passed (verified `active_sessions_after_cooldown=0` and low CPU usage after cooldown).
* **RabbitMQ Resiliency:**
  * **UP test:** Completed sessions are successfully published to `luve.session.completed`.
  * **DOWN test:** Session end and database persistence complete successfully with grace when Broker is down; publish fails non-blocking on best-effort timeout.
  * **RECOVERY test:** Session completion publishing resumes instantly and successfully once RabbitMQ comes back online.

## 4. Grading Backfill Execution Evidence (Local/Dev)

* **Initial audit counts:** `completed_sessions=218`, `grading_results=2`, `completed_missing_grading=216`.
* **Backfill runs:** Executed in controlled increments (`--limit 1`, `5`, `20`, `50`, `50`) against local Postgres with default filters (raw_backup_json IS NOT NULL + at least one accepted USER_TURN).
* **Final DB state after full backfill:**
  * `grading_results` total: **138**
  * `completed_missing_grading`: **80**
  * Remaining 80 sessions all have `raw_backup_json IS NULL` (no event log; not eligible for default backfill).
  * `missing_has_raw=0`: no eligible sessions with event data were skipped.
* **Idempotency verified:** Rerun targeting an already-graded session produced `candidates_seen=0`; no duplicate row was created. The `LEFT JOIN … gr.session_id IS NULL` filter in the candidate query excluded it before any grading logic ran.
* **Backfill filter confirmed:** Default filter correctly excluded empty/noise/rapid-disconnect stress sessions with no accepted speech turns.

## 5. Patch 1 Offline LLM Grader Scaffold (commit `675e3a2`)

**What exists:**
* `services/grading-worker/src/llm_grader.py` — provider-agnostic offline scaffold. No external/provider/network imports. Contains:
  * `build_grading_prompt(EvaluationInput) -> str` — formats transcript + rubric; requests JSON-only response.
  * `parse_grading_response(raw_json, *, session_id) -> GradingResult` — strict JSON parse, required-field check, `[0, 10]` range enforcement (raises on violation), malformed-correction filtering, overall score computed as `fluency×0.30 + grammar×0.35 + vocab×0.35`.
  * `llm_grade_with_client(EvaluationInput, client) -> GradingResult` — `GraderClient` Protocol seam for future provider injection; raises `LLMGraderError` if zero student turns.
  * `LLMGraderError` — typed exception for all parse/validation failures.
* `services/grading-worker/src/contracts.py` — `GradingResult.grader_version` loosened from `Literal["fake_grader.v1"]` to `str` with default `"fake_grader.v1"`.
* `services/grading-worker/tests/` — 22 mocked tests (no real API calls).

**What is NOT yet done:**
* `llm_grader.py` is **not wired into `worker.py`**. The live grading path calls `fake_grade()` only.
* No real LLM API has been called.
* No `grading_results` row has been written by `llm_grader.v1`.
* UI still shows "DEV PREVIEW — Simulated Grading" and `fake_grader.v1` scores.
* No provider client implementation exists. Patch 2 must add it.

**Verification evidence:**
* `py_compile` pass on all 4 Patch 1 files.
* 22/22 mocked `llm_grader` tests pass.
* `fake_grader` regression pass — `grader_version="fake_grader.v1"` unchanged.
* `grep` confirmed: no `httpx`, `groq`, `google`, `openai`, `anthropic`, `requests`, `aiohttp` imports in `llm_grader.py`.

**Local venv drift note:**
`pytest` and `pytest-asyncio` were installed into `services/core-api/venv` during Patch 1 verification. This is local environment drift only — not a git-tracked change and not in any `requirements.txt`. It has no effect on the production grading worker runtime.

## 6. Patch 2A Safe Grading Provider Dispatch (commit `06acf97`)

**What was added:**
* `worker.py` now supports `GRADING_PROVIDER` env-flag dispatch:
  * Unset or `"fake"` → `fake_grade()` as before.
  * `"llm"` → attempts `llm_grade_with_client()`; currently falls back to `fake_grade()` because `_build_grader_client()` raises `LLMGraderError` (real provider not yet implemented).
  * Unknown value → `WARNING` log + fallback to `"fake"`.
* `process_session_completed_job` now returns early (no upsert) for sessions with zero accepted student turns. Previously these sessions wrote floor-score fake rows; now they produce no `grading_results` row. The API returns 404; the UI shows "Grading pending." This is consistent with the established backfill/reconciliation policy.
* Completion log updated: now emits `provider_requested=` and `grader_version=` instead of the hardcoded `fake_grader=true`.
* `grader_info` marker prepended to `detailed_corrections` JSONB on successful LLM grading — queryable without a schema migration.
* 12 new mocked worker dispatch tests added.

**What is NOT yet done (at time of Patch 2A):**
* No real LLM provider client existed. `GRADING_PROVIDER=llm` was structurally wired but always fell back to fake.
* No `httpx` or provider SDK added to `requirements.txt`.
* No `services/core-api/` or DB schema changes.
* No real LLM API calls had been made by the grader.
* UI still shows "DEV PREVIEW — Simulated Grading" and `fake_grader.v1` scores.
* Patch 2B added exactly one provider client — see section 7 below.

**Verification evidence:**
* `py_compile` pass on `worker.py` and `tests/test_worker_patch2a.py`.
* 34/34 mocked tests pass (`test_llm_grader.py` 22 + `test_worker_patch2a.py` 12).
* `grep` confirmed: no `httpx`, `requests`, `aiohttp`, `google`, `groq`, `openai`, `anthropic` imports in `worker.py` or the new test file.

## 7. Patch 2B Groq Grading Provider Client (commit `1cae30b`)

**What was added:**
* `services/grading-worker/src/grading_provider_client.py` — `GroqClient` class:
  * Raw `httpx.AsyncClient` POST to `https://api.groq.com/openai/v1/chat/completions` (OpenAI-compatible endpoint; no Groq SDK, no OpenAI SDK).
  * Constructor validates `api_key` (blank → error), `model` (blank → error), `timeout_seconds` (≤0 → error). No env-var reads inside the class.
  * `grade(prompt) -> str` builds Authorization header and request body, posts, extracts `choices[0]["message"]["content"]`, strips whitespace.
  * All `LLMGraderError` messages are safe: no API key, prompt, transcript, response body, Authorization header, or full URL logged.
* `services/grading-worker/requirements.txt` — `httpx>=0.27,<1` declared (was already installed in venv as transitive dep; now declared for production correctness).
* `services/grading-worker/src/worker.py` — `_build_grader_client()` now reads:
  * `LLM_PROVIDER` (default `"groq"`): any value other than `"groq"` raises `LLMGraderError` → falls back to fake.
  * `GROQCLOUD_API_KEY`: absent or blank raises `LLMGraderError` → falls back to fake.
  * `GROQ_MODEL` (default `"llama-3.1-8b-instant"`).
  * `GROQ_TIMEOUT_SECONDS` or `LLM_TIMEOUT_SECONDS` (default `"20.0"`): non-float value raises `LLMGraderError` → falls back to fake.
  * Returns a constructed `GroqClient` on success.
* All error paths — missing key, unsupported provider, invalid timeout, `LLMGraderError` from `llm_grade_with_client`, `asyncio.TimeoutError` — fall back to `fake_grade()` through the existing exception handler in `process_session_completed_job`.
* `services/grading-worker/tests/test_grading_provider_client.py` — 17 mocked `GroqClient` tests: 5 constructor validation, 2 success, 2 transport errors, 2 non-2xx, 4 malformed response, 2 security (no key or prompt in exceptions or logs).
* `services/grading-worker/tests/test_worker_patch2a.py` — 6 new worker integration tests for `_build_grader_client()` env wiring added; existing 12 tests updated for Groq hermeticity (delenv `GROQCLOUD_API_KEY` + `LLM_PROVIDER` where needed).

**What is NOT yet done:**
* Real Groq live test has **not** been run. No `grading_results` row has been written by `llm_grader.v1`.
* `GRADING_PROVIDER` default/unset remains `"fake"`. Live path remains fake unless `GRADING_PROVIDER=llm` is explicitly set.
* UI still shows "DEV PREVIEW — Simulated Grading" and `fake_grader.v1` scores.
* No `services/core-api/` or DB schema changes.
* Patch 3 (controlled real Groq test) requires a separate approved prompt.
* **Security:** Any previously exposed Groq API key must be rotated/revoked before running a live test. Refer only to env var names (`GROQCLOUD_API_KEY`) — never print or store key values.

**Verification evidence (pre-commit):**
* `py_compile` pass on all 5 Patch 2B files.
* 57/57 mocked grading-worker tests pass across the full test suite.
* No Gemini references anywhere in grading-worker source or tests.
* No Groq SDK, OpenAI SDK, or other provider SDK import (`httpx` only).
* No real API calls in tests (all via `patch("src.grading_provider_client.httpx.AsyncClient")`).
* No DB or RabbitMQ calls in tests.
* No API key, prompt, transcript, response body, Authorization header, or full URL in any log or exception message.

## 8. Known Limitations & Gaps

* **No Durable Outbox:** If RabbitMQ is down when a session finishes, the session event is not persisted locally for later retry. The reconciliation scanner provides partial automated recovery but is not a transactional outbox; missed sessions require scanner execution (cron or manual) to be graded.
* **Recovery Tools (dev/ops-only):**
  * `backfill_completed_sessions.py` — manual one-shot backfill; verified via historical backfill execution.
  * `reconciliation_scanner.py` — one-shot scanner with `--grace-minutes` grace window; cron-ready; dry-run default; no RabbitMQ dependency; commit `fc18916`. Not a daemon; does not loop internally.
  * Both tools are idempotent (ON CONFLICT DO UPDATE on `grading_results`); neither replaces a transactional outbox.
* **80 Sessions with NULL raw_backup_json (historical):** Audited and root cause confirmed. These pre-patch sessions have `raw_backup_json IS NULL` because the old `_persist_event_log` if/else omitted the column when `_event_log` was empty (noise, rapid-disconnect, silent connections). **Do not backfill or migrate these 80 rows.** They are historical data; `fake_grader.v1` would produce meaningless fixed scores for 0-turn input. Future sessions are no longer affected — see patch `440ff98`.
* **`_persist_event_log` [] patch applied (`440ff98`):** `_persist_event_log` now always writes `raw_backup_json = CAST(:logs AS jsonb)`. Empty sessions store `[]` instead of NULL. Sessions with accepted speech turns are unchanged. DB-verified with monkeypatched RabbitMQ no-op: `raw_backup_json::text = '[]'`, `status = 'completed'`, `ended_at IS NOT NULL`. The backfill script's `IS NOT NULL` filter will now count formerly-NULL-producing sessions as candidates, but the `user_turns=0` Python guard skips them — no false grading results.
* **`SQLSessionStore.persist_event_log` is dead code:** Defined in `services/core-api/src/realtime/session_store.py` with an identical NULL-producing if/else pattern; appears unused by current call-site search. Removal should be a separate cleanup with verification.
* **Connection Shutdown:** `close_publisher()` exists but is not wired into the application shutdown lifecycles; TEN gateway shutdown may print robust connection warning logs.
* **Grading Analysis UI (dev preview only):** `GET /api/v1/sessions/{session_id}/grading` is exposed via the control center Session Analysis card. Returns `GradingRead` (4 scores + summary + corrections + graded_at). Session ownership enforced via `sessions.user_id` JOIN. UI fetch is one-shot with 2s delay after `session_ended` or manual disconnect. Card is labeled "DEV PREVIEW — Simulated Grading" because `fake_grader.v1` scores are not pedagogically valid. Manual browser end-to-end dev-preview test passed for session `26af0fc2-9965-48c6-b509-54e89cc56c8b`: TEN real STT/LLM/TTS ran, `raw_backup_json` persisted 12 events, `session.completed` published, grading result displayed in the Session Analysis card. Real LLM grader remains deferred.
* **Grading Worker:** `GRADING_PROVIDER` dispatch is wired (commit `06acf97`). `GroqClient` now exists (commit `1cae30b`). Default/unset remains `"fake"`. Setting `GRADING_PROVIDER=llm` + `LLM_PROVIDER=groq` + `GROQCLOUD_API_KEY` set will now call Groq — but this live path has **not** been tested yet. Patch 3 (controlled real Groq test) requires a separate approved prompt. Any previously exposed Groq API key must be rotated before Patch 3 runs.
* **VAD & Whisper Warm Policy:** Changing VAD thresholds or disabling Whisper unload is high risk; these changes are not current next tasks.
* **Not Production-Ready:** Code is tuned for local single-session correctness and local stress verification; do not claim production scale.
