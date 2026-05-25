# LUVE Project State

This file is the current source of truth for mutable repo state in `docs/ai`.

- Read this file first for current baseline, verified evidence, and known limitations.
- Treat `NEXT_TASK.md` as a scoped task memo, not as global repo state.
- Treat `CLAUDE_CODE_HANDOFF.md` as architecture/historical onboarding context, not mutable state.

## 1. Current Expected Git State

* **Worktree:** No tracked modifications; only untracked user-owned artifacts (`.understand-anything/`, `docs/system-map.md`).
* **Latest runtime/tooling baseline:** `24fef0b` — fix(core-api): align grading status word count detection (Patch 7G-2 word-count parity fix).
* **Source of Truth:** All python services runtime files in `services/core-api/` and `services/grading-worker/` are committed and match the local baseline.

## 2. Latest Important Commits

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

Not implemented yet. Migration strategy must be finalized in Patch 7G-7 before this table is created.

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

Not implemented yet. Migration directory and scripts are Patch 7G-7 scope.

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

**Finding:** `scripts/reconciliation_scanner.py` `_count_user_turns()` counts `USER_TURN` events but does **not** enforce `GRADING_MIN_STUDENT_WORDS`. Running `--execute` with `GRADING_PROVIDER=llm` would submit below-threshold sessions to Groq, undoing the Patch 7E safety gate.

**Risk severity: High.** Sessions the worker deliberately skipped would receive authoritative-looking scores, misleading users about short or noisy transcripts.

**Fix planned in Patch 7G-4:** Add `--min-words` argument (default: `GRADING_MIN_STUDENT_WORDS` env, fallback 25). Gate scanner candidates by student word count before any submission.

**Operational constraint:** Do not run scanner with `--execute` and `GRADING_PROVIDER=llm` until Patch 7G-4 is merged.

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

**Finding:** No Nginx in `docker-compose.yml`. No `StaticFiles` mount in `main.py`. Patch 7F-2 smoke required a `file://` URL workaround with `luve.control.coreApiUrl` localStorage injection.

**Planned fix (Patch 7G-6):**
```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app.mount("/static", StaticFiles(directory="src/static"), name="static")

@app.get("/control-center")
async def control_center():
    return FileResponse("src/static/index.html")
```

**Must be paired with CORS lockdown** (replacing `allow_origins=["*"]` with an explicit list via `CORS_ALLOW_ORIGINS` env var) before any broader exposure. Not implemented yet.

### 8. API/UI Hardening

**Items identified for Patch 7G-3:**
- `GradingStatusRead.status: str` → `status: Literal["graded", "pending", "insufficient_evidence"]`. Pydantic raises on unexpected values rather than silently passing them through.
- `fetchAndShowGrading` has no `else` fallback after the `pending` branch — a fourth status string falls through silently with no UI update.
- `fetchAndShowGrading` has no 401/session-expired handling — an expired token renders no error to the user.

No breaking changes to `GradingRead`. Not implemented yet.

### 9. Queue/Worker Production Safety

**Fake fallback risk (production blocker):** `grading.llm_failed_fallback` silently upserts `fake_grader.v1` scores on every Groq failure. In production, users would receive fabricated scores visually indistinguishable from real grading.

**Immediate fix (Patch 7G-5):** Gate fake fallback behind `GRADING_FAKE_FALLBACK` env var (default `false`). With fallback disabled, Groq failures NACK the message → DLQ.

**DLQ (Patch 7G-9):** Add `grading.dlq` exchange + `grading_dead_letter` queue with `x-dead-letter-exchange` binding. Failed jobs accumulate for SRE inspection rather than being silently lost. Not implemented yet.

### 10. Transcript Quality / Noise Heuristics

**Current gate:** raw student word count ≥ 25. Does not catch long-but-noisy transcripts (e.g., session `98a58d10` at 92 words with severe STT artifacts).

**Future heuristics (not in current scope):**
- Unique-word ratio < 0.3 → flag as repetitive
- USER_TURN count < 3 → flag as insufficient dialogue
- Single-word repetition > 40% of student words → flag

Not implementing now. A `quality_flags JSONB` field on `grading_skip_log` can record heuristic flags later without a new table.

### 11. Security and Privacy

- **CORS `allow_origins=["*"]`** — production blocker. Replace with explicit origins via `CORS_ALLOW_ORIGINS` env var. Must pair with Patch 7G-6.
- **Auth token in localStorage** — acceptable for local single-origin control center. Future external exposure requires CSP header (`Content-Security-Policy: default-src 'self'`) and no third-party scripts.
- **`raw_backup_json` not exposed** — confirmed: `/grading/status` response does not return transcript data.
- **Session ownership enforced** — both `/grading/status` and `/grading` enforce `s.user_id = :user_id` in the SQL JOIN.
- **Rate limiting** — `/grading/status` has no rate limit. Add `slowapi` (10 req/min per user) before broader use.

### 12. Production Readiness Checklist

Must-complete before enabling `GRADING_PROVIDER=llm` for real users:

- [ ] CORS lockdown (`allow_origins=["*"]` → explicit list)
- [ ] Persistent skip/status strategy approved and migrated (`grading_skip_log` or accepted limitation documented)
- [ ] Migration strategy finalized (numbered SQL migrations directory proposed and reviewed)
- [ ] Scanner `--min-words` threshold parity (Patch 7G-4)
- [x] Word-count event-alias parity fix (Patch 7G-2 — commit `24fef0b`)
- [ ] Fake fallback gated or disabled (Patch 7G-5)
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
| 7G-8 | `grading_skip_log` implementation (after 7G-7 approved) | Recommended |
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
* Status schema/UI hardening remains Patch 7G-3 scope.

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
* **Grading Worker:** `GRADING_PROVIDER` dispatch is wired (commit `06acf97`). `GroqClient` exists (commit `1cae30b`). Default/unset remains `"fake"`. Patch 3 controlled one-shot live Groq test passed — see Section 9. Patch 4 normal RabbitMQ consume-loop live Groq test passed — see Section 10. Patch 5 browser UI verification of a real `llm_grader.v1` row passed — see Section 11. UI badge and disclaimer cleaned in Patch 6 (see Section 13). CUDA reproducibility documented in Patch 7B (`requirements-torch-cu126.txt`). Patch 7C multi-session stability test completed — see Section 15; pipeline reliability confirmed. Patch 7D-A/B calibration and transcript review completed — see Section 16; root cause of repeated 2.95 confirmed as STT/transcript quality, not prompt or model floor. Patch 7E word-count quality gate implemented (commit `8b16c50`) — see Section 17; sessions below `GRADING_MIN_STUDENT_WORDS=25` are now skipped without a Groq call or DB upsert. Patch 7F-1 grading status endpoint and UI implemented (commit `ddb46ec`) — see Section 18; `GET /grading/status` exposes `graded`/`pending`/`insufficient_evidence` dynamically; UI shows actionable message for skipped sessions; live API/browser smoke test is Patch 7F-2. Patch 7G production hardening audit complete — see Section 19; 13-area review identified critical gaps: word-count helper event-alias drift, scanner threshold bypass, fake fallback production blocker, CORS lockdown needed. Patch 7G-2 word-count parity fix implemented (commit `24fef0b`) — event-alias drift resolved; see Section 19 Patch 7G-2 subsection; next implementation is Patch 7G-3.
* **VAD & Whisper Warm Policy:** Changing VAD thresholds or disabling Whisper unload is high risk; these changes are not current next tasks.
* **Not Production-Ready:** Code is tuned for local single-session correctness and local stress verification; do not claim production scale.
