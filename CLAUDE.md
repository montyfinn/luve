
---
name: comprehensive-ai-coding-guidelines
description: 12 Behavioral guidelines to reduce common LLM coding mistakes, optimize system resources, and ensure scalability. Use when writing, reviewing, or refactoring code to avoid overcomplication, make surgical changes, surface assumptions, and protect system architecture.
license: MIT
---

# LUVE Project: Active Task Priority

> These rules override or narrow the general guidelines below when working in this repository.

| Authority | File | Role |
|---|---|---|
| Active task scope | `docs/ai/NEXT_TASK.md` | Defines current mode (audit-only, implement, etc.) and allowed read paths. Overrides general guidelines. |
| Current baseline | `docs/ai/PROJECT_STATE.md` | Current git state, reliability evidence, and known limitations. |
| Architecture context | `docs/ai/CLAUDE_CODE_HANDOFF.md` | Service map, pipelines, protected files, and operating rules. |
| General behavior | `CLAUDE.md` (this file) | Applies only when not overridden by the above. |

## LUVE-Specific Hard Rules

- If `NEXT_TASK.md` says **audit-only**: do not modify, stage, or commit any file.
- If `git status --short` shows unexpected dirty files outside those permitted by the active task: stop and report.
- Do not touch the realtime hot path (VAD, STT, LLM, TTS, WebRTC) unless the active task explicitly authorizes it.
- Do not publish RabbitMQ messages unless the active task explicitly authorizes it.
- Do not run destructive database commands (`DROP`, `DELETE`, `TRUNCATE`, `UPDATE` without a `WHERE`) under any circumstances.
- Never print or log secrets, passwords, tokens, API keys, JWTs, cookies, or database URLs containing credentials.

## Architecture Orientation

LUVE is a Docker Compose monorepo for real-time English speaking practice. Services communicate only over HTTP and RabbitMQ — **`core-api` and `grading-worker` never import each other's code.**

- `services/core-api/` — the `core_api` image. Runs two FastAPI apps from the same codebase: `src/main.py` (REST/auth/session UI, port `8000`) and `run_ten.py` (TEN/WebRTC realtime gateway, port `8080`). The realtime hot path lives here: `src/ten_ext/luve_extension.py` (orchestration), `src/realtime/adapters/ten_compat.py` (WebRTC bridge, 1-session/node cap), `src/media/{stt_worker,brain,tts}.py` (STT / LLM / TTS).
- `services/grading-worker/` — RabbitMQ consumer for `luve.session.completed`. Grades via Groq or an offline `fake` grader (`GRADING_PROVIDER` env flag). Eligibility/word-count gating in `src/session_eligibility.py` + `src/worker.py`.
- `infrastructure/db-init/01-init.sql` — fresh-volume baseline schema. `infrastructure/db-migrations/000N_*.sql` — numbered manual migrations (no Alembic); existing volumes need manual apply per `db-migrations/README.md`.

**Session→grading flow:** on session end the gateway commits `sessions` (status, `raw_backup_json`, `ended_at`) **and** a `session_outbox` row in one transaction, then publishes `session.completed` inline. Inline publish is the live path; the transactional outbox relay exists but is **default-off** (`OUTBOX_RELAY_ENABLED=false`). Grading is idempotent (deduped on `session_id`). Full service map, pipelines, and protected-file list: `docs/ai/CLAUDE_CODE_HANDOFF.md`.

## Build, Run, and Test Commands

Compose runs **containers**; manual `venv` runs are for debugging a single service and must not run while the stack is up (port/queue conflicts).

```bash
# Full stack (CPU default). Plain `up -d` with no profile starts ONLY infra.
docker compose --profile app up -d --build      # first run / after image changes
docker compose --profile app up -d              # fast restart
docker compose --profile app down               # stop (NEVER add -v — wipes DB + STT model)

# Opt-in GPU STT (ten_gateway only):
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile app up -d --build

# Logs / status
docker compose ps
docker compose logs -f ten_gateway              # realtime pipeline
docker compose logs -f grading_worker           # look for worker.ready, grading.completed
```

Tests use each service's `pytest`, run from the **core-api venv** (grading-worker has no venv of its own and needs `pytest-asyncio`, which lives there):

```bash
# core-api
cd services/core-api && venv/bin/python -m pytest tests/ -q

# grading-worker (run from its dir, using the core-api venv interpreter)
cd services/grading-worker && ../core-api/venv/bin/python -m pytest tests/ -q

# single file / single test
venv/bin/python -m pytest tests/test_worker_patch2a.py -q
venv/bin/python -m pytest tests/test_worker_patch2a.py::test_name -q
```

Prefer **focused** test runs — a full `tests/` run has intermittently hung in some environments, so the full suite is not asserted green. Quick syntax/import smokes used throughout this repo:

```bash
cd services/core-api
venv/bin/python -m py_compile src/main.py run_ten.py          # compile check
venv/bin/python -c "from src.main import app; print(app.title)"   # import smoke
node --check src/static/index.html   # (after extracting the inline <script>) JS syntax
```

Health checks: `curl http://localhost:8000/readyz` (core_api: 200 iff DB reachable), `curl http://localhost:8080/readyz` (gateway: shallow startup readiness), `curl http://localhost:8080/rtc/health` (realtime session snapshot). Control center UI: `http://localhost:8000/control-center`.

---

# 12 Comprehensive AI Coding Guidelines

Behavioral guidelines combining [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) with strict architectural and system-optimization principles. 

**Tradeoff:** These guidelines bias toward caution, resource optimization, and strict architectural control over blind speed. 

---

## Part 1: The Karpathy Core (Behavior & Precision)

### 1. Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First
**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes
**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution
**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

## Part 2: The Extended Core (Architecture, Cost & Feasibility)

### 5. Micro-Scoping (Task Decomposition)
**Decompose large tasks. Keep the context window lean.**
- Never accept monolithic tasks. Break them into independent, modular steps.
- Smaller context windows save token costs and prevent AI hallucinations.
- Provide a clear, overarching view of the module's workflow before diving into implementation details.

### 6. Architectural Ownership & Feasibility
**The human owns the architecture. The AI acts as the builder.**
- Do not invent database schemas, logic flows, or core technologies without a strict evaluation of feasibility, cost, and performance.
- Always prioritize the most resource-efficient approach.
- Keep system constraints in mind to prevent bottlenecks and ensure the system will not overload during sudden user traffic spikes.

### 7. The Verification Loop (Reality Check)
**No claims without evidence. Verify reality first.**
- Use tools to read files, grep codebases, or run scripts BEFORE attempting a fix or proposing a solution.
- AI assertions mean nothing without actual log outputs or terminal results. Do not guess the state of the system.

### 8. Strict Versioning & Rollbacks
**Commit incrementally. Protect the UX.**
- Make small, atomic changes after every successful micro-step.
- If a smooth user experience (UX) or workflow is compromised by a change, the code must be structured so a clean rollback is immediately possible without untangling hours of work.

### 9. Anchor What Works (Zero Regression)
**Freeze safe zones. Do not break existing flows.**
- When asked to improve component C, explicitly recognize that components A and B are working perfectly.
- Set a hard boundary: Do not touch A and B. Ensure the current smooth operation remains completely uninterrupted.

### 10. Limit "Future-Proofing" (Resource Optimization)
**Solve today's scale. Don't over-engineer for tomorrow.**
- Do not write speculative, bloated code for hypothetical future expansions.
- Only build what is strictly necessary for the current user experience to be seamless.
- Real scalability comes from calculated architectural design when the time is right, not from AI-generated boilerplate code.

### 11. Contextual Precision
**Feed exact data. Treat context like server RAM.**
- Only consume the exact files, error logs, or specific rules required for the immediate task.
- Do not read entire directories aimlessly. 
- Optimize context usage to maintain high execution speed and low API cost.

### 12. Aggressive Review & Bottleneck Prevention
**Scrutinize every line for performance and clarity.**
- Evaluate logic rigorously to ensure no hidden performance bottlenecks or memory leaks are introduced.
- The final solution must be the most optimal path to save server resources.
- Code must be clean and transparent enough so that a human engineer can rapidly read, understand, and extract the best practices from it.