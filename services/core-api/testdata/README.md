# STT Testdata

Thư mục này dùng cho bộ đo `final STT` với audio mẫu cố định.

Với `live WebRTC/TEN -> final STT`, xem thêm:

- [LIVE_STT_ACCEPTANCE.md](LIVE_STT_ACCEPTANCE.md)

## Cách dùng

1. Copy [stt_cases.example.json](stt_cases.example.json) thành `stt_cases.json`.
2. Đặt các file audio thật vào `testdata/audio/`.
3. Chạy:

```bash
cd services/core-api
source venv/bin/activate
python scripts/eval_stt_final.py --manifest testdata/stt_cases.json
```

## Quy tắc chọn audio mẫu

- Giữ cố định 1-3 file ngắn, dễ lặp lại.
- Mỗi file chỉ nên chứa 1 utterance final rõ ràng.
- Ưu tiên `.wav` hoặc `.m4a` thu từ đúng thiết bị người dùng thật.
- Không thay file cũ khi chưa lưu lại kết quả benchmark trước đó.
