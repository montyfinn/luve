# LUVE Workspace - Monorepo Architecture

## 📋 Cấu trúc dự án

```
LUVE_Workspace/
├── .git/                        # Hệ thống quản lý cỗ máy thời gian
├── .gitignore                   # Chặn file rác và .env
├── README.md                    # Bản hướng dẫn này
├── docker-compose.yml           # Bảng giao hưởng: chạy toàn bộ backend 1 lệnh
│
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
docker compose logs -f core-api
```

### 4. Dừng toàn bộ hệ thống

```bash
docker compose down
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
