# LUVE_FACTS — verified system knowledge for the thesis

System-design baseline: **`main@6a61bc8`** (the commit the architecture,
schema, and flow discussion is anchored to). Final submitted GitHub source:
**`main@b38fe63`**. Evidence/runtime baseline: **`main@6640171`** (the HEAD of
the worktree `/home/minhthuy/project/luve-code-hygiene` used to run the demo
and capture Chapter 4 evidence). The commits leading to `b38fe63` are
code-review / documentation / static-copy polish, GPU CUDA runtime support
(PR #5), app/UI refinements, and later tutor/STT/grading-prompt polish; they
do **not** replace the Chapter 4 runtime evidence or change the core
architecture, component boundaries, schema, or data/control flows.
Only write claims you can trace to the running system. The constraints
below are hard limits — do not soften them in the thesis.

## Thesis writing policy
- **Thesis body language: English.** All visible thesis text (headings,
  abstract, body, captions) is written in English.
- **Internal figure/table preparation notes may be Vietnamese**, but only
  inside `% TODO-FIGURE [VI]:` / `% TODO-TABLE [VI]:` comments in
  `main.tex` (and inside `FIGURE_TODO.md`). They are never typeset into the
  PDF. All other comments (`% TODO-CITE`, `% [PLACEHOLDER]`) are English.
- **Main focus: software / system design** — architecture, component
  responsibilities, data/control flow, real-time communication, backend/
  frontend integration, database and queue design, implementation
  decisions, runtime/devops constraints.
- **Avoid over-emphasizing** pedagogy theory, business value, marketing
  claims, learner psychology, or unsupported learning-effectiveness
  claims. Pedagogical terms appear only to name software features (tutor
  reply, grading result, feedback display, session analysis).

## Truth constraints (do NOT violate)
- ❌ Do **not** claim production-ready. LUVE is a **controlled-demo /
  research prototype**.
- ❌ Do **not** claim stable multilingual STT. Stable demo mode is
  **`forced_en` + `small.en` + second-pass disabled**.
- ❌ Do **not** claim true acoustic/phoneme pronunciation scoring.
  "Pronunciation" is a **clarity estimate derived from STT
  confidence/uncertainty**, not phoneme analysis.
- ❌ Do **not** claim exactly-once queue delivery. Delivery is
  **at-least-once**; grading is **idempotent (dedup on `session_id`)**.
- ❌ Do **not** claim horizontal scaling. The realtime hot path is
  **single-session-per-node**.
- ⚠️ The backend/system-design baseline remains **`main@6a61bc8`**; the
  final submitted GitHub source is **`main@b38fe63`**, while **`main@6640171`**
  is the evidence/runtime baseline (GPU runtime added via PR #5,
  no core-architecture change — see header note).
  Current cat-companion/current-UI screenshots may be used only as client
  presentation/interface evidence for the demo. They do not redefine the
  frozen backend baseline, prove backend correctness, or imply that PR #2 /
  current UI work is merged or validated as backend behavior.

## What the system is
A Docker Compose monorepo for **real-time English speaking practice**:
STT capture → streaming LLM tutor replies → saved sessions → grading
pipeline.

## Services (communication boundaries: HTTP/WebRTC, PostgreSQL persistence, RabbitMQ async grading)
<!-- Communication boundaries: client-facing and control paths use HTTP/WebRTC where applicable; PostgreSQL provides durable persistence; RabbitMQ carries asynchronous grading work. -->

- **core-api** (`core_api` image) runs **two FastAPI apps from one codebase**:
  - `src/main.py` — REST / auth / sessions, **port 8000**.
  - `run_ten.py` — TEN / WebRTC realtime gateway, **port 8080**. Hot path
    lives here (`src/ten_ext/luve_extension.py`, `src/media/*`).
- **grading-worker** — RabbitMQ consumer on `luve.session.completed`.
  Grades via **Groq LLM** or an offline **`fake`** grader
  (`GRADING_PROVIDER`, default **`fake`**; `GRADING_FAKE_FALLBACK`
  default **off**).

## Realtime pipeline
VAD → STT → LLM → TTS → WebRTC. STT is **faster-whisper `small.en`,
`forced_en`**; `stt_enable_second_pass_verification` default **`False`**.
Single-session-per-node cap enforced in the WebRTC adapter.

## Session → grading flow (verified)
On session end the gateway commits, **in one transaction**, the
`sessions` row (status, `raw_backup_json`, `ended_at`) **and** a
`session_outbox` row, then **attempts inline publish of `session.completed` after DB commit**.
- Inline publish is the **live** path (attempted, not guaranteed).
- The transactional-outbox **relay exists but is default-off**
  (`OUTBOX_RELAY_ENABLED=false`) — recovery from a publish failure is
  **manual** unless the relay is enabled.
- Publish failure is **logged as a warning** (does not crash completion).
- Grading is **idempotent** (deduped on `session_id`).

## Privacy / logging (PR #1, merged into `main`)
Raw recognized transcript text is **redacted from the relevant STT recognition
log lines; those lines retain metadata** such as text length and confidence
values (`text_len`, `avg_logprob`, `no_speech_prob`), not the transcript text.
Two sites fixed: `coordinator.py` and `luve_extension.py`.

## Auth / CORS (be precise — the two apps differ)
- **REST API (`main.py`, :8000):** CORS is **locked** —
  `get_cors_allow_origins()` (no wildcard), `allow_credentials=False`,
  methods `GET/POST/OPTIONS`. `/readyz` returns 200 **iff** DB reachable
  (`SELECT 1`).
- **Realtime gateway (`run_ten.py`, :8080):** CORS is currently
  **`allow_origins=["*"]` with `allow_credentials=True`** (permissive —
  document this honestly as a hardening item, not as "locked").
  `/healthz` liveness; `/readyz` shallow (gateway-init only, no DB);
  `/rtc/health` is **unauthenticated** and returns session metadata
  (UUIDs / connection info, **no transcript / PII**); `/rtc/offer|ice|cmd`
  are gated by `assert_session_owner`.

## Database
Tables (in `infrastructure/db-init/01-init.sql`): **USERS, LESSONS,
SESSIONS, GRADING_RESULTS, GRADING_SKIP_LOG, SESSION_OUTBOX**.
`GRADING_RESULTS` has `overall/fluency/grammar/vocab/pronunciation_score
NUMERIC(4,2)`, `skill_feedback_json`, `score_schema_version`, `provider`,
`grader_version`. Migrations are **numbered manual SQL**
(`db-migrations/0001..0004` + README) — **no Alembic, no automated
migration runner**; existing volumes need manual apply.

## Grading skills (contract)
`GradingSkill = {"fluency","grammar","vocabulary","pronunciation_clarity"}`.
`pronunciation_clarity` is derived from **STT confidence/uncertainty or
LLM text**, explicitly **not** acoustic phoneme scoring; the LLM grader
is instructed to use `null` when evidence is insufficient.

## Known limitations (use in §5.3 and the abstract caveats)
1. Controlled demo / research prototype, **not** production.
2. English-focused STT (`small.en` + `forced_en`); multilingual
   second-pass is scaffolded **default-off** and unproven.
3. Pronunciation = **clarity estimate** from STT confidence, not phonemes.
4. Queue recovery: durable outbox row exists, but **relay default-off →
   recovery is manual**; delivery is at-least-once + idempotent grading.
5. **No production-grade migration runner**; manual numbered SQL.
6. Shallow readiness/health (REST = DB-only; gateway = startup-only,
   **no RabbitMQ probe**); observability is log-grep + DLQ, **no metrics
   endpoint**.
7. Realtime path is **single-session-per-node**; multi-gateway scaling
   not proven; no per-inference STT timeout.
8. Realtime gateway (:8080) CORS is currently permissive (`*` +
   credentials) — a hardening item.
9. `/rtc/health` exposes operational metadata **unauthenticated**
   (no transcript / PII).
10. Full test suite has intermittently hung in some environments; no CI
    gate — prefer focused `pytest` runs.

## Build / run (for Appendix C)
```bash
docker compose --profile app up -d --build   # full stack (CPU default)
docker compose --profile app up -d            # fast restart
docker compose --profile app down             # stop (never -v: wipes DB + STT model)
```
Health: `curl :8000/readyz` (DB), `curl :8080/readyz` (gateway),
`curl :8080/rtc/health` (session snapshot).

## Cite-worthy technologies (look up real references yourself)
faster-whisper / Whisper, the LLM tutor model family (Groq-served),
WebRTC, FastAPI, PostgreSQL, RabbitMQ, transactional-outbox pattern.
