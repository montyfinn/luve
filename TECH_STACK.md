1. **Ngôn ngữ & Runtime (Languages)
   Core API (Khu vực 2): Python 3.11+ (FastAPI).**

Lý do: Tốc độ phát triển cực nhanh, hỗ trợ Asynchronous (Async/Await) cực tốt cho hàng ngàn request cùng lúc và tương thích tuyệt đối với các thư viện AI.

Worker (Khu vực 4): Python 3.11+.

Lý do: Đồng bộ với Core API để dùng chung các Model Database và dễ dàng gọi các thư viện xử lý ngôn ngữ (LLM SDKs).

Media Gateway (Khu vực 3): TEN Framework (C++ / Go / Python).

Lý do: Đây là framework chuyên dụng để xây dựng Real-time AI với độ trễ cực thấp.

2. **Cơ sở dữ liệu & Trạng thái (Storage)
   RDBMS (Chính): PostgreSQL 15+.**

ORM: SQLAlchemy 2.0 + Alembic (để quản lý Migration/thay đổi DB).

In-Memory (Nháp): Redis 7.0.

Thư viện: redis-py. Dùng để lưu Transcript thời gian thực trước khi đẩy xuống Postgres.

3. **Giao tiếp & Mạng (Communication)
   Internal Messaging: RabbitMQ (AMQP Protocol).**

Thư viện: Pika hoặc FastAPI-Users.

Real-time Audio: WebRTC (Truyền âm thanh UDP để không bị giật lag).

Metadata & Subtitles: WebSockets (Truyền phụ đề và lệnh nút bấm).

API Standard: RESTful API (Định dạng JSON:API chuẩn).

4. **Bảo mật & Xác thực (Security)
   Auth: JWT (JSON Web Token) với thuật toán HS256.**

Password Hashing: Argon2 hoặc Bcrypt (đã cấu hình trong SQL).

Rate Limiting: Dùng Redis Fixed Window để chặn spam request.

5. **Môi trường & Triển khai (DevOps)
   Containerization: Docker & Docker Compose.**

Múi giờ: Asia/Ho_Chi_Minh (Toàn bộ container).

AI CLI: Cursor/Cline với model GPT-5.3-Codex là "đội trưởng" điều phối code.

📂 Sơ đồ kết nối kỹ thuật (Technical Wiring)
