# 2026-05-15 Grading Worker Commit Notes

## Scope

This note records the two grading-worker commits made after the realtime boundary refactor.

## Commits

### 2183fe9 feat(grading-worker): add evaluation input skeleton

Purpose:
- Start the grading-worker path without putting final grading logic into core-api.
- Define the `session.completed` job contract and `EvaluationInput` v1 inside `services/grading-worker`.
- Build deterministic evaluation input from persisted `sessions.raw_backup_json`.
- Add fake deterministic grading so the worker flow can be tested before wiring a real LLM.

Files included:
- `services/grading-worker/requirements.txt`
- `services/grading-worker/scripts/smoke_evaluation_input.py`
- `services/grading-worker/src/__init__.py`
- `services/grading-worker/src/contracts.py`
- `services/grading-worker/src/evaluation_input_builder.py`
- `services/grading-worker/src/fake_grader.py`
- `services/grading-worker/src/grading_repository.py`
- `services/grading-worker/src/worker.py`

Verified:
- `py_compile` passed for the grading-worker skeleton.
- `scripts/smoke_evaluation_input.py` printed EvaluationInput JSON and fake grading output.
- Smoke script included assertions and printed `PASS grading-worker evaluation input smoke`.

Important constraints:
- No real LLM call was added.
- No core-api runtime, WebRTC, TEN gateway, or LUVEExtension hot path was changed.
- No DB migration was added.

### 636ab74 chore(grading-worker): redact example database credentials

Purpose:
- Keep the grading-worker env example safe to share.
- Replace default-looking DB credentials with placeholders.

File included:
- `services/grading-worker/.env.example`

Change:
- The grading-worker `.env.example` was updated to use `<DB_USER>` and `<DB_PASSWORD>` placeholders instead of default-looking database credentials.

Verified:
- Staged diff contained no real secret values.
- `services/grading-worker` was clean after commit.

## Lessons

- Keep skeleton commits separate from env hygiene commits. It makes review safer and avoids mixing behavior scaffolding with secret-handling cleanup.
- For untracked skeleton files, `git diff -- path` may show nothing. Use `git status --short` and inspect file contents directly.
- Smoke scripts should have real assertions plus a clear PASS marker, not only print JSON.
- Do not commit `.env.example` changes automatically just because they look safe; check whether they are env hygiene, runtime config contract changes, or unrelated notes.
