# AGENTS.md

## Mục tiêu file này

File này dành cho agent hoặc lập trình viên mới vào repo `luve`.

Ưu tiên tuyệt đối:

- Bám vào code đang tồn tại, không bám mù vào tài liệu định hướng cũ.
- Tối ưu cho độ trễ, chi phí vận hành, và khả năng chịu tải tăng đột ngột.
- Không over-engineer khi nền tảng session orchestration và grading worker còn chưa hoàn thiện.

Nếu tài liệu và code mâu thuẫn nhau, tin code trước.

## 1. Hiện trạng thật của dự án

Repo này là một monorepo đang ở trạng thái chưa hoàn thiện đều.

Thực tế hiện tại:

- `services/core-api/` là phần duy nhất có code backend đáng kể và là trung tâm của repo.
- `clients/mobile-app/` hiện trống.
- `services/grading-worker/` mới chỉ có `.env.example`, chưa có worker implementation.
- `services/media-server/` hiện chưa có code thực thi.
- `docker-compose.yml` hiện chỉ dựng hạ tầng: PostgreSQL, Redis, RabbitMQ.
- Core API và TEN/WebRTC gateway chưa được docker hóa đầy đủ trong repo này, đang chạy thủ công.

Kết luận thực dụng:

- Đừng giả định repo đã có kiến trúc microservice hoàn chỉnh.
- Đừng tách thêm service mới nếu chưa có nhu cầu bắt buộc.
- Khi sửa tính năng, ưu tiên chỉnh trong `services/core-api` trước.

## 2. Nguồn sự thật trong repo

Đọc theo thứ tự ưu tiên này:

1. Code trong `services/core-api/src/` và `services/core-api/run_ten.py`
2. SQL schema trong `infrastructure/db-init/01-init.sql`
3. Env contract trong `services/core-api/.env.example`
4. Tài liệu định hướng:
   - `README.md`
   - `TECH_STACK.md`
   - `FUNCTIONAL_GUIDE.md`
   - `fullpro.md`
   - `workflow.md`
   - `continue`

Lưu ý:

- Các file tài liệu ở root mô tả vision 5 khu vực, nhưng hiện code thực tế chưa đạt đến mức đó.
- Khi viết code mới, phải ghi rõ đang bám theo “hiện trạng code” hay “định hướng kiến trúc”.

## 3. Bản đồ code hiện tại

### `services/core-api/src/main.py`

FastAPI app chính ở port `8000`.

Hiện có:

- REST auth routes qua `src/api/v1/auth.py`
- WebSocket audio route qua `src/api/v1/stream.py`
- static control center tại `/control-center`

### `services/core-api/src/api/v1/auth.py`

Auth nền tảng:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

Phụ thuộc:

- `src/services/auth_service.py`
- `src/core/security.py`
- `src/core/db.py`
- `src/models/user.py`

### `services/core-api/src/api/v1/stream.py`

WebSocket pipeline text/binary cho audio:

- `WS /ws/chat/{session_id}`

Ràng buộc rất quan trọng:

- Yêu cầu token qua query param hoặc cookie.
- Yêu cầu Redis có key `session:{session_id}`.
- Yêu cầu bảng `sessions` trong PostgreSQL có row cùng `session_id` thuộc về user đang đăng nhập.

Hiện repo chưa có API hoàn chỉnh để tạo session cho flow này. Đừng giả định đường đi session đã khép kín.

### `services/core-api/src/media/`

Đây là vùng nhạy cảm nhất về latency.

- `buffer.py`: gom audio chunk theo thứ tự, auto clear khi im lặng lâu.
- `stt_worker.py`: singleton `WhisperInference`, có fallback CUDA -> CPU.
- `brain.py`: gọi Gemini và stream phản hồi text.
- `tts.py`: Edge-TTS chính, Piper là fallback local tùy chọn.
- `coordinator.py`: điều phối VAD -> STT partial/final -> LLM -> TTS -> subtitle events.
- `webrtc.py`: transform track cho `aiortc`.

### `services/core-api/run_ten.py`

Gateway WebRTC/TEN chạy riêng ở port `8080`.

Endpoint hiện có:

- `GET /healthz`
- `GET /rtc/graph`
- `POST /rtc/offer`
- `POST /rtc/ice`
- `POST /rtc/cmd`
- `GET /control-center`

File này là cầu nối giữa `aiortc` và `src/ten_ext/luve_extension.py`.

### `services/core-api/src/ten_ext/luve_extension.py`

Đây là nhánh realtime kiểu TEN extension nhưng hiện đang chạy cả ở chế độ fallback Python.

Chức năng đáng chú ý:

- ingest audio PCM
- partial/final STT
- LLM/TTS
- barge-in
- ghi `event_log` vào RAM
- khi stop thì cố ghi `raw_backup_json` vào bảng `SESSIONS`

Điểm phải nhớ:

- Đây là code nóng, rất dễ tự làm tăng độ trễ nếu thêm logic không cẩn thận.
- Không được nhét DB/network/blocking logic vào nhánh per-frame.

## 4. Hạ tầng và schema

### Docker Compose

`docker-compose.yml` hiện chỉ dựng:

- PostgreSQL
- Redis
- RabbitMQ

Không dựng sẵn:

- FastAPI app
- TEN gateway
- grading worker

### Database

Schema trong `infrastructure/db-init/01-init.sql` có các bảng:

- `users`
- `lessons`
- `sessions`
- `grading_results`

Quan trọng:

- Auth hiện mới dùng `users`.
- WebSocket stream kiểm tra ownership trong `sessions`.
- TEN extension khi stop có `UPDATE SESSIONS SET raw_backup_json = ...`.
- Nếu session row không tồn tại hoặc không đồng bộ với Redis, flow realtime sẽ fail.

## 5. Cách chạy đúng

Từ root repo:

```bash
docker compose up -d
```

Core API:

```bash
cd services/core-api
source venv/bin/activate
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

TEN/WebRTC gateway:

```bash
cd services/core-api
source venv/bin/activate
python run_ten.py
```

Production-ish command cho API đã được ghi trong file `run`:

```bash
python -m gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Control center:

- API app: `http://localhost:8000/control-center`
- TEN gateway: `http://localhost:8080/control-center`

## 6. Env và dependency

File chuẩn: `services/core-api/.env.example`

Biến bắt buộc tối thiểu cho API:

- `DATABASE_URL`
- `SECRET_KEY`

Biến bắt buộc để WebSocket stream chạy ổn:

- `REDIS_URL`

Biến tùy chọn nhưng ảnh hưởng tính năng:

- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `STT_*`
- `VAD_*`
- `TTS_*`
- `PIPER_*`

Dependency nặng và nhạy cảm:

- `faster-whisper`
- `aiortc`
- `av`
- `edge-tts`
- `google-genai`

Không nâng version bừa bãi nếu chưa test lại luồng audio thật.

## 7. Quy tắc sửa code trong repo này

### Ưu tiên hiệu năng và độ trễ

Trong các file sau, mọi thay đổi phải xem như thay đổi vùng nóng:

- `src/api/v1/stream.py`
- `src/media/coordinator.py`
- `src/media/stt_worker.py`
- `src/media/tts.py`
- `src/ten_ext/luve_extension.py`
- `run_ten.py`

Không làm các việc sau trong hot path:

- ghi DB theo từng audio chunk
- gọi Redis đồng bộ theo từng frame
- parse/serialize JSON lớn lặp lại không cần thiết
- log quá dày trong vòng lặp realtime
- tạo object nặng lặp lại cho mỗi chunk
- tăng queue/buffer vô tội vạ để “chữa cháy” latency

### Giữ triết lý hiện tại của pipeline

- Whisper model là singleton, giữ nguyên tinh thần đó nếu chưa có lý do cực mạnh để đổi.
- Partial STT phải rẻ hơn final STT.
- Barge-in phải được ưu tiên hơn phát audio của assistant.
- Nếu user bắt đầu nói lại, phải ưu tiên cắt TTS/LLM đang chạy hơn là cố phát nốt.

### Tôn trọng ranh giới hiện trạng

- Không cross-import giữa service nếu sau này worker/media-server được tách ra thật.
- Nhưng ở hiện tại, đừng cố tách service chỉ để “đẹp kiến trúc”.
- Nếu thêm tính năng mới, mô tả rõ nó đang nằm ở “vision” hay “implementation now”.

### Khi docs và code lệch nhau

- `README.md`, `workflow.md`, `fullpro.md`, `FUNCTIONAL_GUIDE.md` là tài liệu định hướng.
- Code trong `services/core-api` mới là hiện trạng thực thi.
- Nếu cần sửa tài liệu, ưu tiên làm rõ chỗ nào là “đã có” và chỗ nào là “chưa làm”.

## 8. Những chỗ dang dở phải biết trước khi đụng vào

- Chưa có session creation flow đầy đủ cho nhánh WebSocket `/ws/chat/{session_id}`.
- Chưa có grading worker implementation thật.
- `clients/mobile-app` chưa có code.
- `services/media-server` chưa có implementation.
- Test suite chưa chuẩn hóa theo `pytest`.
- Các file `test_stt.py`, `test_stt_void.py`, `test_fallback.py` là script thử tay, không phải regression suite chuẩn.

Vì vậy:

- Đừng hứa “xong end-to-end” nếu chưa khép session + Redis + DB + gateway.
- Khi thêm tính năng mới, phải chỉ ra dependency còn thiếu để tránh ảo tưởng tiến độ.

## 9. Testing thực dụng

Hiện repo này phù hợp với các mức test sau:

- unit test cho validator, buffer, parser
- integration test nhẹ cho auth và DB
- manual test cho audio realtime

Nếu thêm test mới, ưu tiên:

- logic thuần trong `buffer.py`
- schema trong `schemas/`
- auth service
- phần diff/parse text trong `brain.py` hoặc `coordinator.py`

Không nên bắt đầu bằng test E2E audio nặng nếu mục tiêu chỉ là fix logic nhỏ.

## 10. Repo hygiene

- Không commit `.env`.
- Không commit file audio test lớn.
- Không commit `venv/`, `__pycache__/`, log tạm.
- `services/core-api/venv/` đang tồn tại trong workspace local; coi như artifact, không dùng làm “source of truth”.
- Worktree có thể đang bẩn; không tự ý revert thay đổi của người khác.

## 11. Cách ra quyết định kỹ thuật trong repo này

Khi có nhiều phương án, ưu tiên theo thứ tự:

1. Phương án ít tăng độ trễ nhất
2. Phương án ít tăng chi phí vận hành nhất
3. Phương án ít tạo coupling hạ tầng nhất
4. Phương án ít tạo gánh nặng bảo trì nhất
5. Phương án đẹp kiến trúc nhất

Nói ngắn gọn:

- UX realtime và chi phí vận hành quan trọng hơn “kiến trúc nhìn cho sang”.
- Chỉ tách thêm thành phần khi có lý do đo được: latency, tải, fault isolation, hoặc ownership rõ ràng.

## 12. Nếu bạn là agent mới vào sửa repo này

Trước khi code:

1. Đọc `services/core-api/src/main.py`, `src/api/v1/stream.py`, `src/media/coordinator.py`, `run_ten.py`.
2. Đọc `services/core-api/.env.example`.
3. Kiểm tra schema `infrastructure/db-init/01-init.sql`.
4. Kiểm tra worktree có đang bẩn không.

Trước khi kết luận một tính năng “đã có”:

1. Tìm endpoint thật trong code.
2. Tìm nơi session được tạo/lưu.
3. Tìm nơi dữ liệu được persist.
4. Xác nhận có đường test hoặc manual path chạy được.

Nếu chưa xác nhận đủ 4 điểm trên, hãy mô tả tính năng là “chưa khép kín”.

## 13. Dùng AI_MEMORY.md thế nào

`AI_MEMORY.md` chỉ dùng để giữ các fact vận hành đã xác minh, các bẫy đã gặp, và các quyết định thực dụng đã chốt qua nhiều phiên.

Không dùng `AI_MEMORY.md` để thay source of truth.

Thứ tự ưu tiên vẫn là:

1. code đang chạy
2. schema và env contract
3. `AGENTS.md`
4. `AI_MEMORY.md`

Nếu `AI_MEMORY.md` mâu thuẫn với code hiện tại, tin code trước và cập nhật lại `AI_MEMORY.md` sau.

## 13.1. Dùng CODEX.md và EXPERIENCE.md thế nào

`CODEX.md` là checklist luật làm việc bắt buộc cho Codex/agent trong mỗi phiên.

`EXPERIENCE.md` là file kinh nghiệm thực chiến: các lỗi đã từng gặp, nguyên nhân thật, cách kiểm tra, và cách tránh lặp lại.

Khi bắt đầu task đủ lớn hoặc liên quan runtime/audio/session, đọc theo thứ tự:

1. `AGENTS.md`
2. `CODEX.md`
3. `AI_MEMORY.md`
4. `EXPERIENCE.md`

Không dùng `CODEX.md`, `AI_MEMORY.md`, hoặc `EXPERIENCE.md` để thay code đang chạy. Nếu mâu thuẫn, tin code/runtime trước rồi cập nhật tài liệu sau.

## 14. Trước Khi Compact

Trước khi `/compact`, tạo một handoff summary ngắn nhưng đủ.

Phải gồm:

1. Original goal
2. Current task status
3. Validated conclusions
   Chỉ gồm các điểm đã được chứng minh bằng code, command, test, log, DB query, browser automation, hoặc bằng chứng user cung cấp.
4. Important files inspected or changed, và vì sao mỗi file quan trọng
5. Bugs found and suspected root causes
6. Changes already made
7. Remaining steps, ordered by priority
8. Constraints / things not to change
9. Operational traps discovered
   Gồm các bẫy về environment, assumption sai, command lỗi, path, API quirks, capacity limits
10. Exact commands, endpoints, env vars, ports, model settings, IDs, token handling rules, và session IDs thực sự cần cho debug
11. What still needs real-world verification vs what is already proven
12. Recommended next prompt after `/compact`

Quy tắc bảo mật:

- Không ghi secret thật.
- Redact password, `DATABASE_URL` có credential thật, API key, access token, refresh token, bearer token, JWT, cookie, login payload secret, private credential, và production-only identifier nhạy cảm.
- Dùng placeholder như:
  - `<DATABASE_URL>`
  - `<DB_USER>`
  - `<DB_PASSWORD>`
  - `<JWT_TOKEN>`
  - `<BEARER_TOKEN>`
  - `<API_KEY>`
  - `<COOKIE>`
  - `<SESSION_ID>`
- Chỉ giữ session id thật nếu nó thực sự cần cho debug; nếu không thì redact.

Quy tắc nội dung:

- Giữ factual.
- Không đưa speculation nếu chưa gắn nhãn `unverified`.
- Không copy log dài nguyên văn; chỉ giữ dòng hoặc ID thực sự quan trọng.
- Không lôi lịch sử hội thoại không liên quan vào handoff.
