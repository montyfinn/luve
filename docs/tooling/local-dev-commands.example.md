# Chạy LUVE bằng Docker Compose

# Chạy CPU/default
docker compose --profile app up -d

# Chạy GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile app up -d --build

# Kiểm tra GPU override trước khi chạy
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile app config | grep -n -A5 -B5 'gpus'

# Nếu host không có NVIDIA driver/toolkit ổn định, giữ CPU/default
nvidia-smi || true

# Chuyển CPU -> GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile app up -d --build --force-recreate ten_gateway

# Chuyển GPU -> CPU
docker compose --profile app up -d --force-recreate ten_gateway

# Tắt app, giữ data
docker compose --profile app down

# Tắt app GPU mode, giữ data
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile app down

# Nếu muốn dừng API/gateway/worker nhưng giữ Postgres/Redis/RabbitMQ:
docker compose stop core_api ten_gateway grading_worker

## 1. Nguyên tắc

                                                 http://127.0.0.1:8080/control-center

LUVE hiện chạy bằng Docker Compose, gồm các container:

* `postgres_db`
* `redis_cache`
* `rabbitmq_queue`
* `rabbitmq_init`
* `core_api`
* `ten_gateway`
* `grading_worker`

## 2. Vào thư mục project

```bash
cd ~/project/luve
```

---

## 3. Kiểm tra root `.env`

Compose đọc biến từ file root `.env`:

```bash
~/project/luve/.env
```

Không phải:

```bash
services/grading-worker/.env
```

Kiểm tra các biến chính, không in secret:

```bash
grep -nE '^(DATABASE_URL|GRADING_DATABASE_URL|GRADING_PROVIDER|LLM_PROVIDER|GRADING_FAKE_FALLBACK)=' .env
grep -n '^GROQCLOUD_API_KEY=' .env | sed 's/=.*/=<redacted>/'
```

Kỳ vọng:

```env
DATABASE_URL=postgresql+asyncpg://...
GRADING_DATABASE_URL=postgresql://...
GRADING_PROVIDER=llm
LLM_PROVIDER=groq
GRADING_FAKE_FALLBACK=false
GROQCLOUD_API_KEY=<redacted>
```

Lưu ý:

* `DATABASE_URL` dùng cho `core_api` và `ten_gateway`, phải là `postgresql+asyncpg://...`
* `GRADING_DATABASE_URL` dùng cho `grading_worker`, là `postgresql://...`
* Trong Docker, host DB là `postgres_db`, không phải `localhost`
* Không paste secret/key/password vào chat/log

---

## 4. Kiểm tra port 8000/8080 trước khi chạy

Nếu từng chạy manual app, kiểm tra port:

```bash
sudo ss -ltnp 'sport = :8000 or sport = :8080' || true
```

Nếu thấy process host như `uvicorn`, `python`, `python3` đang chiếm port, dừng bằng PID:

```bash
sudo kill <PID_8000> <PID_8080>
```

Kiểm lại:

```bash
sudo ss -ltnp 'sport = :8000 or sport = :8080' || true
```

Nếu chỉ thấy `docker-proxy` sau khi app đã chạy bằng Compose thì bình thường.

---

## 5. Chạy full app

# cpu

Lần đầu hoặc sau khi đổi Dockerfile/dependency:

```bash
docker compose --profile app up -d --build
```

Đường CPU/default không được yêu cầu GPU cho `ten_gateway`. Nếu từng lỡ chạy
GPU override trên máy không có NVIDIA driver, recreate gateway bằng config mặc
định để quay về `Runtime=runc` và `DeviceRequests=null`:

```bash
docker compose --profile app up -d --no-deps --force-recreate ten_gateway
docker inspect luve_ten_gateway --format 'Runtime={{.HostConfig.Runtime}} DeviceRequests={{json .HostConfig.DeviceRequests}}'
```

Nếu image đã build rồi:

```bash
docker compose --profile app up -d
```

Nếu vừa sửa root `.env`, recreate các app service:

```bash
docker compose --profile app up -d --force-recreate core_api ten_gateway grading_worker
```
# gpu 

cd ~/project/luve

GPU là opt-in, chỉ dùng khi `nvidia-smi` chạy được và host đã cài NVIDIA
Container Toolkit. Không dùng `docker-compose.gpu.local.yml` làm đường mặc
định; file đó chỉ dành cho thử nghiệm local và không commit.

```bash #chỉ chạy lần đầu 
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile app up -d --build
```
```bash 
docker compose -f docker-compose.yml -f docker-compose.gpu.yml logs -f ten_gateway
```
---

## 6. Kiểm tra container

```bash
docker compose ps
```

Kỳ vọng:

```text
postgres_db        healthy
redis_cache        healthy
rabbitmq_queue     healthy
rabbitmq_init      Exited (0)
core_api           healthy, port 8000 published
ten_gateway        healthy, port 8080 published
grading_worker     Up
```

Kiểm port publish:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'luve_core_api|luve_ten_gateway'
```

Kỳ vọng có:

```text
0.0.0.0:8000->8000/tcp
0.0.0.0:8080->8080/tcp
```

---

## 7. Kiểm readiness

```bash
curl -fsS http://localhost:8000/readyz; echo
curl -fsS http://localhost:8080/readyz; echo
curl -fsS http://localhost:8080/rtc/health; echo
```

Kỳ vọng:

```json
{"status":"ready","checks":{"database":"ok"}}
{"status":"ready","checks":{"gateway":"initialized"}}
{"status":"ok", ...}
```

---

## 8. Kiểm grading worker đang dùng Groq thật

```bash
docker compose exec grading_worker sh -lc '
printf "GRADING_PROVIDER=%s\n" "$GRADING_PROVIDER"
printf "LLM_PROVIDER=%s\n" "$LLM_PROVIDER"
printf "GRADING_FAKE_FALLBACK=%s\n" "$GRADING_FAKE_FALLBACK"
if [ -n "$GROQCLOUD_API_KEY" ]; then echo "GROQCLOUD_API_KEY=<set>"; else echo "GROQCLOUD_API_KEY=<missing>"; fi
'
```

Kỳ vọng:

```text
GRADING_PROVIDER=llm
LLM_PROVIDER=groq
GRADING_FAKE_FALLBACK=false
GROQCLOUD_API_KEY=<set>
```

Xem log worker:

```bash
docker compose logs --tail=100 grading_worker
```

Kỳ vọng:

```text
worker.ready queue=luve.session.completed prefetch_count=1
```

---

## 9. Mở app

Mở trên trình duyệt:

```text
http://localhost:8000
```

Nếu cần vào control center qua gateway:

```text
http://127.0.0.1:8080/control-center
```

Tạo/connect session, cho phép microphone, nói tiếng Anh đủ dài.

Ví dụ câu test:

```text
Today I practiced English with my virtual tutor. I talked about my daily routine, my study goals, and why I want to improve my speaking confidence.
```

Sau đó end/disconnect session.

---

## 10. Theo dõi logs khi demo

Mở terminal riêng:

```bash
cd ~/project/luve
docker compose logs -f grading_worker
```

Nếu muốn xem realtime/STT gateway:

```bash
docker compose logs -f ten_gateway
```

---

## 11. Kiểm kết quả grading

```bash
docker compose exec postgres_db psql -U dat_admin -d luve_database -c \
"SELECT session_id,status,provider,grader_version,overall_score,graded_at
 FROM grading_results
 ORDER BY graded_at DESC
 LIMIT 5;"
```

Nếu không có result, kiểm skip log:

```bash
docker compose exec postgres_db psql -U dat_admin -d luve_database -c \
"SELECT session_id,skipped_reason,student_word_count,skipped_at
 FROM grading_skip_log
 ORDER BY skipped_at DESC
 LIMIT 5;"
```

---

## 12. Kiểm RabbitMQ queue / DLQ

```bash
docker compose exec rabbitmq_queue rabbitmqctl list_queues name messages consumers | grep -E 'luve.session.completed|dlq'
```

Kỳ vọng:

```text
luve.session.completed      0   1
luve.session.completed.dlq  0   0
```

---

## 13. Tắt app

Tắt container nhưng giữ data volume:

```bash
docker compose down
```

Không dùng `-v` trừ khi cố ý xóa DB/RabbitMQ volumes.

---

# Ghi chú về GPU/CUDA

Hiện app chạy được bằng CPU fallback. Docker GPU runtime trên máy đã được cài và `docker run --gpus all ... nvidia-smi` đã pass.

Tuy nhiên, khi ép `ten_gateway` dùng GPU, STT CUDA hiện fail vì image thiếu CUDA runtime library:

```text
RuntimeError: Library libcublas.so.12 is not found or cannot be loaded
```

Vì vậy để demo ổn định, chạy CPU mode trước. Không dùng GPU override nếu chưa fix Docker image CUDA libs.

Nếu lỡ tạo file local GPU override:

```bash
docker-compose.gpu.local.yml
```

thì không dùng nó khi chạy demo thường. Chạy demo thường bằng:

```bash
docker compose --profile app up -d
```

Không chạy:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.local.yml ...
```

cho tới khi CUDA image được fix.
