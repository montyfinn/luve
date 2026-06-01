# LUVE

**LUVE** is an open-source backend for **real-time English speaking practice**. A
browser "control center" streams microphone audio over WebRTC to a realtime
pipeline (VAD → speech-to-text → LLM reply → text-to-speech), and after a session
ends the conversation is scored asynchronously by an LLM grader.

It is a Docker Compose monorepo of independent services that communicate over HTTP
and RabbitMQ — they never import each other's code.

## Status

**Local / dev / demo-ready — not production-ready.** It runs end-to-end on a
single machine for demos and development. Production deployment still needs:
TLS / reverse proxy, secrets management, CI/CD, production migration workflow,
observability/metrics, deployment hardening, and the transactional-outbox
**runtime** (only the schema + helper foundation exists today, so event publishing
is not yet exactly-once).

Realtime STT has been validated only in a constrained demo config (forced English,
`small.en`); multilingual/auto-language STT is not validated. See
`docs/ai/PROJECT_STATE.md` for the detailed baseline.

## Services

| Service | Port | Role |
|---|---|---|
| `core_api` | 8000 | REST API, auth, control-center UI + static, readiness |
| `ten_gateway` | 8080 | WebRTC / TEN realtime pipeline (VAD→STT→LLM→TTS); reuses the `core_api` image |
| `grading_worker` | — | Consumes `session.completed` from RabbitMQ; grades via Groq (or an offline "fake" grader); writes `grading_results` |
| `postgres_db` | 5432 | PostgreSQL |
| `redis_cache` | 6379 | Redis (rate limiting / realtime transcript) |
| `rabbitmq_queue` | 5672, 15672 | RabbitMQ broker + management UI |
| `rabbitmq_init` | — | One-shot: declares the grading dead-letter topology, then exits |

App services run under the Compose `app` profile.

## Quick start (CPU default)

These commands run **containers**, not manual `venv` processes.

```bash
# 1. Create the root .env (Compose reads this — see "Configuration" below)
cp .env.example .env   # then fill in real values locally

# 2. Start the full stack (first run needs --build so ten_gateway can reuse the
#    core_api image). Plain `docker compose up -d` (no profile) starts ONLY infra.
docker compose --profile app up -d --build

# Fast restart later (images already built):
docker compose --profile app up -d
```

CPU STT is the default, stable mode and needs no GPU.

## Optional GPU STT (opt-in)

Runs `ten_gateway` STT on an NVIDIA GPU. It affects **`ten_gateway` only** —
`grading_worker`/Groq and every other service are unchanged. Requires the NVIDIA
Container Toolkit.

```bash
# Prerequisite check:
docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi

# Start with the GPU override (builds luve-core-api:gpu with the CUDA libs
# ctranslate2/faster-whisper need):
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile app up -d --build
```

Omit the override to return to the CPU default — no GPU required.

## Configuration

**Compose reads the root `.env`** (Compose variable interpolation). The
per-service `services/*/.env` files are only for running a service standalone
(advanced/debug); they are **not** used by Docker Compose. Real `.env` files are
git-ignored — only `.env.example` templates are tracked. Never commit secrets.

Key variables (names only — fill in locally):

```bash
# core_api + ten_gateway use SQLAlchemy async — note the +asyncpg driver:
DATABASE_URL=postgresql+asyncpg://<user>:<url-encoded-password>@postgres_db:5432/luve_database
# grading_worker uses raw asyncpg — plain postgresql:// scheme:
GRADING_DATABASE_URL=postgresql://<user>:<url-encoded-password>@postgres_db:5432/luve_database
SECRET_KEY=<random-secret>

POSTGRES_USER=dat_admin
POSTGRES_PASSWORD=<password>
POSTGRES_DB=luve_database
RABBITMQ_USER=<user>
RABBITMQ_PASS=<password>

# Grading provider. Default is the offline "fake" dev grader. For REAL Groq grading:
GRADING_PROVIDER=llm
LLM_PROVIDER=groq
GRADING_FAKE_FALLBACK=false
GROQCLOUD_API_KEY=<your-groq-key>
```

URL-encode reserved characters (`@ / : %`) in passwords.

## Access

- Control center UI: `http://localhost:8000/control-center`
- Core API: `http://localhost:8000`
- RabbitMQ management: `http://localhost:15672` (credentials from your `.env`)

Readiness / health:

```bash
curl http://localhost:8000/readyz     # core_api: 200 iff DB reachable
curl http://localhost:8080/readyz     # ten_gateway: shallow startup readiness
curl http://localhost:8080/rtc/health # ten_gateway: realtime session snapshot
```

## Logs & verification

```bash
docker compose ps
docker compose logs -f ten_gateway     # realtime pipeline
docker compose logs -f grading_worker  # async grading (look for worker.ready, grading.completed)
```

After a session ends, grading is asynchronous; results land in `grading_results`
once the worker finishes (you can confirm via `psql` inside `postgres_db` if
needed).

## Stop

```bash
docker compose --profile app down
```

⚠️ Do **not** add `-v` unless you intend to delete volumes — `down -v` wipes the
Postgres data and the cached STT model.

## Running a service manually (advanced / debug only)

Manual `venv` runs (`uvicorn src.main:app`, `python run_ten.py`, the worker) are
for debugging a single service in isolation. **Do not run them while the Compose
stack is up** — they conflict on ports 8000/8080 and on the RabbitMQ queue.

## Repository layout

![LUVE architecture](./docs/luve-architecture.drawio.svg)

```
luve/
├── docker-compose.yml          # default CPU stack
├── docker-compose.gpu.yml      # opt-in GPU override (ten_gateway)
├── .env.example                # root template (Compose reads root .env)
├── services/
│   ├── core-api/               # core_api image (also runs ten_gateway via run_ten.py)
│   └── grading-worker/         # async grading consumer (Groq / offline fake)
├── infrastructure/
│   ├── db-init/                # 01-init.sql (fresh-volume baseline schema)
│   └── db-migrations/          # numbered SQL migrations
└── docs/                       # architecture + AI/ops handoff docs
```

**Rule — no cross-importing:** `core-api` and `grading-worker` never import each
other's code; they communicate only over HTTP and RabbitMQ.

## Known limitations

- **Grading is asynchronous** — it runs after disconnect; the Session Analysis
  panel may need a refresh/poll before the result appears.
- **Pronunciation** may be unavailable when a session has insufficient clear-audio
  evidence.
- **CPU STT** (default) has higher latency than GPU STT.
- **GPU STT** requires the NVIDIA Container Toolkit.
- One active realtime session per node (gateway capacity is 1 by design).
- Not production-ready (see **Status**).
