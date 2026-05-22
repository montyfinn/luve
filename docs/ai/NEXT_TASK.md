# LUVE Next Task

## Completed Task
Audit grading delivery reliability, design and implement backfill script, execute backfill.

### Summary of Work Done
* Audited grading delivery gap: `_persist_event_log` commits DB first then publishes best-effort; no durable outbox.
* Designed and implemented `services/grading-worker/scripts/backfill_completed_sessions.py` (commit `c5cf2c3`).
* Executed backfill against local Postgres in controlled increments:
  * `grading_results` total: 2 → **138**
  * `completed_missing_grading`: 216 → **80**
  * Remaining 80 all have `raw_backup_json IS NULL`; excluded by default filter.
* Verified idempotency: rerun on already-graded session produced `candidates_seen=0`, no duplicate row.

---

## Current Task
Audit why completed sessions have `raw_backup_json IS NULL` and whether that is expected.

## 1. Operating Constraints
* **Mode:** AUDIT-ONLY.
* **Modification Policy:**
  * Do not modify any runtime files. Do not stage. Do not commit.
  * If git status is not clean, stop and report.
  * Run only read-only SQL queries if needed; do not run destructive DB commands.
  * Do not publish any real RabbitMQ messages or trigger actual events.
* **Credentials Policy:** Never print or leak any passwords, database credentials, API keys, cookies, or JWTs.

## 2. Access Controls

### Allowed Read Paths
* `services/core-api/src/ten_ext/luve_extension.py`
* `services/core-api/src/api/v1/`
* `services/core-api/src/main.py`
* `services/core-api/src/services/session_event_publisher.py`
* `services/grading-worker/`
* `infrastructure/db-init/01-init.sql`
* `docs/ai/`

### Forbidden Changes (DO NOT TOUCH)
* No changes to VAD thresholding or noise floor tracking.
* No changes to Whisper warm singleton or unload policies.
* No changes to Redis configuration or persistence parameters.
* No changes to password hashing, passlib, or bcrypt.
* No modifications in the realtime hot paths (VAD, STT, LLM, TTS, WebRTC).
* No changes to `_persist_event_log` or session completion logic without a separate approved prompt.

## 3. Expected Outputs
A rigorous markdown analysis covering:
1. **Code path analysis:** Under what conditions does `_persist_event_log` write a NULL `raw_backup_json`? Trace the exact branch in the code.
2. **Session categorization:** Which session types are expected to produce NULL `raw_backup_json` (e.g., empty/noise/rapid-disconnect stress sessions, sessions that ended before any STT was accepted)?
3. **Backfill policy recommendation:** Should the 80 remaining NULL sessions ever be backfilled using `--include-empty-raw`? What would grading produce for a 0-turn session, and is it operationally useful?
4. **Prevention recommendation:** Is there a safe, minimal change to `_persist_event_log` that always writes at least an empty array `[]` instead of NULL, to keep future backfill and grading consistent? State the risk and blast radius clearly. Do not implement — audit only.
