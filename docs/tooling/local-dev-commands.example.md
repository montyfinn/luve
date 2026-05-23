# Local Dev Commands Example

This file documents common local commands without storing private credentials,
local login payloads, or machine-specific secrets.

## Core API

```bash
cd services/core-api
source venv/bin/activate
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Production-ish local command:

```bash
cd services/core-api
source venv/bin/activate
python -m gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## Infrastructure

```bash
docker compose up -d
docker compose ps
docker compose stop
docker compose start
docker compose down
docker compose up -d --build
```

## TEN/WebRTC Gateway

```bash
cd services/core-api
source venv/bin/activate
python run_ten.py
```


##Grading

```
cd ~/project/luve/services/grading-worker

set -a
source ../core-api/.env 2>/dev/null
set +a
export DATABASE_URL="$(grep '^DATABASE_URL=' ../core-api/.env | cut -d= -f2-)"

PYTHONPATH=. ../core-api/venv/bin/python -m src.worker

```

## Auth Token For Local Debug

Keep login payload files local and ignored by git. Do not commit real tokens,
passwords, cookies, or login payloads.

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d @login.json \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])'
```

http://127.0.0.1:8080/control-center
