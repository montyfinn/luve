-- ============================================================
-- Migration: 0003_session_outbox
-- Purpose:   Add transactional outbox table for session lifecycle events (T7)
-- Scope:     New session_outbox table + pending-poll index
-- Idempotent: Yes (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS)
-- Requires:  sessions table from infrastructure/db-init/01-init.sql
-- Rollback:  See Rollback Notes below
-- Applied:   [YYYY-MM-DD] by [developer name]
-- ============================================================

-- === Preflight ===
-- SELECT to_regclass('public.sessions') IS NOT NULL AS sessions_exists;

BEGIN;

CREATE TABLE IF NOT EXISTS session_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'v1',
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'published', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    UNIQUE (session_id, event_type)
);

CREATE INDEX IF NOT EXISTS session_outbox_pending_idx
    ON session_outbox(created_at) WHERE status = 'pending';

COMMIT;

-- === Verification (run after COMMIT) ===
-- SELECT column_name FROM information_schema.columns WHERE table_name = 'session_outbox' ORDER BY ordinal_position;
-- SELECT conname FROM pg_constraint WHERE conrelid = 'session_outbox'::regclass ORDER BY conname;
-- SELECT indexname FROM pg_indexes WHERE tablename = 'session_outbox' ORDER BY indexname;

-- === Rollback Notes ===
-- WARNING: Rollback drops any outbox rows not yet published. Only run after
-- backup and explicit approval.
--
-- BEGIN;
-- DROP INDEX IF EXISTS session_outbox_pending_idx;
-- DROP TABLE IF EXISTS session_outbox;
-- COMMIT;
