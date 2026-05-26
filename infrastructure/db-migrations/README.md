# DB Migrations — LUVE Project

## Current Schema Source of Truth

`infrastructure/db-init/01-init.sql` is the canonical baseline schema for fresh database volumes.

It is mounted via Docker Compose into `/docker-entrypoint-initdb.d/` and creates:
- `USERS` — authentication, quota, soft-delete
- `LESSONS` — scenario library
- `SESSIONS` — session state, `raw_backup_json`, `metadata`
- `GRADING_RESULTS` — per-session scores, corrections, summary
- Three indexes: `idx_sessions_user_id`, `idx_grading_session_id`, `idx_users_email`

**Critical behavior:** `entrypoint-initdb.d` scripts run **only when the Postgres data directory is empty** (first container start against a new volume). They do not re-run when a container restarts against an existing volume. Adding a table to `01-init.sql` does not automatically add it to any existing developer database.

---

## Why Numbered SQL Files Instead of Alembic

This project deliberately uses plain numbered SQL migration files rather than Alembic at this stage. Reasons:

1. **Incomplete ORM model coverage.** Only the `users` table has a SQLAlchemy ORM model (`models/user.py`). Tables `sessions`, `grading_results`, and `lessons` are accessed entirely via raw SQL strings (`sqlalchemy.text()` in `session_service.py`, raw `asyncpg` in `grading_repository.py`). Alembic's autogeneration walks `Base.metadata` — it would silently miss three of the four existing tables and produce misleading empty migrations.

2. **No `create_all` at startup.** `db.py` never calls `Base.metadata.create_all()`. No FastAPI lifespan event applies DDL. The app assumes the schema already exists — startup DDL would be a regression.

3. **Scale appropriate.** This is a thesis/demo project with a single developer managing the database. The operational overhead of Alembic version tables, `env.py` configuration, and `alembic upgrade head` does not add safety at this scale. Plain SQL files are readable, diffable, and reviewable by any engineer without framework knowledge.

Alembic can be adopted later if the project scales to a team or requires automated upgrade pipelines. The numbered-SQL directory is forward-compatible: Alembic can be layered on top without disrupting existing migration history.

---

## Relationship Between db-init and db-migrations

```
Fresh empty Docker volume
  └── entrypoint-initdb.d/01-init.sql runs once
      └── All baseline tables created in one shot
      └── Migration files in db-migrations/ are NOT run automatically

Existing Docker volume (developer already has data)
  └── entrypoint-initdb.d is SKIPPED entirely
      └── New tables from 01-init.sql do NOT appear
      └── Must apply numbered migration files manually (see Runbook below)

After a migration is verified on an existing volume
  └── Mirror the schema addition into 01-init.sql in a separate approved patch
      └── Keeps fresh installs and migrated installs aligned
      └── Do NOT edit 01-init.sql in the same patch that creates the migration file
```

**Do not edit `01-init.sql` in Patch 7G-7.** It is updated in a subsequent patch after the migration has been applied and verified on a real database.

---

## Naming Convention

```
NNNN_<snake_case_description>.sql
```

- `NNNN` — zero-padded 4-digit sequence number, starting at `0001`.
- `<snake_case_description>` — short, lowercase description of the schema change.
- One migration file per logical schema change.
- Never reuse a sequence number. Never renumber existing files.

Examples:
```
0001_grading_skip_log.sql
0002_add_grader_version_column.sql
0003_add_sessions_rate_limit_table.sql
```

---

## Migration File Required Sections

Every migration file in this directory must contain all of the following sections as SQL comments and DDL:

```
-- ============================================================
-- Migration: NNNN_<description>
-- Purpose:   <one sentence — what this migration does>
-- Scope:     <which tables/indexes are created/altered/dropped>
-- Idempotent: Yes | Partial | No  (with explanation if not Yes)
-- Requires:  <tables or extensions that must pre-exist>
-- Rollback:  <DROP TABLE IF EXISTS ... | see Rollback Notes below>
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
-- Confirm required tables exist:
-- SELECT to_regclass('public.sessions') IS NOT NULL;

BEGIN;

-- === Forward migration ===
-- (Use IF NOT EXISTS guards wherever possible for idempotency.)

<DDL here>

COMMIT;

-- === Verification (run after COMMIT) ===
-- SELECT to_regclass('public.<new_table>') IS NOT NULL AS table_exists;
-- SELECT indexname FROM pg_indexes WHERE tablename = '<new_table>';
-- SELECT COUNT(*) FROM <new_table>;  -- expect 0 on fresh migration

-- === Rollback Notes ===
-- WARNING: Rollback destroys all data in the affected table/column.
-- Only apply rollback if the forward migration was verified erroneous.
-- Ensure a pg_dump backup exists before proceeding.
--
-- BEGIN;
-- DROP TABLE IF EXISTS <new_table>;
-- COMMIT;

-- === Fresh DB Sync Note ===
-- After this migration is verified on an existing volume, mirror the
-- schema addition into infrastructure/db-init/01-init.sql in a
-- separate approved patch so fresh Docker volumes also get this table.
```

**Rules:**
- All migrations must be wrapped in `BEGIN; ... COMMIT;`. If the DDL fails mid-transaction, Postgres rolls back automatically.
- Use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` wherever Postgres supports them.
- `ALTER TABLE ADD COLUMN` does not support `IF NOT EXISTS` before Postgres 9.6; use a `DO $$ ... $$` block if needed for idempotency on column additions.
- Never use `DROP TABLE`, `DROP COLUMN`, or `TRUNCATE` in a forward migration without explicit SRE approval and a confirmed backup.

---

## Safe Apply Runbook

**Never run a migration without completing steps 1–3 first.**

### Step 1 — Backup (mandatory)

Take a full database dump before any schema change. Example command structure (do not print or log credentials):

```bash
# Replace <db_name> with your actual database name (from POSTGRES_DB in .env)
# Replace <backup_file> with a descriptive timestamped filename
# Never echo DATABASE_URL or credentials in terminal history
pg_dump -Fc -d <db_name> -h localhost -U <db_user> \
  -f backups/backup_pre_NNNN_$(date +%Y%m%d_%H%M%S).dump
```

Store the backup file outside the repo. Confirm the backup file size is non-zero before proceeding.

### Step 2 — Inspect the migration file

```bash
# Read the migration file before applying — never apply blind
cat infrastructure/db-migrations/0001_grading_skip_log.sql
```

Confirm:
- `BEGIN;` and `COMMIT;` are present.
- All DDL uses `IF NOT EXISTS` guards.
- No `DROP TABLE`, `TRUNCATE`, or destructive statements appear unexpectedly.
- No secrets, credentials, or hardcoded values are present.

### Step 3 — Preflight (run queries from the Preflight section of the migration file)

Execute the preflight queries listed in the migration's `Preflight` comment block. Do not proceed if long-running transactions exist against the target tables.

### Step 4 — Apply (only in a future approved prompt)

```bash
# Only run this after steps 1–3 are complete and approved
psql "$DATABASE_URL" -f infrastructure/db-migrations/0001_grading_skip_log.sql
```

Do not apply to a production or staging database without a confirmed backup and explicit written approval.

### Step 5 — Verify

Run the verification queries listed at the bottom of the migration file:

```sql
-- Confirm table exists
SELECT to_regclass('public.<new_table>') IS NOT NULL AS table_exists;

-- Confirm indexes exist
SELECT indexname FROM pg_indexes WHERE tablename = '<new_table>';

-- Confirm row count is 0 (no spurious data)
SELECT COUNT(*) FROM <new_table>;
```

### Step 6 — Rollback (only if needed)

If the migration produced unexpected results and must be undone, apply the rollback block from the migration file's `Rollback Notes` section. Rollback for `CREATE TABLE` is clean (`DROP TABLE`). Rollback for `ALTER TABLE ADD COLUMN` may cause data loss — confirm before executing.

### Step 7 — Sync 01-init.sql (separate approved patch)

After the migration is verified on the local dev database, create a separate git patch that mirrors the schema addition into `infrastructure/db-init/01-init.sql`. This keeps fresh Docker volumes and migrated volumes aligned. Do not edit `01-init.sql` in the same patch as the migration file.

---

## Operational Rules

- **App startup must never auto-apply migrations.** No FastAPI lifespan event, no grading-worker startup hook, no script called from `docker-compose.yml` command should run migration files. Migrations are always operator-initiated.
- **One migration per schema change.** Do not bundle unrelated changes (e.g., new table + column rename) into a single migration file. Smaller files have smaller rollback blast radius.
- **Never edit a migration file after it has been applied.** If a migration was wrong, write a new corrective migration (e.g., `0003_fix_grading_skip_log_constraint.sql`).
- **Never reuse sequence numbers.** If migration `0002` is abandoned before apply, either delete the unapplied file or rename it with a descriptive suffix (e.g., `0002_ABANDONED_grader_version.sql`).
- **Privacy principle.** Schema changes for grading-related tables must never store raw transcript text, raw audio, or personally identifiable speech content. Skip/status tables record counts and metadata only.

---

## Patch 7G-8 Preview (Future — Not Implemented in Patch 7G-7)

Patch 7G-8 is expected to add a `grading_skip_log` table for persistent skip/status tracking. The migration file will be `infrastructure/db-migrations/0001_grading_skip_log.sql`.

**Patch 7G-7 does not create or apply this migration.**

High-level table sketch (for design review only — not executable DDL):

```
grading_skip_log
  id                  UUID PRIMARY KEY
  session_id          UUID NOT NULL, FK → sessions(id) ON DELETE CASCADE
  skipped_reason      TEXT NOT NULL  (insufficient_words | no_user_turns |
                                      no_raw_backup | invalid_raw_backup)
  student_word_count  INT            (NULL unless reason = insufficient_words)
  min_words_threshold INT            (threshold in effect at skip time)
  skipped_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP

  UNIQUE (session_id)
  INDEX  (skipped_reason)
  INDEX  (skipped_at DESC)
```

**Privacy principle:** No raw transcript text, no audio data, no speech content stored in this table. Only word counts and metadata.

**Idempotency:** The worker's `log_grading_skip()` call will use `ON CONFLICT (session_id) DO UPDATE` so that re-processing the same session updates the existing row rather than failing with a unique violation.

**Alignment with `01-init.sql`:** After `0001_grading_skip_log.sql` is applied and verified on a real database, a separate patch will mirror the table definition into `01-init.sql` so fresh Docker volumes also get the table.

---

## Appendix: Postgres DDL Idempotency Reference

| DDL Statement | IF NOT EXISTS supported? | Notes |
|---|---|---|
| `CREATE TABLE` | Yes (Postgres 9.1+) | Always use |
| `CREATE INDEX` | Yes (Postgres 9.5+) | Always use |
| `CREATE UNIQUE INDEX` | Yes | Always use |
| `CREATE EXTENSION` | Yes | Already in 01-init.sql |
| `ALTER TABLE ADD COLUMN` | Yes (Postgres 9.6+) | Use `ADD COLUMN IF NOT EXISTS` |
| `ALTER TABLE DROP COLUMN` | Yes | Destructive — backup required |
| `DROP TABLE` | Yes | Destructive — rollback only |
| `CREATE TYPE` (enum) | No direct support | Wrap in `DO $$ IF NOT EXISTS ... $$` block |

When Postgres does not support `IF NOT EXISTS` for a DDL statement, use a `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;` guard in the migration.
