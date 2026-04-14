from faster_whisper import WhisperModel
import time

# Cấu hình: Dùng model 'small' để cân bằng giữa tốc độ và độ chính xác
# Với 4GB VRAM, bản 'small' sẽ chạy cực mượt (chỉ tốn khoảng 1GB VRAM)
model_size = "small"

print(f"--- Đang nạp Model {model_size} vào GPU... ---")
# device="cuda" để ép nó chạy trên RTX 3050 Ti
# compute_type="float16" để tối ưu hóa tốc độ trên kiến trúc Ampere của bạn
model = WhisperModel(model_size, device="cuda", compute_type="float16")

print("--- Bắt đầu nhận diện (giả lập)... ---")
start_time = time.time()

audio_url = "https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac"
segments, info = model.transcribe(audio_url, beam_size=5)

print(f"Phát hiện ngôn ngữ: {info.language} với xác suất {info.language_probability:.2f}")

for segment in segments:
    print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")

end_time = time.time()
print(f"--- Hoàn thành trong: {end_time - start_time:.2f} giây ---")

# Sửa lại dòng này trong script của bạn
segments, info = model.transcribe(audio_url, beam_size=5, word_timestamps=True)

print("-" * 30)
for segment in segments:
    for word in segment.words:
        print(f"[{word.start:5.2f}s -> {word.end:5.2f}s] {word.word:15} (Conf: {word.probability:.2%})")