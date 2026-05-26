# Chương 1: Giới Thiệu

---

## 1.1 Lý Do Chọn Đề Tài

Kỹ năng nói tiếng Anh ngày càng trở nên quan trọng trong bối cảnh toàn cầu hóa và hội nhập quốc tế. Đối với sinh viên và người đi làm tại Việt Nam, khả năng giao tiếp bằng tiếng Anh là một yếu tố cạnh tranh đáng kể trên thị trường lao động. Tuy nhiên, việc luyện tập kỹ năng nói gặp nhiều rào cản thực tế: thiếu đối tác luyện tập, chi phí giáo viên bản ngữ cao, và quan trọng nhất là thiếu phản hồi tức thì trong quá trình luyện tập.

Các ứng dụng học tiếng Anh hiện tại phần lớn tập trung vào từ vựng và ngữ pháp theo dạng bài trắc nghiệm hoặc thẻ nhớ. Số ít ứng dụng hỗ trợ luyện nói chủ yếu hoạt động theo cơ chế ghi âm — phát lại — chấm điểm phát âm đơn lẻ, không tạo được trải nghiệm hội thoại tự nhiên theo thời gian thực. Người học không có cơ hội phản ứng với phản hồi của AI theo dòng hội thoại liên tục như khi giao tiếp với người thật.

Sự phát triển của ba công nghệ trong những năm gần đây mở ra hướng giải quyết mới:

- **WebRTC** (Web Real-Time Communication): cho phép truyền audio/video trực tiếp giữa trình duyệt và server với độ trễ thấp, không cần plugin.
- **Mô hình nhận dạng giọng nói tự động (ASR/STT)**: đặc biệt là Whisper của OpenAI, đạt độ chính xác cao cho tiếng Anh và có thể chạy cục bộ trên GPU phổ thông.
- **Mô hình ngôn ngữ lớn (LLM)**: có khả năng sinh phản hồi hội thoại tự nhiên và đánh giá chất lượng ngôn ngữ theo nhiều chiều.

Sự kết hợp của ba công nghệ này tạo ra khả năng xây dựng một hệ thống luyện nói tiếng Anh theo thời gian thực — nơi người dùng nói vào microphone, hệ thống nhận dạng giọng nói, sinh phản hồi AI và phát lại âm thanh, tất cả trong vòng vài giây. Đề tài này được chọn để khám phá tính khả thi kỹ thuật của hướng tiếp cận đó trong phạm vi môi trường phát triển cục bộ.

---

## 1.2 Vấn Đề Nghiên Cứu

Đề tài đặt ra ba câu hỏi nghiên cứu chính:

**Câu hỏi 1 — Kỹ thuật realtime:**
Làm thế nào để xây dựng một luồng hội thoại tiếng Anh thời gian thực hoàn chỉnh (WebRTC → STT → LLM → TTS) hoạt động ổn định trên phần cứng phát triển thông thường?

**Câu hỏi 2 — Đánh giá tự động:**
Làm thế nào để tự động đánh giá chất lượng ngôn ngữ (phát âm, từ vựng, ngữ pháp, mạch lạc) của người học mà không làm gián đoạn trải nghiệm thời gian thực?

**Câu hỏi 3 — Mở rộng đa người dùng:**
Kiến trúc hệ thống cần được thiết kế như thế nào để hỗ trợ nhiều người dùng luyện tập đồng thời mà không can thiệp lẫn nhau, trong giới hạn phần cứng phát triển cục bộ?

Ba câu hỏi này tương ứng với ba thách thức kỹ thuật cốt lõi mà hệ thống LUVE (*Language User Voice Evaluator*) được thiết kế để giải quyết.

---

## 1.3 Mục Tiêu Đề Tài

### Mục tiêu tổng quát

Xây dựng và kiểm thử một hệ thống prototype hỗ trợ luyện nói tiếng Anh theo thời gian thực, tích hợp WebRTC, nhận dạng giọng nói tự động, mô hình ngôn ngữ lớn, và pipeline chấm điểm bất đồng bộ.

### Mục tiêu cụ thể

| # | Mục tiêu | Tiêu chí hoàn thành |
|---|----------|---------------------|
| MT-1 | Xây dựng gateway WebRTC tùy chỉnh xử lý luồng audio thời gian thực | HTTP offer 200, VAD/STT/LLM/TTS hoạt động đầu cuối |
| MT-2 | Triển khai cơ chế giới hạn phiên và trả lỗi 503 rõ ràng | `TEN_SINGLE_SESSION_CAPACITY = 1`, HTTP 503 khi vượt giới hạn |
| MT-3 | Thiết kế kiến trúc scale-out đa người dùng không cần thay đổi code | N tiến trình trên N cổng, mỗi người dùng một tiến trình độc lập |
| MT-4 | Xây dựng pipeline chấm điểm bất đồng bộ qua message queue | Worker RabbitMQ, eligibility gate, LLM grader, kết quả lưu DB |
| MT-5 | Kiểm thử scale-out và thu thập bằng chứng định lượng | Smoke test 2, 4, 6 người dùng đồng thời với PASS tất cả tiêu chí |
| MT-6 | Ghi nhận trung thực các giới hạn phần cứng và phạm vi kiểm thử | Báo cáo VRAM, latency, suppress rate theo mức tải |

---

## 1.4 Phạm Vi Đề Tài

### Trong phạm vi

- Hệ thống hoạt động trên **một máy phát triển cục bộ** duy nhất (Ubuntu Linux, GPU NVIDIA RTX 3050 Ti, 4 GiB VRAM).
- Gateway WebRTC được xây dựng bằng thư viện **aiortc** thuần Python. Tên file cấu hình (`graph.json`, `manifest.json`, `property.json`) lấy cảm hứng từ định dạng TEN framework, nhưng TEN native SDK không được cài đặt — gateway là một triển khai aiortc hoàn toàn tùy chỉnh.
- Kiểm thử đa người dùng sử dụng công cụ stress tự động (`realtime_stress.py`) trên cùng một máy, không phải người dùng thật qua trình duyệt công khai.
- Pipeline chấm điểm sử dụng LLM bên ngoài (Groq API) hoặc local model; kết quả lưu vào PostgreSQL.
- Bằng chứng scale-out được thu thập ở mức 2, 4, và 6 người dùng đồng thời.

### Ngoài phạm vi

- **Triển khai production**: hệ thống không được thiết kế hay kiểm thử cho môi trường nhiều máy chủ, load balancer, hay lưu lượng công khai.
- **Trình duyệt WebRTC thực**: quá trình ICE negotiation và đường truyền mạng thực của trình duyệt không được kiểm thử; các phiên được tạo bởi script tự động.
- **Hiệu chuẩn điểm số giáo dục**: độ chính xác của kết quả chấm điểm LLM theo khung năng lực ngôn ngữ (CEFR, IELTS,...) không nằm trong phạm vi đánh giá.
- **Giao diện người dùng hoàn chỉnh**: frontend phục vụ mục đích điều khiển và demo, không phải sản phẩm thương mại.
- **Kịch bản 8 người dùng đồng thời**: không được kiểm thử có chủ đích do rủi ro CUDA OOM vượt mức an toàn trên phần cứng phát triển.

---

## 1.5 Phương Pháp Thực Hiện

Đề tài áp dụng phương pháp thiết kế — triển khai — kiểm thử lặp theo từng tầng của hệ thống:

### Giai đoạn 1 — Thiết kế kiến trúc
- Phân tích yêu cầu kỹ thuật cho luồng realtime và luồng chấm điểm.
- Lựa chọn công nghệ: aiortc (WebRTC), Faster-Whisper (STT), RabbitMQ (message queue), FastAPI (Core API), PostgreSQL (dữ liệu).
- Thiết kế kiến trúc phân lớp 4 tầng: giao tiếp → nghiệp vụ → nhắn tin → lưu trữ.

### Giai đoạn 2 — Triển khai theo patch
- Xây dựng các thành phần theo đơn vị nhỏ, có thể kiểm thử độc lập.
- Mỗi patch được đặt tên và gắn với commit git cụ thể để truy vết.
- Unit test với mock database được viết song song với code production.

### Giai đoạn 3 — Kiểm thử theo lớp
- **Lớp 1 — Kiểm thử tự động an toàn**: `py_compile`, `pytest` với database mock. Có thể chạy bất kỳ lúc nào, không cần dịch vụ thật.
- **Lớp 2 — Kiểm thử smoke live**: `realtime_stress.py` nhắm vào các tiến trình gateway đang chạy. Yêu cầu phê duyệt từng lần, cờ `--i-understand-this-is-live`.

### Giai đoạn 4 — Thu thập và phân tích bằng chứng
- Sinh báo cáo tự động theo dấu thời gian vào `test-results/`.
- Phân tích VRAM, latency (dc_ms, stt_final_ms), suppress rate theo mức tải.
- Ghi nhận dấu hiệu suy giảm và giới hạn phần cứng một cách trung thực.

---

## 1.6 Đóng Góp Của Đề Tài

Đề tài đóng góp ba nội dung kỹ thuật chính:

### Đóng góp 1 — Gateway WebRTC tùy chỉnh tích hợp AI

Hệ thống LUVE xây dựng một gateway WebRTC hoàn toàn bằng Python (aiortc), tích hợp toàn bộ chuỗi xử lý giọng nói: VAD phát hiện lượt nói → Whisper STT chuyển đổi giọng nói thành văn bản → LLM sinh phản hồi hội thoại → TTS phát âm thanh. Cơ chế giới hạn cứng một phiên trên mỗi tiến trình (`TEN_SINGLE_SESSION_CAPACITY = 1`) đảm bảo cô lập tài nguyên và phản hồi lỗi rõ ràng (HTTP 503) khi quá tải.

### Đóng góp 2 — Pipeline chấm điểm bất đồng bộ

Hệ thống tách biệt hoàn toàn luồng chấm điểm khỏi luồng thời gian thực qua RabbitMQ. Một grading worker tiêu thụ hàng đợi `luve.session.completed`, kiểm tra điều kiện đủ tư cách chấm điểm qua bốn mã lý do (`no_raw_backup`, `invalid_raw_backup`, `no_user_turns`, `insufficient_words`), và ghi kết quả vào cơ sở dữ liệu PostgreSQL. Cơ chế `ON CONFLICT DO UPDATE` đảm bảo idempotency — worker có thể xử lý lại cùng một phiên mà không tạo dữ liệu trùng lặp.

### Đóng góp 3 — Bằng chứng scale-out đa người dùng có kiểm soát

Đề tài trình bày bằng chứng định lượng về khả năng phục vụ đồng thời 2, 4, và 6 người dùng thông qua cơ chế chạy N tiến trình gateway độc lập trên N cổng. Tất cả ba mức tải đều đạt PASS theo các tiêu chí chấp nhận đã định nghĩa (HTTP offer 200, `failures=[]`, `active_sessions=0` sau cleanup, không CUDA OOM). Dữ liệu VRAM, latency và suppress rate theo mức tải được ghi lại trung thực, bao gồm cả các dấu hiệu suy giảm ở 6-user.

---

## 1.7 Cấu Trúc Khóa Luận

Khóa luận được tổ chức thành năm chương:

**Chương 1 — Giới thiệu** (chương này): Trình bày lý do chọn đề tài, vấn đề nghiên cứu, mục tiêu, phạm vi, phương pháp và đóng góp của đề tài.

**Chương 2 — Cơ sở lý thuyết**: Trình bày nền tảng lý thuyết và kỹ thuật liên quan, bao gồm WebRTC và aiortc, các mô hình nhận dạng giọng nói (Whisper), mô hình ngôn ngữ lớn (LLM), text-to-speech, kiến trúc message queue (RabbitMQ), và kiến trúc microservice. So sánh ngắn các lựa chọn công nghệ đã xem xét.

**Chương 3 — Thiết kế hệ thống**: Mô tả kiến trúc phân lớp bốn tầng của LUVE, chi tiết các thành phần (Gateway, Core API, Grading Worker, Frontend), luồng xử lý thời gian thực (WebRTC offer → VAD → STT → LLM → TTS → kết thúc phiên), luồng chấm điểm bất đồng bộ (RabbitMQ → eligibility gate → grading), chiến lược scale-out đa tiến trình, và thiết kế cơ sở dữ liệu.

**Chương 4 — Đánh giá thực nghiệm**: Trình bày môi trường kiểm thử, chiến lược hai lớp (tự động an toàn và smoke live), kết quả kiểm thử chức năng (TC-01..TC-05), kết quả smoke đa gateway (2/4/6 người dùng), phân tích tài nguyên VRAM, phân tích latency và suppress rate, và thảo luận giới hạn kiểm thử.

**Chương 5 — Kết luận và hướng phát triển**: Tổng kết kết quả đạt được, đánh giá theo mục tiêu ban đầu, nhận định các hạn chế trung thực, và đề xuất hướng phát triển tiếp theo.
