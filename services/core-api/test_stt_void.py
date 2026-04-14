from faster_whisper import WhisperModel
import time
import os

# Đường dẫn file của bạn
audio_path = "/home/minhthuy/project/luve/services/core-api/void1.mp3"

# Kiểm tra file có tồn tại không trước khi nã đạn
if not os.path.exists(audio_path):
    print(f"❌ Lỗi: Không tìm thấy file tại {audio_path}")
    exit()

model_size = "small"
print(f"--- Đang nạp Model {model_size} vào GPU RTX 3050 Ti... ---")

# Khởi tạo model với cấu hình tối ưu cho 4GB VRAM
model = WhisperModel(model_size, device="cuda", compute_type="float16")

print(f"--- Đang xử lý file: {os.path.basename(audio_path)} ---")
start_time = time.time()

# word_timestamps=True: Để lấy time và % cho từng từ
segments, info = model.transcribe(audio_path, beam_size=5, word_timestamps=True)

print(f"Phát hiện ngôn ngữ: {info.language} ({info.language_probability:.2%})")
print("-" * 50)

for segment in segments:
    for word in segment.words:
        # In ra: [Bắt đầu -> Kết thúc] Từ (Độ tự tin %)
        print(f"[{word.start:5.2f}s -> {word.end:5.2f}s] {word.word:15} | Conf: {word.probability:.2%}")

end_time = time.time()
print("-" * 50)
print(f"🚀 Tổng thời gian xử lý: {end_time - start_time:.2f} giây")
for segment in segments:
    print(f"\n--- Segment Metadata ---")
    print(f"Confidence đoạn: {segment.avg_logprob:.2f}")
    print(f"Xác suất không phải tiếng người: {segment.no_speech_prob:.2%}")
    
    for word in segment.words:
        # In thêm cả thuộc tính 'probability' (xác suất của từng token)
        status = "✅ OK" if word.probability > 0.6 else "❌ FAIL"
        print(f"[{word.start:5.2f}s] {word.word:15} | Conf: {word.probability:.2%} | {status}")