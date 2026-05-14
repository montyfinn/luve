# 2026-05-15 Repo Cleanup And Runtime Commit Log

## Scope

This note records the commit checkpoints made during the realtime boundary, grading-worker, repo hygiene, STT tooling, docs cleanup, and runtime config recovery sequence.

Use this as operational context only. Code, tests, schema, and runtime evidence remain the source of truth.

## Commit Ledger

### 9bb679e refactor(core-api): split realtime TEN-compatible gateway boundaries

Purpose:
- Split the TEN-compatible realtime gateway boundary out of `run_ten.py`.
- Keep `run_ten.py` focused on FastAPI bootstrap and public route surface.
- Add `src/realtime/` contracts, output protocol, session store boundary, TEN-compatible adapter, placeholder engine, and TEN-native adapter boundary.

Verified:
- `py_compile` passed for `run_ten.py` and new realtime modules.
- `import run_ten` passed.
- Route surface remained intact.
- Live smoke verified `/healthz`, auth/session checks, WebRTC offer/ICE, STT partial/final, disconnect cleanup, and `raw_backup_json` persistence.

### 2183fe9 feat(grading-worker): add evaluation input skeleton

Purpose:
- Start the grading-worker path without putting final grading logic into core-api.
- Add `session.completed` job and `EvaluationInput` contracts.
- Build evaluation input from `raw_backup_json` `USER_TURN` and `AI_TURN` events.
- Add deterministic fake grader, repository skeleton, RabbitMQ worker skeleton, and smoke script.

Verified:
- `py_compile` passed.
- `smoke_evaluation_input.py` passed with assertions and `PASS grading-worker evaluation input smoke`.

### 636ab74 chore(grading-worker): redact example database credentials

Purpose:
- Replace default-looking grading-worker database credentials with placeholders.
- Keep the env example safe for sharing.

Verified:
- Staged diff contained no real secret values.

### 20dd0e2 chore: ignore local auth payloads

Purpose:
- Add `login.json` to `.gitignore`.
- Avoid committing local login/auth payloads.

Verified:
- Staged diff only added `login.json`.

### 0793011 docs(ai): add agent workflow and operational memory

Purpose:
- Add root agent instructions and Codex operating rules.
- Add verified operational memory and lessons learned.
- Add pre-compact handoff prompt and repo-local AI coding skill guidance.

Verified:
- No real secret values detected.

### 5aaa6f1 chore: ignore generated debug and local STT artifacts

Purpose:
- Ignore generated Playwright/debug output.
- Ignore TEN runtime log output.
- Ignore local STT audio fixtures and local STT case manifest by default.
- Keep audio fixture directory with `.gitkeep`.

Verified:
- Commit scope was limited to `.gitignore` and `services/core-api/testdata/audio/.gitkeep`.

### 21853ec docs(stt): add local STT testdata guidance

Purpose:
- Add STT testdata README and live acceptance checklist.
- Add example STT case manifest for local audio fixtures.
- Document that real audio fixtures and `stt_cases.json` remain local.

Verified:
- Docs used relative links.
- No local absolute paths remained in committed docs.

### 76d367e fix(core-api): freeze mutable audio buffer chunks

Purpose:
- Store immutable snapshots for `bytearray` and `memoryview` inputs.
- Keep `bytes` inputs zero-copy through `memoryview`.
- Add `push()` alias for buffer producers.
- Preserve `get_flat_audio()` bytes output.

Verified:
- AudioBuffer immutability/order/push smoke passed.
- `py_compile` passed.

### dc571fc chore(core-api): add STT eval config and dependencies

Purpose:
- Add minimal STT model and beam settings to core config.
- Add STT eval/audio dependencies.
- Keep LLM/TTS/WebRTC/VAD settings out of that commit.

Verified:
- `py_compile` passed.
- settings import smoke passed.

### 1b9e393 feat(core-api): add STT eval runtime tooling

Purpose:
- Add offline final-STT evaluation script.
- Add audio frame PCM extraction helper.
- Add STT transcript postprocessing helper.
- Add Whisper inference runtime wrapper.

Verified:
- `py_compile` passed.
- Import smoke passed without loading the model.
- No secret or local absolute path patterns detected.

### 7c72a9b docs(ai): move agent workflow docs under docs/ai

Purpose:
- Keep `AGENTS.md` at repo root as the agent entrypoint.
- Move Codex, memory, experience, and compact prompt docs under `docs/ai/`.
- Update `AGENTS.md` references to the new paths.

Verified:
- `AGENTS.md` references were updated.
- Old root AI docs were removed.
- `docs/ai` contained the moved workflow docs.

### da1b5fa docs(tooling): add sanitized local dev commands

Purpose:
- Replace the root scratch command file with a sanitized tooling doc.
- Document local core-api, infrastructure, TEN gateway, and auth token commands.
- Avoid machine-specific paths and secret values.

Verified:
- No local absolute paths or secret values detected.

### 5f19b54 docs(notes): archive legacy project notes

Purpose:
- Move useful commit notes under `docs/notes/commits/`.
- Archive legacy roadmap and generated notes under `docs/notes/legacy/`.
- Label legacy notes as historical and not source of truth.
- Redact credential-looking database URL examples.

Verified:
- No credential-looking DB URL remained.
- No services/runtime files were staged.

### 7d06778 docs(architecture): move diagram assets under docs

Purpose:
- Move existing diagram sources and rendered images from `gemi/` to `docs/architecture/diagrams/`.
- Preserve existing diagram assets without treating them as finalized architecture docs.
- Keep architecture assets out of the repo root.

Verified:
- Moved files matched existing tracked blobs.
- No services/runtime files were staged.

### 2dd2511 fix(core-api): restore realtime runtime config fields

Purpose:
- Restore WebRTC runtime settings required by TEN gateway startup.
- Restore LLM provider settings required by `LUVEExtension`.
- Restore TTS settings required by `LUVEExtension` startup.
- Keep changes limited to `Settings` fields and properties.

Verified:
- `py_compile` passed.
- settings smoke passed.
- `import run_ten` passed.
- `run_ten.py` startup smoke passed.

## Lessons

- Keep skeleton, env hygiene, docs moves, runtime config, and hot-path behavior in separate commits.
- After trimming config scope, run import and startup smoke, not only `py_compile`; missing Pydantic settings fail at runtime.
- Do not claim `curl :8080/healthz` validates new code unless the gateway was restarted from that code.
- Untracked or ignored moved files may require explicit force-add only for the intended files.
- Diagram/image moves should be treated as asset relocation, not as proof that architecture docs are finalized.
- Notes and AI memory files are operational context, not source of truth.
