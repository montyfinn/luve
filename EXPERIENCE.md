# EXPERIENCE.md

## Mục Tiêu

File này ghi lại kinh nghiệm thực chiến đã rút ra khi debug repo `luve`.

Nó trả lời câu hỏi: "Lần trước đã mất thời gian vì lỗi gì, nguyên nhân thật là gì, và lần sau phải kiểm tra theo thứ tự nào?"

Không dùng file này thay source of truth. Nếu file này mâu thuẫn với code, schema, env contract, hoặc log runtime hiện tại, tin runtime/code trước và cập nhật lại file này sau.

## Quy Tắc Ghi Nhớ

- Chỉ ghi bài học đã có bằng chứng từ code, command, test, log, DB query, browser/live test, hoặc user-provided evidence.
- Không ghi secret thật, token thật, password, API key, cookie, bearer token, JWT, hoặc `DATABASE_URL` có credential.
- Không copy log dài. Chỉ ghi pattern lỗi, nguyên nhân, cách kiểm tra, và cách tránh lặp lại.
- Không ghi kế hoạch ngắn hạn chỉ có ý nghĩa trong một turn chat.

## Bài Học Vận Hành

### 1. Luôn phân biệt offline STT, browser mic file, và live WebRTC STT

Đã có lúc offline STT trên audio sạch cho kết quả tốt, nhưng live WebRTC vẫn nghe tệ.

Kinh nghiệm:
- Offline pass không chứng minh live path pass.
- Browser mic file pass không chứng minh VAD/live segmentation pass.
- Live WebRTC phải kiểm tra riêng bằng event `stt_partial`, `stt_final`, `stt_result_suppressed`, `audio_ms`, `speech_ms`, `noise_floor_db`, và `effective_threshold_db`.

### 2. Partial STT không phải source of truth

Đã gặp trường hợp ô suy nghĩ/partial hiển thị đúng hoặc sai rất lớn, trong khi final khác.

Nguyên nhân đã xác minh:
- Partial từng chạy quá sớm trên audio rất ngắn.
- Whisper có thể hallucinate khi nhận audio nền, audio quá ngắn, hoặc đoạn chưa đủ speech.
- Final và partial từng đi qua decode path khác nhau khi final bật internal VAD còn partial thì không.

Kinh nghiệm:
- Partial chỉ là preview, không dùng để persist hoặc trigger LLM.
- Final mới là source of truth cho `USER_TURN`.
- Partial cần ràng buộc tối thiểu về audio/speech trước khi hiển thị.
- Nếu partial sai, kiểm tra `audio_ms`, `speech_ms`, `noise_floor_db`, `effective_threshold_db` trước khi chỉnh model.

### 3. Không chạy Whisper internal VAD lần hai cho live final nếu live VAD đã cắt câu

Đã gặp nghi vấn "partial đúng nhưng final sai" do final dùng `vad_filter=True` còn partial dùng `vad_filter=False`.

Kinh nghiệm:
- Live VAD sở hữu boundary của utterance.
- Whisper internal VAD có thể trim/mutate lại đoạn audio đã cắt, làm final lệch partial.
- Với live path hiện tại, final STT nên dùng `vad_filter=False` để nhất quán với partial và legacy coordinator.

### 4. Whisper hallucination trên audio nền là lỗi thật, không phải chỉ là UI

Đã gặp pattern partial lặp `"Thank you."` trên audio ngắn/nền.

Kinh nghiệm:
- `"Thank you"`, `"Thanks"`, `"Thanks for watching"`, `"Please subscribe"` trên audio ngắn/nền thường là hallucination.
- Cần suppress các filler ngắn khi live VAD chứng minh speech quá ít.
- Cần suppress transcript có mật độ chữ phi thực tế so với độ dài audio.
- Không mở rộng filter quá tay, vì người dùng có thể thật sự nói "thank you".

### 5. VAD energy threshold là nút cổ chai của live STT

Đã xác minh live path đang dùng VAD dựa trên năng lượng âm thanh, không phải speech-aware VAD.

Kinh nghiệm:
- Energy VAD không phân biệt giọng người với nhạc nền.
- Nhạc nền có thể làm hệ thống nghĩ là đang có speech hoặc làm noise floor/threshold sai.
- Khi có nhạc nền, ưu tiên xem `noise_floor_db` và `effective_threshold_db`, không vội đổi Whisper model.
- Nếu STT nghe tốt trong phòng yên tĩnh nhưng fail khi có nhạc nền, nghi phạm số 1 là VAD/live audio frontend.

### 6. TTS/LLM có thể làm nhiễu kết luận STT

Đã có giai đoạn STT tốt hơn khi bật STT-only, nhưng tệ khi TTS/LLM tham gia.

Kinh nghiệm:
- Khi debug STT, luôn test `STT-only test mode` trước.
- Nếu bật TTS, phải coi echo-protection, assistant speaking flag, barge-in, và audio tail là tác nhân ảnh hưởng mic.
- Đừng tối ưu TTS khi chưa chốt STT live.
- Đừng dùng lỗi Gemini/LLM để kết luận STT sai.

### 7. Gemini quota 429 không phải lỗi STT

Đã gặp Gemini trả `429 Too Many Requests` / quota exhausted.

Kinh nghiệm:
- Nếu `assistant_final.source=local_fallback` hoặc log có Gemini 429, LLM không chạy theo ý muốn.
- Lỗi này không giải thích partial/final STT sai.
- Khi test STT, tắt LLM/TTS hoặc bỏ qua lỗi Gemini quota.

### 8. CUDA có thể "thấy GPU" nhưng Python vẫn không dùng được

Đã gặp trạng thái:
- `nvidia-smi` thấy GPU.
- `torch.cuda.device_count()` thấy 1.
- Nhưng `torch.cuda.is_available()` false và `ctranslate2.get_cuda_device_count()` bằng 0.
- Khi shutdown `run_ten.py`, native CUDA/CTranslate2 có thể crash với `CUDA failed with error unknown error`.

Nguyên nhân đã thấy:
- GPU/driver ở trạng thái lỗi kiểu "GPU requires reset".
- Có lúc device node `/dev/nvidia*` không ổn trong sandbox/tool context.
- Driver package từng lệch giữa metapackage và open kernel module.
- `nvidia-smi` bản ngắn có thể vẫn hiện GPU bình thường; phải xem chi tiết bằng `nvidia-smi -q` mới thấy các dòng `GPU requires reset`.

Kinh nghiệm:
- Không kết luận CUDA OK chỉ vì `nvidia-smi` chạy.
- Phải kiểm tra bằng:
  - `ctranslate2.get_cuda_device_count()`
  - `torch.cuda.is_available()`
  - runtime thực của `WhisperInference`
- Nếu GPU requires reset, app không sửa được triệt để. Cần reboot/power-cycle hoặc xử lý driver host.
- Khi GPU đang `requires reset`, STT phải fallback CPU sớm thay vì cố load CUDA.
- Log cần in rõ `requires_reset`, `ctranslate2_cuda_devices`, `torch_cuda_available`, và `torch_cuda_device_count` ở thời điểm chọn runtime, không chỉ ghi chung chung "CUDA failed".
- Không log GPU health theo từng audio frame; chỉ log ở startup/load model/fallback/shutdown boundary để tránh làm hỏng realtime latency.

### 9. Sandbox có thể làm sai kết luận về GPU/port

Đã gặp lệnh trong sandbox không thấy `/dev/nvidia*` hoặc không expose port như process ngoài sandbox.

Kinh nghiệm:
- Với GPU, `nvidia-smi`, `ctranslate2`, và Torch nên kiểm tra ngoài sandbox khi cần kết luận runtime thật.
- Với gateway `:8080`, nếu process chạy trong tool sandbox mà browser không connect được, start gateway ngoài sandbox.
- Luôn kiểm tra port bằng `ss -ltnp` ngoài sandbox khi debug `Address already in use` hoặc `curl` fail.

### 10. Port 8000 và 8080 thường bị giữ bởi process cũ

Đã gặp nhiều lần:
- API `:8000` đã chạy bởi `uvicorn`.
- TEN gateway `:8080` đã chạy bởi `python run_ten.py`.
- Chạy lại bị `Errno 98 Address already in use`.

Kinh nghiệm:
- Trước khi start, kiểm tra `ss -ltnp`.
- Không kill bừa nếu chưa biết process nào đang chạy.
- Sau khi sửa `run_ten.py` hoặc `luve_extension.py`, phải restart gateway `:8080`; API reload không tự reload gateway.

### 11. Control-center state có thể gây nhầm khi debug

Đã gặp session id bị mất sau disconnect hoặc reuse session gây khó debug.

Kinh nghiệm:
- `Current Session ID` nên trống sau disconnect để tránh reuse nhầm.
- `Last Session ID` cần giữ lại để query/debug.
- Connect nên tự tạo session mới nếu current trống.
- Remember token chỉ dành cho control-center nội bộ; không được persist token thật vào docs/log.

### 12. Multi-session là rủi ro privacy nếu chưa route đúng session

Đã bị review cảnh báo cross-session broadcast.

Kinh nghiệm:
- Khi TEN extension vẫn single-session, `MAX_WEBRTC_SESSIONS` phải bị hard cap ở 1.
- Không expose capacity >1 nếu output audio/event chưa route theo `session_id`.
- Bất kỳ thay đổi realtime nào cũng phải kiểm tra session ownership và cross-session leakage.

### 13. Endpoint RTC control/signaling phải có auth và session scope

Đã bị review cảnh báo command RTC unauthenticated/global.

Kinh nghiệm:
- RTC offer, ICE, và cmd phải kiểm tra bearer token/session ownership.
- Không cho phép command thiếu `session_id` tác động global.
- `BARGE_IN`, `END_SESSION`, `FLUSH` phải thuộc session cụ thể.

### 14. Audio file extension không đáng tin

Đã gặp file `.webm` thực chất là MP3 44.1kHz stereo.

Kinh nghiệm:
- Luôn kiểm tra file bằng `file` hoặc `ffprobe`.
- Không suy luận codec/sample rate từ extension.
- Eval STT phải decode/resample qua path rõ ràng về PCM 16k mono.

### 15. Review feedback thường chỉ ra lỗi self-contained/security/data ownership

Đã từng bị review chỉ ra:
- Patch import file chưa tracked nên clean checkout không chạy.
- Secret/API key bị đưa vào repo.
- `memoryview` mutable bị giữ tham chiếu sống, có thể corrupt audio buffer.

Kinh nghiệm:
- Trước khi chốt patch, kiểm tra `git status --short`.
- Không commit secret.
- Audio buffer nên sở hữu bản copy ổn định ở boundary.
- Clean checkout phải đủ file để start app.

### 16. Tách commit skeleton khỏi commit env hygiene

Đã tạo grading-worker skeleton và sau đó tách riêng commit redaction `.env.example`.

Kinh nghiệm:
- Skeleton/service-boundary commit nên chỉ chứa code và smoke test thuộc đúng scope.
- Env hygiene nên là commit riêng nếu chỉ đổi placeholder/secret-handling.
- Không gộp `.env.example` vào commit feature nếu diff không trực tiếp cần cho feature.
- Trước khi commit, luôn kiểm tra `git diff --cached --name-status` và `git diff --cached --stat`.
- Nếu staged set rỗng, không tự stage khi yêu cầu là "commit only currently staged".

### 17. Smoke script phải có assert và PASS marker

Đã gặp smoke script ban đầu chỉ in JSON, khó biết pass/fail thực sự.

Kinh nghiệm:
- Smoke script tối thiểu phải có assert cho các invariant chính.
- Output nên có dòng PASS rõ ràng để agent/người test biết script đã chạy hết.
- Dùng UUID cố định trong smoke script để output ổn định và dễ review.
- Với file untracked, `git diff -- path` không hiện nội dung; dùng `git status --short` và đọc file trực tiếp.

### 18. Grading-worker không được cross-import core-api

Đã chốt hướng grading-worker skeleton theo service boundary riêng.

Kinh nghiệm:
- Grading-worker đọc dữ liệu đã persist, không import Python code từ core-api.
- Input grading hiện lấy từ `sessions.raw_backup_json`, chủ yếu `USER_TURN` và `AI_TURN`.
- Chưa gọi LLM thật khi skeleton flow chưa được xác minh.
- Nếu schema `grading_results` thiếu `evaluation_input_json`, `status`, `error_message`, hoặc `grader_version`, phải báo cần migration riêng, không tự nhét vào schema hiện tại.

## Checklist Khi Debug STT Live

1. Xác nhận CUDA thật:
   - `ctranslate2.get_cuda_device_count() == 1`
   - `torch.cuda.is_available() == True`
   - `WhisperInference.runtime.device == "cuda"`
2. Chạy STT-only trước.
3. Tắt nhạc nền, nói câu ngắn rõ, xem `stt_final`.
4. Bật nhạc nền, so sánh `noise_floor_db` và `effective_threshold_db`.
5. Nếu partial sai, xem `stt_partial.audio_ms` và `stt_partial.speech_ms`.
6. Nếu final sai, xem `trigger`, `audio_ms`, `speech_ms`, và decode settings.
7. Nếu có `stt_result_suppressed`, kiểm tra text bị suppress có thật sự là hallucination không.
8. Chỉ sau khi live STT ổn mới bật LLM/TTS để test end-to-end.
