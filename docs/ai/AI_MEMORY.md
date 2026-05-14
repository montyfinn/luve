# AI_MEMORY.md

## Mục tiêu

File này là bộ nhớ vận hành ngắn hạn nhưng đủ bền giữa nhiều phiên làm việc.

Nó không thay `AGENTS.md`.

- `AGENTS.md`: quy tắc làm việc, bản đồ repo, ưu tiên kỹ thuật.
- `docs/ai/AI_MEMORY.md`: fact đã xác minh, bẫy đã gặp, quyết định đã chốt.

Chỉ ghi các mục có khả năng còn đúng ở các phiên sau.
Không ghi log dài, transcript dài, hay giả định chưa xác minh.

## Fact

- `services/core-api/` là backend chính hiện có giá trị thực thi trong repo.
- Audio production path nên đi qua `WebRTC/TEN`, không phải `legacy WS raw audio`.
- `ENABLE_LEGACY_WS_AUDIO=false` là mặc định an toàn cho production path.
- Node hiện tại đang khóa `MAX_WEBRTC_SESSIONS=1` để tránh quá tải và vì gateway/session state chưa đủ an toàn để nhồi nhiều phiên.
- `POST /api/v1/sessions` đã tồn tại và là đường tạo session chuẩn cho flow `WebRTC/TEN`.
- `control-center` hiện có thể:
  - nhập `Bearer token`
  - tạo session qua UI
  - tự tạo session mới khi bấm `Connect` nếu `Current Session ID` đang trống
- `control-center` hiện tách:
  - `Current Session ID`
  - `Last Session ID`
- `WhisperInference` vẫn đang được giữ theo mô hình singleton.
- Bug PCM do đọc `bytes(item.planes[0])` đã được vá bằng helper `audio_frame_to_pcm16le_bytes(...)`.
- Script `services/core-api/scripts/eval_stt_final.py` hiện tự add project root vào `sys.path`, không còn phụ thuộc việc set `PYTHONPATH` thủ công.

## Trap

- Đuôi file audio không đáng tin. Đã gặp trường hợp file `.webm` thực chất là `mp3 44.1kHz stereo`. Luôn kiểm tra bằng `file` hoặc `ffprobe`.
- Nếu gateway đang full slot, `POST /rtc/offer` sẽ trả `503`, rồi các `POST /rtc/ice` sau đó có thể trả `404`. Gốc lỗi là `503`, không phải `404`.
- Với `MAX_WEBRTC_SESSIONS=1`, rất dễ tự chặn chính mình khi còn tab/browser test cũ chưa giải phóng slot.
- Event Log của `control-center` hiện vẫn dễ bị ngập bởi `assistant_audio_meta`, nên khi debug STT thực tế cần ưu tiên đọc lại `raw_backup_json` trong bảng `sessions`.
- `Disconnect` không nên giữ `Current Session ID` để reuse mặc định; nếu reuse nhầm sẽ làm việc debug các lượt test bị dính session.
- Browser automation/live test có thể fail sớm ở `getUserMedia()` nếu browser context chưa được grant quyền `microphone`.
- Đo WER bằng clip phim hay audio không phải mic thật dễ làm kết luận sai về chất lượng live path.

## Decision

- Không dùng `WS raw audio` làm đường speech production.
- Ưu tiên test STT bằng clip ngắn, một utterance rõ, thay vì file dài.
- Muốn chốt chất lượng STT phải dùng `gold transcript` có người xác nhận, không lấy chính output STT làm gold.
- Muốn chứng minh live path phải phân biệt rõ:
  - `offline decode + STT`
  - `browser mic file`
  - `live WebRTC session`
- Với node hiện tại, ưu tiên:
  1. ít độ trễ
  2. ít coupling hạ tầng
  3. ít concurrency hơn
  4. scale ngang sau
- Khi debug session live, thứ tự kiểm tra nên là:
  1. `POST /api/v1/sessions` có thành công không
  2. `POST /rtc/offer` có `200` không
  3. gateway có đang full slot không
  4. session có persist `raw_backup_json` không
- Nếu cần xem transcript thật của một phiên live, ưu tiên đọc `sessions.raw_backup_json` theo `session_id`.

## Secret Rule

- Không lưu secret thật trong `docs/ai/AI_MEMORY.md`.
- Không lưu password thật, `DATABASE_URL` có credential thật, API key, access token, refresh token, bearer token, JWT, cookie, hay private credential.
- Luôn thay bằng placeholder như:
  - `<DATABASE_URL>`
  - `<DB_USER>`
  - `<DB_PASSWORD>`
  - `<JWT_TOKEN>`
  - `<BEARER_TOKEN>`
  - `<API_KEY>`
  - `<COOKIE>`
  - `<SESSION_ID>`
- Chỉ giữ session id thật nếu nó thực sự cần cho debug kỹ thuật; nếu không thì redact.

## Không Ghi Ở Đây

- output benchmark tạm thời theo từng ngày
- transcript dài của từng file test
- log nguyên văn của từng session
- workaround tạm thời chưa được xác minh
- kế hoạch ngắn hạn chỉ có ý nghĩa trong một turn chat
