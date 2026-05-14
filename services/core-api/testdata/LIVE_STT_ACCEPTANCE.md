# Live STT Acceptance

Mục tiêu của file này là chốt xem `live WebRTC/TEN -> final STT` đã đủ bền để nối sang grading chưa.

Không dùng checklist này để đo WER chi tiết.  
WER offline dùng [stt_cases.json](stt_cases.json).  
Checklist này chỉ để bắt các lỗi live quan trọng như:

- final nhảy sai nhịp
- nuốt mất đoạn
- dính transcript giữa các turn
- session không persist được
- barge-in làm hỏng turn sau

## Khi nào được dùng checklist này

Chỉ dùng sau khi:

- API đang chạy ở `:8000`
- gateway `run_ten.py` đang chạy ở `:8080`
- `control-center` đã connect được thật
- `control-center` đã được hard refresh sau thay đổi mới nhất
- log UI đã đủ sạch để nhìn `stt_result`, `assistant_final`, `assistant_audio_meta:start|complete`
- panel `STT Diagnostics` hiển thị được final STT summary sau mỗi lượt nói

## Bộ test tối thiểu trước grading

Chạy vòng đầu với `STT-only test mode` bật. Mục tiêu là cô lập STT khỏi LLM/TTS.
Chỉ khi vòng này qua gate mới chạy lại một vòng nhỏ với TTS bật để kiểm tra barge-in và echo.

Chạy ít nhất `10 session` ngắn, mỗi session chỉ kiểm một kiểu tình huống chính:

1. `2 session` câu ngắn, rõ, nói chậm
2. `2 session` câu ngắn, nói nhanh hơn bình thường
3. `2 session` có ngắt nghỉ giữa câu khoảng `0.5-1.5s`
4. `2 session` câu dài hơn bình thường, khoảng `12-20` từ
5. `1 session` có noise nền nhẹ
6. `1 session` có barge-in hoặc nói lại khi assistant đang/chuẩn bị phát

Không nên test nhiều biến trong cùng một session ở giai đoạn đầu.  
Mục tiêu là cô lập lỗi nhanh.

## Cách chạy mỗi session

1. Mở `http://127.0.0.1:8000/control-center`
2. Dán bearer token test
3. Bật `STT-only test mode`
4. Bấm `Connect`
5. Nói đúng `1-3` câu đã chuẩn bị trước
6. Chờ `final` nhảy xong
7. Bấm `Copy Summary` trong `STT Diagnostics`
8. Bấm `Disconnect`
9. Lưu lại:
   - spoken reference text
   - final text trên UI
   - `Last Session ID`
   - JSON từ `STT Diagnostics`
   - nhận xét `pass`, `warn`, hoặc `fail`

Format ghi nhanh:

```text
Session N
spoken: ...
final: ...
result: pass|warn|fail
summary: <paste STT Diagnostics JSON>
note: ...
```

## Cách đối chiếu DB

Sau mỗi session, dùng `Last Session ID` để kiểm tra row trong `sessions`.

Nếu muốn kiểm tra nhanh qua API trước:

```bash
curl -sS "http://127.0.0.1:8000/api/v1/sessions/<SESSION_ID>" \
  -H "Authorization: Bearer <BEARER_TOKEN>"
```

Kết quả cần có:

- `id` đúng với `Last Session ID`
- `status` đã về `completed`
- `raw_backup_json` không rỗng

Nếu cần soi kỹ hơn hoặc API không đủ tiện, dùng `psql`.

Ví dụ:

```bash
psql "<DATABASE_URL>" -c "
SELECT id, status, started_at, ended_at
FROM sessions
WHERE id = '<SESSION_ID>';
"
```

Kiểm tra `raw_backup_json` có được persist không:

```bash
psql "<DATABASE_URL>" -c "
SELECT jsonb_pretty(raw_backup_json)
FROM sessions
WHERE id = '<SESSION_ID>';
"
```

Nếu muốn xem nhanh chỉ các `USER_TURN`:

```bash
psql "<DATABASE_URL>" -c "
SELECT jsonb_pretty(raw_backup_json)
FROM sessions
WHERE id = '<SESSION_ID>'
  AND raw_backup_json IS NOT NULL;
"
```

`USER_TURN.payload.text` là dữ liệu quan trọng nhất để so với câu đã nói thật.

## Pass / Warn / Fail

### Pass

- `final` ra đủ ý chính của câu
- không bị dính text từ turn trước
- không bị lặp cụm từ bất thường
- `raw_backup_json` có `USER_TURN` đúng session
- với câu ngắn rõ ràng, sai khác nếu có chỉ là punctuation hoặc 1 từ không quan trọng

### Warn

- có `1` lỗi lexical nhỏ nhưng vẫn giữ đúng ý chính
- final hơi chậm nhưng vẫn ổn định
- UI nhìn ổn nhưng DB persist thiếu một số metadata không quan trọng
- noise làm `dbfs_avg` hoặc `noise_floor_db` tăng nhưng final vẫn giữ đúng ý

### Fail

- final rỗng dù user nói rõ
- final nhảy quá sớm hoặc quá muộn làm mất ý
- turn sau dính text của turn trước
- lặp câu hoặc lặp cụm rõ ràng
- barge-in làm hỏng final của turn kế tiếp
- `raw_backup_json` không persist được
- session không kết thúc sạch, hoặc `Last Session ID` không truy được row đúng

## Gate trước grading

Chỉ nối grading khi thỏa cả 4 điều kiện:

1. `0 critical fail` trong `10 session`
2. ít nhất `8/10 session` là `pass`
3. tất cả session đều truy ra được `raw_backup_json`
4. không có pattern lỗi lặp lại ở câu ngắn rõ ràng

Nếu chưa qua gate này, chưa nên chấm grading trên text live.

## Đọc STT Diagnostics

- `audio_ms` quá thấp với câu thật đã nói:
  - VAD/finalization đang cắt quá sớm.
- `speech_frames` thấp trong khi bạn nói rõ:
  - VAD đang bỏ sót tiếng nói hoặc threshold đang quá gắt.
- `silence_frames` rất thấp và final chậm:
  - nền/noise có thể đang giữ trạng thái speech quá lâu.
- `dbfs_avg` và `noise_floor_db` cùng tăng khi bật nhạc nền:
  - energy VAD đang tới giới hạn; ưu tiên speech-aware VAD.
- `audio_ms` đủ dài và frame stats hợp lý nhưng text sai nhiều:
  - mới xét STT model/prompt/beam/audio normalization.

## Khi fail thì quay lại đâu

- final sai nhịp hoặc nuốt đoạn:
  - xem lại `VAD`, `finalization`, trigger silence
- text dính turn trước:
  - xem lại reset state, session cleanup, previous-text context
- session không persist:
  - xem `luve_extension.py`, DB session row, và lifecycle `session_ended`
- UI khó debug:
  - ưu tiên sửa `control-center` trước khi tinh chỉnh model

## Ghi chú thực dụng

- `Một session thấy ổn` không có nghĩa là pipeline đã bền.
- `Offline WER tốt` không thay thế được live acceptance.
- Ưu tiên tìm lỗi hệ thống lặp lại trước khi tối ưu model hoặc tăng concurrency.
