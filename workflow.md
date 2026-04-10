Sự thật là: Trong kiến trúc hiện đại (Microservices),  **không có một cục nào duy nhất gọi là "Backend"** . Backend của L.U.V.E được chẻ ra làm **3 Khu Vực Độc Lập** (3 cụm Server khác nhau) để chia để trị. Thằng nào lo việc nấy, thằng này sập không làm chết thằng kia.

Dưới đây là Bản Đồ Kiến Trúc Chi Tiết (Architecture Blueprint) của toàn bộ hệ thống L.U.V.E. Hãy nhìn nó như một dây chuyền nhà máy:

### KHU VỰC 1: CLIENT (Giao diện người dùng)

* **Nằm ở đâu:** App Mobile (React Native/Flutter) hoặc Web (ReactJS/Vue).
* **Nhiệm vụ:**
  * Vẽ UI/UX, nút bấm, hiển thị chữ.
  * Chạy **VAD (Van cảm biến)** để lọc tiếng ồn.
  * Mở kết nối WebRTC (gửi/nhận âm thanh).
  * Mở kết nối WebSocket (nhận phụ đề, gửi lệnh điều khiển).

---

### KHU VỰC 2: CORE API BACKEND (Trạm Điều Hành Chính)

*Đây chính là cái "Backend" truyền thống mà bạn hay nghĩ tới.*

* **Viết bằng:** Node.js, Python (FastAPI/Django), hoặc Go.
* **Nhiệm vụ:** * Cung cấp **REST API (HTTP)** cho App tĩnh.
  * Quản lý tài khoản Đạt: Đăng nhập, cấp Token.
  * Quản lý Level: Tra cứu xem Đạt đang ở trình độ nào.
  * Phục vụ Giao diện: Truy xuất lịch sử học tập, bảng điểm từ Database để trả về cho App hiển thị.
* **Đặc điểm:** Chỉ xử lý text và logic cơ bản, không bao giờ đụng vào âm thanh.

---

### KHU VỰC 3: MEDIA BACKEND (Nhà Máy Thời Gian Thực - Nơi chứa TEN)

*Tuyệt đối tách biệt khu vực này với Core API. Đây là nơi ngốn CPU nhất.*

* **Nằm ở đâu:** Các máy chủ chuyên dụng cho Audio/Video.
* **Thành phần lõi:** **TEN Framework** (kết hợp với WebRTC Media Server).
* **Nhiệm vụ:**
  * "Hứng" luồng WebRTC từ Client.
  * Bơm âm thanh vào Node STT (bắt phụ đề).
  * Bơm âm thanh vào Node STS/AI (trả lời).
  * Đẩy text nháp/chốt sổ qua WebSocket.
  * Ghi chú tọa độ thời gian và append liên tục vào  **REDIS (RAM)** .
* **Đặc điểm:** Chạy hỏa tốc, không được phép có độ trễ. Phiên học kết thúc là bộ phận này rửa tay gác kiếm.

---

### KHU VỰC 4: ASYNC WORKER BACKEND (Khu Vực Hậu Kiểm & Cứu Hộ)

*Khu vực cày cuốc âm thầm phía sau, không cần Real-time.*

* **Nằm ở đâu:** Các máy chủ chạy ngầm (Background Jobs).
* **Thành phần:**
  * **Message Queue (Hàng đợi):** RabbitMQ hoặc Kafka.
  * **Worker Nodes:** Các đoạn code Python/Node.js chạy độc lập.
* **Nhiệm vụ:**
  * Đợi TEN báo "Học xong rồi", Worker sẽ moi cục JSON kịch bản từ Redis ra.
  * Lưu ngay một bản **Backup Thô** xuống Database.
  * Cầm cục data thô đó đi gõ cửa API của LLM (OpenAI/Google) nhờ chấm điểm.
  * Lấy điểm số về, ghi đè vào Database, báo hoàn thành.

---

### KHU VỰC 5: STORAGE (Kho Chứa Dữ Liệu)

Gồm 2 loại kho chứa tách biệt hoàn toàn về mục đích:

1. **REDIS (RAM):** Kho tạm thời siêu tốc. Chỉ lưu trữ mảng JSON kịch bản (Text + Metadata)  *trong lúc cuộc gọi đang diễn ra* . Cuộc gọi kết thúc, đem data đi chỗ khác rồi xóa sạch.
2. **DATABASE CHÍNH (PostgreSQL / MongoDB):** Kho lưu trữ vĩnh viễn (Ổ cứng). Nơi chứa User Profile, Level của Đạt, Bản Backup Thô, và Bảng điểm cuối cùng.

---

### VÍ DỤ CHUỖI VẬN HÀNH (Chỉ đường cho bạn dễ code):

Hãy nhìn cách các cục này đá bóng cho nhau trong 1 vòng đời:

1. **Khởi động:** App gọi HTTP lên **[Core API Backend]** xin phép học. Core API check DB, cấp thẻ qua cổng.
2. **Bắt tay:** App mở WebSocket kết nối vào  **[Media Backend - TEN]** , gửi thông số VAD 4 giây (nhờ Core API báo).
3. **Vào việc (Real-time):** App bơm âm thanh qua WebRTC. **[TEN]** xử lý, gọi STT/STS, trả âm thanh, nhét chữ liên tục vào  **[Redis]** .
4. **Sự cố giữa chừng:** Đạt bấm Tạm Dừng. App bắn WebSocket. **[TEN]** nhận lệnh, cho STT/STS đi ngủ, cài đồng hồ hẹn giờ cho file trên  **[Redis]** .
5. **Kết thúc:** Đạt bấm End. **[TEN]** báo cáo xong việc. **[Worker]** nhảy vào, lôi data từ **[Redis]** ra, cất bản thô vào  **[Database]** , rồi ném vô **[RabbitMQ]** chờ LLM chấm điểm.
6. **Xem thành quả:** Hôm sau Đạt mở App. App gọi HTTP lên  **[Core API Backend]** . Core API móc từ **[Database]** ra bảng điểm đẹp đẽ, trả về cho Đạt xem.

**Tổng kết:** Khi bạn chia hệ thống L.U.V.E ra thành 5 cục rõ ràng như thế này, nếu ngày mai lượng truy cập tăng gấp 100 lần (do người dùng vào xem điểm nhiều), bạn chỉ cần bỏ tiền thuê thêm máy chủ cho cụm  **Core API** , còn cụm **TEN** không hề bị ảnh hưởng. Đây chính là cách thiết kế hệ thống "như một vị thần" — rõ ràng, tối ưu chi phí, và bất khả chiến bại trước tải trọng đột ngột! Mọi thứ đã đủ sáng tỏ để bạn bắt tay vào vẽ sơ đồ UML và thiết kế Database chưa?
