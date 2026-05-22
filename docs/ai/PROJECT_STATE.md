# LUVE Project State

## 1. Current Expected Git State

* **Clean Worktree:**
  * Before committing these docs: only docs/ai files may be untracked/modified.
  * After committing these docs: git status --short should be clean.
* **Source of Truth:** All python services runtime files in `services/core-api/` and `services/grading-worker/` are untouched, matching the local baseline.

## 2. Latest Important Commits

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

## 4. Known Limitations & Gaps

* **No Durable Outbox / Backfill:** If RabbitMQ is down when a session finishes, the session event is not persisted locally for later retry; grading will be missed until backfilled manually.
* **Connection Shutdown:** `close_publisher()` exists but is not wired into the application shutdown lifecycles; TEN gateway shutdown may print robust connection warning logs.
* **Grading Worker:** Currently uses a simulated fake grader instead of final pedagogical grading.
* **VAD & Whisper Warm Policy:** Changing VAD thresholds or disabling Whisper unload is high risk; these changes are not current next tasks.
* **Not Production-Ready:** Code is tuned for local single-session correctness and local stress verification; do not claim production scale.
