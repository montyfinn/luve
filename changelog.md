
# 📜 CHANGELOG - L.U.V.E Ecosystem

## [2026-04-11] - Phase 2: Core API & Auth Foundation (COMPLETED)

### 🚀 Performance & Scale (The "Monty Finn" Special)

* **Multi-processing Engine** : Triển khai `Gunicorn` với `UvicornWorker`, kích hoạt cơ chế đa nhân ( **4 Workers** ).
* **CPU Optimization** : Giải phóng xiềng xích của Python GIL, cho phép hệ thống tận dụng tối đa sức mạnh của cỗ máy 16 nhân.
* **Stress Tested** : Vượt qua bài kiểm tra áp lực bằng `Apache Benchmark (ab)` với 500 requests đồng thời. Xác nhận khả năng phục hồi tài nguyên (CPU/RAM) ngay lập tức sau khi xử lý xong tải nặng (Bcrypt hashing).

### 🏗️ Infrastructure & DevOps

* **Docker Orchestration** : Hoàn thiện `docker-compose.yml` cô lập 3 khu vực chiến lược:
* **PostgreSQL 15-alpine** : Database chính thức cho User & Core Data.
* **Redis 7-alpine** : Caching và Rate Limiting cho tương lai.
* **RabbitMQ 3-management** : Điều phối hàng đợi tác vụ bất đồng bộ (Khu vực 4).
* **Persistence Strategy** : Cấu hình Docker Volumes cho dữ liệu bền vững.
* **Environment Management** : Chuẩn hóa hệ thống `.env`, tách biệt cấu hình và mã nguồn.

### 🔐 Security & Auth Logic

* **Hashing Engine** : Tích hợp `Bcrypt` với cơ chế bảo mật cao cấp (tự động điều chỉnh rounds).
* **Bearer Authentication** : Triển khai JWT (JSON Web Token) dùng thuật toán `HS256`.
* **Identity Provider** :
* `POST /api/v1/auth/register`: Đăng ký người dùng với UUID định danh duy nhất.
* `POST /api/v1/auth/login`: Xác thực và cấp phát Access Token.
* `GET /api/v1/auth/me`: Middleware bảo mật trích xuất thông tin người dùng từ Token.

### 🛠️ Backend Architecture

* **SQLAlchemy 2.0** : Sử dụng kiến trúc `Mapped` và `mapped_column` hiện đại nhất.
* **Async Engine** : Toàn bộ luồng dữ liệu là bất đồng bộ (`async/await`), tối ưu hóa I/O.
* **Dependency Injection** : Hệ thống `get_db` và `get_current_user` linh hoạt, dễ dàng mở rộng.
* **Pydantic V2** : Validate dữ liệu đầu vào/đầu ra nghiêm ngặt bằng Schemas.

### 🐞 Fixed (Vết nứt đã vá)

* **Database Initialization** : Sửa lỗi lệch mật khẩu Postgres khi khởi tạo Container lần đầu (Xử lý qua `down -v`).
* **Parsing Bug** : Khắc phục lỗi SQLAlchemy không đọc được URL chứa ký tự đặc biệt (`!`) và lỗi lặp key `DATABASE_URL`.
* **Worker Conflict** : Sửa lỗi `ModuleNotFoundError` khi chạy Gunicorn trong môi trường Virtual Environment (`venv`).

---

### 🛰️ Upcoming: Phase 3 - Media Server & AI Real-time

* **WebSocket Gateway** : Xây dựng đường ống truyền tải âm thanh nhị phân (Binary Streaming).
* **STT Engine** : Tích hợp Whisper/Faster-Whisper để chuyển đổi giọng nói thời gian thực.
* **Async Worker (Area 4)** : Triển khai Celery để chấm điểm và hậu xử lý kết quả học tập.
* **Frontend Integration** : Kết nối giao diện người dùng để thực hiện cuộc gọi AI đầu tiên.
