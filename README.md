# LUVE Workspace - Monorepo Architecture

## 🌐 About Luve (English)

**Luve** is an open-source, real-time AI backend for speech and pronunciation
learning, organized as a Docker Compose monorepo with four cooperating parts:

- **core-api** (FastAPI) — session control, auth, and the realtime gateway.
- **media-server** — a TEN-Framework-compatible realtime pipeline
  (WebRTC → VAD → STT → LLM → TTS).
- **grading-worker** — asynchronous post-session scoring via an LLM provider (Groq).
- **infrastructure** — PostgreSQL, RabbitMQ, and Redis, wired through `docker-compose.yml`.

Services never import each other's code; they communicate over HTTP and RabbitMQ.

### Quick start

```bash
# 1. Provide configuration (copy each template, fill in real values locally)
cp .env.example .env
cp services/core-api/.env.example services/core-api/.env
cp services/grading-worker/.env.example services/grading-worker/.env

# 2. Start the whole backend
docker compose up -d

# 3. Check status / logs
docker compose ps
docker compose logs -f core-api
```

Real `.env` files are git-ignored and must never be committed; only the
`.env.example` templates are tracked.

### Project status (honest)

Luve is under active DevOps/reliability hardening and is **not** a finished
product:

- **Realtime STT** has so far been validated only in a constrained demo
  configuration (forced English, `small.en` model, second-pass disabled).
  Multilingual / auto-language STT is **not** production-validated.
- **Reliability work in progress:** a RabbitMQ dead-letter queue for poison
  messages is in place; a transactional session-outbox **foundation** (schema +
  helper) exists, but the outbox relay is **not yet wired into the runtime**, so
  event publishing is not yet exactly-once.
- Some hot-path improvements are still local work-in-progress and are not part
  of the published history yet.

See `docs/ai/PROJECT_STATE.md` for the detailed baseline and known limitations.

---

## 📋 Cấu trúc dự án

```
LUVE_Workspace/
├── .git/                        # Hệ thống quản lý cỗ máy thời gian
├── .gitignore                   # Chặn file rác và .env
├── fullpro.md                    # tổng quan dự án
├──   workflow.md			# chi tiết workflow
├── docker-compose.yml           # Bảng giao hưởng: chạy toàn bộ backend 1 lệnh
├── .rules              # Hiến pháp cho AI (Tuyệt đối quan trọng)
├── README.md                # Bản đồ chỉ dẫn dự án
├── TECH_STACK.md            # Đặc tả kỹ thuật (Stack)
├── FUNCTIONAL_GUIDE.md      # Danh mục chức năng & Độ phức tạp
├── clients/                     # FRONTEND
│   └── mobile-app/
│       ├── src/
│       └── package.json
│
├── services/                    # BACKEND (4 KHU VỰC XỬ LÝ)
│   ├── core-api/                # Trạm kiểm soát chính
│   │   ├── src/
│   │   ├── models/
│   │   ├── Dockerfile
│   │   ├── .env.example
│   │   └── package.json
│   │
│   ├── media-server/            # Nhà máy TEN Framework (WebRTC, STT, STS)
│   │   ├── extensions/
│   │   ├── property.json
│   │   └── Dockerfile
│   │
│   └── grading-worker/          # Hậu kiểm & LLM (Python + Redis + OpenAI)
│       ├── src/
│       ├── Dockerfile
│       └── requirements.txt
│
└── infrastructure/              # HẠ TẦNG & LƯU TRỮ
    ├── db-init/                 # Script SQL khởi tạo DB
    └── config/                  # Config Redis, RabbitMQ, v.v.
```

# 🏛️ Kiến Trúc Hệ Thống L.U.V.E (Architecture Diagram)

Dưới đây là sơ đồ luồng dữ liệu thời gian thực (Real-time Data Flow) của dự án, được chia thành 5 khu vực độc lập để tối ưu hóa hiệu năng và khả năng mở rộng:

![Sơ đồ kiến trúc L.U.V.E](./docs/luve-architecture.drawio.svg)

*Sơ đồ được thiết kế bởi Đạt - Master Architect.*

## 🚀 Bắt đầu nhanh

### 1. Chạy toàn bộ backend với Docker Compose

```bash
docker compose up -d
```

### 2. Kiểm tra trạng thái các service

```bash
docker compose ps
```

### 3. Xem log của một service 

```bash
docker compose logs -f core-api # Xem log trạm kiểm soát chính
```

### 4. Dừng toàn bộ hệ thống

```bash
docker compose down
```

## 5. Xem log nhà máy xử lý âm thanh

```bash
docker compose logs -f media-server
```

### 6. Xem log hội đồng giám khảo chấm điểm

```bash
docker compose logs -f grading-worker
```

## ⚙️ Cấu hình môi trường

Mỗi service có file `.env.example`. Để chạy:

```bash
# Core API
cd services/core-api
cp .env.example .env
# Điền thông tin vào .env (không commit file này!)

# Grading Worker
cd services/grading-worker
cp .env.example .env
# Điền thông tin vào .env
```

## 📝 3 Quy tắc Sắt Đá

### ✋ Quy tắc 1: Cấm "Vượt rào" (No Cross-importing)

**KHÔNG ĐƯỢC phép**: `services/core-api/` import code từ `services/grading-worker/`

**Lý do**: Chúng sẽ chạy trên 2 máy chủ khác nhau!

**Cách giao tiếp đúng**: HTTP hoặc RabbitMQ (qua mạng), không import code trực tiếp.

### 🐳 Quy tắc 2: Sự kỳ diệu của docker-compose.yml

- Không cần tạo thư mục code cho Database, Redis, RabbitMQ
- File `docker-compose.yml` tự động tải images có sẵn từ Docker Hub
- 1 lệnh `docker compose up -d` = toàn bộ hệ thống chạy

### 🔐 Quy tắc 3: Bảo mật file .env

- ✅ **ĐƯỢC commit**: `.env.example` (file mẫu rỗng)
- ❌ **KHÔNG commit**: `.env` (chứa mật khẩu thật)
- File `.env` đã được chặn bởi `.gitignore`

Nội dung `.env.example`:

```
DATABASE_URL=
OPENAI_API_KEY=
RABBITMQ_HOST=
REDIS_URL=
```

## 🔗 Links hữu ích

- PostgreSQL: `postgres://postgres:postgres@localhost:5432/luve_db`
- Redis: `redis://localhost:6379`
- RabbitMQ Management: `http://localhost:15672` (user: guest, pass: guest)

---

**Created**: 2026-04-09 | **Maintained by**: DevOps Team
