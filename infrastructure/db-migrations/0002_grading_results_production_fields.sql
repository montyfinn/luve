-- ============================================================
-- Migration: 0002_grading_results_production_fields
-- Purpose:   Add production status, provider, retry, and structured skill feedback fields to grading_results
-- Scope:     grading_results columns, checks, and indexes
-- Idempotent: Yes (ADD COLUMN IF NOT EXISTS, guarded constraints/indexes)
-- Requires:  grading_results table from infrastructure/db-init/01-init.sql
-- Rollback:  See Rollback Notes below
-- Applied:   [YYYY-MM-DD] by [developer name]
-- ============================================================

-- === Preflight ===
-- SELECT to_regclass('public.grading_results') IS NOT NULL AS grading_results_exists;

BEGIN;

ALTER TABLE grading_results
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'graded',
    ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS grader_version TEXT NOT NULL DEFAULT 'legacy',
    ADD COLUMN IF NOT EXISTS score_schema_version TEXT NOT NULL DEFAULT 'grading.v1',
    ADD COLUMN IF NOT EXISTS pronunciation_score NUMERIC(4,2),
    ADD COLUMN IF NOT EXISTS skill_feedback_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS input_quality_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS error_code TEXT,
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS attempt_count INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'grading_results_status_check'
          AND conrelid = 'grading_results'::regclass
    ) THEN
        ALTER TABLE grading_results
            ADD CONSTRAINT grading_results_status_check
            CHECK (status IN ('processing', 'graded', 'failed'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_grading_status
    ON grading_results(status);

CREATE INDEX IF NOT EXISTS idx_grading_updated_at
    ON grading_results(updated_at DESC);

COMMIT;

-- === Verification (run after COMMIT) ===
-- SELECT column_name FROM information_schema.columns WHERE table_name = 'grading_results' ORDER BY ordinal_position;
-- SELECT conname FROM pg_constraint WHERE conrelid = 'grading_results'::regclass ORDER BY conname;
-- SELECT indexname FROM pg_indexes WHERE tablename = 'grading_results' ORDER BY indexname;

-- === Rollback Notes ===
-- WARNING: Rollback drops production grading metadata accumulated after apply.
-- Only run after backup and explicit approval.
--
-- BEGIN;
-- DROP INDEX IF EXISTS idx_grading_updated_at;
-- DROP INDEX IF EXISTS idx_grading_status;
-- ALTER TABLE grading_results DROP CONSTRAINT IF EXISTS grading_results_status_check;
-- ALTER TABLE grading_results
--     DROP COLUMN IF EXISTS updated_at,
--     DROP COLUMN IF EXISTS attempt_count,
--     DROP COLUMN IF EXISTS error_message,
--     DROP COLUMN IF EXISTS error_code,
--     DROP COLUMN IF EXISTS input_quality_json,
--     DROP COLUMN IF EXISTS skill_feedback_json,
--     DROP COLUMN IF EXISTS pronunciation_score,
--     DROP COLUMN IF EXISTS score_schema_version,
--     DROP COLUMN IF EXISTS grader_version,
--     DROP COLUMN IF EXISTS provider,
--     DROP COLUMN IF EXISTS status;
-- COMMIT;
