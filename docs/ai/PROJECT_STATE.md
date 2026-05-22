# LUVE Project State

## 1. Current Expected Git State

* **Clean Worktree:** `git status --short` should be empty (clean) after committing these docs.
* **Latest runtime/tooling baseline:** `440ff98` — fix(core-api): persist empty event logs as arrays.
* **Source of Truth:** All python services runtime files in `services/core-api/` and `services/grading-worker/` are committed and match the local baseline.

## 2. Latest Important Commits

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

## 5. Known Limitations & Gaps

* **No Durable Outbox:** If RabbitMQ is down when a session finishes, the session event is not persisted locally for later retry; future sessions will miss grading until manually backfilled again.
* **Backfill Script (dev-only):** `services/grading-worker/scripts/backfill_completed_sessions.py` exists and is verified, but is a manual dev-ops tool, not a production recovery mechanism.
* **80 Sessions with NULL raw_backup_json (historical):** Audited and root cause confirmed. These pre-patch sessions have `raw_backup_json IS NULL` because the old `_persist_event_log` if/else omitted the column when `_event_log` was empty (noise, rapid-disconnect, silent connections). **Do not backfill or migrate these 80 rows.** They are historical data; `fake_grader.v1` would produce meaningless fixed scores for 0-turn input. Future sessions are no longer affected — see patch `440ff98`.
* **`_persist_event_log` [] patch applied (`440ff98`):** `_persist_event_log` now always writes `raw_backup_json = CAST(:logs AS jsonb)`. Empty sessions store `[]` instead of NULL. Sessions with accepted speech turns are unchanged. DB-verified with monkeypatched RabbitMQ no-op: `raw_backup_json::text = '[]'`, `status = 'completed'`, `ended_at IS NOT NULL`. The backfill script's `IS NOT NULL` filter will now count formerly-NULL-producing sessions as candidates, but the `user_turns=0` Python guard skips them — no false grading results.
* **`SQLSessionStore.persist_event_log` is dead code:** Defined in `services/core-api/src/realtime/session_store.py` with an identical NULL-producing if/else pattern; appears unused by current call-site search. Removal should be a separate cleanup with verification.
* **Connection Shutdown:** `close_publisher()` exists but is not wired into the application shutdown lifecycles; TEN gateway shutdown may print robust connection warning logs.
* **Grading Worker:** Currently uses a simulated fake grader instead of final pedagogical grading.
* **VAD & Whisper Warm Policy:** Changing VAD thresholds or disabling Whisper unload is high risk; these changes are not current next tasks.
* **Not Production-Ready:** Code is tuned for local single-session correctness and local stress verification; do not claim production scale.
