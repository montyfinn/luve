# LUVE Thesis — Outline và Completion Roadmap

---

## 1. Tên Đề Tài Đề Xuất

**Tiếng Việt:**
> Thiết kế và xây dựng hệ thống hỗ trợ luyện tập kỹ năng nói tiếng Anh theo thời gian thực sử dụng công nghệ WebRTC, nhận dạng giọng nói tự động và mô hình ngôn ngữ lớn

**Tiếng Anh (phụ đề nếu cần):**
> LUVE: A Real-Time English Speaking Practice System Using WebRTC, Automatic Speech Recognition, and Large Language Models

---

## 2. Thesis Statement

Hệ thống LUVE chứng minh rằng một nền tảng luyện nói tiếng Anh thời gian thực có thể được xây dựng và kiểm thử trên phần cứng phát triển tiêu chuẩn (một GPU RTX 3050 Ti) bằng cách kết hợp: (1) gateway WebRTC tùy chỉnh dựa trên aiortc xử lý một phiên trên mỗi tiến trình, (2) nhận dạng giọng nói Whisper cục bộ, (3) phản hồi LLM, và (4) kiến trúc scale-out đa tiến trình phục vụ 2–6 người dùng đồng thời, với pipeline chấm điểm bất đồng bộ qua RabbitMQ.

---

## 3. Cấu Trúc Chương 1–5

| Chương | Tên | Nội dung cốt lõi |
|--------|-----|-----------------|
| 1 | Giới thiệu | Bối cảnh, vấn đề, mục tiêu, phạm vi, đóng góp, bố cục |
| 2 | Cơ sở lý thuyết | WebRTC, STT/ASR, LLM, TTS, message queue, kiến trúc microservice |
| 3 | Thiết kế hệ thống | Kiến trúc, luồng realtime, luồng chấm điểm, scale-out, dữ liệu |
| 4 | Đánh giá thực nghiệm | Môi trường, chiến lược test, kết quả, phân tích VRAM/latency |
| 5 | Kết luận và hướng phát triển | Tổng kết đóng góp, giới hạn, hướng mở rộng |

---

## 4. Mục Tiêu Từng Chương

### Chương 1 — Giới thiệu
- Nêu rõ bài toán: học nói tiếng Anh thiếu phản hồi tức thời, giáo viên khan hiếm.
- Trình bày mục tiêu luận văn: xây dựng prototype hệ thống thời gian thực, kiểm thử scale-out.
- Xác định phạm vi: môi trường phát triển cục bộ; không phải hệ thống production.
- Liệt kê đóng góp: gateway aiortc, grading pipeline, kiểm thử đa gateway.

### Chương 2 — Cơ sở lý thuyết
- Giải thích WebRTC (ICE, SDP, DTLS, SRTP) và lý do dùng aiortc thuần Python.
- Trình bày Whisper (Faster-Whisper, int8_float16) và đặc tính VRAM.
- Mô tả vai trò LLM (Groq / local) và TTS (edge-tts) trong vòng hội thoại.
- Trình bày RabbitMQ pub/sub và lý do chọn kiến trúc bất đồng bộ cho chấm điểm.
- So sánh ngắn các lựa chọn kỹ thuật đã xem xét.

### Chương 3 — Thiết kế hệ thống
- Mô tả kiến trúc phân lớp 4 tầng.
- Mô tả gateway aiortc tùy chỉnh và cơ chế `TEN_SINGLE_SESSION_CAPACITY = 1`.
- Trình bày luồng realtime (VAD → STT → LLM → TTS) bằng sequence diagram.
- Mô tả luồng chấm điểm bất đồng bộ và cổng eligibility gate.
- Giải thích thiết kế scale-out N tiến trình trên N cổng.
- Trình bày schema `grading_skip_log` và `raw_backup_json`.

### Chương 4 — Đánh giá thực nghiệm
- Mô tả môi trường kiểm thử (RTX 3050 Ti, Ubuntu, aiortc, không phải TEN SDK).
- Trình bày kết quả kiểm thử tự động (TC-01..05): PASS/SKIP.
- Trình bày kết quả smoke 2/4/6-user: tất cả PASS theo tiêu chí chấp nhận.
- Phân tích VRAM, dc_ms, stt_final_ms, suppress rate.
- Thảo luận giới hạn: automated stress, không phải browser thực; single host; 8-user không kiểm thử.

### Chương 5 — Kết luận
- Tóm tắt đóng góp: prototype hoạt động, bằng chứng scale-out 2/4/6-user, grading pipeline.
- Nhận định giới hạn trung thực.
- Đề xuất hướng phát triển: multi-host, GPU riêng, browser ICE thực, nâng Whisper model.

---

## 5. Trạng Thái Từng Chương

| Chương | Trạng thái | Ghi chú |
|--------|-----------|---------|
| Chương 1 | **missing** | Chưa có file nào. Cần viết từ đầu. |
| Chương 2 | **missing** | Chưa có file nào. Cần viết từ đầu. |
| Chương 3 | **draft exists** | `docs/thesis/chapter3_draft.md` — 435 dòng, commit `1a9c1a4`. Đã review, sửa DDL và raw_backup_json wording. |
| Chương 4 | **draft exists** | `docs/thesis/chapter4_draft.md` — 287 dòng, commit `5c0fc1a`. Đã review, sửa overclaim "đạt giới hạn thực tế". |
| Chương 5 | **missing** | Chưa có file nào. Nội dung ngắn (~2–3 trang), có thể viết nhanh từ kết luận Chương 4. |

---

## 6. Evidence Map

### Chương 3 — lấy từ đâu

| Nội dung | Nguồn |
|----------|-------|
| Kiến trúc 4 tầng, module gateway | Code: `run_ten.py`, `luve_extension.py`, `ten_compat.py:34`, `whisper_inference.py` |
| TEN-inspired naming, không phải TEN SDK | Code: `try: import ten` stub dòng 27–37 `luve_extension.py`; venv không có `ten` package |
| `TEN_SINGLE_SESSION_CAPACITY = 1` | Code: `ten_compat.py:34` và dòng 89–94 (HTTP 503) |
| Luồng VAD → STT → LLM → TTS | Code: `luve_extension.py` orchestration logic |
| Scale-out N tiến trình trên N cổng | Architecture decision; confirmed by smoke tests (Chương 4) |
| `getDefaultGatewayUrl()` | Code: `src/static/index.html` |
| Schema `grading_skip_log` | Migration: `infrastructure/db-migrations/0001_grading_skip_log.sql` |
| `evaluate_grading_eligibility()`, 4 reason codes | Code: `services/grading-worker/src/session_eligibility.py` |
| `log_grading_skip()` ON CONFLICT DO UPDATE | Code: `services/grading-worker/src/grading_repository.py` |
| R-01..R-10 requirements | `docs/testing/TRACEABILITY_MATRIX.md` |

### Chương 4 — lấy từ đâu

| Nội dung | Nguồn |
|----------|-------|
| Phần cứng, phần mềm | `docs/testing/TEST_ENVIRONMENT.md` |
| TC-01..TC-05 PASS/SKIP | `test-results/20260526_210210-thesis-evidence.md` |
| 2-user smoke chi tiết | `test-results/20260526_2user_multigateway_smoke.md` |
| 2/4/6-user comparative + VRAM + latency | `test-results/20260526_multigateway_scale_summary.md` |
| Stress log raw data (dc_ms, stt_final_ms, failures) | `/tmp/luve_stress_808{1..6}.log` (local, không commit) |
| TC-MG-001 definition | `docs/testing/TEST_CASES.md` |
| Traceability R-01..R-10 | `docs/testing/TRACEABILITY_MATRIX.md` |
| pytest 183/183 pass evidence | git commit message `cb79155`, `85ce409` |

### Screenshots / demo cần bổ sung (hiện còn thiếu)

| Hạng mục | Loại | Ưu tiên |
|----------|------|---------|
| Browser tại `http://localhost:8081/control-center` — input gateway-url auto-fill | Screenshot | Should-have |
| `psql \d grading_skip_log` — xác nhận schema khớp migration | Terminal screenshot | Should-have |
| `SELECT * FROM grading_skip_log LIMIT 5` — xác nhận row tồn tại | Terminal screenshot | Should-have |
| RabbitMQ management UI (:15672) — queue depth = 0 | Screenshot | Nice-to-have |
| `nvidia-smi` trong lúc chạy 6-gateway | Terminal screenshot | Nice-to-have |

---

## 7. Việc Còn Lại Trong 3 Ngày

### Must-have (bảo vệ không thể thiếu)

| Việc | Ước tính | Ghi chú |
|------|----------|---------|
| Viết Chương 1 (Giới thiệu) | 3–4 giờ | Bối cảnh, mục tiêu, phạm vi, đóng góp, bố cục |
| Viết Chương 2 (Cơ sở lý thuyết) | 4–5 giờ | WebRTC, Whisper, LLM/TTS, RabbitMQ, microservice |
| Viết Chương 5 (Kết luận) | 1–2 giờ | Ngắn; tóm tắt từ Chương 3–4 |
| Hoàn thiện format + biên tập toàn bộ | 2–3 giờ | Đánh số hình/bảng, danh mục tài liệu tham khảo, kiểm tra thuật ngữ nhất quán |
| Chuẩn bị slide demo 5–8 phút | 2–3 giờ | Xem mục 10 |

### Should-have (nên có nếu kịp)

| Việc | Ghi chú |
|------|---------|
| Chụp screenshot browser `localhost:8081/control-center` (TC-11) | Cần gateway đang chạy; phê duyệt trước |
| Chụp `psql \d grading_skip_log` và `SELECT * FROM grading_skip_log LIMIT 5` | Cần psql và DB đang chạy; phê duyệt trước |
| Cập nhật `docs/testing/EVIDENCE_MATRIX.md` với timestamp run_thesis_evidence.sh | File tự động; chỉ thêm row vào bảng |
| Đọc lại Chương 3–4 sau khi Chương 1–2 hoàn thành để đảm bảo nhất quán thuật ngữ | — |

### Nice-to-have (nếu còn thời gian)

| Việc | Ghi chú |
|------|---------|
| Chụp RabbitMQ management queue depth = 0 | Cần RabbitMQ + worker đang chạy |
| Thêm hình kiến trúc được vẽ bằng draw.io / Excalidraw | Đẹp hơn Mermaid cho bản in |
| Chạy lại `run_thesis_evidence.sh` để tạo evidence report mới nhất | Không cần phê duyệt; safe |
| Viết phụ lục: hướng dẫn khởi động gateway | Dành cho người đọc muốn reproduce |

---

## 8. Những Claim Được Phép Nói

| Claim | Bằng chứng hỗ trợ |
|-------|------------------|
| Hệ thống sử dụng gateway WebRTC tùy chỉnh dựa trên thư viện **aiortc** | Code: `luve_extension.py`, venv không có TEN package |
| Tên file cấu hình lấy cảm hứng từ TEN framework; không được thực thi bởi TEN runtime | `try: import ten; except ImportError: ten = _FallbackTen()` stub |
| Mỗi tiến trình gateway phục vụ tối đa một phiên WebRTC (`TEN_SINGLE_SESSION_CAPACITY = 1`) | `ten_compat.py:34`, HTTP 503 response |
| Scale-out đa người dùng bằng cách chạy N tiến trình độc lập trên N cổng | Không cần thay đổi code; confirmed by smoke tests |
| 2, 4, 6 người dùng đồng thời đạt PASS theo các tiêu chí chấp nhận đã định nghĩa | `test-results/20260526_multigateway_scale_summary.md` |
| VRAM tăng ~466 MiB mỗi mô hình Whisper small.en (CUDA, int8_float16) | Đo thực tế trong smoke tests |
| Kịch bản 8-user không được kiểm thử có chủ đích vì rủi ro CUDA OOM | Lý luận trong `20260526_multigateway_scale_summary.md §9` |
| 183/183 unit test pass trong grading-worker | Commit messages `cb79155`, `85ce409` |
| Grading pipeline sử dụng `ON CONFLICT DO UPDATE` (idempotent) | `grading_repository.py` |
| Stress test dùng `realtime_stress.py`, không phải browser WebRTC thực | Script code; caveats trong smoke report |
| Kiểm thử chỉ trên máy phát triển đơn lẻ (RTX 3050 Ti, không phải production) | `docs/testing/TEST_ENVIRONMENT.md` |
| Dấu hiệu suy giảm ở 6-user (dc_ms 1.269 ms, suppress ~55%) phản ánh giới hạn GPU đơn lẻ, không phải lỗi kiến trúc | Observed in stress logs; consistent với expected behavior |

---

## 9. Những Claim Tuyệt Đối Không Được Nói

| Claim bị cấm | Lý do |
|-------------|-------|
| "Sử dụng TEN framework SDK" / "TEN runtime" / "TEN native" | TEN package vắng mặt trong venv; gateway là aiortc thuần Python |
| "Hỗ trợ N người dùng đồng thời trong một tiến trình" | `TEN_SINGLE_SESSION_CAPACITY = 1`; multi-user chỉ qua N tiến trình |
| "Sẵn sàng cho production" / "production-ready" | Môi trường phát triển đơn lẻ; không có load balancer, không multi-host |
| "Kiểm thử với trình duyệt thực" | Chỉ dùng `realtime_stress.py` (automated script, không phải browser ICE path) |
| "8 người dùng đã được kiểm thử và PASS" | 8-user không được chạy có chủ đích |
| "Hệ thống không bao giờ OOM" / "không bao giờ crash" | Không có bằng chứng bao quát; chỉ có bằng chứng không OOM/crash ở 2/4/6-user |
| "raw_backup_json luôn không phải NULL" | `no_raw_backup` là supported skip reason; NULL có thể xảy ra |
| "Chấm điểm LLM đã được xác minh dưới tải 6-user" | Pipeline chấm điểm ở tải cao chưa được kiểm thử riêng biệt |
| "Hệ thống hoạt động với bất kỳ số người dùng nào" | Chỉ kiểm thử 2/4/6; giới hạn phần cứng đã quan sát được |
| "Kết quả score chính xác / đã được hiệu chuẩn" | 4 phiên live đều cho overall≈2.95; vấn đề hiệu chuẩn chưa giải quyết |
| "Vercel hosting toàn bộ backend" / "Vercel full backend hosting" | Vercel không hỗ trợ WebRTC gateway, Whisper CUDA, hay RabbitMQ; backend chạy local Linux |

---

## 10. Demo Checklist (5–8 Phút)

Mục tiêu demo: trình bày ngắn gọn, rõ ràng, không gây hoang mang. Mỗi bước có kết quả observable.

### Slide 1 — Giới thiệu (30 giây)
- [ ] Tên đề tài, tên sinh viên
- [ ] 1 câu mô tả: "hệ thống luyện nói tiếng Anh realtime, WebRTC + Whisper + LLM"

### Slide 2 — Kiến trúc (1 phút)
- [ ] Sơ đồ component: Browser → Gateway (aiortc) → Core API → RabbitMQ → Worker → DB
- [ ] Nhấn mạnh: gateway là custom aiortc, không phải TEN SDK
- [ ] Nhấn mạnh: 1 phiên/tiến trình; scale-out bằng N tiến trình

### Slide 3 — Demo realtime (2 phút)
- [ ] Mở `http://localhost:8081/control-center` trên trình duyệt
- [ ] Chỉ ra input gateway-url đã tự điền `http://localhost:8081` (TC-11)
- [ ] Nếu gateway đang chạy: bắt đầu phiên, nói 1–2 câu tiếng Anh ngắn, nhận phản hồi AI
- [ ] **Fallback nếu gateway không chạy**: trình chiếu log/artifact từ `realtime_stress.py` cho thấy `offer=200`, `failures=[]`
- [ ] **Fallback nếu Groq API lỗi giữa demo**: chuyển sang local LLM hoặc trình chiếu sẵn log phiên đã chạy thành công từ `20260526_2user_multigateway_smoke.md`

### Slide 4 — Scale-out multi-gateway (2 phút)
- [ ] Bảng so sánh 2/4/6-user từ `test-results/20260526_multigateway_scale_summary.md`
- [ ] VRAM table: ~466 MiB/model, không OOM
- [ ] Nhấn mạnh caveat: automated stress, không phải browser thực; single host
- [ ] Giải thích tại sao dừng ở 6-user (rủi ro CUDA OOM tại 8-user)

### Slide 5 — Grading pipeline (1 phút)
- [ ] Sơ đồ: Worker nhận event → eligibility gate (4 reason codes) → skip-log hoặc LLM grade
- [ ] Chỉ ra `grading_skip_log` schema (UUID PK, UNIQUE session_id, ON CONFLICT DO UPDATE)
- [ ] Nếu có: screenshot `SELECT * FROM grading_skip_log`

### Slide 6 — Kết luận (30 giây)
- [ ] Đóng góp: prototype WebRTC realtime + grading pipeline + scale-out evidence
- [ ] Giới hạn trung thực: single host, automated stress, score calibration chưa giải quyết
- [ ] Hướng tiếp theo: multi-host, GPU riêng, browser real ICE

### Chuẩn bị trước demo
- [ ] Slide không quá 6 trang (tốt hơn ít trang + bảng/diagram rõ)
- [ ] Chuẩn bị câu trả lời: "Tại sao không dùng TEN SDK?" — aiortc cho kiểm soát toàn bộ vòng đời phiên trong Python thuần, không phụ thuộc runtime ngoại vi
- [ ] Chuẩn bị câu trả lời: "Score 2.95 là đúng không?" — calibration chưa hoàn thiện; 4 phiên live cho kết quả tương tự; đây là hướng mở rộng tiếp theo
- [ ] Chuẩn bị câu trả lời: "8-user sao không thử?" — VRAM headroom ~821 MiB sau 6-user; concurrent inference peak risk; 2/4/6-user là evidence đủ và trung thực hơn

---

*Tài liệu tham khảo nội bộ: `docs/thesis/chapter3_draft.md`, `docs/thesis/chapter4_draft.md`, `docs/testing/TRACEABILITY_MATRIX.md`, `docs/testing/EVIDENCE_MATRIX.md`, `test-results/20260526_multigateway_scale_summary.md`*
