-- ============================================================
-- Migration: 0004_users_google_oauth
-- Purpose:   Add Google OAuth (OIDC) identity support to users
-- Scope:     users.google_sub column + partial unique index;
--            password_hash made nullable; auth-method CHECK constraint
-- Idempotent: Yes (ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS,
--            constraint guarded by DO block)
-- Requires:  users table from infrastructure/db-init/01-init.sql
-- Rollback:  See Rollback Notes below
-- Applied:   [YYYY-MM-DD] by [developer name]
--
-- Why password_hash becomes nullable:
--   Google-only accounts have no password. A CHECK constraint guarantees
--   every row still has at least one usable auth method (password OR google_sub).
--   Existing email/password rows keep password_hash and a NULL google_sub, so
--   they continue to satisfy the constraint and log in unchanged.
-- ============================================================

-- === Preflight ===
-- SELECT to_regclass('public.users') IS NOT NULL AS users_exists;
-- SELECT count(*) AS null_password_rows FROM users WHERE password_hash IS NULL; -- expect 0 pre-migration

BEGIN;

-- Stable Google subject identifier (the OIDC `sub` claim). NULL for password users.
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub TEXT;

-- Partial unique index: enforce one account per Google subject while allowing
-- many NULLs (every existing password user has google_sub = NULL).
CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_key
    ON users (google_sub) WHERE google_sub IS NOT NULL;

-- Google-only users have no password_hash.
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

-- Every user must retain at least one auth method.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_auth_method'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT chk_users_auth_method
            CHECK (password_hash IS NOT NULL OR google_sub IS NOT NULL);
    END IF;
END$$;

COMMIT;

-- === Verification (run after COMMIT) ===
-- SELECT is_nullable FROM information_schema.columns
--   WHERE table_name = 'users' AND column_name = 'password_hash';        -- expect YES
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'users' AND column_name = 'google_sub';           -- expect 1 row
-- SELECT indexname FROM pg_indexes WHERE tablename = 'users' AND indexname = 'users_google_sub_key';
-- SELECT conname FROM pg_constraint WHERE conname = 'chk_users_auth_method';

-- === Rollback Notes ===
-- WARNING: Re-adding NOT NULL to password_hash fails if any Google-only rows
-- (password_hash IS NULL) exist. Only roll back before any Google account is
-- created, and after backup + explicit approval.
--
-- BEGIN;
-- ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_auth_method;
-- DROP INDEX IF EXISTS users_google_sub_key;
-- ALTER TABLE users DROP COLUMN IF EXISTS google_sub;
-- -- ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL; -- only if no NULL rows
-- COMMIT;
