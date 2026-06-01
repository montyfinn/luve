# Contributing to Luve

Thanks for your interest in Luve! This is an actively developed, early-stage
project, so issues, pull requests, and review feedback are all welcome.

## Ground rules

- **Do not change the realtime hot path** (VAD, STT, LLM, TTS, WebRTC) without
  prior discussion — these paths are latency-sensitive and easy to regress.
- **Never commit secrets.** Real `.env` files are git-ignored; only
  `.env.example` templates are tracked.
- **Keep services isolated:** `core-api` and `grading-worker` must not import
  each other's code. They communicate over HTTP and RabbitMQ.
- Keep changes small, focused, and reviewer-friendly.

## Development setup

```bash
cp .env.example .env
cp services/core-api/.env.example services/core-api/.env
cp services/grading-worker/.env.example services/grading-worker/.env
docker compose up -d
```

## Tests

The Python services are tested with `pytest`. After installing each service's
dependencies, run the suite from within that service, for example:

```bash
cd services/core-api && pytest
cd services/grading-worker && pytest
```

If a test needs a running service or external dependency that you cannot start
locally, say so in your pull request rather than skipping it silently.

## Pull requests

1. Branch from `main`.
2. Make a focused change with a clear, Conventional-Commits-style message
   (e.g. `feat(...)`, `fix(...)`, `docs(...)`).
3. Ensure the tests relevant to your change pass, and note anything you could
   not verify locally.
4. Open a PR describing **what** changed and **why**.
