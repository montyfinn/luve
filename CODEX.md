# CODEX.md

## Mục Tiêu

File này là rule vận hành bắt buộc cho Codex/agent khi làm việc trong repo `luve`.

Đọc file này ở đầu mỗi phiên cùng với:

1. `AGENTS.md`
2. `AI_MEMORY.md`
3. `EXPERIENCE.md`
4. Code/runtime liên quan đến task hiện tại

Nếu các file memory/rule mâu thuẫn với code đang chạy, tin code và runtime evidence trước.

## Nguyên Tắc Cốt Lõi

### 1. Không đoán trạng thái hệ thống

Trước khi kết luận:
- đọc code
- chạy command phù hợp
- xem log
- kiểm tra port/process
- kiểm tra DB nếu task liên quan persist/session
- kiểm tra browser/live path nếu task liên quan UI/audio realtime

Không nói "đã ổn" nếu chưa có bằng chứng.

### 2. Sửa ít nhất có thể

Mỗi thay đổi phải truy ngược được về yêu cầu hiện tại.

Không:
- refactor lan rộng
- đổi kiến trúc để đẹp hơn
- thêm abstraction chưa cần
- chỉnh formatting hàng loạt
- xóa code không liên quan

Nếu phát hiện vấn đề ngoài phạm vi, ghi nhận và báo lại, không tự ý sửa trừ khi nó chặn task hiện tại.

### 3. Ưu tiên latency, chi phí, và khả năng chịu tải

Trong repo này, UX realtime quan trọng hơn kiến trúc nhìn sang.

Ưu tiên:
1. ít tăng độ trễ nhất
2. ít tăng chi phí vận hành nhất
3. ít coupling hạ tầng nhất
4. ít gánh nặng bảo trì nhất
5. đẹp kiến trúc sau cùng

Không thêm DB/network/blocking IO vào hot path audio frame.

### 4. Source of truth theo thứ tự

Ưu tiên đọc:

1. Code đang chạy trong `services/core-api/src/` và `services/core-api/run_ten.py`
2. Schema trong `infrastructure/db-init/01-init.sql`
3. Env contract trong `services/core-api/.env.example`
4. `AGENTS.md`
5. `AI_MEMORY.md`
6. `EXPERIENCE.md`
7. Docs vision như `README.md`, `workflow.md`, `fullpro.md`

Docs vision không được dùng để khẳng định tính năng đã có.

### 5. Bảo mật là mặc định

Không bao giờ ghi secret thật vào repo hoặc summary:
- password
- API key
- access token
- refresh token
- bearer token
- JWT
- cookie
- `DATABASE_URL` có credential
- private credential

Dùng placeholder:
- `<DATABASE_URL>`
- `<DB_USER>`
- `<DB_PASSWORD>`
- `<JWT_TOKEN>`
- `<BEARER_TOKEN>`
- `<API_KEY>`
- `<COOKIE>`
- `<SESSION_ID>`

Nếu user paste secret vào chat, không lặp lại giá trị đó trong final answer hoặc docs.

## Quy Trình Bắt Đầu Mỗi Task

1. Đọc `AGENTS.md`, `CODEX.md`, `AI_MEMORY.md`, `EXPERIENCE.md` nếu task đủ lớn hoặc liên quan audio/session/runtime.
2. Kiểm tra `git status --short`.
3. Xác định file hot path có bị đụng không.
4. Nêu ngắn gọn giả định và bước kiểm tra đầu tiên.
5. Chỉ edit sau khi đã có đủ context tối thiểu.

## Quy Tắc Với Audio Realtime

Các file sau là vùng nóng:

- `services/core-api/run_ten.py`
- `services/core-api/src/ten_ext/luve_extension.py`
- `services/core-api/src/media/stt_worker.py`
- `services/core-api/src/media/tts.py`
- `services/core-api/src/media/coordinator.py`
- `services/core-api/src/media/webrtc.py`
- `services/core-api/src/static/index.html`

Khi sửa vùng này:
- không log quá dày trong vòng lặp frame
- không ghi DB theo từng chunk audio
- không tạo object nặng theo từng frame
- không tăng queue/buffer vô tội vạ
- không làm partial thành source of truth
- không trigger LLM/TTS từ partial
- không đổi VAD/threshold mà không có log `audio_ms`, `speech_ms`, `noise_floor_db`, `effective_threshold_db`

## Quy Tắc Với STT

- Offline STT pass không chứng minh live STT pass.
- Partial STT là preview, final STT mới là source of truth.
- Nếu partial sai, kiểm tra live segmentation trước khi đổi model.
- Nếu final sai, kiểm tra audio boundary, VAD, `vad_filter`, prompt, beam size, và latency.
- Khi debug STT, ưu tiên `STT-only test mode`.
- Không tối ưu TTS/LLM khi đang đo STT.
- Không dùng Gemini quota error để kết luận STT hỏng.

## Quy Tắc Với TTS/LLM

- TTS có thể ảnh hưởng mic qua echo-protection, assistant speaking flag, barge-in, và audio tail.
- LLM quota/fallback không phải lỗi STT.
- Nếu `assistant_final.source=local_fallback`, đừng kết luận Gemini đang hoạt động.
- Khi TTS phát méo/chậm, kiểm tra sample rate, chunking, decode/resample boundary, và browser playout path.

## Quy Tắc Với CUDA/GPU

Không kết luận CUDA OK chỉ vì `nvidia-smi` chạy.

Phải kiểm tra:

```bash
cd services/core-api
./venv/bin/python -c 'import ctranslate2, torch; print("ctranslate2_cuda_devices", ctranslate2.get_cuda_device_count()); print("torch_cuda_available", torch.cuda.is_available()); print("torch_cuda_device_count", torch.cuda.device_count())'
```

Và nếu cần, load thật `WhisperInference` để xem runtime device.

Nếu GPU báo "requires reset", app không sửa được triệt để. Cần xử lý host driver/reboot/power-cycle.

## Quy Tắc Với Session/WebRTC

- TEN/WebRTC gateway hiện chạy ở `:8080`.
- Core API chạy ở `:8000`.
- `MAX_WEBRTC_SESSIONS` không được quảng cáo > 1 khi TEN extension còn single-session.
- RTC signaling/control phải auth và scope theo owner/session.
- Không broadcast audio/event cross-session.
- Khi debug session live, giữ `Last Session ID` để query; không reuse `Current Session ID` bừa.

## Quy Tắc Verify

Tùy task, chọn verify đủ hẹp:

- Python syntax: `./venv/bin/python -m py_compile ...`
- JS syntax trong control-center: extract script rồi `node -c`
- Health: `curl http://127.0.0.1:8080/healthz`
- Port/process: `ss -ltnp`
- STT offline: `./venv/bin/python scripts/eval_stt_final.py --manifest testdata/stt_cases.json`
- CUDA: kiểm tra `ctranslate2`, Torch, và nếu cần `WhisperInference.runtime`
- Live STT: đọc event `stt_partial`, `stt_final`, `stt_result_suppressed`

Không cần chạy test nặng nếu task là docs hoặc logic nhỏ không liên quan runtime.

## Khi Gặp Review Feedback

Ưu tiên sửa lỗi correctness/security trước:

1. Secret committed
2. Clean checkout không chạy
3. Auth/session ownership
4. Cross-session leak
5. Data ownership/mutable buffer
6. Timeout/cancellation
7. Config bị ignore

Không tranh luận với review nếu có thể chứng minh bằng code rằng lỗi đúng.

## Khi Trước Compact

Tạo handoff summary theo `PRE_COMPACT_PROMPT.md`.

Không ghi secret.
Không paste log dài.
Không đưa lịch sử chat không liên quan.
Chỉ ghi fact đã xác minh và việc còn lại.

