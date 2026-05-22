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

---

## Current Task
Commit AI state docs after `raw_backup_json` NULL audit.

## 1. Operating Constraints
* **Mode:** DOCS-COMMIT-ONLY.
* **Modification Policy:**
  * Only `docs/ai/PROJECT_STATE.md` and `docs/ai/NEXT_TASK.md` may be staged and committed.
  * Do not modify any runtime files.
  * Do not run destructive DB commands.
  * Do not publish any RabbitMQ messages.
* **Credentials Policy:** Never print or leak any passwords, database credentials, API keys, cookies, or JWTs.

## 2. Steps
1. Verify `git status --short` shows only the two docs files as modified (M).
2. Stage: `git add docs/ai/PROJECT_STATE.md docs/ai/NEXT_TASK.md`
3. Commit with message: `docs(ai): record raw_backup_json NULL audit findings`
4. Verify `git status --short` is clean and `git log --oneline -n 3` shows the new commit at HEAD.

## 3. Expected Outputs
* Clean worktree after commit.
* New HEAD commit with message `docs(ai): record raw_backup_json NULL audit findings`.
