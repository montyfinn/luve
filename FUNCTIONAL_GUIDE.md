### File `FUNCTIONAL_GUIDE.md` (Chỉ dẫn chức năng)

Dùng để đối chiếu khi code các tính năng phức tạp.

* **Core:** Real-time Voice Engine, Session Handshake, Async Grading.
* **Complex:** Hybrid EOS Logic (**$Latency = VAD_{timeout} + STT + LLM + TTS$**), Word-level Timestamping.
* **X-Factors:** AI Backchanneling ("Uhm", "I see"), Auto-leveling logic.

## 🏆 L.U.V.E PROJECT: THE MASTER INVENTORY (100% COMPLETE)

## 1. PHÂN CẤP CHỨC NĂNG (FEATURE HIERARCHY)

### A. Chức năng Cốt lõi (Core - Phải chạy bằng mọi giá)

1. **Real-time Voice Engine:** Thu âm người dùng **$\rightarrow$** STT **$\rightarrow$** LLM **$\rightarrow$** TTS **$\rightarrow$** Phát ra loa với độ trễ **$< 2s$**.
2. **Session Handshake:** Quy trình "Bắt tay" giữa App, Core API và Media Server để mở một phiên học an toàn.
3. **Async Grading:** Worker bóc tách kịch bản từ Redis, gọi AI chấm điểm và lưu vào Postgres sau khi cúp máy.
4. **Auth & Profile:** Đăng ký/Đăng nhập và quản lý Level người dùng.

### B. Chức năng Phức tạp (Complex - Cần tập trung cao độ)

1. **Hybrid EOS Logic:** Xử lý sự kiện "Nút bấm chủ động" cắt ngang luồng VAD tự động mà không làm treo luồng âm thanh.
2. **Word-level Timestamping:** Lưu chính xác từng miligiây của từng từ nói ra để phát hiện sự ngập ngừng (hesitation).
3. **Token & Quota Guard:** Hệ thống tính toán và trừ số phút/token ngay trong lúc đang nói để ngăn chặn việc dùng quá hạn mức.

---

## 2. NHỮNG ĐIỂM DỄ GÂY NHẦM LẪN (LOGIC TRAPS)

| **Điểm dễ nhầm**  | **Thực tế cần làm**                                                                  | **Tại sao?**                                                            |
| --------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **VAD (Cắt đoạn)** | Cần làm ở cả Client (App) và Server (TEN).                                                | Client cắt ồn để giảm băng thông, Server cắt đoạn để nạp vào AI. |
| **Room vs Session**   | Luôn dùng chữ**Session**trong tài liệu.                                             | Room nghe giống chat nhiều người, Session là phiên học 1-1 riêng tư.  |
| **Transcript**        | Có 2 loại:**Live**(phụ đề xem ngay) và**Final**(bản đã chỉnh sửa lỗi). | Live dùng Web Socket, Final dùng Worker xử lý chậm sau khi kết thúc.    |
| **Múi giờ**         | Luôn dùng `Asia/Ho_Chi_Minh`cho mọi DB/Log.                                               | Tránh việc lịch sử học tập bị nhảy sang ngày hôm sau.                |

---

## 3. CHIẾN LƯỢC TRIỂN KHAI (IMPLEMENTATION STRATEGY)

Để không bị "ngợp", chúng ta sẽ đi theo 3 đợt tấn công:

### Đợt 1: "Xây móng & Dựng rào" (The Skeleton)

* **Mục tiêu:** Chạy được Docker, kết nối được Core API vào Database.
* **Trọng tâm:** Auth Service (Register/Login).
* **Model:**  **GPT-5.3-Codex (1x)** .

### Đợt 2: "Tiếng nói & Phản xạ" (The Soul)

* **Mục tiêu:** WebRTC chạy được, AI nghe và trả lời được "Hello".
* **Trọng tâm:** Khu vực 3 (TEN Framework) và sự kiện Manual EOS (Nút bấm).
* **Model:** **GPT-5.3-Codex (1x)** kết hợp tra cứu tài liệu bằng  **GPT-5 mini (0x)** .

### Đợt 3: "Trí tuệ & Điểm số" (The Brain)

* **Mục tiêu:** Chấm được điểm, hiện được lỗi sai trên App.
* **Trọng tâm:** Khu vực 4 (Worker) và Logic phân tích của LLM.
* **Model:**  **GPT-5.3-Codex (1x)** .

### 🛡️ KHU VỰC 1 & 2: BỘ NÃO ĐIỀU PHỐI (Core API & Auth)

* **Hệ thống Định danh (Auth):**
  * Đăng ký/Đăng nhập bảo mật (Bcrypt hashing).
  * Quản lý phiên bằng JWT (JSON Web Token).
* **Hồ sơ Năng lực (Profile):**
  * Lưu trình độ (`fluency_level`) và "Ví thời gian" (`quota_minutes`).
* **Quản lý Thư viện (Lesson Manager):**
  * Duyệt/Lọc bài học theo chủ đề và độ khó (`target_level`).
* **Điều phối Phiên (Session Orchestration):**
  * Cấp phát Room Token cho WebRTC.
  * Nạp cấu hình VAD và System Prompt vào Media Backend.
* **Chốt chặn Bảo mật (Safety):**
  * **Rate Limiting:** Chặn spam request/nút bấm (Dùng Redis).
  * **Session Heartbeat:** Tự động đóng phiên nếu App mất mạng đột ngột để cứu tài nguyên.

### 🎙️ KHU VỰC 3: TRẢI NGHIỆM ĐÀM THOẠI (Media Backend - TEN)

* **Truyền tải Full-duplex:** Nói và nghe đồng thời qua WebRTC (UDP).
* **Cảm biến giọng nói (Dynamic VAD):** Tự động ngắt đoạn theo sự im lặng (Beginner chậm, Advanced nhanh).
* **Nút bấm Chốt câu (Manual EOS):** Cơ chế "Hybrid" để ngắt đoạn tức thì, giảm Latency.
* **Âm thanh đệm (Backchanneling):** AI phát "Uhm", "I see" khi đang suy nghĩ.
* **Transcript Real-time:** Hiện phụ đề ngay lập tức qua WebSocket.
* **Tối ưu phản xạ (Streaming TTS):** Phát âm thanh AI theo dạng "cuốn chiếu" (Chunk-based) ngay khi có dữ liệu đầu tiên (~500ms).

### 🧠 KHU VỰC 4: HỘI ĐỒNG GIÁM KHẢO (Worker & AI Grading)

* **Hàng đợi (Queue):** RabbitMQ tiếp nhận Session ID để xử lý bất đồng bộ.
* **Chấm điểm đa tiêu chí:** Fluency (Trôi chảy), Grammar (Ngữ pháp), Vocabulary (Từ vựng).
* **Phân tích chi tiết:** Chỉ rõ lỗi sai, tại sao sai và đưa ra gợi ý sửa đổi (`detailed_corrections`).
* **Quản trị tài chính (Token Tracking):** Ghi nhận tổng lượng Token đã tiêu tốn vào bảng `SESSIONS`.
* **Chốt chặn dữ liệu (Schema Guard):** Dùng Pydantic để ép AI trả về đúng cấu trúc JSON, tránh làm sập Worker.

### 🗄️ KHU VỰC 5: LƯU TRỮ & HẬU CẦN (Database & Persistence)

* **Sao lưu hộp đen (Raw Backup):** Đẩy kịch bản thô từ Redis xuống `raw_backup_json` trong Postgres.
* **Bảng điểm & Lịch sử:** Lưu trữ mọi phiên học để vẽ biểu đồ tiến độ.
* **Cơ chế Tự động (Auto-leveling):** Đề xuất tăng Level nếu điểm cao liên tục trong 5 phiên.
* **Quyền riêng tư (Soft Delete):** Đánh dấu `deleted_at` thay vì xóa vĩnh viễn dữ liệu.
* **Phục hồi (Session Recovery):** Lưu trạng thái vào cột `metadata` để người dùng tiếp tục bài học nếu rớt mạng.

### 💎 CÁC TÍNH NĂNG "VỊ THẦN" (X-FACTORS)

1. **Hybrid EOS:** Kết hợp VAD tự động + Nút bấm thủ công.
2. **Word-level Timestamps:** Bắt lỗi ngập ngừng chính xác đến từng mili giây.
3. **Prompt Injection Protection:** Ngăn chặn người dùng "bẻ lái" AI.
4. **Timezone Sync:** Đồng bộ chuẩn `Asia/Ho_Chi_Minh` trên toàn hệ thống.

---

## 🛠️ DANH SÁCH FILE CẦN KIỂM TRA NGAY (CHECKLIST)

| **Loại file**  | **Đường dẫn dự kiến**      | **Trạng thái**                        |
| --------------------- | -------------------------------------- | --------------------------------------------- |
| **Hạ tầng**   | `docker-compose.yml`                 | Đã có TZ, Postgres, Redis, RabbitMQ.       |
| **Dữ liệu**   | `infrastructure/db-init/01-init.sql` | Đã có Soft Delete, Metadata, Manual_count. |
| **Quy tắc AI** | `.cursorrules`/`.clinerules`       | Đã có Bản Hiến Pháp LUVE.               |
| **Đặc tả**   | `FUNCTIONAL_GUIDE.md`                | Bản đồ 5 khu vực và độ phức tạp.     |
| **Kỹ thuật**  | `TECH_STACK.md`                      | FastAPI, SQLAlchemy, Pika, WebRTC.            |
