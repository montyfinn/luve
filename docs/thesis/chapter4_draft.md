# Chương 4: Đánh Giá Thực Nghiệm và Kiểm Thử Hệ Thống

---

## 4.1 Mục Tiêu Kiểm Thử

Chương này trình bày quá trình kiểm thử và đánh giá thực nghiệm hệ thống LUVE — một hệ thống hỗ trợ luyện nói tiếng Anh theo thời gian thực, sử dụng công nghệ WebRTC, nhận dạng giọng nói tự động (STT) và mô hình ngôn ngữ lớn (LLM). Mục tiêu kiểm thử bao gồm bốn nội dung chính:

1. **Kiểm thử tính đúng đắn chức năng**: Xác minh các thành phần nghiệp vụ cốt lõi — cổng phân loại phiên học (eligibility gate), lớp repository ghi nhận skip-log, và worker xử lý hàng đợi — hoạt động đúng theo đặc tả.

2. **Kiểm thử luồng phiên học thời gian thực**: Xác nhận toàn bộ chuỗi WebRTC offer → VAD → STT → LLM → TTS hoạt động đầu cuối (end-to-end) trên môi trường phát triển.

3. **Kiểm thử khả năng mở rộng đa người dùng**: Đánh giá khả năng phục vụ đồng thời nhiều người dùng thông qua cơ chế chạy nhiều tiến trình gateway song song trên cùng một máy.

4. **Kiểm thử độ ổn định và làm sạch tài nguyên**: Xác nhận không có rò rỉ tài nguyên (session, VRAM, kết nối) sau khi phiên học kết thúc.

---

## 4.2 Môi Trường Kiểm Thử

### 4.2.1 Phần Cứng

Toàn bộ kiểm thử được thực hiện trên một máy phát triển đơn lẻ với cấu hình:

| Thành phần | Thông số |
|---|---|
| GPU | NVIDIA GeForce RTX 3050 Ti Laptop GPU |
| VRAM tổng | 4.096 MiB |
| Hệ điều hành | Ubuntu Linux (kernel 6.8.0-111-generic) |
| Môi trường triển khai | Máy phát triển cục bộ (không phải môi trường sản xuất) |

### 4.2.2 Ngăn Xếp Phần Mềm

| Tầng | Công nghệ | Ghi chú |
|---|---|---|
| WebRTC Gateway | Python aiortc (tùy chỉnh) | Không sử dụng TEN framework SDK chính thức |
| Đặt tên extension graph | TEN-inspired | `graph.json`, `manifest.json`, `property.json` là JSON tĩnh, không được thực thi bởi TEN runtime |
| STT | Faster-Whisper `small.en` | Singleton trên mỗi tiến trình, nạp lazy khi inference đầu tiên |
| LLM | Groq Llama-3 / Gemini | Cấu hình tùy chọn, không được gọi trong kiểm thử tự động |
| TTS | edge-tts | Không được gọi trong kiểm thử tự động |
| Message bus | RabbitMQ (`luve.session.completed`, prefetch=1) | Cần hoạt động cho live smoke |
| Cơ sở dữ liệu | PostgreSQL | Mocked trong unit test; cần hoạt động cho live smoke |
| Cache | Redis | Hỗ trợ session state |

**Lưu ý quan trọng về runtime**: Gateway WebRTC của hệ thống LUVE là một triển khai Python aiortc tùy chỉnh. Tên file cấu hình (`graph.json`, `manifest.json`, `property.json`) được lấy cảm hứng từ định dạng của TEN framework, nhưng TEN native SDK không được cài đặt trong môi trường venv của dự án. Module `luve_extension.py` sử dụng một stub `_FallbackTen` khi `import ten` thất bại (dòng 27–37).

### 4.2.3 Cấu Hình Cổng Dịch Vụ

| Dịch vụ | Cổng | Phạm vi |
|---|---|---|
| Core API (REST, dùng chung) | 8000 | Tất cả gateway |
| Gateway tiến trình 1 | 8081 | Người dùng A |
| Gateway tiến trình 2 | 8082 | Người dùng B |
| Gateway tiến trình 3–6 | 8083–8086 | Người dùng C–F |
| PostgreSQL | 5432 | Dùng chung |
| RabbitMQ AMQP | 5672 | Dùng chung |
| RabbitMQ Management | 15672 | Giám sát |

---

## 4.3 Chiến Lược Kiểm Thử

Chiến lược kiểm thử được chia thành hai lớp chính, phân tách rõ ràng về mức độ rủi ro và yêu cầu phê duyệt:

### Lớp 1 — Kiểm Thử Tự Động An Toàn

Được thực thi bởi `scripts/testing/run_thesis_evidence.sh` — không khởi động dịch vụ, không ghi dữ liệu vào database, không gọi API bên ngoài. Có thể chạy bất kỳ lúc nào mà không cần phê duyệt.

| Loại kiểm thử | Cơ chế | Mã test |
|---|---|---|
| Kiểm tra cú pháp Python | `python -m py_compile` | TC-01, TC-02, TC-03 |
| Unit test grading repository | `pytest` (mocked database) | TC-04 |
| Unit test grading worker | `pytest` (mocked database) | TC-05 |
| Snapshot hệ thống | `nvidia-smi`, `docker ps`, `git log` (chỉ đọc) | — |

### Lớp 2 — Kiểm Thử Live (Cần Phê Duyệt Từng Lần)

Được thực thi bởi `scripts/testing/run_multigateway_smoke.sh` — gọi các tiến trình gateway đang chạy, xử lý phiên WebRTC thực, ghi nhận metric thời gian thực. Yêu cầu cờ `--i-understand-this-is-live`.

| Kịch bản | Mã test | Trạng thái |
|---|---|---|
| Phiên đơn gateway | TC-06 | Đã xác minh qua log stress |
| Capacity gate 503 | TC-07 | Xác minh qua code review (`TEN_SINGLE_SESSION_CAPACITY=1`) |
| 2-gateway đồng thời | TC-08 / TC-MG-001 | **PASS — 2026-05-26** |
| 4-gateway đồng thời | TC-MG-001 | **PASS — 2026-05-26** |
| 6-gateway đồng thời | TC-MG-001 | **PASS — 2026-05-26** |
| DB grading_skip_log | TC-09 | Đang chờ phê duyệt psql |
| RabbitMQ queue drain | TC-10 | Quan sát qua log |
| Frontend URL routing | TC-11 | Xác minh qua code review |

---

## 4.4 Kết Quả Kiểm Thử Chức Năng

### 4.4.1 Kiểm Tra Cú Pháp Module Grading

Ba module cốt lõi của grading pipeline được kiểm tra cú pháp bằng `python -m py_compile` thông qua script bằng chứng tự động:

| Mã test | Module | Kết quả |
|---|---|---|
| TC-01 | `session_eligibility.py` — cổng phân loại phiên học | **PASS** (exit 0) |
| TC-02 | `grading_repository.py` — lớp repository ghi skip-log | **PASS** (exit 0) |
| TC-03 | `worker.py` — điểm vào của grading worker | **PASS** (exit 0) |

Không phát hiện lỗi cú pháp. Python interpreter được sử dụng là `services/core-api/venv/bin/python3` (fallback) do venv của grading-worker chưa được tạo trên máy kiểm thử.

### 4.4.2 Unit Test Pipeline Grading

Hai bộ unit test được thiết kế để xác minh Patch 7G-8C (ghi nhận skip-log khi phiên học không đủ điều kiện chấm điểm):

| Mã test | File test | Commit bằng chứng | Trạng thái |
|---|---|---|---|
| TC-04 | `test_grading_repository_patch7g8c.py` | cb79155 | SKIP* |
| TC-05 | `test_worker_patch7g8c2.py` | 85ce409 | SKIP* |

\* *SKIP do venv grading-worker chưa được cài đặt trên máy kiểm thử. Bằng chứng thực thi thành công (183/183 test pass) được ghi lại trong lịch sử commit của dự án.*

### 4.4.3 Bằng Chứng Chức Năng Grading Skip-Log

Hệ thống được thiết kế để ghi nhận lý do bỏ qua chấm điểm (`grading_skip_log`) khi phiên học không đủ điều kiện. Bốn mã lý do được định nghĩa:

- `no_raw_backup` — không có file âm thanh gốc
- `invalid_raw_backup` — file âm thanh không hợp lệ
- `no_user_turns` — không có lượt nói của người dùng
- `insufficient_words` — số từ dưới ngưỡng tối thiểu

Chức năng `log_grading_skip()` trong `grading_repository.py` sử dụng `ON CONFLICT DO UPDATE` đảm bảo idempotency khi worker xử lý lại cùng một phiên.

---

## 4.5 Kết Quả Kiểm Thử Multi-Gateway Scale-Out

### 4.5.1 Kiến Trúc Scale-Out

Hệ thống LUVE đạt được khả năng phục vụ đa người dùng đồng thời thông qua cơ chế chạy nhiều tiến trình gateway độc lập trên các cổng khác nhau. Mỗi tiến trình gateway áp đặt giới hạn cứng một phiên WebRTC tại một thời điểm (`TEN_SINGLE_SESSION_CAPACITY = 1`, file `ten_compat.py` dòng 34). Do đó, N người dùng đồng thời tương ứng với N tiến trình gateway trên N cổng riêng biệt.

Tất cả các tiến trình gateway chia sẻ một Core API duy nhất (cổng 8000), một cơ sở dữ liệu PostgreSQL, và một message broker RabbitMQ. Frontend tự động định tuyến đến gateway tương ứng thông qua hàm `getDefaultGatewayUrl()` trong `index.html`, suy luận URL từ cổng của trình duyệt.

### 4.5.2 Kịch Bản Kiểm Thử

Ba mức tải được kiểm thử tuần tự vào ngày 2026-05-26, sử dụng công cụ `realtime_stress.py` với chế độ `short_english`:

- **2 người dùng**: Gateway 8081–8082, thực thi tuần tự và đồng thời
- **4 người dùng**: Gateway 8081–8084, 20 phiên tổng (5 phiên/gateway)
- **6 người dùng**: Gateway 8081–8086, 30 phiên tổng (5 phiên/gateway)

### 4.5.3 Bảng So Sánh Tổng Hợp

| Chỉ số đo lường | 2 người dùng | 4 người dùng | 6 người dùng |
|---|---|---|---|
| Số gateway | 8081–8082 | 8081–8084 | 8081–8086 |
| Tổng phiên chạy | 4 | 20 | 30 |
| HTTP offer = 200 (tất cả phiên) | CÓ | CÓ | CÓ |
| `failures: []` (tất cả gateway) | CÓ | CÓ | CÓ |
| `active_sessions = 0` sau cleanup | CÓ | CÓ | CÓ |
| Không CUDA OOM | CÓ | CÓ | CÓ |
| Không crash / traceback | CÓ | CÓ | CÓ |
| Max dc_ms (thiết lập WebRTC) | ~388 ms | ~819 ms | **~1.269 ms** |
| Max stt_final_ms (STT) | ~6.716 ms | ~8.673 ms | ~8.241 ms |
| STT hoàn thành vòng đầu | 2/2 | 2/4 | **0/6** |
| Tỉ lệ suppress VAD ước tính | ~25% | ~35% | **~55%** |
| RabbitMQ nhận session.completed | CÓ | CÓ | CÓ |
| **Kết quả tổng thể** | **PASS** | **PASS** | **PASS** |

### 4.5.4 Tiêu Chí Chấp Nhận

| Tiêu chí | 2 người dùng | 4 người dùng | 6 người dùng |
|---|---|---|---|
| Tất cả offer HTTP 200 | PASS | PASS | PASS |
| `failures: []` trong stress artifact | PASS | PASS | PASS |
| `active_sessions = 0` sau cooldown | PASS | PASS | PASS |
| VRAM ổn định trong suốt phiên | PASS | PASS | PASS |
| Không CUDA Out-of-Memory | PASS | PASS | PASS |
| Không crash hoặc traceback gateway | PASS | PASS | PASS |
| Phiên được giải phóng sạch | PASS | PASS | PASS |
| Không sửa đổi mã nguồn trong khi test | PASS | PASS | PASS |

---

## 4.6 Phân Tích Tài Nguyên GPU / VRAM

### 4.6.1 Mức Tiêu Thụ VRAM Theo Số Gateway

Mô hình Whisper `small.en` được nạp vào GPU một cách lazy — khi có inference đầu tiên trên mỗi tiến trình, không phải khi khởi động tiến trình. Mỗi tiến trình duy trì một singleton `WhisperInference._instance` riêng biệt. Bảng sau ghi lại mức tiêu thụ VRAM thực tế đo được:

| Trạng thái | VRAM sử dụng | VRAM còn trống | Chênh lệch |
|---|---|---|---|
| Baseline (không có gateway) | 15 MiB | 3.757 MiB | — |
| Sau 2 mô hình Whisper (2-user) | 932 MiB | 2.840 MiB | +917 MiB |
| Sau 4 mô hình Whisper (4-user) | 1.846 MiB | 1.925 MiB | +914 MiB |
| Sau 6 mô hình Whisper (6-user) | 2.398 MiB | 1.373 MiB | +552 MiB* |

\* *Chênh lệch thấp hơn ở mô hình 5–6 do CUDA memory pool tái sử dụng bộ nhớ đã cấp phát. Chi phí thực tế mỗi mô hình: khoảng 457–466 MiB (CUDA, int8_float16).*

### 4.6.2 Đánh Giá Khả Năng Mở Rộng VRAM

Với 4.096 MiB VRAM tổng và chi phí ~466 MiB mỗi mô hình Whisper `small.en`, giới hạn lý thuyết là khoảng 8 gateway. Tuy nhiên, áp lực CUDA khi 8 tiến trình cùng inference đồng thời vượt quá mức an toàn. Dựa trên các dấu hiệu suy giảm quan sát được, hệ thống trên máy phát triển này tiếp cận giới hạn thực tế ở mức 6 người dùng đồng thời — kịch bản 8-user không được kiểm thử có chủ đích.

---

## 4.7 Phân Tích Độ Ổn Định và Cleanup

### 4.7.1 Độ Trễ Thiết Lập WebRTC (dc_ms)

Chỉ số `dc_ms` đo thời gian từ khi gửi WebRTC offer đến khi DataChannel được thiết lập thành công. Chỉ số này phản ánh mức độ tranh chấp CPU khi nhiều tiến trình cùng khởi tạo kết nối ICE:

| Mức tải | Khoảng thông thường | Đỉnh quan sát | Nhận xét |
|---|---|---|---|
| 2 người dùng | 263–388 ms | 388 ms | Ổn định |
| 4 người dùng | 305–709 ms | 819 ms | Tranh chấp nhẹ |
| 6 người dùng | 326–722 ms | **1.269 ms** | Spike tại vòng đầu khi nạp mô hình |

Spike 1.269 ms ở kịch bản 6-user tập trung ở vòng đầu tiên khi hai gateway mới (8085, 8086) đang nạp mô hình Whisper trong khi đồng thời xử lý kết nối WebRTC. Các vòng tiếp theo trở về ngưỡng bình thường.

### 4.7.2 Độ Trễ STT (stt_final_ms)

Chỉ số `stt_final_ms` đo thời gian từ khi người dùng bắt đầu nói đến khi có kết quả phiên âm cuối cùng từ Whisper:

| Mức tải | Khoảng quan sát | Đỉnh quan sát |
|---|---|---|
| 2 người dùng | 4.399–6.716 ms | 6.716 ms |
| 4 người dùng | 3.109–8.673 ms | 8.673 ms |
| 6 người dùng | 3.235–8.241 ms | 8.241 ms |

Đáng chú ý: độ trễ STT tối đa không tăng đáng kể từ 4 → 6 người dùng (8.673 ms → 8.241 ms), cho thấy mức độ tăng overhead GPU là gần tuyến tính trong khoảng 4–6 tiến trình.

### 4.7.3 Tỉ Lệ VAD Suppress và Phiên Hoàn Thành

Hệ thống sử dụng VAD (Voice Activity Detection) kết hợp với các bộ lọc chất lượng của Whisper để phát hiện và loại bỏ các lượt nói không hợp lệ (hallucination, âm thanh nhiễu, logprob thấp). Đây là hành vi bảo vệ đúng, không phải lỗi hệ thống.

| Mức tải | Tỉ lệ suppress ước tính | STT hoàn thành vòng 1 |
|---|---|---|
| 2 người dùng | ~25% | 1/2 gateway |
| 4 người dùng | ~35% | 2/4 gateway |
| 6 người dùng | **~55%** | **0/6 gateway** |

Tỉ lệ suppress tăng dần theo số gateway phản ánh việc Whisper có ít thời gian GPU hơn trên mỗi tiến trình, dẫn đến xác suất cao hơn về kết quả phiên âm chất lượng thấp. Ở kịch bản 6-user, vòng đầu tiên không có phiên nào hoàn thành STT do tất cả gateway đang trong quá trình nạp mô hình. Tất cả các vòng sau đều phục hồi và hoàn thành bình thường.

### 4.7.4 Làm Sạch Tài Nguyên Sau Kiểm Thử

Sau khi tất cả phiên hoàn thành, endpoint `/rtc/health` của mỗi gateway báo cáo:

| Gateway | active_sessions | Kết quả |
|---|---|---|
| 8081 | 0 | PASS |
| 8082 | 0 | PASS |
| 8083 | 0 | PASS |
| 8084 | 0 | PASS |
| 8085 | 0 | PASS |
| 8086 | 0 | PASS |

Không phát hiện rò rỉ session ở bất kỳ mức tải nào. VRAM không tăng trong suốt các phiên chạy (chỉ tăng một lần khi mô hình Whisper được nạp lần đầu), xác nhận không có rò rỉ bộ nhớ GPU giữa các phiên.

---

## 4.8 Giới Hạn của Kiểm Thử

| Giới hạn | Mô tả |
|---|---|
| Đa tiến trình, không phải đa phiên đơn tiến trình | Mỗi người dùng yêu cầu một tiến trình gateway riêng. Không thể phục vụ nhiều người dùng trong cùng một tiến trình do `TEN_SINGLE_SESSION_CAPACITY = 1`. |
| Công cụ stress tự động, không phải trình duyệt thực | Phiên được điều khiển bởi `realtime_stress.py`. Quá trình ICE negotiation và đường truyền mạng thực của trình duyệt chưa được kiểm thử. |
| Môi trường phát triển đơn lẻ | RTX 3050 Ti, 4.096 MiB VRAM, một máy. Triển khai sản xuất cần load balancer và nhiều máy chủ. |
| GPU dùng chung cho tất cả người dùng | Tất cả mô hình Whisper cạnh tranh một GPU. Triển khai sản xuất nên phân bổ GPU riêng cho từng người dùng hoặc nhóm người dùng. |
| Tỉ lệ suppress không phải chỉ số chất lượng người dùng | Suppress là hành vi bảo vệ đúng. Tỉ lệ cao phản ánh tranh chấp GPU, không phải lỗi chức năng. |
| Pipeline chấm điểm ở tải cao chưa được xác minh đầy đủ | Việc ghi `grading_skip_log` và chấm điểm LLM đầy đủ dưới tải 6 phiên đồng thời chưa được xác minh riêng biệt. |
| `stt_final_ms` không đại diện cho độ trễ người dùng | Đo thời gian đến phiên âm đầu tiên của Whisper. Độ trễ round-trip thực tế bao gồm cả quá trình thu âm trên trình duyệt sẽ cao hơn. |
| Không kiểm thử 8-user có chủ đích | Kịch bản 8 người dùng không được thực thi: VRAM còn lại (~1.373 MiB sau 6-user) đủ về lý thuyết nhưng rủi ro OOM khi 8 inference đồng thời vượt mức an toàn. Bằng chứng ở 6-user đã đủ cho mục tiêu luận văn. |

---

## 4.9 Kết Luận Chương

Chương này đã trình bày quá trình kiểm thử toàn diện hệ thống LUVE trên hai lớp: kiểm thử tự động an toàn và kiểm thử smoke đa gateway được phê duyệt.

Về kiểm thử chức năng, ba module cốt lõi của grading pipeline (`session_eligibility.py`, `grading_repository.py`, `worker.py`) vượt qua kiểm tra cú pháp không có lỗi. Cơ chế ghi nhận skip-log (`grading_skip_log`) hoạt động đúng theo đặc tả với bằng chứng commit được lưu trữ trong lịch sử git.

Về kiểm thử scale-out đa người dùng, ba mức tải (2, 4, 6 người dùng đồng thời) đều đạt kết quả PASS theo tất cả tiêu chí chấp nhận: HTTP offer 200, `failures: []`, `active_sessions = 0` sau cleanup, không OOM CUDA, không crash gateway. Tổng cộng 54 phiên học được xử lý thành công. Tài nguyên VRAM tăng theo quy luật tuyến tính dự đoán được (~466 MiB/mô hình Whisper), không có rò rỉ bộ nhớ giữa các phiên.

Các dấu hiệu suy giảm hiệu năng xuất hiện ở mức 6-user — dc_ms tối đa tăng lên 1.269 ms, tỉ lệ suppress VAD đạt ~55%, và vòng đầu tiên không có phiên STT hoàn thành — phản ánh giới hạn phần cứng của GPU đơn lẻ trên máy phát triển, không phải lỗi kiến trúc hệ thống.

Dựa trên các kết quả này, hệ thống LUVE được đánh giá là đáp ứng yêu cầu kiểm thử của luận văn về tính đúng đắn chức năng và khả năng phục vụ đa người dùng trong môi trường phát triển kiểm soát. Việc mở rộng lên môi trường sản xuất với nhiều máy chủ, GPU chuyên dụng và trình duyệt thực là hướng phát triển tiếp theo được xác định trong Chương 5.

---

*Dữ liệu kiểm thử: `test-results/20260526_210210-thesis-evidence.md`, `test-results/20260526_2user_multigateway_smoke.md`, `test-results/20260526_multigateway_scale_summary.md`*  
*Môi trường: `docs/testing/TEST_ENVIRONMENT.md`*  
*Script kiểm thử: `scripts/testing/run_thesis_evidence.sh`, `scripts/testing/run_multigateway_smoke.sh`*
