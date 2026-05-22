# LUVE Next Task

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

---

## Current Task
Audit durable outbox vs current manual backfill safety net.

## 1. Operating Constraints
* **Mode:** AUDIT-ONLY.
* **Modification Policy:**
  * Do not modify any runtime files. Do not stage. Do not commit.
  * Run only read-only SQL queries if needed; do not run destructive DB commands.
  * Do not publish any real RabbitMQ messages or trigger actual events.
* **Credentials Policy:** Never print or leak any passwords, database credentials, API keys, cookies, or JWTs.

## 2. Allowed Read Paths
* `services/core-api/src/ten_ext/luve_extension.py`
* `services/core-api/src/services/session_event_publisher.py`
* `services/core-api/src/core/db.py`
* `services/grading-worker/scripts/backfill_completed_sessions.py`
* `infrastructure/db-init/01-init.sql`
* `docs/ai/`

## 3. Audit Questions
1. What is the exact failure mode when RabbitMQ is down at session completion? What data is preserved? What is lost?
2. Is the current manual backfill script a sufficient operational safety net? What scenarios does it not cover?
3. What would a minimal transactional outbox look like in this codebase? What tables/columns would be needed?
4. Is a scheduled reconciliation job a simpler alternative to a full outbox for this workload?
5. What is the blast radius and implementation complexity of each option?

## 4. Expected Output
A rigorous markdown analysis covering:
1. Current delivery gap: exact failure path and data preservation guarantees
2. Backfill coverage: what it recovers and what it cannot
3. Design options: transactional outbox / scheduled reconciliation / status-based polling
4. Risk analysis per option: complexity, blast radius, operational risk
5. Recommendation: implement outbox / maintain current pattern / defer — with explicit conditions
