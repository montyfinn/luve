# LUVE Next Task

## Current Task
Audit grading delivery reliability and outbox/backfill options.

## 1. Operating Constraints
* **Mode:** AUDIT-ONLY.
* **Modification Policy:** 
  * Do not modify any runtime files. Do not stage. Do not commit.
  * If git status is not clean (excluding untracked docs/ai/ files before commit), stop and report.
  * Run only read-only SQL queries if needed; do not run destructive DB commands.
  * Do not publish any real RabbitMQ messages or trigger actual events.
* **Credentials Policy:** Never print or leak any passwords, database credentials, API keys, cookies, or JWTs.

## 2. Access Controls

### Allowed Read Paths
* `services/core-api/src/services/session_event_publisher.py`
* `services/core-api/src/main.py`
* `services/core-api/src/api/v1/`
* `services/core-api/src/ten_ext/luve_extension.py`
* `services/grading-worker/`
* `infrastructure/db-init/01-init.sql`
* `docs/ai/`

### Forbidden Changes (DO NOT TOUCH)
* No changes to VAD thresholding or noise floor tracking.
* No changes to Whisper warm singleton or unload policies.
* No changes to Redis configuration or persistence parameters.
* No changes to password hashing, passlib, or bcrypt.
* No modifications in the realtime hot paths (VAD, STT, LLM, TTS, WebRTC).

## 3. Expected Outputs
A rigorous markdown analysis covering:
1. **Current Delivery Architecture:** Visual or step-by-step trace of how a session goes from completion to DB update, queue publish, and worker grading results.
2. **Completed Sessions Missing Grading Results:** Strategic analysis of why completed sessions in the DB may miss grading results (e.g., broker down, unhandled consumer crashes) and how to identify them safely via read-only SQL queries.
3. **Outbox Pattern vs. Backfill Script Comparison:** Structural comparison of a durable database transactional outbox vs. an offline backfill script, showing pros, cons, and performance trade-offs under high-concurrency environments.
4. **Recommended Smallest Patch:** Detailed blueprint of the minimal, safest implementation to bridge the delivery gap without introducing runtime performance regression.
