-- ============================================================
-- Migration: 0001_grading_skip_log
-- Purpose:   Create grading_skip_log table for persistent per-session skip/status tracking
-- Scope:     New table grading_skip_log; two supporting indexes
-- Idempotent: Yes (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS)
-- Requires:  sessions table (baseline from infrastructure/db-init/01-init.sql)
-- Rollback:  DROP TABLE IF EXISTS grading_skip_log CASCADE; (see Rollback Notes below)
-- Applied:   [YYYY-MM-DD] by [developer name]
-- ============================================================

-- === Preflight ===
-- (Run these queries manually before applying. Do not include as executable SQL.)
-- Check for active transactions on affected tables:
-- SELECT pid, state, now() - query_start AS duration, left(query, 80)
-- FROM pg_stat_activity
-- WHERE state != 'idle'
-- ORDER BY duration DESC;
--
-- Confirm sessions table exists:
-- SELECT to_regclass('public.sessions') IS NOT NULL;
--
-- Confirm grading_skip_log does not already exist (should be NULL on first apply):
-- SELECT to_regclass('public.grading_skip_log') IS NULL AS not_yet_created;

BEGIN;

-- === Forward migration ===
-- Creates grading_skip_log for the grading worker and reconciliation tools to persist
-- ineligibility decisions. One row per session (UNIQUE on session_id). The worker,
-- scanner, and backfill write to this table via ON CONFLICT (session_id) DO UPDATE
-- so repeated processing of the same session is safe.
--
-- Columns:
--   id                  — surrogate PK, consistent with all other tables
--   session_id          — FK to sessions, UNIQUE (one skip row per session),
--                         ON DELETE CASCADE (follows sessions row lifecycle)
--   skipped_reason      — CHECK-constrained to the four eligibility reason codes
--                         emitted by session_eligibility.evaluate_grading_eligibility:
--                           no_raw_backup      (raw_backup_json IS NULL)
--                           invalid_raw_backup (present but not a JSON array)
--                           no_user_turns      (no USER_TURN events found)
--                           insufficient_words (word count below threshold)
--   student_word_count  — NULL unless skipped_reason = 'insufficient_words';
--                         the count observed at skip time
--   min_words_threshold — NULL unless skipped_reason = 'insufficient_words';
--                         the GRADING_MIN_STUDENT_WORDS value in effect at skip time
--   source              — which component wrote this row: worker / scanner /
--                         backfill / manual
--   skipped_at          — timestamp of first skip record for this session
--   updated_at          — timestamp of most recent ON CONFLICT DO UPDATE;
--                         tracks when eligibility was last re-evaluated
--
-- Privacy: no raw transcript text, no audio, no PII. Only word counts and metadata.

CREATE TABLE IF NOT EXISTS grading_skip_log (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID        NOT NULL UNIQUE REFERENCES sessions(id) ON DELETE CASCADE,
    skipped_reason      TEXT        NOT NULL CHECK (skipped_reason IN (
                                        'no_raw_backup',
                                        'invalid_raw_backup',
                                        'no_user_turns',
                                        'insufficient_words'
                                    )),
    student_word_count  INT,
    min_words_threshold INT,
    source              TEXT        NOT NULL DEFAULT 'worker'
                                    CHECK (source IN (
                                        'worker',
                                        'scanner',
                                        'backfill',
                                        'manual'
                                    )),
    skipped_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index on skipped_reason for aggregate queries (e.g. skip reason distribution).
CREATE INDEX IF NOT EXISTS grading_skip_log_skipped_reason_idx
    ON grading_skip_log (skipped_reason);

-- Index on skipped_at DESC for time-ordered audit queries.
CREATE INDEX IF NOT EXISTS grading_skip_log_skipped_at_idx
    ON grading_skip_log (skipped_at DESC);

-- Note: no separate unique index for session_id is needed.
-- The UNIQUE constraint on the session_id column above creates an implicit
-- unique index (grading_skip_log_session_id_key) that ON CONFLICT (session_id)
-- resolves against.

COMMIT;

-- === Verification (run after COMMIT) ===
-- Confirm table exists:
-- SELECT to_regclass('public.grading_skip_log') IS NOT NULL AS table_exists;
--
-- Confirm indexes exist (expect 3: session_id_key, skipped_reason_idx, skipped_at_idx):
-- SELECT indexname FROM pg_indexes WHERE tablename = 'grading_skip_log' ORDER BY indexname;
--
-- Confirm row count is 0 (no spurious data on fresh migration):
-- SELECT COUNT(*) FROM grading_skip_log;
--
-- Optional: confirm check constraints are present:
-- SELECT conname, consrc
-- FROM pg_constraint
-- WHERE conrelid = 'grading_skip_log'::regclass
--   AND contype = 'c'
-- ORDER BY conname;

-- === Rollback Notes ===
-- WARNING: Rollback destroys all skip-log audit data accumulated since apply.
-- Only apply rollback if the forward migration was verified erroneous.
-- Ensure a pg_dump backup exists before proceeding.
-- Do NOT run this block unless the forward migration must be undone.
--
-- BEGIN;
-- DROP TABLE IF EXISTS grading_skip_log CASCADE;
-- COMMIT;

-- === Fresh DB Sync Note ===
-- After this migration is applied and verified on an existing volume, mirror the
-- grading_skip_log table definition into infrastructure/db-init/01-init.sql in a
-- separate approved patch so fresh Docker volumes also get this table.
-- Do not edit infrastructure/db-init/01-init.sql in Patch 7G-8A.
