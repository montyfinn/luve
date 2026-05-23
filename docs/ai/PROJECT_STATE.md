# LUVE Project State

This file is the current source of truth for mutable repo state in `docs/ai`.

- Read this file first for current baseline, verified evidence, and known limitations.
- Treat `NEXT_TASK.md` as a scoped task memo, not as global repo state.
- Treat `CLAUDE_CODE_HANDOFF.md` as architecture/historical onboarding context, not mutable state.

## 1. Current Expected Git State

* **Worktree:** No tracked modifications; only untracked IDE artifacts (`.codegraph/`, `.cursor/`).
* **Latest runtime/tooling baseline:** `675e3a2` — feat(grading-worker): add offline LLM grader scaffold.
* **Source of Truth:** All python services runtime files in `services/core-api/` and `services/grading-worker/` are committed and match the local baseline.

## 2. Latest Important Commits

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

## 6. Known Limitations & Gaps

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
* **Grading Worker:** Currently uses `fake_grader.v1` only. `llm_grader.py` scaffold exists (commit `675e3a2`) but is not yet wired into `worker.py`. Patch 2 (wiring behind `GRADING_PROVIDER` env flag) requires a separate approved prompt.
* **VAD & Whisper Warm Policy:** Changing VAD thresholds or disabling Whisper unload is high risk; these changes are not current next tasks.
* **Not Production-Ready:** Code is tuned for local single-session correctness and local stress verification; do not claim production scale.
