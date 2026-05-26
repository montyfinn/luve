# Test Environment — LUVE Thesis

---

## Hardware

| Component | Spec |
|---|---|
| GPU | NVIDIA RTX 3050 Ti Mobile — 4096 MiB VRAM |
| Whisper model (per process) | `small.en` — ~466 MiB actual VRAM |
| Max gateway processes (VRAM-safe) | 3 (3 × 466 ≈ 1398 MiB, well under 4096) |
| CPU | (local dev machine) |
| OS | Ubuntu (Linux 6.8.0-111-generic) |

---

## Runtime Stack

| Layer | Technology | Notes |
|---|---|---|
| WebRTC gateway | Custom Python (`aiortc`) | NOT the official TEN framework SDK; `ten` package absent from venv |
| Extension graph naming | TEN-inspired (graph.json, manifest.json, property.json) | Read-only JSON; not executed by TEN runtime |
| STT | Faster-Whisper `small.en` | Singleton per-process (`WhisperInference._instance`) |
| LLM | Groq Llama-3 / Gemini (configurable) | Not called during automated tests |
| TTS | edge-tts | Not called during automated tests |
| Message bus | RabbitMQ (`luve.session.completed`, prefetch=1) | Must be running for live smoke |
| Database | PostgreSQL | Must be running for live smoke; mocked in unit tests |
| Session capacity | `TEN_SINGLE_SESSION_CAPACITY = 1` per gateway process (`ten_compat.py:34`) | Multi-user via multiple uvicorn processes on different ports |

---

## Service Ports (Local Dev)

| Service | Port | Start command |
|---|---|---|
| Core API (shared) | 8000 | `uvicorn src.main:app --host 0.0.0.0 --port 8000` |
| Gateway process 1 | 8080 | `uvicorn run_ten:app --port 8080` (default) |
| Gateway process 2 | 8081 | `uvicorn run_ten:app --port 8081` |
| Gateway process 3 | 8082 | `uvicorn run_ten:app --port 8082` |
| PostgreSQL | 5432 | docker-compose service `postgres` |
| RabbitMQ AMQP | 5672 | docker-compose service `rabbitmq` |
| RabbitMQ Management | 15672 | docker-compose service `rabbitmq` |

---

## Key Constraints

- **No TEN native SDK**: `services/core-api/requirements.txt` does not include `ten`. The `luve_extension.py` uses a `_FallbackTen` stub (lines 27–37) when `import ten` fails.
- **Multi-user isolation**: Each gateway process loads its own Whisper model. There is no cross-process session sharing.
- **Frontend routing**: `index.html` `getDefaultGatewayUrl()` infers gateway URL from browser port. Opening `http://localhost:8081/control-center` automatically targets gateway 2.
- **Grading worker**: Horizontally scalable (prefetch=1). Multiple worker processes can run against the same RabbitMQ queue safely.

---

## Python Environments

| Service | Venv path |
|---|---|
| core-api (gateway) | `services/core-api/venv/` |
| grading-worker | `services/grading-worker/venv/` |

---

## Automated Test Scope (No Live Services Required)

The `run_thesis_evidence.sh` script runs without starting any service. It uses:
- The grading-worker venv (`services/grading-worker/venv/bin/python`)
- `pytest` with mocked database connections
- `py_compile` (syntax only)
- Read-only system queries (`nvidia-smi`, `docker ps`, `git`)
