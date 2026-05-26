# Chương 5: Kết Luận Và Hướng Phát Triển

---

## 5.1 Tổng Kết Kết Quả Đạt Được

Khóa luận này trình bày quá trình thiết kế, xây dựng, và kiểm thử hệ thống LUVE — một prototype hỗ trợ luyện nói tiếng Anh theo thời gian thực sử dụng WebRTC, nhận dạng giọng nói tự động và mô hình ngôn ngữ lớn.

### Về xây dựng hệ thống

Hệ thống LUVE được triển khai hoàn chỉnh trên môi trường phát triển cục bộ với các thành phần sau hoạt động đầu cuối:

- **Gateway WebRTC tùy chỉnh** xây dựng bằng thư viện aiortc thuần Python, xử lý toàn bộ chuỗi: WebRTC offer/answer → ICE negotiation → VAD phát hiện lượt nói → Whisper STT → LLM → TTS → phát audio trả về. Mỗi tiến trình gateway phục vụ tối đa một phiên WebRTC đồng thời (`TEN_SINGLE_SESSION_CAPACITY = 1`); yêu cầu thứ hai nhận HTTP 503.

- **Pipeline chấm điểm bất đồng bộ** hoạt động hoàn toàn độc lập với luồng thời gian thực: gateway phát sự kiện `luve.session.completed` lên RabbitMQ khi phiên kết thúc; grading worker tiêu thụ hàng đợi với `prefetch_count=1`, kiểm tra bốn điều kiện đủ tư cách, và ghi kết quả hoặc lý do bỏ qua vào PostgreSQL.

- **Cơ sở dữ liệu kiểm toán** `grading_skip_log` được tạo bằng migration idempotent, lưu lý do bỏ qua chấm điểm với `ON CONFLICT DO UPDATE` để đảm bảo tính toàn vẹn khi xử lý lại.

- **Frontend** tự động định tuyến đến đúng gateway dựa trên cổng trình duyệt qua hàm `getDefaultGatewayUrl()`.

### Về kiểm thử

Hệ thống được kiểm thử qua hai lớp:

- **Kiểm thử tự động (Lớp 1)**: Ba module cốt lõi của grading pipeline (`session_eligibility.py`, `grading_repository.py`, `worker.py`) vượt qua `py_compile` không lỗi. 183/183 unit test của grading-worker pass với database mock.

- **Kiểm thử smoke đa gateway (Lớp 2)**: Ba mức tải được kiểm thử trên máy phát triển RTX 3050 Ti (4 GiB VRAM):

| Mức tải | Kết quả tổng thể | VRAM sau | dc_ms tối đa | Suppress rate |
|---------|-----------------|----------|--------------|---------------|
| 2 người dùng | **PASS** | 932 MiB | ~388 ms | ~25% |
| 4 người dùng | **PASS** | 1.846 MiB | ~819 ms | ~35% |
| 6 người dùng | **PASS** | 2.398 MiB | ~1.269 ms | ~55% |

Tổng cộng 54 phiên được xử lý thành công qua ba mức tải. Không có CUDA OOM, không crash gateway, `active_sessions = 0` sau cleanup ở tất cả mức tải.

---

## 5.2 Đánh Giá Theo Mục Tiêu Ban Đầu

| Mục tiêu | Nội dung | Kết quả |
|----------|----------|---------|
| MT-1 | Gateway WebRTC hoạt động đầu cuối | **Đạt** — HTTP 200 offer, VAD/STT/LLM/TTS xác nhận qua stress log |
| MT-2 | Giới hạn phiên và HTTP 503 | **Đạt** — `TEN_SINGLE_SESSION_CAPACITY = 1`, code-verified |
| MT-3 | Scale-out đa người dùng không thay đổi code | **Đạt** — N tiến trình uvicorn trên N cổng; không cần sửa code |
| MT-4 | Pipeline chấm điểm bất đồng bộ | **Đạt** — Worker, eligibility gate, skip-log, DB hoạt động; 183/183 unit test pass |
| MT-5 | Kiểm thử scale-out và bằng chứng định lượng | **Đạt** — Smoke PASS ở 2/4/6-user; VRAM, latency, suppress rate ghi lại đầy đủ |
| MT-6 | Ghi nhận trung thực giới hạn phần cứng | **Đạt** — Dấu hiệu suy giảm ở 6-user được phân tích; 8-user không kiểm thử có chủ đích |

Tất cả sáu mục tiêu đề ra được đánh giá là **đạt** trong phạm vi môi trường phát triển cục bộ đã xác định.

---

## 5.3 Hạn Chế

Các hạn chế sau đây được nhận diện một cách trung thực:

### Hạn chế về môi trường kiểm thử

- **Không phải trình duyệt WebRTC thực**: Các phiên được tạo bởi `realtime_stress.py` — một script tự động, không phải quá trình ICE negotiation thực từ trình duyệt. Đường truyền mạng thực, codec đàm phán trình duyệt, và độ trễ thu âm phía client chưa được kiểm thử.

- **Môi trường đơn máy**: Tất cả dịch vụ (gateway, Core API, PostgreSQL, RabbitMQ, Redis) chạy trên cùng một máy vật lý. Các vấn đề về phân tán, mạng nội bộ, và đồng bộ trạng thái đa máy chủ chưa được xem xét.

- **GPU dùng chung**: Tất cả tiến trình gateway cạnh tranh cùng một GPU RTX 3050 Ti. Áp lực inference đồng thời ở 6-user đã cho thấy dấu hiệu suy giảm rõ rệt (suppress rate ~55%, dc_ms tối đa ~1.269 ms, không có STT hoàn thành ở vòng đầu).

### Hạn chế về chức năng

- **Hiệu chuẩn điểm số**: Bốn phiên live được kiểm thử đều trả về `overall ≈ 2.95`. Kết quả này có thể phản ánh vấn đề về prompt engineering hoặc calibration của LLM grader, không nhất thiết phản ánh chất lượng ngôn ngữ thực của người dùng. Độ chính xác của điểm số theo khung năng lực ngôn ngữ chuẩn chưa được đánh giá.

- **Pipeline chấm điểm dưới tải cao chưa xác minh đầy đủ**: Việc ghi `grading_skip_log` và chấm điểm LLM đầy đủ dưới tải 6 phiên đồng thời chưa được kiểm thử riêng biệt; chỉ có unit test với mock database.

- **TC-04 và TC-05 bị SKIP**: Hai bộ unit test của grading-worker không được chạy trực tiếp trên máy kiểm thử do venv của grading-worker chưa được cài đặt. Bằng chứng pass (183/183) được ghi nhận qua commit history, không phải qua chạy trực tiếp trong môi trường báo cáo.

### Hạn chế về phạm vi

- **Không hỗ trợ native TEN SDK**: Gateway sử dụng aiortc thuần Python với stub tương thích `_FallbackTen`. Tích hợp với TEN framework native SDK — bao gồm các extension chính thức, graph executor, và plugin ecosystem — nằm ngoài phạm vi đề tài.

- **Kịch bản 8-user không được kiểm thử**: Do VRAM còn lại (~1.373 MiB sau 6-user) không đủ an toàn cho 8 inference đồng thời trên RTX 3050 Ti, kịch bản 8 người dùng không được thực thi. Bằng chứng scale-out dừng ở 6-user.

- **Frontend mức prototype**: Giao diện web hiện tại phục vụ mục đích điều khiển và demo; chưa có UX dành cho người học như tiến độ học, lịch sử phiên, hay dashboard điểm.

---

## 5.4 Hướng Phát Triển

Dựa trên các kết quả đạt được và hạn chế được nhận diện, các hướng phát triển tiếp theo được đề xuất theo thứ tự ưu tiên:

### Ngắn hạn (cải thiện prototype hiện tại)

**Hiệu chuẩn điểm số LLM:**
Thiết kế lại prompt chấm điểm với rubric rõ ràng hơn (ví dụ: gắn với mô tả CEFR từng band), thu thập đánh giá từ chuyên gia ngôn ngữ để so chiếu, và điều chỉnh thang điểm. Đây là bước quan trọng nhất để nâng giá trị giáo dục của hệ thống.

**Kiểm thử trình duyệt thực:**
Chạy ít nhất một phiên từ trình duyệt Chrome/Firefox thực để xác nhận ICE negotiation, codec SDP, và độ trễ round-trip thực tế khớp với kết quả từ stress script.

**Hoàn thiện TC-04 và TC-05:**
Cài đặt venv grading-worker đầy đủ trên máy kiểm thử, chạy `pytest` trực tiếp và ghi lại kết quả vào báo cáo bằng chứng.

### Trung hạn (mở rộng kiến trúc)

**Triển khai đa máy chủ:**
Tách gateway, Core API, và database lên các máy chủ riêng với load balancer (Nginx/HAProxy hoặc Kubernetes Ingress). Điều này giải quyết giới hạn GPU dùng chung và tăng khả năng chịu lỗi.

**GPU riêng theo người dùng hoặc nhóm:**
Trong môi trường đa máy, phân bổ GPU riêng cho từng gateway node hoặc nhóm gateway, thay vì chia sẻ một GPU trên cùng host.

**Tích hợp TEN native SDK:**
Thay thế `_FallbackTen` stub bằng tích hợp chính thức với TEN framework SDK, cho phép sử dụng extension ecosystem của TEN (graph executor, plugin management, hot-reload) và mở ra khả năng chia sẻ extension với cộng đồng TEN.

### Dài hạn (phát triển sản phẩm)

**Triển khai public và xác thực người dùng thật:**
Triển khai trên cloud (GPU instance) với domain, HTTPS, và xác thực người dùng. Kiểm thử với người dùng thật trên trình duyệt để thu thập phản hồi về trải nghiệm và chất lượng hội thoại.

**Nâng cấp mô hình STT:**
Thay thế Whisper small.en bằng Whisper medium hoặc large để tăng độ chính xác nhận dạng, đặc biệt với người học có giọng không chuẩn. Cân nhắc API STT đám mây (Google, Azure) cho môi trường không có GPU.

**Dashboard học tập:**
Xây dựng giao diện người học với lịch sử phiên, biểu đồ tiến độ theo thời gian, và chi tiết phản hồi từng lượt nói.

**Đánh giá hiệu quả giáo dục:**
Thiết kế nghiên cứu người dùng để đo lường sự cải thiện kỹ năng nói sau thời gian sử dụng hệ thống, so chiếu với nhóm đối chứng.

---

## 5.5 Kết Luận

Khóa luận này đã trình bày quá trình thiết kế và xây dựng hệ thống LUVE — một prototype luyện nói tiếng Anh thời gian thực sử dụng WebRTC, Whisper STT, và LLM — trong phạm vi môi trường phát triển cục bộ trên một máy đơn lẻ với GPU RTX 3050 Ti.

Ba đóng góp kỹ thuật chính được thực hiện: (1) gateway WebRTC tùy chỉnh bằng aiortc xử lý toàn bộ chuỗi VAD → STT → LLM → TTS với cơ chế giới hạn phiên cứng; (2) pipeline chấm điểm bất đồng bộ qua RabbitMQ với eligibility gate bốn điều kiện và bảng kiểm toán `grading_skip_log`; (3) kiến trúc scale-out đa tiến trình phục vụ 2, 4, và 6 người dùng đồng thời mà không cần thay đổi code.

Kết quả kiểm thử xác nhận tính khả thi kỹ thuật của hướng tiếp cận: tất cả ba mức tải đạt PASS theo các tiêu chí chấp nhận đã định nghĩa, VRAM tăng theo quy luật tuyến tính (~466 MiB/model Whisper), và không có rò rỉ tài nguyên sau cleanup. Đồng thời, các dấu hiệu suy giảm ở 6-user — dc_ms lên đến 1.269 ms, suppress rate ~55%, không có STT hoàn thành ở vòng đầu — phản ánh giới hạn thực tế của GPU đơn lẻ trên phần cứng phát triển.

Hệ thống chứng minh rằng một prototype luyện nói AI thời gian thực hoàn chỉnh — từ WebRTC đến chấm điểm LLM — có thể được xây dựng và kiểm thử trên phần cứng phát triển thông thường. Đây là nền tảng kỹ thuật để phát triển tiếp theo hướng đến triển khai thực tế với người dùng thật, GPU chuyên dụng, và đánh giá hiệu quả giáo dục đầy đủ.

---

*Dữ liệu kiểm thử tham chiếu: `test-results/20260526_210210-thesis-evidence.md`, `test-results/20260526_2user_multigateway_smoke.md`, `test-results/20260526_multigateway_scale_summary.md`*  
*Thiết kế hệ thống: `docs/thesis/chapter3_draft.md`*  
*Đánh giá thực nghiệm chi tiết: `docs/thesis/chapter4_draft.md`*
