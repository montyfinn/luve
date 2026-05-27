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

Chạy:

ss -ltnp | grep -E ':(8000|8080|8081|8082|8083|8084|8085|8086)'
Nếu muốn dọn sạch toàn bộ app LUVE đang chiếm các port đó:

fuser -k 8000/tcp 8080/tcp 8081/tcp 8082/tcp 8083/tcp 8084/tcp 8085/tcp 8086/tcp
Sau đó kiểm tra lại:

ss -ltnp | grep -E ':(8000|8080|8081|8082|8083|8084|8085|8086)'
Nếu không còn dòng nào thì chạy lại từ đầu:

cd services/core-api
source venv/bin/activate
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
Terminal khác:

cd services/core-api
source venv/bin/activate
python run_ten.py
Nếu máy không có fuser, dùng cách thủ công:

ss -ltnp
kill <PID>