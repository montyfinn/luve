# syntax=docker/dockerfile:1
# ============================================================
# LUVE core-api image (T1: deployability foundation, CPU-only)
#
# One image, two runnable processes:
#   - Core API (:8000):  uvicorn src.main:app --host 0.0.0.0 --port 8000   (default CMD)
#   - TEN gateway (:8080): python run_ten.py                                (override command)
#
# Scope notes:
#   - CPU-only base. GPU/CUDA enablement is deferred to T9.
#   - Whisper model is NOT baked in; faster-whisper downloads it at runtime
#     into HF_HOME. A persistent cache volume is wired in T2.
#   - Compose wiring, healthchecks, ports, and volumes are deferred to T2.
# ============================================================

# ---- Builder: install pinned deps into an isolated venv ----
FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# build-essential covers any pinned package that ships only an sdist (no wheel)
# for cp310. It lives only in this stage and is discarded from the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY services/core-api/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock

# ---- Client build: compile the Vite SPA served at /app ----
# The build context is the repo ROOT (docker-compose.yml: core_api.build.context: .),
# so the client/ source is reachable here. dist/ is produced in-image — it is
# never committed and developers never prebuild it manually.
FROM node:20-slim AS client-build
WORKDIR /client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

# ---- Runtime: slim image with only the venv + app source ----
FROM python:3.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/cache/huggingface

WORKDIR /app

# Bring in the prebuilt virtualenv (no build tools in the runtime layer).
COPY --from=builder /opt/venv /opt/venv

# Writable cache dir for runtime model download (mount a volume here in T2).
RUN mkdir -p /cache/huggingface

# Only the files needed to run the API and the TEN gateway.
# (Build context is the repo root, so these paths are service-relative.)
COPY services/core-api/src ./src
COPY services/core-api/run_ten.py ./run_ten.py
COPY services/core-api/graph.json ./graph.json

# Built Vite SPA, served by the Core API at /app (see src/main.py). Absent in
# local venv runs, where main.py guards the mount before serving.
COPY --from=client-build /client/dist ./client_dist

# Default process is the Core API. Override the command to run the gateway:
#   docker run ... python run_ten.py
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
