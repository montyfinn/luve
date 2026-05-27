# LUVE Project State

This file is the current source of truth for mutable repo state in `docs/ai`.

- Read this file first for current baseline, verified evidence, and known limitations.
- Treat `NEXT_TASK.md` as a scoped task memo, not as global repo state.
- Treat `CLAUDE_CODE_HANDOFF.md` as architecture/historical onboarding context, not mutable state.

## 1. Current Expected Git State

* **Worktree:** No tracked modifications; only untracked user-owned artifacts (`.understand-anything/`, `docs/system-map.md`).
* **HEAD:** `696262e` fix(control-center): add manual grading loader (2026-05-27).
* **Latest runtime/tooling baseline:** `7d522d9` — fix(core-api): serve control center and lock down CORS (Patch 7G-6 — CORS wildcard replaced with 8-origin local allowlist via `get_cors_allow_origins()`; `StaticFiles` mount at `/static`; `/control-center` FileResponse route; `src/core/cors.py` CORS helper; 15/15 mocked tests; py_compile OK; no DB/RabbitMQ/Groq). Latest infrastructure commit: `d2bb908` db: add grading skip log migration (Patch 7G-8A — `infrastructure/db-migrations/0001_grading_skip_log.sql` created). **Patch 7G-8B Execute complete (2026-05-26): `grading_skip_log` migration applied and verified on local DB; table exists, row_count=0, all columns/indexes/constraints/FK verified; backup at `/home/minhthuy/db-backups/backup_pre_0001_grading_skip_log_20260526_145532.dump` (111K, non-zero).** Patch 7G-8C app integration audit/design complete (audit/design only; no DB commands run; no files modified except docs; no app integration implemented; implementation unblocked by 7G-8B Execute; pending separate approved prompts for 7G-8C-3 through 7G-8C-4). **Patch 7G-8C-1 complete (2026-05-26): `GradingRepository.log_grading_skip()` added to `services/grading-worker/src/grading_repository.py`; 5/5 mocked asyncpg tests in `test_grading_repository_patch7g8c.py`; commit `cb79155`.** **Patch 7G-8C-2 complete (2026-05-26): `worker.py` refactored to use `evaluate_grading_eligibility`; all four ineligible reasons write skip rows best-effort; 6/6 mocked tests pass; commit `85ce409`.** **Control Center UX fixes (2026-05-27): auth validation feedback fix `5195315`; URL defaults fix + Bearer Token visibility `c5e68fd`; tooling docs `d61db52`.**
* **Thesis chapters:** All five chapter drafts committed (`chapter1_draft.md` through `chapter5_draft.md`, `outline.md`) in commits `04d4f43`, `be396c0`, `12f02b1`, `1a9c1a4`, `5c0fc1a`. Test evidence, smoke runners, and multi-gateway scale results committed in `fafa538`, `808d7bc`, `36b870b`, `e3f0012`, `e654b91`.
* **Source of Truth:** All python services runtime files in `services/core-api/` and `services/grading-worker/` are committed and match the local baseline.

## 1A. Recent Completed Work (2026-05-27)

* **Fake grading DB/RabbitMQ smoke: PASS.**
  Session `a62d11fc-4793-439b-a835-384f41c23eda`; worker consumed `session.completed`; worker log key `grading.completed`; `grading_results=1`; `grading_skip_log=0`; grader `fake_grader.v1`; Groq not called; scanner/backfill `--execute` not run; worker stopped cleanly; API check was skipped because `sessions.user_id` was `NULL`.
* **User-owned fake grading API smoke: PASS.**
  Smoke email `grading-smoke-1779863297-e28f5e@example.com`; session `905819ff-db81-4243-9347-45abcef6c437`; worker log key `grading.completed`; `grading_results=1`; `grading_skip_log=0`; `GET /grading/status` returned HTTP 200 with `status=graded`; `GET /grading` returned HTTP 200 with `overall_score=5.97`; correction types were `fake_grader_notice` and `input_quality`; worker stopped cleanly; Groq not called; no code changes were required for the smoke itself.
* **Control Center grading UI status.**
  The API grading path works. The earlier fake DB smoke session with `user_id=NULL` is not readable through the authenticated API. Commit `696262e` added a manual `Load Grading` button in the Control Center (`id="load-grading-btn"`); it reads `currentSessionId` or the session input, calls `keepCompletedSessionVisible(sessionId)`, then calls the existing `fetchAndShowGrading(sessionId)` path without bypassing auth. Browser render of the grading card still needs a final manual/browser smoke. Local Playwright/browser automation was unavailable because the CLI package/cache was missing and `npm` fetch failed.
* **Local env caveat.**
  `services/grading-worker/.env` exists, is ignored, and is local-only. The passing smokes found that this file may contain stale or wrong DB/RabbitMQ values on this machine. Successful smokes used safe in-process overrides from root/container env without printing secrets. Do not commit `.env`. Do not print `DATABASE_URL`, DB password, Groq key, or tokens.

## 2. Latest Important Commits

* `696262e` - fix(control-center): add manual grading loader (2026-05-27 — adds visible `Load Grading` button next to `Current Session ID`; button reuses existing Bearer-token path, keeps the completed session visible, and calls existing `fetchAndShowGrading(sessionId)`; inline JS syntax checked with `node --check`; no backend changes).
* `5195315` - fix(control-center): show auth validation errors (2026-05-27 — added `updateAuthState(String(error))` to `loginBtn` click catch, `registerBtn` click catch, and `authPasswordInput` Enter-key catch; `getCredentials()` throws for empty email or short password — error now updates `#auth-state` paragraph visibly instead of only calling `logEvent`; JS syntax OK via `node --check`; no DOM/CSS/handler/backend changes).
* `d61db52` - docs(tooling): add local dev startup commands (2026-05-27 — pre-existing dirty file; Vietnamese-language ss/fuser port-kill commands + uvicorn/gateway startup commands; committed separately from UX fix).
* `c5e68fd` - fix(control-center): resolve auth and core API URL defaults (2026-05-27 — Fix A: added `open` attribute to `<details>` for Bearer Token fallback visibility; Fix B: `getDefaultCoreApiUrl()` updated from string `=== "8080"` to numeric range check `Number(url.port) >= 8080 && <= 8099` covering gateway ports 8081–8086; static smoke curl :8000/control-center HTTP 200 PASS; live browser at :8081 pending gateway start).
* `85ce409` - fix(grading-worker): write skip log from worker eligibility gate (Patch 7G-8C-2 — refactored `process_session_completed_job` to call `evaluate_grading_eligibility` before `build_evaluation_input`; best-effort `log_grading_skip` for all four ineligible reasons; `grading.session_ineligible` log key; non-fatal skip-log failure logs `grading.skip_log_failed`; new `tests/test_worker_patch7g8c2.py` with 6 mocked tests; cascade fix to `test_worker_patch2a.py` and `test_worker_patch7g5.py`; no live DB/RabbitMQ/Groq).
* `cb79155` - feat(grading-worker): add skip log repository method (Patch 7G-8C-1 — added `GradingRepository.log_grading_skip(session_id, reason, source, student_word_count, min_words_threshold)` to `grading_repository.py`; asyncpg ON CONFLICT (session_id) DO UPDATE; try/finally close pattern; new `tests/test_grading_repository_patch7g8c.py` with 5 mocked asyncpg tests; no live DB, no worker/scanner/backfill/core-api changes).
* `d2bb908` - db: add grading skip log migration (Patch 7G-8A — created `infrastructure/db-migrations/0001_grading_skip_log.sql`; idempotent `CREATE TABLE IF NOT EXISTS grading_skip_log` with session_id FK, skipped_reason CHECK, source CHECK, skipped_at/updated_at; two supporting indexes; migration not applied; no DB commands run; no app code changed).
* `bac73d2` - docs(db): add migration strategy runbook (Patch 7G-7 — created `infrastructure/db-migrations/README.md`; numbered SQL migration workflow; backup/preflight/apply/verify/rollback/sync runbook; no Alembic; no DB commands run; no migration applied; no schema changed).
* `7d522d9` - fix(core-api): serve control center and lock down CORS (Patch 7G-6 — extracted `get_cors_allow_origins()` to `src/core/cors.py`; default 8-origin local allowlist, no wildcard; `CORS_ALLOW_ORIGINS` env override; `allow_credentials=False`; `StaticFiles` at `/static`; `/control-center` FileResponse; `tests/__init__.py` + `tests/test_main_patch7g6.py` with 15 mocked tests; py_compile OK; no DB/RabbitMQ/Groq).
* `dcdf9ba` - fix(grading-worker): gate fake fallback behind env flag (Patch 7G-5 — added `_get_fake_fallback_enabled()` reading `GRADING_FAKE_FALLBACK` env; default false: LLM failures log `grading.llm_failed_no_fallback` at ERROR and re-raise; true: preserves `grading.llm_failed_fallback` warning + `fake_grade()` fallback; `GRADING_PROVIDER=fake` and skip gates unchanged; 29 new mocked tests; py_compile + 183/183 full suite passed; no DB/RabbitMQ/Groq).
* `80d4db7` - fix(grading-worker): gate backfill execute by eligibility (Patch 7G-4D — backfill execute path gated by `evaluate_grading_eligibility` before `process_session_completed_job`; `_parse_min_student_words_env` helper added; `--min-student-words` CLI flag; counter names aligned with scanner; 13 mocked tests; py_compile OK; targeted 58/58 passed; full grading-worker suite 154/154 passed (project-venv python); no DB/RabbitMQ/Groq).
* `7dcc9e8` - fix(grading-worker): gate scanner execute by eligibility (Patch 7G-4C — scanner execute path gated by `evaluate_grading_eligibility` before `process_session_completed_job`; ineligible sessions skipped with per-reason counters; execute and dry-run summary bucket naming unified; 11 mocked tests; py_compile + 141/141 tests passed; no DB/RabbitMQ/Groq).
* `5714ae4` - test(grading-worker): categorize scanner dry-run eligibility (Patch 7G-4B — scanner dry-run path wired to `evaluate_grading_eligibility`; per-reason skip counts; `_parse_min_student_words_env` helper; `--min-student-words` CLI flag; 25 mocked unit tests; execute path unchanged; py_compile + 130/130 tests passed; no DB/RabbitMQ/Groq).
* `462f5a4` - test(grading-worker): add session eligibility helper (Patch 7G-4A — pure Python `session_eligibility.py` helper + 45 unit tests; py_compile OK; 105/105 full suite passed; no runtime behavior change; scanner/backfill/worker not yet wired).
* `55a4d02` - fix(core-api): harden grading status UI contract (Patch 7G-3 — `GradingStatusRead.status` narrowed to `Literal["graded", "pending", "insufficient_evidence"]`; `fetchAndShowGrading` hardened with 401/403 auth guard and unknown-status fail-closed guard before `/grading` fetch; response JSON values and all existing UI branches unchanged; py_compile + schema Literal smoke + UI route-intercept smoke 22/22 passed; no DB migration; no worker changes).
* `24fef0b` - fix(core-api): align grading status word count detection (Patch 7G-2 — `_compute_student_word_count` now accepts both `"type"` and `"event"` keys for USER_TURN; Mapping-compatible event/payload checks; 8/8 helper smoke passed; py_compile OK; no DB migration; no API or UI changes).
* `ddb46ec` - feat(core-api): expose grading status for insufficient evidence (Patch 7F-1 — `GradingStatusRead` schema, `GET /api/v1/sessions/{session_id}/grading/status` endpoint, dynamic status inference from existing data, UI `fetchAndShowGrading` updated; no DB migration; no worker changes; py_compile + import + helper smoke passed).
* `8b16c50` - fix(grading-worker): skip insufficient transcript evidence (Patch 7E — word-count quality gate in `worker.py`; `GRADING_MIN_STUDENT_WORDS` env var, default 25; logs `grading.skipped_insufficient_evidence`; 60/60 mocked tests pass; no live services touched).
* `1cae30b` - feat(grading-worker): add Groq grading provider client (`GroqClient` via raw `httpx` REST; `_build_grader_client()` reads `LLM_PROVIDER`/`GROQCLOUD_API_KEY`/`GROQ_MODEL`/`GROQ_TIMEOUT_SECONDS`; `httpx` declared in `requirements.txt`; 57/57 mocked tests pass; real Groq live test not yet run).
* `06acf97` - feat(grading-worker): add safe grading provider dispatch (`GRADING_PROVIDER` env-flag dispatch with fake default; `GRADING_PROVIDER=llm` falls back to fake until real provider client exists; no-user-turn sessions skip without upsert; 34/34 mocked tests pass).
* `675e3a2` - feat(grading-worker): add offline LLM grader scaffold (loosen `grader_version` Literal, add `llm_grader.py` prompt builder + response parser/validator, add 22 mocked tests; worker still uses `fake_grader.v1` only).
* `3da235c` - feat(core-api): add end-of-session grading analysis API and UI (`GradingRead` schema, `GET /api/v1/sessions/{session_id}/grading` endpoint, Session Analysis card in control center UI with dev-preview badge and `escapeHtml` sanitization).
* `fc18916` - feat(grading-worker): add completed session reconciliation scanner (one-shot, dry-run default, `--grace-minutes` grace window, no RabbitMQ dependency for recovery).
* `440ff98` - fix(core-api): persist empty event logs as arrays (`_persist_event_log` always writes `raw_backup_json`; empty event logs now store `[]` instead of NULL).
* `da4a0d9` - docs(ai): record raw_backup_json NULL audit findings.
* `c5cf2c3` - test(grading-worker): add completed session backfill script (dry-run-first, USER_TURN filter, idempotent upsert).
* `9ec6c05` - docs(ai): add Claude coding guardrails (CLAUDE.md with LUVE-specific priority header).
* `aa8a9e9` - docs(ai): add Claude Code handoff state.
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

## 4. Grading Backfill Execution Evidence (Local/Dev)

* **Initial audit counts:** `completed_sessions=218`, `grading_results=2`, `completed_missing_grading=216`.
* **Backfill runs:** Executed in controlled increments (`--limit 1`, `5`, `20`, `50`, `50`) against local Postgres with default filters (raw_backup_json IS NOT NULL + at least one accepted USER_TURN).
* **Final DB state after full backfill:**
  * `grading_results` total: **138**
  * `completed_missing_grading`: **80**
  * Remaining 80 sessions all have `raw_backup_json IS NULL` (no event log; not eligible for default backfill).
  * `missing_has_raw=0`: no eligible sessions with event data were skipped.
* **Idempotency verified:** Rerun targeting an already-graded session produced `candidates_seen=0`; no duplicate row was created. The `LEFT JOIN … gr.session_id IS NULL` filter in the candidate query excluded it before any grading logic ran.
* **Backfill filter confirmed:** Default filter correctly excluded empty/noise/rapid-disconnect stress sessions with no accepted speech turns.

## 5. Patch 1 Offline LLM Grader Scaffold (commit `675e3a2`)

**What exists:**
* `services/grading-worker/src/llm_grader.py` — provider-agnostic offline scaffold. No external/provider/network imports. Contains:
  * `build_grading_prompt(EvaluationInput) -> str` — formats transcript + rubric; requests JSON-only response.
  * `parse_grading_response(raw_json, *, session_id) -> GradingResult` — strict JSON parse, required-field check, `[0, 10]` range enforcement (raises on violation), malformed-correction filtering, overall score computed as `fluency×0.30 + grammar×0.35 + vocab×0.35`.
  * `llm_grade_with_client(EvaluationInput, client) -> GradingResult` — `GraderClient` Protocol seam for future provider injection; raises `LLMGraderError` if zero student turns.
  * `LLMGraderError` — typed exception for all parse/validation failures.
* `services/grading-worker/src/contracts.py` — `GradingResult.grader_version` loosened from `Literal["fake_grader.v1"]` to `str` with default `"fake_grader.v1"`.
* `services/grading-worker/tests/` — 22 mocked tests (no real API calls).

**What is NOT yet done:**
* `llm_grader.py` is **not wired into `worker.py`**. The live grading path calls `fake_grade()` only.
* No real LLM API has been called.
* No `grading_results` row has been written by `llm_grader.v1`.
* UI still shows "DEV PREVIEW — Simulated Grading" and `fake_grader.v1` scores.
* No provider client implementation exists. Patch 2 must add it.

**Verification evidence:**
* `py_compile` pass on all 4 Patch 1 files.
* 22/22 mocked `llm_grader` tests pass.
* `fake_grader` regression pass — `grader_version="fake_grader.v1"` unchanged.
* `grep` confirmed: no `httpx`, `groq`, `google`, `openai`, `anthropic`, `requests`, `aiohttp` imports in `llm_grader.py`.

**Local venv drift note:**
`pytest` and `pytest-asyncio` were installed into `services/core-api/venv` during Patch 1 verification. This is local environment drift only — not a git-tracked change and not in any `requirements.txt`. It has no effect on the production grading worker runtime.

## 6. Patch 2A Safe Grading Provider Dispatch (commit `06acf97`)

**What was added:**
* `worker.py` now supports `GRADING_PROVIDER` env-flag dispatch:
  * Unset or `"fake"` → `fake_grade()` as before.
  * `"llm"` → attempts `llm_grade_with_client()`; currently falls back to `fake_grade()` because `_build_grader_client()` raises `LLMGraderError` (real provider not yet implemented).
  * Unknown value → `WARNING` log + fallback to `"fake"`.
* `process_session_completed_job` now returns early (no upsert) for sessions with zero accepted student turns. Previously these sessions wrote floor-score fake rows; now they produce no `grading_results` row. The API returns 404; the UI shows "Grading pending." This is consistent with the established backfill/reconciliation policy.
* Completion log updated: now emits `provider_requested=` and `grader_version=` instead of the hardcoded `fake_grader=true`.
* `grader_info` marker prepended to `detailed_corrections` JSONB on successful LLM grading — queryable without a schema migration.
* 12 new mocked worker dispatch tests added.

**What is NOT yet done (at time of Patch 2A):**
* No real LLM provider client existed. `GRADING_PROVIDER=llm` was structurally wired but always fell back to fake.
* No `httpx` or provider SDK added to `requirements.txt`.
* No `services/core-api/` or DB schema changes.
* No real LLM API calls had been made by the grader.
* UI still shows "DEV PREVIEW — Simulated Grading" and `fake_grader.v1` scores.
* Patch 2B added exactly one provider client — see section 7 below.

**Verification evidence:**
* `py_compile` pass on `worker.py` and `tests/test_worker_patch2a.py`.
* 34/34 mocked tests pass (`test_llm_grader.py` 22 + `test_worker_patch2a.py` 12).
* `grep` confirmed: no `httpx`, `requests`, `aiohttp`, `google`, `groq`, `openai`, `anthropic` imports in `worker.py` or the new test file.

## 7. Patch 2B Groq Grading Provider Client (commit `1cae30b`)

**What was added:**
* `services/grading-worker/src/grading_provider_client.py` — `GroqClient` class:
  * Raw `httpx.AsyncClient` POST to `https://api.groq.com/openai/v1/chat/completions` (OpenAI-compatible endpoint; no Groq SDK, no OpenAI SDK).
  * Constructor validates `api_key` (blank → error), `model` (blank → error), `timeout_seconds` (≤0 → error). No env-var reads inside the class.
  * `grade(prompt) -> str` builds Authorization header and request body, posts, extracts `choices[0]["message"]["content"]`, strips whitespace.
  * All `LLMGraderError` messages are safe: no API key, prompt, transcript, response body, Authorization header, or full URL logged.
* `services/grading-worker/requirements.txt` — `httpx>=0.27,<1` declared (was already installed in venv as transitive dep; now declared for production correctness).
* `services/grading-worker/src/worker.py` — `_build_grader_client()` now reads:
  * `LLM_PROVIDER` (default `"groq"`): any value other than `"groq"` raises `LLMGraderError` → falls back to fake.
  * `GROQCLOUD_API_KEY`: absent or blank raises `LLMGraderError` → falls back to fake.
  * `GROQ_MODEL` (default `"llama-3.1-8b-instant"`).
  * `GROQ_TIMEOUT_SECONDS` or `LLM_TIMEOUT_SECONDS` (default `"20.0"`): non-float value raises `LLMGraderError` → falls back to fake.
  * Returns a constructed `GroqClient` on success.
* All error paths — missing key, unsupported provider, invalid timeout, `LLMGraderError` from `llm_grade_with_client`, `asyncio.TimeoutError` — fall back to `fake_grade()` through the existing exception handler in `process_session_completed_job`.
* `services/grading-worker/tests/test_grading_provider_client.py` — 17 mocked `GroqClient` tests: 5 constructor validation, 2 success, 2 transport errors, 2 non-2xx, 4 malformed response, 2 security (no key or prompt in exceptions or logs).
* `services/grading-worker/tests/test_worker_patch2a.py` — 6 new worker integration tests for `_build_grader_client()` env wiring added; existing 12 tests updated for Groq hermeticity (delenv `GROQCLOUD_API_KEY` + `LLM_PROVIDER` where needed).

**What is NOT yet done (at time of Patch 2B):**
* `GRADING_PROVIDER` default/unset remains `"fake"`. Live path remains fake unless `GRADING_PROVIDER=llm` is explicitly set.
* No `services/core-api/` or DB schema changes.
* Real Groq live test was completed in Patch 3 — see Section 9.

**Verification evidence (pre-commit):**
* `py_compile` pass on all 5 Patch 2B files.
* 57/57 mocked grading-worker tests pass across the full test suite.
* No Gemini references anywhere in grading-worker source or tests.
* No Groq SDK, OpenAI SDK, or other provider SDK import (`httpx` only).
* No real API calls in tests (all via `patch("src.grading_provider_client.httpx.AsyncClient")`).
* No DB or RabbitMQ calls in tests.
* No API key, prompt, transcript, response body, Authorization header, or full URL in any log or exception message.

## 8. CUDA/STT Stabilization (torch cu118 → cu126)

**Context:** During Patch 3 preparation a TEN session's STT fell back to CPU. Root cause: `torch+cu118` bundled `libcudart.so.11.0`; system `ldconfig` registered CUDA 12.1 libraries; `ctranslate2 4.7.1` requires `libcublas.so.12` (CUDA 12.x). Mixed CUDA 11/12 runtimes in the same process → `cudaErrorUnknown`. GPU: NVIDIA GeForce RTX 3050 Ti Laptop GPU, driver 595.58.03.

**Fix applied (venv-only, no source changes):**
* Upgraded `torch 2.7.1+cu118` → `torch 2.7.1+cu126`, `torchaudio 2.7.1+cu118` → `2.7.1+cu126`, `torchvision 0.22.1+cu118` → `0.22.1+cu126`.
* All 14 `nvidia-*-cu12` packages installed at exact torch-pinned versions via `--index-url https://download.pytorch.org/whl/cu126 --force-reinstall`.
* Removed 24 orphan packages: 11 `nvidia-*-cu11` and 13 no-suffix/cu13 packages. Note: pip namespace package corruption occurred during cu11 removal (shared namespace dirs deleted); resolved by a second full torch+cu126 force-reinstall to restore exact-version files.
* Final `pip check`: no broken requirements.
* After package fix, `cuInit(0)` still returned `CUDA_ERROR_UNKNOWN (999)` — root cause was the NVIDIA kernel module (`nvidia.ko`) in a bad state, not a package issue. Confirmed via direct ctypes call: `libcuda.so.1 cuInit(0) → 999`. Resolved by system reboot.

**Post-reboot verification (all gates passed):**
* `cuInit(0)` via ctypes: `0 → CUDA_SUCCESS`.
* `torch.cuda.is_available()`: `True` (no warning).
* `torch.cuda.device_count()`: `1`.
* `ctranslate2.get_cuda_device_count()`: `1`.
* `faster-whisper tiny` on `device="cuda"`, `compute_type="float16"`: loaded successfully.
* `pip check`: no broken requirements.
* No source files, DB rows, or git commits modified during stabilization.

**Ongoing drift note:** `torch`, `torchaudio`, `torchvision`, and all `nvidia-*` packages remain absent from `services/core-api/requirements.txt` — they are manually installed local venv drift, not tracked changes.

## 9. Patch 3 Controlled One-Shot Groq Grading Test

**Pre-conditions met:**
* CUDA/STT stabilized (Section 8). TEN GPU path active.
* Grading-worker consume loop was **not running**.
* Reconciliation scanner `--execute` was **not used**.
* Target session `...a3d35b36` had `has_grading=False` confirmed by pre-live SELECT.

**TEN session (suffix `...a3d35b36`):**
* STT GPU path confirmed in TEN log: `ctranslate2_cuda_devices=1`, `torch_cuda_available=True`, Whisper loaded on `device=cuda`, `compute_type=int8_float16`.
* Session completed cleanly: `raw_backup_json` persisted 30 events, 15 `USER_TURN` events, `session.completed` published.

**Live grading invocation:**
* Exactly one direct `process_session_completed_job` call with `GRADING_PROVIDER=llm`, `LLM_PROVIDER=groq`, `GROQCLOUD_API_KEY` set (env var name only — value never printed).
* Groq call succeeded. `grading_results` row created.

**Verified DB result (SELECT-only):**
* `detailed_corrections[0].type`: `grader_info` ← confirms LLM path executed, not fake fallback.
* `detailed_corrections[0].grader_version`: `llm_grader.v1`.
* `is_fake_text`: `False` (summary text is not the fake grader placeholder).
* `feedback_len`: 252 characters.
* `overall_score`: 2.95 ✅ in [0, 10].
* `fluency_score`: 4.00 ✅ in [0, 10].
* `grammar_score`: 2.00 ✅ in [0, 10].
* `vocab_score`: 3.00 ✅ in [0, 10].
* `graded_at`: 2026-05-23 18:17:07 UTC.

**What is NOT yet done:**
* Normal RabbitMQ grading-worker consume loop with `GRADING_PROVIDER=llm` has **not** been tested.
* Browser UI verification of the real Groq `grading_results` row has **not** been done.
* UI still shows "DEV PREVIEW — Simulated Grading" badge and disclaimer. Badge removal requires separate authorization.
* Real grading stability over multiple sessions is unverified.
* `grader_version` is not a DB column — stored only in `detailed_corrections[0]` JSONB.
* DB schema, migrations, `requirements.txt`, and all runtime source files were **not modified** during Patch 3.

## 10. Patch 4 Normal RabbitMQ Consume-Loop Groq Grading Test

**What was tested:**
* Normal RabbitMQ grading-worker consume-loop path with `GRADING_PROVIDER=llm` via `consume_forever()`.
* This was **not** the Patch 3 direct one-shot invocation. The worker connected to RabbitMQ, consumed the queued message, called Groq, and wrote to DB through the full production code path.

**Queue preparation (separate approved step before test):**
* Queue had 4 stale messages from prior development sessions.
* Purged via `rabbitmqctl purge_queue luve.session.completed`; confirmed `messages=0`.
* One fresh TEN session was then created. Queue confirmed `messages=1` before starting worker.

**Fresh session (target suffix `...218666a0`):**
* Pre-worker DB state: `status=completed`, `raw_backup_json` present, `event_count=8`, `USER_TURN count=4`, `has_grading=False`.

**Worker invocation:**
* Started exactly once using `timeout 60 python -m src.worker` (no code changes).
* `RABBITMQ_HOST=localhost` override required — default is `"rabbitmq"` (Docker-internal hostname); worker ran as a local Python process.
* Env vars loaded by grep from `.env`; values never printed.

**Worker log (sanitized):**
```
HTTP Request: POST https://api.groq.com/openai/v1/chat/completions "HTTP/1.1 200 OK"
grading.completed session_id=9de7a1e3-... overall_score=2.95 provider_requested=llm grader_version=llm_grader.v1
```
* No `grading.llm_failed_fallback` occurred.
* Exit code 124 (SIGKILL from `timeout` after idle) — expected.

**Queue after worker:** `messages=0`, `messages_ready=0`, `messages_unacknowledged=0`, `consumers=0`.

**Verified DB result (SELECT-only):**
* `detailed_corrections[0].type`: `grader_info` ← confirms LLM path, not fake fallback.
* `detailed_corrections[0].grader_version`: `llm_grader.v1`.
* `is_fake_text`: `False`.
* `feedback_len`: 168 characters.
* `overall_score`: 2.95 ✅ in [0, 10].
* `fluency_score`: 4.00 ✅ in [0, 10].
* `grammar_score`: 2.00 ✅ in [0, 10].
* `vocab_score`: 3.00 ✅ in [0, 10].
* All score range checks: True.

**What remained after Patch 4:**
* Browser UI verification of a real `llm_grader.v1` row — completed in Patch 5 (see Section 11).
* UI DEV PREVIEW badge and disclaimer label remain; removal and text correction require a separate authorized patch — see Patch 6 (Section 12 Known Limitations).
* Real grading stability over multiple sessions is unverified.
* CUDA dependency reproducibility from `services/core-api/requirements.txt` remains unresolved local venv drift.

## 11. Patch 5 UI Verification of Real llm_grader.v1 Row

**What was verified:**
* Actual browser-rendered UI for session `9de7a1e3-e374-487e-af91-4d0b218666a0` (suffix `...218666a0`) — the same session graded by `llm_grader.v1` via the full RabbitMQ consume-loop in Patch 4.
* Verification used temporary Playwright automation (`/tmp/luve-playwright-ui-check/`; installed outside the repo using system Chrome `/usr/bin/google-chrome`). No repo files were modified.
* Token file `/tmp/luve_token` was deleted immediately after the verification run.
* Later re-run attempts failed because `/tmp/luve_token` was not visible inside Claude Code's Bash mount namespace. The first successful run (exit code 0, all checks passed) is the authoritative result.

**Correct UI URL confirmed:**
* `http://localhost:8080/control-center` — returns HTTP 200 and the correct control center page.
* `http://localhost:8000/static/index.html` — returns HTTP 404. This route does not exist.

**API response (`GET /api/v1/sessions/9de7a1e3-.../grading`):**
* HTTP status: **200** ✓
* `overall_score`: 2.95 ✓
* `fluency_score`: 4.00 ✓
* `grammar_score`: 2.00 ✓
* `vocab_score`: 3.00 ✓
* `detailed_corrections[0].type`: `grader_info` ✓
* `detailed_corrections[0].grader_version`: `llm_grader.v1` ✓
* `ai_summary_feedback`: non-empty ✓
* Fake placeholder text (`"Fake grading completed…"`): absent ✓

**Rendered UI (Playwright DOM verification):**
* Session Analysis card (`#session-grading-card`): visible ✓
* Overall tile: `3.0` (`Number(2.95).toFixed(1)` → rounds to 3.0 in JS) ✓
* Fluency tile: `4.0` ✓
* Grammar tile: `2.0` ✓
* Vocab tile: `3.0` ✓
* Summary paragraph: non-empty ✓
* `Graded at:` timestamp: visible ✓
* Retry button: absent ✓ (200 response, card rendered scores)
* DEV PREVIEW badge: visible (as expected — not removed) ✓
* `fake_grader.v1` disclaimer: visible (as expected — not removed) ✓

**Semantic issue confirmed (pre-existing static HTML debt):**
* The badge reads `"DEV PREVIEW — Simulated Grading"` and the disclaimer reads `"…generated by fake_grader.v1…"` even though this row was produced by `llm_grader.v1`.
* These strings are static HTML in `services/core-api/src/static/index.html` — not driven by JS or any API field.
* This is a labeling inaccuracy introduced before Patch 3, not by Patch 5.
* Fixing these requires a separate authorized patch (Patch 6). Do not modify `static/index.html` without explicit authorization.

**What is NOT yet done:**
* UI label/disclaimer text fix (badge still says "Simulated Grading"; disclaimer still says `fake_grader.v1`). Requires Patch 6.
* Decision on whether UI should expose `grader_version`, provider name, or a real/fake indicator from the API response.
* Multi-session real grading stability remains unverified.
* CUDA dependency reproducibility from `services/core-api/requirements.txt` remains unresolved local venv drift.

**Constraints respected:**
* No Groq calls. No grading-worker started. No DB writes. No new TEN sessions. No RabbitMQ publish/consume. No repo files modified. No secrets printed.

## 13. Patch 6 — UI Label/Disclaimer Cleanup

**Patch 6 is complete (runtime change verified by static grep; committed separately).**

**Goal:** Remove the inaccurate "Simulated Grading" badge suffix and `fake_grader.v1` disclaimer reference from the Session Analysis card static HTML. Replace with neutral wording that is accurate for both `fake_grader.v1` and `llm_grader.v1` rows without overclaiming production readiness.

**File changed:** `services/core-api/src/static/index.html`

**Badge text (line ~144):**
* Old: `DEV PREVIEW — Simulated Grading`
* New: `DEV PREVIEW`

**Disclaimer text (line ~149):**
* Old: `Dev preview: current scores are generated by fake_grader.v1 and are not final pedagogical grading.`
* New: `Dev preview: scores are automatically generated and are not final pedagogical grading.`

**No other files changed.** No JS logic, no backend, no schema, no worker, no DB, no API changes.

**Verification (static grep — conclusive for text-only change):**
* Old strings absent: `grep "Simulated Grading\|fake_grader\.v1" static/index.html` → no output ✓
* New strings present: `grep "DEV PREVIEW" static/index.html` → line 144 ✓; `grep "automatically generated" static/index.html` → line 149 ✓
* Browser Playwright re-run was not completed due to `/tmp` mount namespace / token-file isolation issue. Not required for a static text-only HTML change with no JS logic modified.

**Remaining as-is (not part of Patch 6):**
* DEV PREVIEW badge itself retained — production readiness is not claimed.
* `is_dev_preview: bool = True` in `GradingRead` remains hardcoded; JS does not read it. Wiring is future scope.
* No top-level `grader_version` or `is_ai_graded` field added to `GradingRead`.

**Constraints respected:**
* No Groq calls. No grading-worker started. No DB writes. No new TEN sessions. No RabbitMQ publish/consume. No backend/schema/worker files modified. No secrets printed.

## 14. Patch 7A + 7B — IDE Artifacts Ignored; CUDA Reproducibility Documented

**Both patches are complete and committed.**

### Patch 7A — `.gitignore` IDE artifacts (commit `ec94d10`)
* Added `.codegraph/` and `.cursor/` to `.gitignore` under the IDEs section.
* No runtime code changed. Eliminates recurring untracked entries from `git status`.

### Patch 7B — CUDA/cu126 reproducibility file
* Created `services/core-api/requirements-torch-cu126.txt`.
* Records the known-working PyTorch cu126 stack: `torch==2.7.1+cu126`, `torchaudio==2.7.1+cu126`, `torchvision==0.22.1+cu126`.
* Includes install-order instructions: this file must be installed before `requirements.txt` when creating a fresh GPU-capable venv.
* Documents the cuInit=999 kernel module reboot caveat.
* Does not add nvidia-\* packages manually — the torch cu126 wheel pulls correct transitive deps.
* `ctranslate2==4.7.1` and `faster-whisper==1.2.1` remain in `requirements.txt`.
* **No venv modified. No packages installed or uninstalled. No runtime code changed.**

**Verified environment (read-only venv check):**
* `torch`: `2.7.1+cu126` ✓
* `torch.version.cuda`: `12.6` ✓
* `torchaudio`: `2.7.1+cu126` ✓
* `torchvision`: `0.22.1+cu126` ✓
* `ctranslate2`: `4.7.1` ✓
* `faster-whisper`: `1.2.1` ✓

**Remaining gap:** Fresh-venv rebuild from these requirements files has not been executed. The reproducibility claim is based on recording the known-working state — not a clean install test.

**Constraints respected:**
* No packages installed or uninstalled. No venv modified. No runtime Python source changed. No Groq calls. No DB writes. No secrets printed.

## 15. Patch 7C — Multi-Session Real Groq Grading Stability Test

**Two sessions graded via normal RabbitMQ consume-loop with `GRADING_PROVIDER=llm`. Both returned structurally valid `llm_grader.v1` rows with no fallback. Score sensitivity at `temperature=0` is unresolved.**

### Session A (`f56364d6`)
* session_id: `20545d7f-e92a-4029-9bf3-e8c5f56364d6`
* Pre-worker DB: `status=completed`, `ended=True`, `raw_present=True`, `user_turn_count=2`, `has_grading=False`.
* Worker: started exactly once, `timeout 60`. Groq HTTP 200. `grading.completed`. No `grading.llm_failed_fallback`. Exit code 124 (idle timeout — expected).
* Queue: `messages=1` before → `messages=0` after.
* DB result (SELECT-only):
  * `marker_type`: `grader_info`
  * `marker_grader_version`: `llm_grader.v1`
  * `is_fake_text`: `False`
  * `feedback_len`: 173 characters
  * `overall_score`: 2.95 ✅ in [0, 10]
  * `fluency_score`: 4.00 ✅ in [0, 10]
  * `grammar_score`: 2.00 ✅ in [0, 10]
  * `vocab_score`: 3.00 ✅ in [0, 10]
  * All score range checks: True

### Session B (`98a58d10`)
* session_id: `9bc88289-2969-402b-940f-d64f98a58d10`
* Context: Originally attempted with a longer script that caused STT/finalization difficulty. Session finalized asynchronously after the user disconnected, completing with `user_turn_count=10`. Confirmed via SELECT-only DB check before worker run. One unsafe session (`af661bda`: `status=ready`, `ended=False`, `raw_present=False`, `user_turn_count=0`) was explicitly excluded — it never completed in the DB and produced no queue message.
* Pre-worker DB: `status=completed`, `ended=True`, `raw_present=True`, `user_turn_count=10`, `has_grading=False`.
* Worker: started exactly once, `timeout 60`. Groq HTTP 200. `grading.completed`. No `grading.llm_failed_fallback`. Exit code 124 (idle timeout — expected).
* Queue: `messages=1` before → `messages=0` after.
* DB result (SELECT-only):
  * `marker_type`: `grader_info`
  * `marker_grader_version`: `llm_grader.v1`
  * `is_fake_text`: `False`
  * `feedback_len`: 226 characters
  * `overall_score`: 2.95 ✅ in [0, 10]
  * `fluency_score`: 4.00 ✅ in [0, 10]
  * `grammar_score`: 3.00 ✅ in [0, 10]
  * `vocab_score`: 2.00 ✅ in [0, 10]
  * All score range checks: True

### Score Comparison (all four live-graded sessions)

| Session | Patch | overall | fluency | grammar | vocab |
|---|---|---|---|---|---|
| `a3d35b36` | Patch 3 (direct one-shot) | 2.95 | 4.00 | 2.00 | 3.00 |
| `218666a0` | Patch 4 (consume-loop) | 2.95 | 4.00 | 2.00 | 3.00 |
| `f56364d6` | Patch 7C Session A | 2.95 | 4.00 | 2.00 | 3.00 |
| `98a58d10` | Patch 7C Session B | 2.95 | 4.00 | 3.00 | 2.00 |

* No single dimension changed by ≥1.5 across any session pair.
* Session B grammar/vocab swapped relative to all prior sessions (grammar +1.00, vocab −1.00); overall unchanged at 2.95.

### Verdict: INVESTIGATE

**Reliability conclusion:** RabbitMQ consume-loop, provider dispatch, `GroqClient`, DB upsert, and queue drain behaved reliably across multiple sequential runs. Worker exit-code-124 pattern (idle timeout after single message) is confirmed stable.

**Calibration conclusion:** Score sensitivity is unresolved. Repeated `overall=2.95` across all four sessions — including sessions with different transcript lengths (2, 4, 10, 15 user turns) and different intended quality — suggests possible anchoring in the prompt/rubric, a model floor effect at `temperature=0`, or STT transcript noise masking real quality differences.

**SRE caution:** Do not expand `GRADING_PROVIDER=llm` usage, run further Groq calls, or claim production readiness until the prompt/rubric and transcript quality are audited (Patch 7D). No production-readiness claim is made.

**Constraints respected:**
* No runtime source files modified. No DB writes beyond worker-initiated upserts. No RabbitMQ purged. No secrets printed. Git worktree clean throughout.

## 16. Patch 7D-A/B — Grader Calibration and Sanitized Transcript Review

**Patch 7D-B synthetic calibration test and Patch 7D-A sanitized transcript review are complete. Both were read/call-only; no files, DB rows, or RabbitMQ messages were modified.**

### Patch 7D-B: Synthetic Direct Calibration Test (1 Groq call, no DB write)

A synthetic strong English transcript was constructed in code — no STT, no RabbitMQ, no DB, no session. `llm_grade_with_client` was called directly with `GroqClient` using `llama-3.1-8b-instant` at `temperature=0`.

**Result:**
* `fluency_score`: 8.00
* `grammar_score`: 9.00
* `vocab_score`: 8.50
* `overall_score`: 8.52
* `grader_version`: `llm_grader.v1`
* `high_score_pass`: True (all 3 sub-scores ≥ 7.0)

**Conclusion:** Prompt and model are fully capable of producing high scores when input is clean and well-structured. A prompt calibration floor or model floor does **not** exist — these hypotheses are ruled out.

### Patch 7D-A: Sanitized Transcript Quality Review (read-only)

SELECT-only DB access. No `raw_backup_json` printed. USER_TURN `.payload.text` fields extracted, sanitized, and analyzed per session.

| Session | Turns | Words | Avg chars/turn | Key STT issue | Scores |
|---|---|---|---|---|---|
| `a3d35b36` | 15 | 74 | 23 | Fragmented informal, short turns, "Worship man!", "I am very love you" | 2.95 / 4.00 / 2.00 / 3.00 |
| `218666a0` | 4 | 23 | 28 | Very short; "first hot. Yes, first hot." is a clear STT artifact | 2.95 / 4.00 / 2.00 / 3.00 |
| `f56364d6` | 2 | 14 | 34 | Only 2 of 3 intended sentences captured; "buyed" → "apply" (STT misrecognition) | 2.95 / 4.00 / 2.00 / 3.00 |
| `98a58d10` | 10 | 92 | 47 | Severe STT noise first half ("last whisker", "first pressed pull and break and break and break"); cleaner second half | 2.95 / 4.00 / 3.00 / 2.00 |

### Root-Cause Conclusion

**Confirmed primary cause:** STT/transcript quality. All four live sessions contained short, fragmented, noisy, or grammatically limited transcripts. The grader scored each session correctly for what it received. The synthetic test (8.52 overall from clean input) proves the grader is functional.

**Ruled out:** Prompt calibration anchoring, parser defaults, model hard floor.

**Remaining structural gap (not primary cause):** Grammar and vocab both carry weight 0.35 in `overall = fluency×0.30 + grammar×0.35 + vocab×0.35`. Any g/v swap produces identical overall. Session B (`98a58d10`) returned g=3/v=2 instead of g=2/v=3 — real sub-score change, but invisible at the overall level. The formula is not the root cause of the repeated 2.95, but it masks sub-score sensitivity.

### SRE Warning

Do not enable broader `GRADING_PROVIDER=llm` use until a transcript quality gate or "insufficient evidence" behavior is implemented (Patch 7E). Sessions with 14 words or severe STT noise currently receive authoritative numeric scores, which misrepresents grading confidence to users. No production-readiness claim is made.

**Constraints respected:**
* No runtime source files modified. No DB writes. No RabbitMQ operations. No secrets or raw transcripts printed. Exactly 1 Groq call made (Patch 7D-B). Git worktree clean throughout.

## 17. Patch 7E — Transcript Quality Gate

**Runtime commit: `8b16c50` fix(grading-worker): skip insufficient transcript evidence**

**Files changed:**
* `services/grading-worker/src/worker.py` — +12 lines (gate logic)
* `services/grading-worker/tests/test_worker_patch2a.py` — +81 lines (fixture update + 3 new gate tests; existing fixture word count increased to 34 student words so existing tests pass the gate)

### Behavior

A second early-return guard was added to `process_session_completed_job` immediately after the existing `has_student_turns` check and before provider dispatch:

```
if not has_student_turns → existing gate (unchanged)
↓
min_student_words = int(os.getenv("GRADING_MIN_STUDENT_WORDS", "25"))
student_word_count = int(quality_signals.get("student_word_count", 0) or 0)
if student_word_count < min_student_words → new gate
    log grading.skipped_insufficient_evidence + return
↓
provider dispatch → Groq / fake (unchanged)
```

* **Default threshold:** 25 student words (`GRADING_MIN_STUDENT_WORDS=25`).
* **Threshold read at call time** (not module import) so `monkeypatch.setenv` works in tests.
* **Below threshold:** logs `grading.skipped_insufficient_evidence` with `session_id`, `user_turn_count`, `student_word_count`, `min_student_words` — no transcript text in logs. Returns immediately. No `_build_grader_client()` call, no `llm_grade_with_client()` call, no `fake_grade()` call, no `repository.upsert_grading_result()` call.
* **Above threshold:** existing provider dispatch / fallback / upsert behavior unchanged.
* **Gate disabled:** `GRADING_MIN_STUDENT_WORDS=0` disables the gate (all sessions with at least one student turn proceed to provider dispatch).
* **Idempotency:** early return is clean (`None`); RabbitMQ `message.process(requeue=False)` ACKs the message regardless; same message redelivered produces same early return.

### Calibration basis

| Session | student_word_count | gate outcome at threshold=25 |
|---|---|---|
| `f56364d6` | ~14 | **skipped** |
| `218666a0` | ~23 | **skipped** |
| `a3d35b36` | ~74 | passes gate → Groq call |
| `98a58d10` | ~92 | passes gate → Groq call |

The 25-word threshold is conservative — it targets only sessions that are objectively too thin for reliable scoring. It does not gate longer-but-noisy STT transcripts.

### Verification

* `py_compile` passed for 5 grading-worker modules: `worker.py`, `llm_grader.py`, `grading_provider_client.py`, `evaluation_input_builder.py`, `grading_repository.py`.
* **60/60 mocked tests passed** across `test_worker_patch2a.py` (21), `test_llm_grader.py` (17), `test_grading_provider_client.py` (22).
* No live services started. No Groq calls. No DB writes. No RabbitMQ operations.

### DevOps/SRE value

* Reduces misleading authoritative numeric scores for sessions too short to grade reliably.
* Reduces avoidable Groq spend on sessions where the model cannot produce a meaningful result.
* Logs include counts (not text) — log-safe and grep-able for skip rate monitoring.
* No DB schema changes, no API changes, no UI changes, no migration required.

### Known limitations (as of Patch 7E)

* Below-threshold sessions produce **no `grading_results` row**. `GET /api/v1/sessions/{id}/grading` returns HTTP 404. UI shows "Grading pending — try again later." indefinitely. There is no user-facing "session too short to grade" status.
* No DB marker or row exists for skipped sessions — skips are observable only via logs (`grading.skipped_insufficient_evidence`).
* Gate checks minimum word count only. Longer transcripts with severe STT noise (e.g., `98a58d10` at 92 words) still pass the gate and receive a Groq call.
* `GRADING_MIN_STUDENT_WORDS` set to a non-integer string would cause `int()` to raise `ValueError` inside `process_session_completed_job` — caught by the outer `except Exception` handler in `consume_forever()`, logged as `grading.job_failed`, message ACK'd. Env validation hardening is future work.

### Future work (beyond Patch 7E)

* Explicit "insufficient evidence" API/UI status so users see a meaningful message instead of "pending" (Patch 7F).
* Top-level `grader_version` / `grading_status` field in `GradingRead` or a separate status endpoint.
* Optional transcript noise / STT-confidence gate for transcripts that pass word-count but have high character-level noise.
* Monitoring: skip count rate, fallback count rate, score distribution over time, queue depth.
* Regrade mechanism: if `GRADING_MIN_STUDENT_WORDS` threshold is lowered, previously skipped sessions have no DB row and no queue message — a reconciliation re-publish or direct one-shot call would be needed.

## 18. Patch 7F-1 — Grading Status Endpoint and Insufficient-Evidence UI

**Runtime/UI commit: `ddb46ec` feat(core-api): expose grading status for insufficient evidence**

**Files changed:**
* `services/core-api/src/api/v1/sessions.py`
* `services/core-api/src/schemas/session.py`
* `services/core-api/src/services/session_service.py`
* `services/core-api/src/static/index.html`

### Behavior

A new read-only `GET /api/v1/sessions/{session_id}/grading/status` endpoint was added. It returns a `GradingStatusRead` response with the following fields:
* `session_id` — UUID
* `status` — one of: `"graded"`, `"pending"`, `"insufficient_evidence"`
* `student_word_count` — `int | None` (present when status was inferred from word count; absent for `"graded"`)

**Status inference logic (server-side, no DB write):**
1. `grading_results` row exists for session → `"graded"`
2. No row and `student_word_count < GRADING_MIN_STUDENT_WORDS` → `"insufficient_evidence"`
3. Otherwise → `"pending"`

`raw_backup_json` is parsed server-side to compute `student_word_count` but is never returned in the response. If `raw_backup_json` is `NULL`, `student_word_count` is `None` and status conservatively falls back to `"pending"`.

**Malformed `GRADING_MIN_STUDENT_WORDS`** (non-integer string) falls back to `25` via `_get_min_student_words()`.

**Existing contracts unchanged:**
* `GET /api/v1/sessions/{session_id}/grading` is unmodified.
* `GradingRead` schema is unmodified; score fields (`overall_score`, `fluency_score`, `grammar_score`, `vocab_score`) remain non-nullable `float`.
* No DB migration. No worker changes.

**Route registration order:** `GET /grading/status` → `GET /grading` → `GET /{session_id}`. FastAPI path parameters cannot shadow literal path segments at different URL depths; order is for clarity.

Three pure helpers added to `session_service.py`:
* `_parse_raw_backup_events(raw_backup_json)` — handles SQLAlchemy (decoded Python list/dict) and asyncpg (JSON string) JSONB shapes.
* `_compute_student_word_count(raw_backup_json)` — returns `None` for `None` input; returns `int` (possibly 0) for all other inputs. Handles list[dict], JSON string, double-encoded events, and unparsable strings.
* `_get_min_student_words()` — reads `GRADING_MIN_STUDENT_WORDS` at call time (not module import) with `25` fallback.

### UI behavior

`fetchAndShowGrading` in `static/index.html` was updated to call `/grading/status` first, then branch on `status`:
* `"insufficient_evidence"` → renders `"Not enough speech to grade. Try a longer session."` (amber text); no Retry button; no score tiles.
* `"pending"` → keeps existing "Grading pending — try again later." message + Retry button.
* `"graded"` → proceeds to call `/grading` and renders existing score tile UI (unchanged).
* `/grading/status` 404 → hides the grading card.
* Non-200 status → rose error message with HTTP code.

### Verification

* `py_compile` passed for: `src/schemas/session.py`, `src/services/session_service.py`, `src/api/v1/sessions.py`.
* Import smoke passed: `/sessions/{session_id}/grading/status` registered; `/sessions/{session_id}/grading` still present; `GradingRead.overall_score` remains `float`; `GradingStatusRead` has `student_word_count`.
* Helper smoke passed: list[dict], JSON string, double-encoded events, `None`, and invalid JSON all handled correctly (5 assertion checks).
* UI grep passed: `/grading/status` call present; `insufficient_evidence` branch present; `"Not enough speech to grade. Try a longer session."` present; `status === "graded"` guard present.
* No Groq calls. No worker started. No DB writes. No RabbitMQ operations. No sessions created.

### DevOps/SRE value

* Removes retry treadmill for users whose sessions were skipped by the Patch 7E word-count gate — they now see an actionable message instead of an indefinite "pending" retry loop.
* Preserves full backward compatibility: existing `/grading` consumers are unaffected.
* Avoids DB migration — status is inferred dynamically from data already present.
* Avoids misleading numeric scores in the UI for below-threshold sessions.
* Log event `grading.status_inferred` emitted on each `/grading/status` call with `session_id`, `status`, and `student_word_count` for grep-based observability.

### Known limitations (as of Patch 7F-1)

* No DB audit trail for skipped sessions — skip state is dynamic inference, not a persisted row.
* Status inference is threshold-dependent: if `GRADING_MIN_STUDENT_WORDS` is changed, the same session may infer differently on a subsequent `/grading/status` call.
* No persistent `grading_status` column yet — adding one requires a migration strategy that does not currently exist in the repo.

### Future work (beyond Patch 7F-1/7F-2)

* Metrics/log aggregation for skip and pending rates over time.
* Eventual DB-backed `grading_status` column once a migration strategy is established.
* Production hardening: shared quality helper between worker and status endpoint, 8080/control-center proxy standardisation, regrade mechanism for threshold changes (Patch 7G).

### Patch 7F-2 — Read-only Smoke Test (PASS)

**Verdict: PASS — all 5 API checks and 13/13 UI assertions passed.**

**Candidate sessions (SELECT-only, no raw transcripts printed):**

| Type | Suffix | student_word_count | has_grading |
|---|---|---|---|
| graded | `98a58d10` (`9bc88289-…`) | 92 | True |
| insufficient_evidence | `3d1eca15` (`f794869a-…`) | 5 | False |
| pending | `49639bde` (`4e624753-…`) | None (NULL raw_backup_json) | False |

Real candidates existed for all three statuses — no route interception mock needed.

**API smoke results (curl, Bearer token from `/tmp/luve_token`, token never printed):**

| Call | Expected | Result |
|---|---|---|
| `GET /grading/status` — graded | `200 status=graded` | ✅ 200 graded |
| `GET /grading` — graded | `200 numeric scores, llm_grader.v1` | ✅ 200 overall=2.95 feedback_len=226 |
| `GET /grading/status` — insufficient | `200 status=insufficient_evidence wc=5` | ✅ 200 insufficient_evidence wc=5 |
| `GET /grading` — insufficient | `404 Grading result not ready` | ✅ 404 |
| `GET /grading/status` — pending | `200 status=pending wc=None` | ✅ 200 pending wc=None |

**UI smoke results (Playwright 1.60, headless Chrome `/usr/bin/google-chrome`):**

Port 8080 Nginx proxy was not running. UI loaded via `file:///…/static/index.html` with `luve.control.coreApiUrl` localStorage override pointing to `http://localhost:8000`. All API calls hit the live core-api on port 8000.

| Assertion | Result |
|---|---|
| graded — card visible | ✅ PASS |
| graded — score tiles present (Overall/Fluency/Grammar/Vocab) | ✅ PASS |
| graded — no insufficient message | ✅ PASS |
| graded — no Retry button | ✅ PASS |
| insufficient — card visible | ✅ PASS |
| insufficient — "Not enough speech to grade. Try a longer session." | ✅ PASS |
| insufficient — no score tiles | ✅ PASS |
| insufficient — no Retry button | ✅ PASS |
| insufficient — `/grading` not called after `status=insufficient_evidence` | ✅ PASS |
| pending — card visible | ✅ PASS |
| pending — "Grading pending — try again later." | ✅ PASS |
| pending — Retry button present | ✅ PASS |
| pending — no score tiles | ✅ PASS |

**13/13 PASS**

**DevOps/SRE conclusions:**
* `NULL raw_backup_json` → `student_word_count=None` → conservatively infers `pending`, preventing false `insufficient_evidence` for sessions with no event log.
* `/grading/status` and `/grading` routes both live and returning correct data.
* `/grading` backward compatibility fully preserved — existing consumers unaffected.
* UI branch prevents `/grading` fetch after `insufficient_evidence` — no retry treadmill.

**Side effects confirmed absent:**
* No files modified or staged during smoke.
* No Groq calls. No grading-worker started. No TEN/browser sessions.
* No DB writes. RabbitMQ queue: `messages=0`, `consumers=0` unchanged pre/post.
* No secrets, raw transcripts, `raw_backup_json`, or full feedback printed.
* `.understand-anything/` and `docs/system-map.md` untouched.

**Remaining limitations after Patch 7F-2:**
* Status is still dynamically inferred on each request — no persistent DB audit trail for skips.
* Port 8080 Nginx/proxy was not part of this smoke (UI loaded via `file://`).
* No DB-backed `grading_status` column yet.

## 19. Patch 7G — Production Hardening Audit

**Status: Audit/design complete (2026-05-25). No runtime files modified.**

This audit assessed production readiness requirements across 13 areas for the Patch 7E/7F grading status and quality gate system. No migrations, implementations, DB changes, Groq calls, or runtime code changes were made.

### 1. DB Persistence for Skipped Sessions

**Recommended approach: separate `grading_skip_log` table (Option D).** Four options were evaluated:

- **Option A — `grading_status` column on `grading_results`**: Cannot record skipped sessions; rows only exist after a grade completes.
- **Option B — nullable score row + `skipped_reason`**: Upserts a row with NULL scores. Requires `GradingRead.overall_score` to become `Optional[float]` — high blast radius on all existing consumers.
- **Option C — `grading_status` column on `sessions` table**: Adds unrelated state to the core sessions table; pollutes `SessionRead` schema decisions.
- **Option D — separate `grading_skip_log` table** (recommended): Purely additive migration, no null-score problem, clean rollback (`DROP TABLE`), enables SRE queryability, and enables regrade list sourcing from one authoritative table.

Proposed schema:
```sql
CREATE TABLE IF NOT EXISTS grading_skip_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES sessions(id),
    skipped_reason      TEXT NOT NULL,
    student_word_count  INT,
    min_words_threshold INT,
    skipped_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS grading_skip_log_session_id_key ON grading_skip_log (session_id);
```

Migration SQL file created in Patch 7G-8A (commit `d2bb908`): `infrastructure/db-migrations/0001_grading_skip_log.sql` exists and is committed. **Migration applied and verified on local DB — Patch 7G-8B Execute complete (2026-05-26).** `grading_skip_log` table now exists in the database; row_count=0; backup taken before apply at `/home/minhthuy/db-backups/backup_pre_0001_grading_skip_log_20260526_145532.dump` (111K, non-zero). See Patch 7G-8B Execute subsection in Section 19 for full results. Patch 7G-8C app integration audit/design is complete (audit/design only — no files modified except docs; see Patch 7G-8C subsection in Section 19); app integration implementation is partially complete: Patch 7G-8C-1 repository helper done (commit `cb79155`); **Patch 7G-8C-2 complete (2026-05-26): `worker.py` refactored to use `evaluate_grading_eligibility`; all four ineligible reasons write skip rows best-effort; commit `85ce409`.** Pending separate approved prompts for 7G-8C-3 through 7G-8C-4.

### 2. Migration Strategy

**Finding:** No Alembic or migration framework exists in the repo. Only `infrastructure/db-init/01-init.sql` (run once by Docker `entrypoint-initdb.d`). No `alembic_version` table confirmed by SELECT-only inspection.

**Recommended approach:** Numbered SQL migration directory:
```
infrastructure/db-migrations/
  0001_grading_skip_log.sql
  0002_...
```

Scripts must be idempotent (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN IF NOT EXISTS`). Each migration requires: `pg_dump` backup → preflight (active transaction check) → apply → verify → rollback plan.

**Postgres safety note:** `ALTER TABLE grading_results ADD COLUMN IF NOT EXISTS grader_version TEXT` is a metadata-only operation in Postgres 15 (nullable column, no DEFAULT) — no table rewrite, minimal lock.

Migration runbook and directory created in Patch 7G-7 (commit `bac73d2`): `infrastructure/db-migrations/README.md` defines naming convention, mandatory sections, apply runbook, privacy principle, and fresh-DB-sync strategy. `infrastructure/db-init/01-init.sql` unchanged. `0001_grading_skip_log.sql` created in Patch 7G-8A (commit `d2bb908`) and subsequently applied and verified in Patch 7G-8B Execute (2026-05-26): `grading_skip_log` table now exists in the database; see Patch 7G-8B Execute subsection in Section 19.

### 3. Critical Drift: Worker vs. Core-API Word-Count Helper

**Finding:** `evaluation_input_builder.build_evaluation_input()` (grading-worker) and `_compute_student_word_count()` (core-api status endpoint) diverge on three points:

| Difference | Worker (`evaluation_input_builder`) | Core-API (`session_service`) | Status |
|---|---|---|---|
| `event` field alias | `event.get("type") or event.get("event")` | `event.get("type")` only | **Fixed in Patch 7G-2** (`24fef0b`) |
| `None` input | `_coerce_event_list(None)` → `[]` → count = 0 | returns `None` (conservative "pending") | Intentional — preserved |
| Nested Mapping events | handled | not handled | **Fixed in Patch 7G-2** (`24fef0b`) |

**Risk (prior to Patch 7G-2):** Worker could skip a session (word count below threshold) while the core-api status endpoint inferred a higher word count and returned `"pending"` instead of `"insufficient_evidence"`, placing the user in a perpetual retry loop.

**Fixed in Patch 7G-2 (commit `24fef0b`):** `event` alias handling and Mapping-compatible checks applied to `_compute_student_word_count`. Helper smoke 8/8 passed. No cross-service import. Intentional remaining difference: `None` input returns `None` in core-api (conservative "pending") rather than `0` — prevents false `insufficient_evidence` for sessions with no event log.

### 4. Reconciliation Scanner Critical Gap

**Finding:** `scripts/reconciliation_scanner.py` `_count_user_turns()` counts `USER_TURN` events but does **not** enforce `GRADING_MIN_STUDENT_WORDS`. Running the scanner with `--execute` may route below-threshold sessions through the grading path, causing queue/job churn and future Groq spend if worker safeguards change; the audit must confirm the exact execute behavior before any runtime changes.

**Risk severity: Medium.** The worker's Patch 7E gate fires even when called directly from the scanner, preventing Groq calls for below-threshold sessions today. Real harms: misleading `ok` output (worker gate silently skips → scanner counts it as `processed`); perpetual re-selection (no grading row created = session always a candidate on next run); fragile dependency on the worker's internal gate remaining in place.

**Audit complete (2026-05-25):** Full findings and implementation sequence in the Patch 7G-4 subsection of this section.

**Operational constraint:** Do not run scanner with `--execute` until Patch 7G-4C is merged.

### 5. Observability

**Current log events (grep-able now):**
- `grading.skipped_insufficient_evidence` — session_id, user_turn_count, student_word_count, min_student_words
- `grading.status_inferred` — session_id, status, student_word_count
- `grading.llm_failed_fallback` — session_id (fake score silently upserted)
- `grading.completed` — session_id, overall_score, provider_requested, grader_version

**Short-term ops check:**
```bash
journalctl -u grading-worker | grep 'grading\.'
```

**Medium-term (Patch 7G-9):** Prometheus counters:
- `grading_jobs_total{outcome}` — `graded_llm`, `graded_fake`, `skipped_insufficient`, `failed_acked`, `failed_nacked`
- `grading_status_requests_total{status}` — `graded`, `pending`, `insufficient_evidence`, `not_found`
- `grading_fallback_total` — every fake-fallback event
- `grading_queue_depth` — sampled from RabbitMQ management API

Not implemented yet.

### 6. Regrade Strategy

**Two scenarios identified:**

1. **Graded but result was wrong:** Extend reconciliation scanner with `--force-regrade` + `--session-id` flags. `upsert_grading_result` `ON CONFLICT DO UPDATE` makes regrade idempotent.
2. **Skipped but threshold later lowered:** Source candidates from `grading_skip_log` (after Option D is implemented). Apply word-count gate with overridable `--min-words`. Delete the skip log row before resubmitting.

**Requirements for both:** dry-run default, batch-size limit (≤ 20), per-call rate limiting to avoid Groq spend spikes. Regrade tooling is Patch 7G-8 scope. Not implemented yet.

### 7. 8080/Control-Center Serving

**Implemented in Patch 7G-6 (commit `7d522d9`).**

`GET /control-center` route added to `main.py`; returns `FileResponse(_STATIC_DIR / "index.html")` where `_STATIC_DIR = Path(__file__).parent / "static"`. `StaticFiles` mount at `/static` serves CSS and other assets. Path computation is independent of uvicorn working directory. Paired with CORS lockdown in the same commit.

**No Nginx in `docker-compose.yml`** — still the case. The control center is now served directly by the FastAPI/Uvicorn process on port 8000. Port 8080 was a prior workaround; the canonical URL is now `http://localhost:8000/control-center`.

**Starlette 1.0.0 uses `anyio`, not `aiofiles`:** `StaticFiles` and `FileResponse` use `anyio.open_file` and `anyio.to_thread.run_sync`. `anyio 4.13.0` is already installed transitively via `uvicorn[standard]`. No new dependency added to `requirements.txt`.

### 8. API/UI Hardening

**Implemented in Patch 7G-3 (commit `55a4d02`):**
- `GradingStatusRead.status: str` → `status: Literal["graded", "pending", "insufficient_evidence"]`. Pydantic now raises `ValidationError` on unexpected values rather than silently passing them through.
- `fetchAndShowGrading` now has a 401/403 guard after the 404 check: shows "Session expired or unauthorized. Please refresh your token and try again." and returns before `/grading`.
- `fetchAndShowGrading` now has a `status !== "graded"` fail-closed guard after the `pending` block: shows "Unknown grading status. Please refresh and try again." and returns before `/grading`.

No breaking changes to `GradingRead`. Response JSON values (`"graded"`, `"pending"`, `"insufficient_evidence"`) unchanged.

### 9. Queue/Worker Production Safety

**Fake fallback risk (resolved in Patch 7G-5, commit `dcdf9ba`):** `grading.llm_failed_fallback` previously silently upserted `fake_grader.v1` scores on every Groq failure. In production, users would receive fabricated scores visually indistinguishable from real grading. **This production blocker is now gated.**

**Implemented (Patch 7G-5):** `GRADING_FAKE_FALLBACK` env var controls behavior:
- Default (unset/false): LLM failures log `grading.llm_failed_no_fallback` at ERROR and re-raise — no fake result written to DB. Exception escaping `process_session_completed_job` should cause `aio_pika`'s `message.process(requeue=False)` to NACK; actual DLQ delivery depends on RabbitMQ DLX configuration, which is not declared in this codebase.
- `GRADING_FAKE_FALLBACK=true`: Preserves previous fallback behavior — logs `grading.llm_failed_fallback` at WARNING and calls `fake_grade()`. Local dev escape hatch.
- `GRADING_PROVIDER=fake`: Explicit fake provider path; unaffected by this flag.

**DLQ (Patch 7G-9):** Add `grading.dlq` exchange + `grading_dead_letter` queue with `x-dead-letter-exchange` binding. Failed jobs accumulate for SRE inspection rather than being silently lost. Not implemented yet.

### 10. Transcript Quality / Noise Heuristics

**Current gate:** raw student word count ≥ 25. Does not catch long-but-noisy transcripts (e.g., session `98a58d10` at 92 words with severe STT artifacts).

**Future heuristics (not in current scope):**
- Unique-word ratio < 0.3 → flag as repetitive
- USER_TURN count < 3 → flag as insufficient dialogue
- Single-word repetition > 40% of student words → flag

Not implementing now. A `quality_flags JSONB` field on `grading_skip_log` can record heuristic flags later without a new table.

### 11. Security and Privacy

- **CORS lockdown (Patch 7G-6 — commit `7d522d9`):** `allow_origins=["*"]` replaced with 8-origin local allowlist (`localhost`/`127.0.0.1` on ports 3000/5173/8000/8080); `allow_credentials=False` (Bearer tokens in headers, not cookies); `CORS_ALLOW_ORIGINS` env var for operator override. No wildcard in default. Not browser-E2E-verified against a real origin; not tested with HTTPS or production domains.
- **Auth token in localStorage** — acceptable for local single-origin control center. Future external exposure requires CSP header (`Content-Security-Policy: default-src 'self'`) and no third-party scripts.
- **`raw_backup_json` not exposed** — confirmed: `/grading/status` response does not return transcript data.
- **Session ownership enforced** — both `/grading/status` and `/grading` enforce `s.user_id = :user_id` in the SQL JOIN.
- **Rate limiting** — `/grading/status` has no rate limit. Add `slowapi` (10 req/min per user) before broader use.

### 12. Production Readiness Checklist

Must-complete before enabling `GRADING_PROVIDER=llm` for real users:

- [x] CORS lockdown (`allow_origins=["*"]` → explicit list; Patch 7G-6 — commit `7d522d9`)
- [ ] Persistent skip/status active: `grading_skip_log` migration applied/verified + worker/scanner/backfill writing skip rows + `/grading/status` reading skip rows
- [x] Migration SQL file created (Patch 7G-8A — `infrastructure/db-migrations/0001_grading_skip_log.sql` committed, commit `d2bb908`; subsequently applied/verified in Patch 7G-8B Execute — 2026-05-26)
- [x] Migration apply plan documented (Patch 7G-8B planning — apply/verify/rollback plan complete; `docker exec luve_postgres` path confirmed; host psql/pg_dump unavailable; execute complete 2026-05-26)
- [x] Migration applied and verified on local DB (Patch 7G-8B Execute — 2026-05-26; table exists; row_count=0; 8 columns, 4 indexes incl. implicit pkey, 5 constraints, FK cascade verified; backup 111K non-zero at `/home/minhthuy/db-backups/backup_pre_0001_grading_skip_log_20260526_145532.dump`)
- [x] App integration audit/design complete (Patch 7G-8C — repository/worker/scanner/backfill/core-api integration design documented; implementation unblocked; 7G-8C-1/7G-8C-2 done, pending 7G-8C-3 through 7G-8C-4)
- [x] Repository `log_grading_skip()` implemented with mocked tests (Patch 7G-8C-1 — commit `cb79155`; `grading_repository.py` + `test_grading_repository_patch7g8c.py`; 5/5 asyncpg mocked tests pass; no live DB; no worker/scanner/backfill/core-api changes)
- [x] Worker skip-log integration implemented with mocked tests (Patch 7G-8C-2 — commit `85ce409`; `worker.py` calls `evaluate_grading_eligibility` before `build_evaluation_input`; best-effort `log_grading_skip` for all four ineligible reasons; 6/6 mocked tests pass; no live DB)
- [x] Migration strategy finalized (Patch 7G-7 — `infrastructure/db-migrations/README.md` created, commit `bac73d2`)
- [x] Scanner `--min-words` threshold parity (Patch 7G-4 — 7G-4A helper `462f5a4`; 7G-4B dry-run `5714ae4`; 7G-4C execute gate `7dcc9e8`)
- [x] Backfill threshold parity (Patch 7G-4D — commit `80d4db7`)
- [x] Word-count event-alias parity fix (Patch 7G-2 — commit `24fef0b`)
- [x] Status schema Literal + UI fail-closed handling (Patch 7G-3 — commit `55a4d02`)
- [x] Fake fallback gated (Patch 7G-5 — commit `dcdf9ba`)
- [ ] DLQ configured (Patch 7G-9)
- [ ] Rate limiting on `/grading/status`
- [ ] Metrics/log runbook written
- [ ] Regrade runbook written
- [ ] Smoke test runbook (standardized on `/control-center`, no `file://` workaround)
- [ ] Rollback plan documented
- [ ] Load/concurrency test at ≥ 10 concurrent sessions
- [ ] Secrets/privacy review (CSP header, localStorage token scope)

### 13. Recommended Patch Sequence

| Patch | Scope | Blocker for production? |
|---|---|---|
| 7G-1 | Audit record (docs only) | No |
| 7G-2 | `event` alias fix + word-count parity + contract tests | Yes |
| 7G-3 | `Literal[...]` status + UI unknown-status fallback + 401 handling | Yes |
| 7G-4 | Scanner `--min-words` hardening | Yes |
| 7G-5 | Fake fallback env gate (`GRADING_FAKE_FALLBACK=false` default) | Yes |
| 7G-6 | `StaticFiles` `/control-center` + CORS lockdown | Yes |
| 7G-7 | Migration strategy docs + numbered migration directory proposal | Yes |
| 7G-8A | `grading_skip_log` migration SQL file created (commit `d2bb908`; subsequently applied/verified in Patch 7G-8B Execute — 2026-05-26) | Yes |
| 7G-8B | Apply/verify `0001_grading_skip_log.sql` on local DB — **complete (Patch 7G-8B Execute — 2026-05-26; applied and verified on local DB; backup taken; all columns/indexes/constraints/FK verified)** | Yes |
| 7G-8C | App integration audit/design complete (Patch 7G-8C planning only); implementation partially complete: 7G-8C-1/7G-8C-2 done, pending 7G-8C-3/7G-8C-4 | After 7G-8B |
| 7G-8C-1 | `GradingRepository.log_grading_skip()` + mocked asyncpg tests — **complete (commit `cb79155`, 2026-05-26; 5/5 tests pass)** | After 7G-8B Execute |
| 7G-8C-2 | Worker eligibility refactor + skip-log write — **complete (commit `85ce409`, 2026-05-26; 6/6 mocked tests pass)** | After 7G-8C-1 |
| 7G-8C-3 to 7G-8C-4 | Scanner/backfill skip logging + core-api status LEFT JOIN — pending separate approved prompts | After 7G-8C-2 |
| 7G-9 | DLQ + Prometheus counters + regrade tooling | Recommended |

**Final recommendation:** Do not jump to DB migration. Do not run 7G-2 and 7G-3 in parallel. The DevOps/SRE-safe implementation order is strictly sequential:

1. Commit Patch 7G-1 audit docs first (this record).
2. Implement Patch 7G-2: event alias / word-count parity + contract tests.
3. Commit 7G-2 independently.
4. Implement Patch 7G-3: `Literal[...]` status type + UI unknown-status fallback + 401 handling.
5. Commit 7G-3.

Running patches in sequence keeps blast radius small, rollback simple (one commit reverts one concern), and test failures easy to attribute to a single change.

### Patch 7G-2 — Word-Count Parity Fix

**Runtime commit: `24fef0b` fix(core-api): align grading status word count detection**

**File changed:**
* `services/core-api/src/services/session_service.py`

**Behavior:**
`_compute_student_word_count()` now accepts `USER_TURN` events keyed by both `"type"` and `"event"` — matching `evaluation_input_builder` semantics. Event and payload type guards broadened from `dict`-only to `Mapping`-compatible, covering `UserDict` and other Mapping subclasses.

Preserved unchanged:
* `raw_backup_json is None` → `None` (conservative — still infers `"pending"`, not `"insufficient_evidence"`)
* Invalid JSON string → `0`
* `get_session_grading_status` logic, status strings (`graded` / `pending` / `insufficient_evidence`)
* `GradingRead`, `/grading` endpoint, `/grading/status` route, UI

**DevOps/SRE value:**
* Eliminates the drift that caused the worker to skip a session while the status endpoint returned `"pending"` instead of `"insufficient_evidence"`, ending the retry treadmill for affected users.
* No DB migration, no API contract change, no UI change — rollback is a single-commit revert.
* Intentional remaining difference: `None` input returns `None` in core-api (prevents false `insufficient_evidence` for sessions with no event log); worker returns `0` for `None` input.

**Verification (pre-commit):**
* `py_compile` passed: `src/services/session_service.py`
* Helper parity smoke: **8/8 PASS** — `type_key_user_turn`, `event_key_user_turn`, `mixed_type_and_event`, `json_string_event_key`, `double_encoded_event_key`, `mapping_like_event_payload`, `none_raw`, `invalid_json`
* No Groq calls. No worker/core-api started. No DB writes. No RabbitMQ operations. No sessions.

**Known limitations (as of Patch 7G-2):**
* No full shared package between services — helpers are duplicated with parity validated by smoke.
* No pytest harness in `services/core-api/` for service-layer unit tests (only STT GPU hardware scripts).
* Reconciliation scanner still has no word-count threshold gate — do not run with `--execute` + `GRADING_PROVIDER=llm` until Patch 7G-4.
* Status schema/UI hardening resolved in Patch 7G-3 (commit `55a4d02`).

### Patch 7G-3 — Status Literal and UI Fail-Closed Handling

**Runtime/UI commit: `55a4d02` fix(core-api): harden grading status UI contract**

**Files changed:**
* `services/core-api/src/schemas/session.py`
* `services/core-api/src/static/index.html`

**Behavior:**

`GradingStatusRead.status` field narrowed from `str` to `Literal["graded", "pending", "insufficient_evidence"]`. Pydantic now raises `ValidationError` on any value outside these three strings. Response JSON values are unchanged — the wire format is identical.

`fetchAndShowGrading` in `static/index.html` hardened with two new guards:

1. **401/403 auth guard** (inserted after 404 check, before generic `!statusRes.ok`):
   - `statusRes.status === 401 || statusRes.status === 403` → shows `"Session expired or unauthorized. Please refresh your token and try again."` → returns before `/grading` fetch.

2. **Unknown-status fail-closed guard** (inserted after `pending` block, before `/grading` fetch):
   - `status !== "graded"` → shows `"Unknown grading status. Please refresh and try again."` → returns before `/grading` fetch.

Preserved unchanged:
* `GradingRead` and all its score fields (`overall_score`, `fluency_score`, `grammar_score`, `vocab_score`) — non-nullable `float`, unchanged.
* `student_word_count: int | None` — unchanged.
* `/grading` endpoint — unchanged.
* `insufficient_evidence`, `pending`, and `graded` UI branches — unchanged.

**DevOps/SRE value:**
* Fail-closed: unexpected backend status values or auth failures cannot accidentally trigger a `/grading` fetch or leave the UI in a blank state.
* Tighter API schema contract: any future bug in the status endpoint that emits an unexpected value surfaces as a Pydantic `ValidationError` rather than silent pass-through.
* No DB migration, no API contract change, no worker changes — rollback is a single-commit revert.

**Verification (pre-commit):**
* `py_compile` passed: `src/schemas/session.py`.
* Schema Literal smoke: `get_origin(status_ann) is Literal`, `get_args(status_ann) == ("graded", "pending", "insufficient_evidence")`, `GradingRead.overall_score annotation is float` — `schema_literal_smoke_ok`.
* UI grep: auth message (L862), `insufficient_evidence` (L873), `pending` (L878), unknown message (L889), `// status === "graded"` (L893).
* Playwright route-intercept branch smoke: **22/22 PASS** — 6 cases (401, 403, unknown_status, insufficient_evidence, pending, graded); no live API calls, dummy token, `file://` page.
* No Groq calls. No worker/core-api started. No DB writes. No RabbitMQ operations. No sessions.

**Remaining (as of Patch 7G-3):**
* Reconciliation scanner threshold parity — audit complete (Patch 7G-4); 7G-4A implementation is next.
* Fake fallback production gate still unresolved (Patch 7G-5).
* Persistent `grading_skip_log` table not yet created in the database. Migration SQL file `0001_grading_skip_log.sql` committed in Patch 7G-8A (commit `d2bb908`) but not yet applied — no DB commands run, table does not exist yet. DB apply/verify is Patch 7G-8B scope; app integration is Patch 7G-8C+ scope.
* 8080/control-center serving and CORS lockdown still unresolved (Patch 7G-6).

### Patch 7G-4 — Reconciliation Scanner Threshold Parity Audit

**Status: Audit/design complete (2026-05-25). No runtime files modified.**

Source files inspected (read-only): `scripts/reconciliation_scanner.py`, `scripts/backfill_completed_sessions.py`, `src/worker.py`, `src/evaluation_input_builder.py`, `src/grading_repository.py`.

#### Scanner Behavior (current state)

`reconciliation_scanner.py` is a grace-window safety net: selects `completed` sessions with `raw_backup_json IS NOT NULL`, no `grading_results` row, and `ended_at` older than the grace threshold (default 5 min). Dry-run default; `--execute` writes to DB. Does **not** publish to RabbitMQ — calls `process_session_completed_job()` directly.

`_count_user_turns()` gaps (lines 80–98):
* Checks only `"type"` key — misses `"event"` alias used by `evaluation_input_builder`
* Uses `isinstance(e, dict)` — does not cover Mapping subclasses (e.g., `asyncpg.Record`)
* **Counts USER_TURN events (turns), not student words** — no word-count threshold applied
* No `GRADING_MIN_STUDENT_WORDS` check anywhere in the script

Execute path problem:
```
scanner: selects session → calls process_session_completed_job() → worker gate skips → returns None
scanner: no exception raised → processed += 1 → prints "ok"
next run: grading_results row still absent → session selected again → perpetual re-selection
```

The worker's Patch 7E gate fires even when invoked directly from the scanner, so Groq calls and fake-grading upserts do **not** happen today. The real harms are operational: misleading `ok` output, perpetual re-selection loop, and fragile dependency on the worker gate remaining in place.

#### Backfill Behavior (current state)

`backfill_completed_sessions.py` has identical `_count_user_turns()` code (same three defects). No grace window. `ORDER BY ended_at DESC` (newest first vs. scanner's ASC). Adds `--include-empty-raw` flag absent from scanner. Lower urgency — not designed for recurring cron — but needs parity in 7G-4D.

#### Threshold Parity Matrix

| Component | USER_TURN key | Mapping guard | None input | Word counting | Min threshold |
|---|---|---|---|---|---|
| `evaluation_input_builder` | `type` OR `event` | `isinstance(event, Mapping)` ✓ | → `[]` | `sum(len(text.split()))` per student turn | N/A — via `quality_signals` |
| `worker.py` gate (7E) | via builder | via builder | row still fetched | via `quality_signals["student_word_count"]` | `GRADING_MIN_STUDENT_WORDS` env, default 25 |
| `session_service` (7G-2) | `type` OR `event` ✓ | `isinstance(event, Mapping)` ✓ | → `None` (conservative) | `len(text_value.split())` | `GRADING_MIN_STUDENT_WORDS` env, default 25 |
| `reconciliation_scanner` | `type` only ✗ | `isinstance(e, dict)` ✗ | → `0` | **turn count only** ✗ | none ✗ |
| `backfill_completed_sessions` | `type` only ✗ | `isinstance(e, dict)` ✗ | → `0` | **turn count only** ✗ | none ✗ |

#### Failure Modes

| Failure Mode | Today? | Severity |
|---|---|---|
| Groq called for below-threshold session via scanner | No — worker gate fires | Low (today) |
| Fake grading row upserted for below-threshold session | No — worker returns before grader dispatch | Low (today) |
| Scanner prints `ok` when worker silently skipped | **Yes** | Medium — ops misleading |
| Session perpetually re-selected on every scanner run | **Yes** — no grading row ever created | Medium — ops noise |
| Groq called if `GRADING_MIN_STUDENT_WORDS=0` or worker gate later removed | Would happen | High — future risk |
| Scanner misses eligible sessions with `"event"` key (type-only check) | **Yes** — semantic error | Low (today) |

#### Desired Behavior Design

* New `--min-student-words N` CLI flag; default: `GRADING_MIN_STUDENT_WORDS` env or 25
* Candidate reason buckets: `eligible`, `skipped_existing_grading`, `skipped_no_raw_backup`, `skipped_invalid_raw_backup`, `skipped_no_user_turns`, `skipped_insufficient_words`
* Updated summary includes `eligible_total` and `skipped_insufficient_words`
* Execute path: call `evaluate_grading_eligibility()` before `process_session_completed_job()` — skip if ineligible, never call worker for below-threshold sessions

#### Shared Eligibility Helper

Proposed new file: `services/grading-worker/src/session_eligibility.py` (7G-4A — pure Python, zero runtime dependencies)

Key functions:
* `parse_raw_backup_events(raw_backup_json) -> list` — handles list, JSON string, per-event strings, None
* `get_event_kind(event) -> str | None` — checks `"type"` OR `"event"` alias; requires `isinstance(event, Mapping)`
* `count_user_turns(raw_backup_json) -> int | None` — None → None (conservative); otherwise int
* `count_student_words(raw_backup_json) -> int | None` — None → None; otherwise sum of word counts per USER_TURN text
* `EligibilityResult` dataclass: `eligible`, `reason`, `user_turn_count`, `student_word_count` — no transcript text
* `evaluate_grading_eligibility(raw_backup_json, min_student_words=25) -> EligibilityResult` — single decision point

Worker refactor is **optional/deferred** — worker already uses `evaluation_input_builder` which is correct; no change required in 7G-4.

#### Implementation Sequence

| Sub-patch | Scope | File(s) |
|---|---|---|
| 7G-4A | `session_eligibility.py` helper + ≥18 unit tests — no scanner/backfill wiring | `src/session_eligibility.py` (new), `tests/test_session_eligibility.py` (new) |
| 7G-4B | Wire scanner dry-run categorization to helper; execute path unchanged | `scripts/reconciliation_scanner.py` |
| 7G-4C | Gate scanner execute path — ineligible sessions skipped before `process_session_completed_job` | `scripts/reconciliation_scanner.py` |
| 7G-4D | Backfill parity | `scripts/backfill_completed_sessions.py` |

#### Test Plan (7G-4A — no DB/RabbitMQ)

Unit tests for helper: `None` input, empty list, invalid JSON, no USER_TURN, `type` key, `event` key, mixed aliases, Mapping-like event, per-event JSON strings, below threshold, exactly threshold (boundary), above threshold, `min_student_words=0` disables gate, multi-turn word sum, AI turns excluded, no transcript text in result.

#### Safety / Rollback

* Scanner does not publish to RabbitMQ — queue depth unaffected
* After 7G-4C: scanner will skip ineligible sessions before any `process_session_completed_job` call
* Each sub-patch is a single-file commit — rollback is one `git revert`
* Until 7G-4C merged: do not run scanner `--execute` on environments where below-threshold sessions exist with `GRADING_MIN_STUDENT_WORDS` unset or `=0`

#### Production-Readiness Impact

Scanner threshold parity is a **production blocker** before enabling recurring scanner/cron with `GRADING_PROVIDER=llm`. Not an immediate runtime blocker while scanner is manual-only and `GRADING_PROVIDER=fake` (default). Sessions below threshold are never Groq-graded today regardless of scanner state.

### Patch 7G-4A — Session Eligibility Helper

**Helper/test commit: `462f5a4` test(grading-worker): add session eligibility helper**

**Files added:**
* `services/grading-worker/src/session_eligibility.py` — pure Python eligibility helper
* `services/grading-worker/tests/test_session_eligibility.py` — 45 unit tests

#### Helper API

| Symbol | Signature | Returns |
|---|---|---|
| `DEFAULT_MIN_STUDENT_WORDS` | constant | `25` |
| `GradingEligibility` | frozen dataclass | `eligible`, `reason`, `user_turn_count`, `student_word_count` |
| `parse_raw_backup_events` | `(raw) -> list \| None` | `None` for None/invalid; list for valid |
| `get_event_kind` | `(event) -> str \| None` | Normalized kind string or `None` |
| `get_event_text` | `(event) -> str` | Student text from `payload.text`, or `""` |
| `count_user_turns` | `(raw) -> int \| None` | `None` for None/invalid; int count otherwise |
| `count_student_words` | `(raw) -> int \| None` | `None` for None/invalid; int word sum otherwise |
| `evaluate_grading_eligibility` | `(raw, min_student_words=25) -> GradingEligibility` | Single decision point |

#### Reason Codes

| Reason | Meaning |
|---|---|
| `eligible` | Session passes all gates |
| `no_raw_backup` | `raw_backup_json` is `None` |
| `invalid_raw_backup` | Present but not parseable as JSON array |
| `no_user_turns` | No `USER_TURN` events found |
| `insufficient_words` | Student word count < `min_student_words` |

#### Semantics

* `parse_raw_backup_events(None)` → `None` (not `[]`): distinguishes "no raw data" from "empty event list", so `evaluate_grading_eligibility` can report `no_raw_backup` vs `no_user_turns` correctly.
* `count_user_turns(None)` → `None`: conservative — means "unknown", not "zero turns".
* `get_event_kind` checks `"type"` key first, falls back to `"event"` key — covers both aliases used by `evaluation_input_builder`.
* `min_student_words=0` disables the word-count gate without special-casing: `0 < 0` is `False`, so `insufficient_words` check passes.
* `_decode_event` (private) handles per-event JSON-encoded strings within the event list.
* Handles: `list[dict]`, JSON array string, per-event JSON object strings, `None`, invalid JSON, `Mapping` subclasses (`UserDict`, `asyncpg.Record`).
* Stdlib-only imports (`json`, `collections.abc`, `dataclasses`, `typing`) — no DB, RabbitMQ, or project-runtime dependencies.
* `GradingEligibility` never exposes transcript text — verified by `test_evaluate_result_has_no_transcript_text`.

#### Verification

* `py_compile src/session_eligibility.py` — `py_compile_ok`
* `pytest tests/test_session_eligibility.py -q` — **45 passed**
* `pytest tests/ -q` — **105 passed** (60 pre-existing + 45 new)
* Import smoke: `eligibility_import_smoke_ok`
* Static safety check: `session_eligibility` referenced only in `src/session_eligibility.py` and `tests/test_session_eligibility.py` — not in scanner, backfill, or worker.
* No Groq calls. No services started. No DB writes. No RabbitMQ operations. No sessions.

#### DevOps/SRE Value

* Establishes correct shared eligibility semantics (type/event aliases, Mapping guard, word counting, threshold) as a tested unit before any scanner/backfill wiring.
* No runtime behavior change — scanner/backfill/worker behavior is unchanged.
* Prevents future scanner patches from embedding inconsistent inline parsing logic.
* Zero-dependency design: importable in any environment without pulling in DB/RabbitMQ/Pydantic.
* Frozen dataclass: `GradingEligibility` is immutable and hashable.

#### Remaining

* Scanner execute path is unchanged and must not be trusted for recurring use until Patch 7G-4C is merged.
* Backfill parity is not yet wired — Patch 7G-4D.

### Patch 7G-4B — Scanner Dry-run Eligibility Categorization

**Runtime/test commit: `5714ae4` test(grading-worker): categorize scanner dry-run eligibility**

**Files changed:**
* `services/grading-worker/scripts/reconciliation_scanner.py` — dry-run path wired to helper; new CLI flag; updated counters and summary
* `services/grading-worker/tests/test_reconciliation_scanner_patch7g4b.py` — 25 mocked unit tests (new file)

#### Behavior

Dry-run path (`if not args.execute`) now short-circuits via `evaluate_grading_eligibility(raw_json, min_student_words=args.min_student_words)` and `continue` — before the execute-path `user_turns = _count_user_turns(raw_json)` line. Execute path is completely untouched.

New pure helper `_parse_min_student_words_env(value: str | None) -> int`:
* `None` → `DEFAULT_MIN_STUDENT_WORDS`; negative → `DEFAULT_MIN_STUDENT_WORDS`; non-integer string → `DEFAULT_MIN_STUDENT_WORDS`; `0` → `0` (gate-disable allowed)
* Used to set the `--min-student-words` CLI argument default from `GRADING_MIN_STUDENT_WORDS` env

New counters in `run()`:
* `skipped_invalid_raw` — dry-run: `raw_backup_json` present but not parseable as JSON array
* `skipped_no_user_turns` — dry-run: no `USER_TURN` events found
* `skipped_insufficient_words` — dry-run: student word count < threshold

Dry-run `would` output now includes `user_turns=` and `student_words=` from `GradingEligibility`.

Dry-run summary now includes `skipped_invalid_raw`, `skipped_no_user_turns`, `skipped_insufficient_words`.

Execute path: `_count_user_turns`, `require_user_turn` gate, and `process_session_completed_job` call are unchanged. `_count_user_turns` docstring updated to note execute-path-only use.

#### Known Patch 7G-4B Limitation

`_count_user_turns` (execute path) still checks only `"type"` key and `isinstance(e, dict)` — does not handle `"event"` alias. Execute-path parity is Patch 7G-4C scope. Documented by `test_dry_run_recognizes_event_key_execute_path_does_not`.

#### Verification

* `py_compile scripts/reconciliation_scanner.py` — `py_compile_ok`
* `pytest tests/test_reconciliation_scanner_patch7g4b.py -q` — **25 passed**
* `pytest tests/ -q` — **130 passed** (105 pre-existing + 25 new)
* Scope guard: execute path behavior confirmed unchanged
* No Groq calls. No services started. No DB writes. No RabbitMQ operations. No scanner `--execute`. No sessions.

#### Test Coverage

* `_parse_min_student_words_env` — 7 tests (None, valid int string, zero, invalid string, negative, float string, empty string)
* Dry-run categorization via `evaluate_grading_eligibility` — 8 tests (all reason codes, boundary, both key aliases)
* Summary counts — 2 tests (mixed candidates produce correct per-reason counts; no transcript text in summary)
* Execute path guard — 5 tests (`_count_user_turns` callable, type-key counted, event-key NOT counted, None→0, invalid→0)
* Structural gap — 1 test (dry-run handles event-key; execute path does not — intentional, documents Patch 7G-4C scope)
* Transcript leakage — 2 tests (eligible + ineligible `GradingEligibility` results contain no transcript text)

#### DevOps/SRE Value

* Dry-run output is now operationally honest: per-reason buckets distinguish `invalid_raw_backup`, `no_user_turns`, and `insufficient_words` instead of lumping all non-eligible sessions together.
* `--min-student-words N` CLI flag matches `GRADING_MIN_STUDENT_WORDS` env default — dry-run threshold is inspectable and overridable without env changes.
* No DB/RabbitMQ/Groq changes — rollback is a single-commit revert.

#### Remaining

* Scanner execute-path eligibility gap resolved in Patch 7G-4C (`7dcc9e8`).
* Backfill parity not yet wired — Patch 7G-4D.

### Patch 7G-4C — Scanner Execute-Path Eligibility Gate

**Runtime/test commit: `7dcc9e8` fix(grading-worker): gate scanner execute by eligibility**

**Files changed:**
* `services/grading-worker/scripts/reconciliation_scanner.py` — execute path eligibility gate; counter and summary bucket rename
* `services/grading-worker/tests/test_reconciliation_scanner_patch7g4c.py` — 11 mocked unit tests (new file)

#### Behavior

Execute path now calls `evaluate_grading_eligibility(raw_json, min_student_words=args.min_student_words)` before `process_session_completed_job`. Ineligible sessions are short-circuited with `continue` — `process_session_completed_job` is never called for ineligible candidates.

Skip reason dispatch in execute path:
* `no_raw_backup` → `skipped_no_raw_backup += 1` (belt-and-suspenders; SQL already filters `raw_backup_json IS NOT NULL`)
* `invalid_raw_backup` → `skipped_invalid_raw += 1`
* `no_user_turns` → `skipped_no_user_turns += 1`
* `insufficient_words` → `skipped_insufficient_words += 1`

Execute summary now includes all four skip buckets: `skipped_no_raw_backup`, `skipped_grace_window`, `skipped_invalid_raw`, `skipped_no_user_turns`, `skipped_insufficient_words`, `errors`.

Dry-run behavior from Patch 7G-4B is preserved unchanged.

`_count_user_turns` is retained in the scanner (callable, importable) but is no longer called in the main candidate loop. Docstring updated to note it is superseded by `evaluate_grading_eligibility` in Patch 7G-4C. Tests in `test_reconciliation_scanner_patch7g4b.py` documenting its known type-key-only limitation are preserved.

#### Verification

* `py_compile scripts/reconciliation_scanner.py` — `py_compile_ok`
* `pytest tests/test_reconciliation_scanner_patch7g4c.py -q` — **11 passed**
* `pytest tests/ -q` — **141 passed** (105 pre-7G-4 + 25 patch7g4b + 11 patch7g4c)
* No scanner `--execute` run. No Groq calls. No services started. No DB writes. No RabbitMQ operations. No sessions.

#### Test Coverage (11 mocked tests)

* Execute path skips: `no_raw_backup`, `invalid_raw_backup`, `no_user_turns`, `insufficient_words` → `process_session_completed_job` call count = 0
* Execute path processes: exactly at threshold (25 words), above threshold (30 words) → call count = 1 each
* `event`-key alias: execute path now correctly processes sessions with `"event": "USER_TURN"` (gap closed vs. Patch 7G-4B `_count_user_turns`)
* Dry-run never calls job for eligible sessions
* Mixed-candidate summary: 6 candidates (`None`, invalid JSON, AI-only, 3-word, 25-word, 30-word) → `candidates_seen=6`, `processed=2`, each skip bucket = 1
* `--min-student-words` override: high threshold skips; low threshold allows

#### DevOps/SRE Value

* Closes the operational gap where the scanner printed misleading `ok` for sessions the worker silently skipped.
* Prevents misleading `ok`/`processed` output and avoids routing ineligible sessions into `process_session_completed_job`; reduces scanner execute churn, though persistent skip/status tracking is a separate future hardening item.
* Execute and dry-run skip buckets now unified — same counter names appear in both summary lines.
* No DB migration, no API changes, no RabbitMQ changes — rollback is a single-commit revert.

#### Remaining

* Backfill parity wired in Patch 7G-4D (`80d4db7`).
* Do not run scanner `--execute` without confirming `GRADING_MIN_STUDENT_WORDS` matches your intent.

### Patch 7G-4D — Backfill Execute-Path Eligibility Gate

**Runtime/test commit: `80d4db7` fix(grading-worker): gate backfill execute by eligibility**

**Files changed:**
* `services/grading-worker/scripts/backfill_completed_sessions.py` — execute path eligibility gate; `_parse_min_student_words_env` helper; `--min-student-words` CLI flag; counter and summary bucket alignment
* `services/grading-worker/tests/test_backfill_completed_sessions_patch7g4d.py` — 13 mocked unit tests (new file)

#### Behavior

Execute path (and dry-run path) now calls `evaluate_grading_eligibility(raw_json, min_student_words=args.min_student_words)` before `process_session_completed_job`. Ineligible sessions are short-circuited with `continue` — `process_session_completed_job` is never called for ineligible candidates.

New pure helper `_parse_min_student_words_env(value: str | None) -> int` (local copy, not cross-imported from scanner):
* `None` → `DEFAULT_MIN_STUDENT_WORDS`; negative → `DEFAULT_MIN_STUDENT_WORDS`; non-integer string → `DEFAULT_MIN_STUDENT_WORDS`; `0` → `0` (gate-disable allowed)
* Used to set the `--min-student-words` CLI argument default from `GRADING_MIN_STUDENT_WORDS` env

New `--min-student-words N` CLI flag (default: `GRADING_MIN_STUDENT_WORDS` env or 25).

`--no-require-user-turn` help text updated: "Retained for CLI backward compatibility. The eligibility helper now enforces user-turn presence; this flag no longer affects execute behavior."

`--include-empty-raw` help text updated to clarify that NULL raw sessions selected by this flag are still gated by `evaluate_grading_eligibility(None)` → `no_raw_backup` before any grading attempt — intentional improvement over previous behavior.

Counter names aligned with scanner (Patch 7G-4C):
* `skipped_no_raw_backup` (was `skipped_no_raw`)
* `skipped_invalid_raw` (new)
* `skipped_no_user_turns` (was `skipped_no_user_turn`)
* `skipped_insufficient_words` (new)

`_count_user_turns` is retained (callable, importable) but no longer called in the main candidate loop. Docstring updated to note it is superseded by `evaluate_grading_eligibility` in Patch 7G-4D.

#### Verification

* `py_compile scripts/backfill_completed_sessions.py` — `py_compile_ok`
* `pytest tests/test_backfill_completed_sessions_patch7g4d.py -q` — **13 passed**
* `pytest tests/ -q` — **154 passed, 0 failed** using `services/core-api/venv/bin/python3 -m pytest tests/ -q` (project-venv invocation, includes `pytest-asyncio 1.3.0`). An earlier run via `~/.local/bin/pytest` produced 122 passed / 32 failed because that runner lacked `pytest-asyncio`; those failures were a runner issue, not a code issue. `de6c6d1` corrected the earlier inaccurate verification status; this approved-env rerun followed.
* No scanner `--execute` run. No Groq calls. No services started. No DB writes. No RabbitMQ operations. No sessions.

#### Test Coverage (13 mocked tests)

* Execute path skips: `no_raw_backup`, `invalid_raw_backup`, `no_user_turns`, `insufficient_words` → `process_session_completed_job` call count = 0
* Execute path processes: exactly at threshold (25 words), above threshold (30 words), `event`-key alias → call count = 1 each
* Dry-run never calls job for eligible sessions
* Mixed-candidate summary: 6 candidates (`None`, invalid JSON, AI-only, 3-word, 25-word, 30-word) → `candidates_seen=6`, `processed=2`, each skip bucket = 1; no transcript text in output
* `--min-student-words` override: high threshold skips; low threshold allows
* `--include-empty-raw` + NULL raw: still gated as `no_raw_backup` — call count = 0
* No transcript leakage: secret word absent from stdout and stderr

#### DevOps/SRE Value

* Closes the backfill parity gap: execute path now prevents ineligible sessions from reaching `process_session_completed_job`, matching Patch 7G-4C scanner behavior.
* `--include-empty-raw` + NULL raw is now safely gated — previously, `--include-empty-raw --no-require-user-turn` could route NULL sessions into the grading path.
* Counter names now unified across scanner and backfill — SRE output is consistent between both tools.
* No DB migration, no API changes, no RabbitMQ changes — rollback is a single-commit revert.

#### Remaining

* Patch 7G-4 series complete. Verification cleanup completed after approved-env rerun: 154/154 full suite passed via project-venv python.
* Patch 7G-5 (fake fallback env gate) implemented — see Patch 7G-5 subsection below.

---

### Patch 7G-5 — Fake Fallback Env Gate

**Runtime/test commit: `dcdf9ba` fix(grading-worker): gate fake fallback behind env flag**

**Files changed:**
* `services/grading-worker/src/worker.py` — added `_get_fake_fallback_enabled()` helper; gated `except Exception` fallback block on new helper
* `services/grading-worker/tests/test_worker_patch2a.py` — added `GRADING_FAKE_FALLBACK=true` to 4 legacy fallback tests to preserve their intent
* `services/grading-worker/tests/test_worker_patch7g5.py` — 29 new mocked tests (new file)

#### Behavior

New helper `_get_fake_fallback_enabled() -> bool`:
* Reads `GRADING_FAKE_FALLBACK` env var; strips, lowercases, checks membership in `{"1", "true", "yes", "on"}`.
* Default (unset or any other value) → `False`.

In `process_session_completed_job`, `provider == "llm"` exception branch now:
* `GRADING_FAKE_FALLBACK` truthy: logs `grading.llm_failed_fallback` at WARNING and calls `fake_grade()` — identical to previous behavior. Local dev escape hatch.
* `GRADING_FAKE_FALLBACK` unset/falsy (default): logs `grading.llm_failed_no_fallback` at ERROR and bare `raise`. No `fake_grade()` call. No `upsert_grading_result` call. No fake row written to DB.

Unchanged paths:
* `GRADING_PROVIDER=fake` (else branch) — calls `fake_grade()` directly as explicit provider, not fallback. Unaffected.
* Insufficient-evidence gate — fires before provider/fallback logic. Unaffected.
* No-student-turns gate — fires before provider/fallback logic. Unaffected.
* `consume_forever()` — unchanged. Exception escaping `process_session_completed_job` should cause `aio_pika`'s `message.process(requeue=False)` to NACK; actual DLQ delivery depends on RabbitMQ DLX configuration, which is not declared in this codebase.

#### Verification

* `py_compile src/worker.py` — OK
* Targeted pytest (`test_worker_patch2a.py` + `test_worker_patch7g5.py`) — **50/50 passed**
* Full grading-worker suite — **183/183 passed** using `services/core-api/venv/bin/python3 -m pytest tests/ -q`
* No live Groq calls. No DB writes/connections. No RabbitMQ operations. No services/TEN. No scanner/backfill `--execute`.

#### Test Coverage (29 mocked test cases)

* `GRADING_PROVIDER=fake` unaffected by `GRADING_FAKE_FALLBACK` (unset/true/false) — 3 cases
* LLM success writes LLM result; no fallback regardless of flag — 1 case
* LLM failure + fallback unset → raises; no upsert — 1 case
* LLM failure + fallback=false → raises; no upsert — 1 case
* `asyncio.TimeoutError` + fallback unset → raises; no upsert — 1 case
* LLM failure + fallback=true → fake upserted — 1 case
* Truthy parsing: `1`, `true`, `True`, `TRUE`, `yes`, `YES`, `on`, `ON` — 8 parametrized cases
* Falsey parsing: `0`, `false`, `no`, `off`, `bogus`, `""`, `"  "` — 7 parametrized cases
* Unset env → disables fallback — 1 case
* Log key `grading.llm_failed_no_fallback` when disabled — 1 case
* Log key `grading.llm_failed_fallback` when enabled — 1 case
* No transcript leakage in logs (disabled path) — 1 case
* No transcript leakage in logs (enabled path) — 1 case
* Insufficient evidence skips before fallback gate; no raise — 1 case

#### DevOps/SRE Value

* Prevents silent fake score writes when `GRADING_PROVIDER=llm` and Groq fails — the core production trust risk.
* Distinguishable log keys (`llm_failed_no_fallback` at ERROR vs `llm_failed_fallback` at WARNING) — alertable without log parsing.
* Rollback: set `GRADING_FAKE_FALLBACK=true` env var (immediate, no redeployment) or `git revert dcdf9ba`.
* No DB migration, no API changes, no RabbitMQ config changes.

---

### Patch 7G-6 — StaticFiles / Control-Center Serving and CORS Lockdown

**Runtime/test commit: `7d522d9` fix(core-api): serve control center and lock down CORS**

**Files changed:**
* `services/core-api/src/main.py` — CORS wildcard replaced; `StaticFiles` mount; `/control-center` route
* `services/core-api/src/core/cors.py` — new CORS helper (no settings/database imports)
* `services/core-api/tests/__init__.py` — new empty package marker
* `services/core-api/tests/test_main_patch7g6.py` — 15 mocked tests (new file)

#### Behavior

**CORS helper (`src/core/cors.py`):**
* `get_cors_allow_origins() -> list[str]` reads `CORS_ALLOW_ORIGINS` env var.
* Unset or empty string → 8-origin default list: `localhost` and `127.0.0.1` on ports 3000, 5173, 8000, 8080. No wildcard in default.
* Non-empty env value → comma-split, strip whitespace, drop empty entries. `"*"` is an explicit operator opt-in.
* No `os.environ` at import; reads at call time (module import in `main.py`). Origins fixed at startup — `CORS_ALLOW_ORIGINS` changes require process restart.
* Standalone imports: only `os` and `__future__`. No `get_settings()` call — importable without `DATABASE_URL` or `SECRET_KEY` env vars.

**`main.py` changes:**
* `allow_origins=get_cors_allow_origins()` replaces hardcoded `["*"]`.
* `allow_credentials=False` — correct because control center uses `Authorization: Bearer <token>` in request headers, not cookies. Browser credentials mode not required.
* `app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")` — serves `src/static/` directory.
* `_STATIC_DIR = Path(__file__).parent / "static"` — path relative to `main.py`, independent of uvicorn working directory.
* `GET /control-center` route returns `FileResponse(_STATIC_DIR / "index.html")`.

**No new dependency:** Starlette 1.0.0 (already installed) uses `anyio.open_file` for both `StaticFiles` and `FileResponse`. `anyio 4.13.0` is already present transitively via `uvicorn[standard]`. `aiofiles` is not needed.

**Test strategy — throwaway app:** Tests do not import `src.main` directly. Importing `src.main` triggers `get_settings()` which validates `DATABASE_URL` and `SECRET_KEY` at module load time, raising `ValidationError` without env vars. Tests use a `_make_app(cors_origins)` factory (minimal FastAPI app mirroring main.py's mount/route/middleware pattern) so all 15 tests run without env var setup.

#### Verification

* `py_compile` — OK for `src/main.py` and `src/core/cors.py`. (Test files verified by pytest, not py_compile.)
* `services/core-api/venv/bin/python3 -m pytest tests/test_main_patch7g6.py -q` — **15/15 passed**.
  * 8 CORS helper unit tests (via `monkeypatch`): no wildcard default, `http://localhost:8000` and `http://127.0.0.1:8080` in default, single-origin override, whitespace trimming, empty-entry dropping, empty string falls back to default (>1 origin, no wildcard), explicit `"*"` opt-in.
  * 5 StaticFiles/route tests via `TestClient`: `/control-center` returns HTTP 200 + `text/html`, body contains `"L.U.V.E"` or `"Control Center"`, `/static/styles.css` served with CSS content-type, `/api/v1/sentinel` not shadowed by static mount, `/api/v1/nonexistent_route_xyz` returns 404 not HTML.
  * 2 CORS preflight tests: allowed origin echoed in `access-control-allow-origin` and is not `"*"`, unlisted origin gets no `access-control-allow-origin` header.
* No Groq calls. No DB writes. No RabbitMQ operations. No live services started.

#### Known Limitations (as of Patch 7G-6)

* **Not browser-E2E-verified:** No Playwright run against `http://localhost:8000/control-center` in this patch. The prior Patch 7F-2 smoke used `file://` + `luve.control.coreApiUrl` localStorage override. A fresh browser smoke against `/control-center` route is deferred to a future browser-smoke task; it is not part of Patch 7G-7 migration audit.
* **TEN gateway CORS not addressed:** TEN gateway (port 8080) has a separate CORS configuration. Only core-api CORS was changed in this patch.
* **No HTTPS/domain origins in default list:** Default allowlist covers only `localhost`/`127.0.0.1` dev origins. Production domains require `CORS_ALLOW_ORIGINS` operator configuration.
* **Origins fixed at startup:** `get_cors_allow_origins()` is called once at import time. Changing `CORS_ALLOW_ORIGINS` requires a process restart.
* **No DLQ yet** — `consume_forever()` NACK behavior on re-raised exceptions depends on RabbitMQ DLX configuration not yet declared. Patch 7G-9 scope.

---

### Patch 7G-7 — Migration Strategy Runbook

**Tooling/docs commit: `bac73d2` docs(db): add migration strategy runbook**

**File created:**
* `infrastructure/db-migrations/README.md` — 261 lines; numbered SQL migration runbook

#### Content

**Schema source of truth documented:**
`infrastructure/db-init/01-init.sql` is the canonical baseline. It is mounted into `/docker-entrypoint-initdb.d/` and runs only when the Postgres data directory is empty (first volume creation). It does not re-run on container restart against an existing volume. Adding a table to `01-init.sql` does not automatically add it to existing developer databases — this is the core problem migrations solve.

**Why numbered SQL files instead of Alembic (documented rationale):**
Only the `users` table has a SQLAlchemy ORM model (`models/user.py`). Tables `sessions`, `grading_results`, and `lessons` are accessed entirely via raw SQL (`sqlalchemy.text()` in `session_service.py`, raw `asyncpg` in `grading_repository.py`). Alembic autogeneration walks `Base.metadata` — it would silently miss three of the four existing tables and produce misleading empty migrations. Alembic is not adopted for now; the numbered-SQL approach is forward-compatible and can be layered under Alembic later if the project scales.

**db-init ↔ db-migrations relationship documented:**
- Fresh empty Docker volume: `entrypoint-initdb.d/01-init.sql` runs once and creates all baseline tables. Migration files are NOT run automatically.
- Existing Docker volume: `entrypoint-initdb.d` is skipped entirely. New tables must be applied via numbered migration files manually.
- After a migration is verified: mirror the schema addition into `01-init.sql` in a separate approved patch to keep both paths aligned. Do not edit `01-init.sql` in the same patch as the migration file.

**Naming convention:** `NNNN_<snake_case_description>.sql` — zero-padded 4-digit sequence, one migration per logical schema change, never reuse sequence numbers.

**Mandatory migration file sections:** Purpose, Scope, Idempotent flag, Requires, Rollback notes, Applied date — plus Preflight (manual queries), Forward migration (wrapped in `BEGIN; COMMIT;`), Verification queries (commented), Rollback block (commented), Fresh DB Sync Note.

**Safe apply runbook (7 steps):** backup via `pg_dump` → inspect SQL file → run preflight queries → apply with `psql` (future approved prompt only) → verify with `to_regclass` and `pg_indexes` → rollback only if needed → sync `01-init.sql` in a separate patch.

**Operational rules documented:**
- App startup must never auto-apply migrations.
- One migration per schema change.
- Never edit a migration file after it has been applied.
- Never reuse sequence numbers.
- Privacy principle: no raw transcript text, audio, or PII in grading skip/status tables.

**Patch 7G-8 preview included:** High-level `grading_skip_log` table sketch (non-executable, design-review-only notation). Explicitly states "Patch 7G-7 does not create or apply this migration."

#### Explicit Non-Changes

* `infrastructure/db-init/01-init.sql` — not modified.
* `infrastructure/db-migrations/0001_grading_skip_log.sql` — not created in Patch 7G-7. Created and committed in Patch 7G-8A (commit `d2bb908`); not yet applied to the database.
* No DB commands run. No schema applied. No DB connection opened.
* No services, tests, or runtime Python files modified.
* No packages installed.

#### Safety

* No `psql`, `alembic`, or `docker compose` commands run.
* No DB connection, no DB write, no DB read.
* No Groq calls. No RabbitMQ operations. No TEN/browser/Playwright.

---

### Patch 7G-8A — grading_skip_log Migration SQL File

**Infrastructure commit: `d2bb908` db: add grading skip log migration**

**File created:**
* `infrastructure/db-migrations/0001_grading_skip_log.sql` — 123 lines; first numbered SQL migration file

#### Content

**Migration structure (per README.md runbook):**
Header block (Migration/Purpose/Scope/Idempotent/Requires/Rollback/Applied) + Preflight comments + `BEGIN;` / forward DDL / `COMMIT;` + Verification comments + Rollback Notes (commented) + Fresh DB Sync Note.

**Forward migration (inside `BEGIN;` / `COMMIT;`):**

`CREATE TABLE IF NOT EXISTS grading_skip_log` with columns:
- `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `session_id UUID NOT NULL UNIQUE REFERENCES sessions(id) ON DELETE CASCADE`
- `skipped_reason TEXT NOT NULL CHECK (... IN ('no_raw_backup', 'invalid_raw_backup', 'no_user_turns', 'insufficient_words'))`
- `student_word_count INT` (nullable; populated only for `insufficient_words`)
- `min_words_threshold INT` (nullable; populated only for `insufficient_words`)
- `source TEXT NOT NULL DEFAULT 'worker' CHECK (... IN ('worker', 'scanner', 'backfill', 'manual'))`
- `skipped_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`

Supporting indexes:
- `CREATE INDEX IF NOT EXISTS grading_skip_log_skipped_reason_idx ON grading_skip_log (skipped_reason)`
- `CREATE INDEX IF NOT EXISTS grading_skip_log_skipped_at_idx ON grading_skip_log (skipped_at DESC)`

Note: no separate unique index for `session_id` — the inline `UNIQUE` constraint creates `grading_skip_log_session_id_key` implicitly.

**Preflight comments:** check active transactions; confirm `sessions` table exists; confirm `grading_skip_log` does not yet exist.

**Verification comments:** `to_regclass` check; `pg_indexes` index listing (expect 3); `COUNT(*)` expect 0; optional `pg_constraint` check constraint listing.

**Rollback:** `DROP TABLE IF EXISTS grading_skip_log CASCADE` — commented only, not executable SQL.

**Fresh DB Sync Note:** After apply/verify on existing volume, mirror to `infrastructure/db-init/01-init.sql` in a separate approved patch. Do not edit `01-init.sql` in Patch 7G-8A.

#### Explicit Non-Changes

* Migration file committed but **not applied**. No `psql`, `alembic`, or `docker compose` commands run.
* `grading_skip_log` table does not yet exist in the database.
* `infrastructure/db-init/01-init.sql` — unchanged.
* `infrastructure/db-migrations/README.md` — unchanged.
* No services, tests, or runtime Python files modified.
* No app code integration at Patch 7G-8A time: worker/scanner/backfill did not write skip rows (worker now writes skip rows as of commit `85ce409`; scanner/backfill do not yet); `/grading/status` does not read `grading_skip_log`.
* Persistent skip/status tracking is not active.
* No packages installed.

#### Safety

* No `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE` in the forward migration — only `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.
* No `raw_backup_json`, transcript text, audio, or metadata JSONB columns in the schema.
* Rollback `DROP TABLE` is commented-only, not executable.
* No DB connection, no DB write, no DB read.
* No Groq calls. No RabbitMQ operations. No TEN/browser/Playwright.

---

### Patch 7G-8B — grading_skip_log Migration Apply/Verify Plan

**Status: Planning complete. No DB commands run. Migration still not applied.**

**Audit/plan only — no files created or modified, no DB commands run. Planning docs being committed does not authorize DB execution; DB apply requires a separate explicit user approval prompt.**

#### Key Findings

- **Host `psql`:** not on PATH. **Host `pg_dump`:** not on PATH. All DB operations must use `docker exec luve_postgres`.
- **Docker:** available (v29.1.3).
- **Postgres service:** service `postgres_db`, container `luve_postgres`, image `postgres:15-alpine`, port `5432:5432`, volume `postgres_data`.
- **Env var names confirmed (values never printed):** `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` present in `.env`. Compose defaults: `POSTGRES_USER:-dat_admin`, `POSTGRES_DB:-luve_database` (actual values come from `.env`, not these defaults).
- **Credential extraction (safe):** `PG_USER=$(docker exec luve_postgres printenv POSTGRES_USER)` reads from container env; no `.env` value echoed on host.
- **Auth inside container:** UNIX socket trust auth in `postgres:15-alpine` — no `--password` flag required for `docker exec psql`.
- **Backup location:** `/home/minhthuy/db-backups/` (outside repo; 282 GB free on host disk; directory does not yet exist — must `mkdir -p` before backup).

#### Approved Backup Command Template

```bash
PG_USER=$(docker exec luve_postgres printenv POSTGRES_USER)
PG_DB=$(docker exec luve_postgres printenv POSTGRES_DB)
mkdir -p /home/minhthuy/db-backups
docker exec luve_postgres pg_dump -U "$PG_USER" -d "$PG_DB" -Fc \
  > /home/minhthuy/db-backups/backup_pre_0001_grading_skip_log_$(date +%Y%m%d_%H%M%S).dump
ls -lh /home/minhthuy/db-backups/backup_pre_0001_*.dump | tail -1
```

Stop if backup file is zero bytes or `pg_dump` exits non-zero.

#### Approved Preflight Queries

Five queries via `docker exec -i luve_postgres psql -U "$PG_USER" -d "$PG_DB"`:

1. Active transactions — no duration > 10s against target tables.
2. `SELECT to_regclass('public.sessions') IS NOT NULL AS sessions_exists;` → must be `t`.
3. `SELECT to_regclass('public.grading_skip_log') IS NULL AS not_yet_created;` → must be `t`.
4. `SELECT extname FROM pg_extension WHERE extname = 'pgcrypto';` → must return one row (`gen_random_uuid()` dependency).
5. `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'sessions' AND column_name = 'id';` → must return `id | uuid`.

#### Approved Apply Command Template

```bash
docker exec -i luve_postgres psql \
  -v ON_ERROR_STOP=1 \
  -U "$PG_USER" \
  -d "$PG_DB" \
  < infrastructure/db-migrations/0001_grading_skip_log.sql
```

Expected output: `BEGIN` / `CREATE TABLE` / `CREATE INDEX` / `CREATE INDEX` / `COMMIT`. Stop on mismatch or non-zero exit.

#### Approved Verification Queries

Six checks via `docker exec -i luve_postgres psql` after COMMIT:

1. `to_regclass('public.grading_skip_log') IS NOT NULL` → `t`
2. `COUNT(*) FROM grading_skip_log` → `0`
3. Eight columns with correct names, types, nullability, defaults: `id uuid NOT NULL`, `session_id uuid NOT NULL`, `skipped_reason text NOT NULL`, `student_word_count int NULL`, `min_words_threshold int NULL`, `source text NOT NULL DEFAULT 'worker'::text`, `skipped_at timestamptz NOT NULL`, `updated_at timestamptz NOT NULL`
4. Three indexes: `grading_skip_log_session_id_key` (implicit unique), `grading_skip_log_skipped_reason_idx`, `grading_skip_log_skipped_at_idx`
5. Two CHECK constraints: `skipped_reason` CHECK (4 values), `source` CHECK (4 values)
6. FK: `session_id → sessions(id)` with `delete_rule = CASCADE`

Stop on any mismatch.

#### Rollback Plan

Only if verified schema defect before any app rows written:

```sql
BEGIN;
DROP TABLE IF EXISTS grading_skip_log CASCADE;
COMMIT;
```

`CASCADE` drops supporting indexes. At apply time row count = 0 — rollback has zero data-loss risk immediately after fresh apply. After any app writes, rollback permanently destroys skip-log audit data.

#### Deployment Sequencing

1. Apply and verify migration (Patch 7G-8B execute — requires explicit user approval).
2. App integration: `GradingRepository.log_grading_skip()`, worker refactor to call `evaluate_grading_eligibility`, scanner/backfill skip logging, `/grading/status` LEFT JOIN `grading_skip_log` (Patch 7G-8C+).
3. Mirror `grading_skip_log` into `infrastructure/db-init/01-init.sql` — separate approved patch after successful DB apply/verify.
4. **Do not deploy app code referencing `grading_skip_log` before migration is applied and verified.**

#### Stop Conditions for Execute Prompt

S1: dirty tracked files. S2: HEAD mismatch. S3: `luve_postgres` not running. S4: backup zero bytes or `pg_dump` non-zero exit. S5: `sessions` table missing. S6: `grading_skip_log` unexpectedly already exists. S7: `pgcrypto` extension missing. S8: active transactions > 10s. S9: apply output mismatch or non-zero exit. S10: any verification mismatch (columns, indexes, constraints, FK, row count). S11: credentials unavailable from container env. S12: wrong container name.

#### Safety

* No `psql`, `pg_dump`, `alembic`, or `docker compose` commands run in planning.
* No DB connection, no DB read, no DB write.
* No `.env` values printed — key names confirmed by redacted `grep` only.
* No app code, infrastructure, or test files modified.
* No Groq calls. No RabbitMQ operations. No TEN/browser/Playwright.
* No packages installed.

---

### Patch 7G-8B Execute — grading_skip_log Migration Apply/Verify

**Status: Complete (2026-05-26). Migration applied and verified on local DB.**

All DB commands run via `docker exec luve_postgres` — host `psql`/`pg_dump` not on PATH.

#### Execution Results

**Backup:**
* Path: `/home/minhthuy/db-backups/backup_pre_0001_grading_skip_log_20260526_145532.dump`
* Size: 111K, non-zero ✓

**Preflight (all 5 checks passed):**
* No active transactions > 10s ✓
* `sessions_exists = t` ✓
* `not_yet_created = t` (grading_skip_log absent before apply) ✓
* `pgcrypto` extension present ✓
* `sessions.id` is `uuid` ✓

**Apply output (exit code 0):** `BEGIN` / `CREATE TABLE` / `CREATE INDEX` / `CREATE INDEX` / `COMMIT`

**Verification — all checks passed:**

| Check | Result |
|---|---|
| `table_exists` | `t` ✓ |
| `row_count` | `0` ✓ |
| Columns (8 exact) | ✓ (see below) |
| Indexes (4 — pkey implicit + 3 named) | ✓ (pkey is implicit PK index — expected, not an error) |
| Constraints (5) | ✓ |
| FK `session_id → sessions(id)` CASCADE | ✓ |

**Columns (8 exact):**
* `id | uuid | NOT NULL | gen_random_uuid()`
* `session_id | uuid | NOT NULL`
* `skipped_reason | text | NOT NULL`
* `student_word_count | integer | NULL`
* `min_words_threshold | integer | NULL`
* `source | text | NOT NULL | 'worker'::text`
* `skipped_at | timestamp with time zone | NOT NULL | CURRENT_TIMESTAMP`
* `updated_at | timestamp with time zone | NOT NULL | CURRENT_TIMESTAMP`

**Indexes (4 total — expected):**
* `grading_skip_log_pkey` — implicit PRIMARY KEY index on `id` (expected, not an error)
* `grading_skip_log_session_id_key` — UNIQUE on `session_id` (from inline UNIQUE constraint)
* `grading_skip_log_skipped_at_idx` — btree `skipped_at DESC`
* `grading_skip_log_skipped_reason_idx` — btree `skipped_reason`

**Constraints (5 total):**
* `grading_skip_log_pkey` — PRIMARY KEY (`id`)
* `grading_skip_log_session_id_fkey` — FOREIGN KEY (`session_id`) REFERENCES `sessions(id)` ON DELETE CASCADE
* `grading_skip_log_session_id_key` — UNIQUE (`session_id`)
* `grading_skip_log_skipped_reason_check` — CHECK `skipped_reason IN ('no_raw_backup', 'invalid_raw_backup', 'no_user_turns', 'insufficient_words')`
* `grading_skip_log_source_check` — CHECK `source IN ('worker', 'scanner', 'backfill', 'manual')`

#### Current DB State

`grading_skip_log` table **now exists** in local DB. `row_count = 0`. All schema constraints, indexes, and FK verified.

#### Explicit Non-Changes

* No files modified, staged, or committed during execute.
* No app integration implemented — worker/scanner/backfill do not yet write skip rows; `/grading/status` does not yet read `grading_skip_log`.
* `infrastructure/db-init/01-init.sql` unchanged — mirror deferred to Patch 7G-8D (separate approved patch after 7G-8C complete).
* No services/tests/Groq/RabbitMQ/TEN/browser/scanner/backfill `--execute` run.
* No secrets, DATABASE_URL, POSTGRES_PASSWORD, or credential values printed.

---

### Patch 7G-8C — grading_skip_log App Integration Audit/Design

**Status: Audit/design complete. No DB commands run. No files modified except docs. No app integration implemented.**

**Audit/design only — no files created or modified (except docs), no DB commands run, no app integration implemented. `grading_skip_log` table was not yet applied at time of this audit; subsequently applied and verified in Patch 7G-8B Execute (2026-05-26). App integration implementation now unblocked; pending separate approved prompts (7G-8C-1 through 7G-8C-4).**

#### Source Files Audited (read-only)

| File | Key finding |
|---|---|
| `grading_repository.py` | Two async methods; each opens own asyncpg connection, try/finally close. No `log_grading_skip()` exists. |
| `worker.py` | Calls `build_evaluation_input` BEFORE eligibility. Does NOT call `evaluate_grading_eligibility`. Two skip paths collapse four reason codes: `no_raw_backup`/`invalid_raw_backup`/`no_user_turns` → `grading.no_user_turns_skip`; `insufficient_words` → `grading.skipped_insufficient_evidence`. |
| `session_eligibility.py` | `evaluate_grading_eligibility(raw_backup_json, min_student_words)` → `GradingEligibility`. Four ineligible reason codes. `student_word_count=None` for `no_raw_backup`/`invalid_raw_backup`. |
| `reconciliation_scanner.py` | Already calls `evaluate_grading_eligibility` on both dry-run and execute paths. Tracks all four reason counters. Does NOT write to `grading_skip_log`. |
| `backfill_completed_sessions.py` | Same as scanner. Already uses `evaluate_grading_eligibility` on both paths. Does NOT write to `grading_skip_log`. |
| `session_service.py` | `get_session_grading_status` LEFT JOINs sessions + grading_results only. Re-derives word count locally via `_compute_student_word_count`, NOT `evaluate_grading_eligibility`. No skip log query. |
| `schemas/session.py` | `GradingStatusRead.status: Literal["graded", "pending", "insufficient_evidence"]`. No `skipped_reason` field. |

#### Recommended Integration Split

**7G-8C-1 — Repository** (`grading_repository.py`):
- Add `async def log_grading_skip(self, session_id, reason, source="worker", student_word_count=None, min_words_threshold=None) -> None`
- SQL: `INSERT INTO grading_skip_log ... ON CONFLICT (session_id) DO UPDATE SET skipped_reason=..., source=..., student_word_count=..., min_words_threshold=..., updated_at=CURRENT_TIMESTAMP`
- Pattern: open own asyncpg connection, try/finally close — same as existing methods
- Privacy: no raw transcript, no `raw_backup_json`, no PII; only UUIDs and integer counts

**7G-8C-2 — Worker** (`worker.py`):
- Call `evaluate_grading_eligibility(session_row["raw_backup_json"], min_student_words=min_student_words)` BEFORE `build_evaluation_input`
- Replace ad-hoc `has_student_turns` and word-count guards with one unified ineligible branch
- Write skip row best-effort with `source="worker"`: wrap `log_grading_skip` in try/except (non-fatal — `consume_forever` uses `requeue=False`)
- No Groq call and no `upsert_grading_result` for ineligible sessions
- Existing log key `grading.skipped_insufficient_evidence` (referenced in `test_worker_patch7g5.py:test_insufficient_evidence_skips_before_fallback_gate`) changes — test must be updated alongside worker refactor

**7G-8C-3 — Scanner/Backfill** (`reconciliation_scanner.py`, `backfill_completed_sessions.py`):
- Execute mode only: after `evaluate_grading_eligibility` ineligibility check, add best-effort `log_grading_skip` call with `source="scanner"` or `source="backfill"`
- Guard with `if repository is not None:` (execute mode only; `repository=None` in dry-run)
- Dry-run: no DB write, existing behavior preserved
- Summary counters unchanged

**7G-8C-4 — Core-API status** (`session_service.py`, `schemas/session.py`):
- Add `LEFT JOIN grading_skip_log sl ON sl.session_id = s.id` to `get_session_grading_status` query
- If skip log row present: use persisted `skipped_reason` rather than re-deriving from `raw_backup_json`
- **Deploy last** — query fails with relation-not-found error if migration not applied; this is a synchronous query that will 500 all `/grading/status` requests if the table is missing
- Schema option A (no API change): map all skip reasons to `"insufficient_evidence"` (minimal blast radius)
- Schema option B (schema change): add `"ineligible"` literal and optional `skipped_reason` field to `GradingStatusRead` (semantically correct)
- Recommendation: Option A for minimal patch unless API schema expansion is explicitly authorized

#### Test Plan

- **Repository** (`test_grading_repository_patch7g8c.py`): asyncpg mock tests — INSERT called with correct params; connection closed in finally; `student_word_count=None` for non-word-count reasons; upsert on conflict
- **Worker** (`test_worker_patch7g8c.py`): extend `_FakeRepo` with `log_grading_skip`; test all four skip reasons; eligible path does not call `log_grading_skip`; `log_grading_skip` failure does not raise; no Groq call or `upsert_grading_result` on any skip; update `test_worker_patch7g5.py` assertion on old log key `skipped_insufficient_evidence`
- **Scanner/Backfill**: execute mode calls `log_grading_skip(source="scanner"/"backfill")`; dry-run does not; failure does not fail run
- **Core-API status**: `get_session_grading_status` with skip log row returns correct status; no skip row preserves existing behavior; graded result overrides skip row
- **Privacy**: no raw transcript or `raw_backup_json` in `log_grading_skip` arguments

#### Key Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Core-API deployed before migration applied | High — 500 on all `/grading/status` requests | Deploy 7G-8C-4 last; verify migration in DB before deploying |
| Worker deployed before migration applied | Low — try/except swallows error; skip log silently not written (data-loss risk, not crash) | Deploy after migration verified; optionally gate behind `ENABLE_GRADING_SKIP_LOG` env flag |
| Old log key `grading.skipped_insufficient_evidence` changes | Medium — breaks `test_worker_patch7g5.py` assertion | Update test in same commit as worker refactor |
| `repository=None` in scanner dry-run | Low — `if repository is not None:` guard prevents accidental write | Add explicit guard before `log_grading_skip` call |

#### Safety

* No `psql`, `pg_dump`, `alembic`, `docker`, or `docker compose` commands run.
* No DB connection, no DB read, no DB write.
* No `.env` values printed.
* No app code, infrastructure, or test files modified.
* No Groq calls. No RabbitMQ operations. No TEN/browser/Playwright.
* No packages installed.

---

### Patch 7G-8C-1 — Repository `log_grading_skip()` Implementation

**Status: Complete (commit `cb79155`, 2026-05-26). 5/5 mocked tests pass. No live DB, no worker/scanner/backfill/core-api changes.**

#### Changes

| File | Change |
|---|---|
| `services/grading-worker/src/grading_repository.py` | Added `async def log_grading_skip(self, session_id, reason, source="worker", student_word_count=None, min_words_threshold=None) -> None` between `fetch_session_row` and `upsert_grading_result` |
| `services/grading-worker/tests/test_grading_repository_patch7g8c.py` | New file — 5 mocked asyncpg tests; no live DB |

#### Implementation

Method follows the existing asyncpg connection pattern exactly: open own connection, `try/finally` close. SQL uses `ON CONFLICT (session_id) DO UPDATE SET skipped_reason, source, student_word_count, min_words_threshold, updated_at = CURRENT_TIMESTAMP` — idempotent; repeated calls for the same session update the existing row.

Privacy: no `raw_backup_json`, no transcript, no audio, no PII. Only `session_id` (UUID), `reason` (string), `source` (string), `student_word_count` (int | None), `min_words_threshold` (int | None).

#### Tests (5/5 pass)

| Test | Coverage |
|---|---|
| `test_log_grading_skip_inserts_with_expected_params` | INSERT called with correct positional params ($1–$5); SQL contains `INSERT INTO grading_skip_log` and `ON CONFLICT (session_id) DO UPDATE`; connection closed |
| `test_log_grading_skip_defaults_source_worker` | `source` defaults to `"worker"` when omitted |
| `test_log_grading_skip_allows_none_counts_for_non_word_reason` | `student_word_count=None`, `min_words_threshold=None` accepted for non-word-count reasons |
| `test_log_grading_skip_closes_connection_on_execute_error` | `connection.close()` awaited even when `execute` raises `RuntimeError` |
| `test_log_grading_skip_does_not_accept_raw_payload_arguments` | `inspect.signature` confirms param names; `raw_backup_json`/`transcript`/`audio`/`metadata`/`payload` not present |

#### Safety

* No `psql`, `pg_dump`, `alembic`, `docker`, or `docker compose` commands run.
* No live DB connection. All tests use `unittest.mock.AsyncMock` + `patch("src.grading_repository.asyncpg.connect", ...)`.
* No `worker.py`, `reconciliation_scanner.py`, `backfill_completed_sessions.py`, `session_service.py`, or any core-api file modified.
* No Groq calls. No RabbitMQ operations. No TEN/browser.
* No `.env` values printed.
* `infrastructure/db-init/01-init.sql` unchanged — mirror deferred to Patch 7G-8D.

---

### Patch 7G-8C-2 — Worker Eligibility Refactor + Skip-Log Write

**Status: Complete (commit `85ce409`, 2026-05-26). 6/6 mocked tests pass. No live DB, no scanner/backfill/core-api changes.**

#### Changes

| File | Change |
|---|---|
| `services/grading-worker/src/worker.py` | Refactored `process_session_completed_job`: replaced ad-hoc skip guards with unified `evaluate_grading_eligibility` call before `build_evaluation_input`; best-effort `log_grading_skip` for ineligible sessions |
| `services/grading-worker/tests/test_worker_patch7g8c2.py` | New file — 6 mocked tests; no live DB |
| `services/grading-worker/tests/test_worker_patch7g5.py` | Added `log_grading_skip` stub to `_FakeRepo`; updated `skipped_insufficient_evidence` → `session_ineligible` assertion |
| `services/grading-worker/tests/test_worker_patch2a.py` | Cascade fix: added `log_grading_skip` stub; updated log key assertions (`no_user_turns_skip`/`skipped_insufficient_evidence` → `session_ineligible`; `min_student_words=` → `min_words_threshold=`) |

#### Implementation

`process_session_completed_job` now calls `evaluate_grading_eligibility(session_row["raw_backup_json"], min_student_words=min_student_words)` before `build_evaluation_input`. On ineligibility, logs `grading.session_ineligible` with `reason=`, `student_word_count=`, `min_words_threshold=` (populated only for `insufficient_words`), then makes a best-effort `repository.log_grading_skip()` call wrapped in `try/except Exception` (non-fatal — skip-log failure logs `grading.skip_log_failed` and does not re-raise, preserving message ACK behavior). Returns before the provider/fallback/upsert path.

#### Tests (6/6 pass)

| Test | Coverage |
|---|---|
| `test_skip_no_raw_backup` | `raw_backup_json=None` → `reason=no_raw_backup`, `source=worker`, counts `None`, no upsert |
| `test_skip_invalid_raw_backup` | `raw_backup_json="not a list"` → `reason=invalid_raw_backup`, counts `None`, no upsert |
| `test_skip_no_user_turns` | `raw_backup_json=[]` → `reason=no_user_turns`, `min_words_threshold=None`, no upsert |
| `test_skip_insufficient_words` | 2-word turn, `min=25` → `reason=insufficient_words`, `student_word_count=2`, `min_words_threshold=25`, no upsert |
| `test_eligible_skips_skip_log_and_upserts` | 34-word session → `skip_log_calls=0`, `upsert_call_count=1` |
| `test_skip_log_failure_is_nonfatal` | `log_grading_skip` raises `RuntimeError` → no re-raise, no upsert |

#### Safety

* No `psql`, `pg_dump`, `alembic`, `docker`, or `docker compose` commands run.
* No live DB connection. All tests use `_FakeRepo` in-process mock.
* No `reconciliation_scanner.py`, `backfill_completed_sessions.py`, `grading_repository.py`, `session_service.py`, or any core-api file modified.
* No Groq calls. No RabbitMQ operations. No TEN/browser.
* No `.env` values printed.
* `infrastructure/db-init/01-init.sql` unchanged — mirror deferred to Patch 7G-8D.

---

## 12. Known Limitations & Gaps

* **No Durable Outbox:** If RabbitMQ is down when a session finishes, the session event is not persisted locally for later retry. The reconciliation scanner provides partial automated recovery but is not a transactional outbox; missed sessions require scanner execution (cron or manual) to be graded.
* **Recovery Tools (dev/ops-only):**
  * `backfill_completed_sessions.py` — manual one-shot backfill; verified via historical backfill execution.
  * `reconciliation_scanner.py` — one-shot scanner with `--grace-minutes` grace window; cron-ready; dry-run default; no RabbitMQ dependency; commit `fc18916`. Not a daemon; does not loop internally.
  * Both tools are idempotent (ON CONFLICT DO UPDATE on `grading_results`); neither replaces a transactional outbox.
* **80 Sessions with NULL raw_backup_json (historical):** Audited and root cause confirmed. These pre-patch sessions have `raw_backup_json IS NULL` because the old `_persist_event_log` if/else omitted the column when `_event_log` was empty (noise, rapid-disconnect, silent connections). **Do not backfill or migrate these 80 rows.** They are historical data; `fake_grader.v1` would produce meaningless fixed scores for 0-turn input. Future sessions are no longer affected — see patch `440ff98`.
* **`_persist_event_log` [] patch applied (`440ff98`):** `_persist_event_log` now always writes `raw_backup_json = CAST(:logs AS jsonb)`. Empty sessions store `[]` instead of NULL. Sessions with accepted speech turns are unchanged. DB-verified with monkeypatched RabbitMQ no-op: `raw_backup_json::text = '[]'`, `status = 'completed'`, `ended_at IS NOT NULL`. The backfill script's `IS NOT NULL` filter will now count formerly-NULL-producing sessions as candidates, but the `user_turns=0` Python guard skips them — no false grading results.
* **`SQLSessionStore.persist_event_log` is dead code:** Defined in `services/core-api/src/realtime/session_store.py` with an identical NULL-producing if/else pattern; appears unused by current call-site search. Removal should be a separate cleanup with verification.
* **Connection Shutdown:** `close_publisher()` exists but is not wired into the application shutdown lifecycles; TEN gateway shutdown may print robust connection warning logs.
* **Grading Analysis UI (dev preview only):** `GET /api/v1/sessions/{session_id}/grading` is exposed via the control center Session Analysis card. Returns `GradingRead` (4 scores + summary + corrections + graded_at). Session ownership enforced via `sessions.user_id` JOIN. UI fetch is one-shot with 2s delay after `session_ended` or manual disconnect. Card is labeled "DEV PREVIEW" (Patch 6 cleaned badge text and disclaimer — see Section 13). Manual browser end-to-end dev-preview test passed for session `26af0fc2-9965-48c6-b509-54e89cc56c8b`: TEN real STT/LLM/TTS ran, `raw_backup_json` persisted 12 events, `session.completed` published, grading result displayed in the Session Analysis card. Real LLM grader tested in Patches 3–5.
* **Grading Worker:** `GRADING_PROVIDER` dispatch is wired (commit `06acf97`). `GroqClient` exists (commit `1cae30b`). Default/unset remains `"fake"`. Patch 3 controlled one-shot live Groq test passed — see Section 9. Patch 4 normal RabbitMQ consume-loop live Groq test passed — see Section 10. Patch 5 browser UI verification of a real `llm_grader.v1` row passed — see Section 11. UI badge and disclaimer cleaned in Patch 6 (see Section 13). CUDA reproducibility documented in Patch 7B (`requirements-torch-cu126.txt`). Patch 7C multi-session stability test completed — see Section 15; pipeline reliability confirmed. Patch 7D-A/B calibration and transcript review completed — see Section 16; root cause of repeated 2.95 confirmed as STT/transcript quality, not prompt or model floor. Patch 7E word-count quality gate implemented (commit `8b16c50`) — see Section 17; sessions below `GRADING_MIN_STUDENT_WORDS=25` are now skipped without a Groq call or DB upsert. Patch 7F-1 grading status endpoint and UI implemented (commit `ddb46ec`) — see Section 18; `GET /grading/status` exposes `graded`/`pending`/`insufficient_evidence` dynamically; UI shows actionable message for skipped sessions; live API/browser smoke test is Patch 7F-2. Patch 7G production hardening audit complete — see Section 19; 13-area review identified critical gaps: word-count helper event-alias drift, scanner threshold bypass, fake fallback production blocker, CORS lockdown needed. Patch 7G-2 word-count parity fix implemented (commit `24fef0b`) — event-alias drift resolved; see Section 19 Patch 7G-2 subsection. Patch 7G-3 status Literal schema and UI fail-closed handling implemented (commit `55a4d02`) — see Section 19 Patch 7G-3 subsection. Patch 7G-4 audit/design complete (2026-05-25) — see Section 19 Patch 7G-4 subsection. Patch 7G-4A session eligibility helper committed; Patch 7G-4C scanner execute-path gate committed (`7dcc9e8`); Patch 7G-4D backfill execute-path gate committed (`80d4db7`) — see Section 19 Patch 7G-4C/7G-4D subsections. Patch 7G-4 series complete; verification cleanup completed after approved-env rerun: 154/154 passed via project-venv python. Patch 7G-5 fake fallback env gate implemented (commit `dcdf9ba`): `GRADING_FAKE_FALLBACK` defaults to false; LLM failures log `grading.llm_failed_no_fallback` and re-raise instead of silently writing fake results. Patch 7G-6 StaticFiles/CORS lockdown implemented (commit `7d522d9`): CORS wildcard replaced with 8-origin local allowlist; `StaticFiles` at `/static`; `/control-center` FileResponse route; 15/15 tests passed. Patch 7G-7 migration strategy runbook established (commit `bac73d2`): `infrastructure/db-migrations/README.md` created; numbered SQL migration workflow, naming convention, backup/preflight/apply/verify/rollback/sync runbook defined; no Alembic adopted for now; no migration SQL applied; no schema changed. Patch 7G-8A migration SQL file committed (commit `d2bb908`): `0001_grading_skip_log.sql` created (table did not yet exist at 7G-8A time); subsequently applied and verified in Patch 7G-8B Execute. Patch 7G-8B Execute complete (2026-05-26): `grading_skip_log` migration applied and verified on local DB; table exists, row_count=0, backup taken, all columns/indexes/constraints/FK verified; see Section 19 Patch 7G-8B Execute subsection. Patch 7G-8C app integration audit/design complete (audit/design only; no DB commands run; no app code modified; see Section 19 Patch 7G-8C subsection); implementation partially complete: Patch 7G-8C-1 done, pending separate approved prompts (7G-8C-2 through 7G-8C-4). Patch 7G-8C-1 repository method implemented (commit `cb79155`, 2026-05-26): `GradingRepository.log_grading_skip()` added to `grading_repository.py`; asyncpg ON CONFLICT upsert pattern; 5/5 mocked tests pass; no live DB, no worker/scanner/backfill/core-api changes in this sub-patch. Patch 7G-8C-2 worker integration complete (commit `85ce409`, 2026-05-26): `worker.py` refactored to call `evaluate_grading_eligibility` before `build_evaluation_input`; best-effort `log_grading_skip` for all four ineligible reasons; 6/6 mocked tests pass; scanner/backfill integration (Patch 7G-8C-3) pending separate approved prompt.
* **Control Center UX Status (2026-05-27):** Auth form redesign in place (email + password login; Bearer Token fallback visible by default via `<details open>`). `getDefaultCoreApiUrl()` maps gateway ports 8080–8099 to Core API port 8000 (commit `c5e68fd`). Sign In / Register / Enter-key validation errors now display visibly in `#auth-state` (commit `5195315`). Static curl smoke at `:8000/control-center` HTTP 200 PASS. Live browser smoke at `http://localhost:8081/control-center` is pending (requires gateway 8081 running). CORS on core-api allows only ports 3000, 5173, 8000, 8080 — gateway ports 8081–8086 are CORS-excluded (pre-existing, not introduced by UX fix). Gateway CORS is `allow_origins=["*"]`.
* **Grading Pipeline Readiness (2026-05-27): PARTIAL.** RabbitMQ (`:5672`) and PostgreSQL (`:5432`) docker services are running. Core API responds at `:8000`. Control Center grading UI is fully wired (`fetchAndShowGrading` calls `GET /grading/status` → `GET /grading`). Worker code (`worker.py`, `grading_repository.py`, `session_eligibility.py`) is complete and correct. **Blockers:** (1) grading-worker process is not running — nothing consumes `luve.session.completed`; (2) `services/grading-worker/.env` does not exist — `DATABASE_URL`, `RABBITMQ_HOST`, and (for LLM mode) `GROQCLOUD_API_KEY` are all absent; (3) `/grading/status` does not read `grading_skip_log` — skip reasons stored by worker are invisible to the API (known gap, not a crash). Minimal safe next action: create `services/grading-worker/.env` with `DATABASE_URL`, `RABBITMQ_HOST=localhost`, `RABBITMQ_PORT=5672`, `RABBITMQ_USER=guest`, `RABBITMQ_PASS=guest`, `GRADING_PROVIDER=fake` — start worker — run one session — verify `grading.completed` in worker log and `GET /grading/status` returns `graded`.
* **VAD & Whisper Warm Policy:** Changing VAD thresholds or disabling Whisper unload is high risk; these changes are not current next tasks.
* **Not Production-Ready:** Code is tuned for local single-session correctness and local stress verification; do not claim production scale.
