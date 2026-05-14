> Historical note: nội dung này là roadmap/progress cũ, có thể đã lệch với code/runtime hiện tại. Không dùng làm source of truth.

  🟢 Đã hoàn thành: 60% (The Skeleton & The Soul)

  Đây là phần khó nhất, tốn nhiều chất xám nhất về mặt hạ tầng mạng và âm thanh thời gian thực.

   * Hạ tầng Core (20%): Đã thiết lập xong Docker, Database (PostgreSQL), Message Queue (RabbitMQ), In-memory Cache (Redis), và cấu trúc thư mục FastAPI.

   * WebRTC & Signaling (15%): Đã mở được cổng giao tiếp Full-duplex giữa App và Server. Khắc phục được các lỗi ICE Candidate và luồng SDP Offer/Answer.

   * Voice Pipeline - STT & VAD (15%): Vừa hoàn thiện xong! Hệ thống đã biết lắng nghe, lọc ồn (VAD 800ms), bắt phụ đề cực nhạy (cửa sổ 3000ms), chống ảo giác (Anti-Hallucination), và hiển thị mượt mà trên UI.

   * AI Brain & TTS Cơ bản (10%): Luồng cơ bản từ STT -> LLM (Prompt sư phạm) -> TTS (Phát ra âm thanh) đã thông suốt. Tính năng ngắt lời (Barge-in/Spacebar) cũng đã được cấu trúc.



  🟡 Đang dở dang & Cần hoàn thiện: 15% (Advanced Conversation)

  Để hội thoại thực sự tự nhiên như "người thật" (chuẩn LiveKit):

   * Bảo lưu Ngữ cảnh (Context Memory): Hiện tại LLM mới chỉ trả lời dựa trên câu nói cuối cùng của User. Chúng ta cần nạp lịch sử hội thoại (5-10 câu gần nhất) vào Prompt để AI nhớ được toàn bộ ngữ cảnh.

   * Âm thanh đệm (Backchanneling): Tính năng AI tự động chêm vào các từ "Uhm", "I see", "Right" trong lúc đợi xử lý để lấp khoảng trống im lặng.

   * Lưu trữ Hộp đen (Blackbox Persistence): Vừa làm xong phần thu thập (Log) vào RAM, nhưng chưa viết logic để hốt cục Log đó ném vào Redis và Postgres khi kết thúc cuộc gọi.



  🔴 Chưa bắt đầu: 25% (The Judge - Hệ thống chấm điểm)

  Đây là linh hồn sư phạm của dự án, biến LUVE từ một con "Chatbot bằng giọng nói" thành một "Gia sư thực thụ".

   * Async Worker Backend: Xây dựng các Worker chạy ngầm lắng nghe RabbitMQ.

   * AI Grading Engine: Dùng LLM mạnh (Gemini 1.5 Pro / GPT-4o) để đọc lại toàn bộ file "Hộp đen", phân tích lỗi ngữ pháp, phát âm (dựa trên thời gian ngập ngừng), từ vựng và xuất ra JSON bảng điểm.

   * Profile & Auto-Leveling: Cập nhật điểm số vào Database, tính toán tiến độ và tự động tăng/giảm Level cho học viên.



  Tóm lại:

  Chúng ta đã vượt qua được ngọn núi khó nhằn nhất là "Thời gian thực" (Real-time Audio Processing). Phần còn lại (40%) thiên về Logic Dữ liệu (Data Engineering) và Thiết kế Prompt (Prompt Engineering). Phần này

  quen thuộc với các lập trình viên Backend hơn và sẽ đi rất nhanh nếu chúng ta làm đúng thiết kế kiến trúc.
 1. Nhìn lại những gì đã làm (The Foundation)
  Chúng ta đã vượt qua giai đoạn "Sống còn":
   * Hạ tầng: Docker, Database, Redis, RabbitMQ đã thông suốt.
   * Audio Real-time: WebRTC ổn định, STT không còn bị ảo giác (hallucination), VAD bắt âm nhạy và tự nhiên.
   * UI: Phụ đề đã hiển thị dạng "cuộn" (rolling), không bị mất chữ.
   * Dữ liệu thô: Đã thiết lập được "Hộp đen" trong RAM để ghi lại từng miligiây hội thoại.

  ---

  2. Kế hoạch Tối ưu Token & Hiệu suất AI
  Để tránh việc tôi bị "ngộp" dữ liệu và tốn token vô ích, tôi sẽ áp dụng các chiến thuật sau:
   * Sliding Window Context: Trong logic hội thoại, ta chỉ gửi 5-10 câu gần nhất lên LLM. Không gửi toàn bộ lịch sử từ đầu buổi học.
   * Sử dụng Sub-agents: Khi cần sửa hàng loạt file hoặc điều tra lỗi sâu trong code, tôi sẽ gọi codebase_investigator hoặc generalist để xử lý cục bộ, giữ cho "đầu óc" của tôi (main context) luôn nhẹ nhàng và
     tập trung vào kiến trúc tổng thể.
   * Prompt Compression: Chuyển các hướng dẫn dài dòng vào các file .rule hoặc .env để AI đọc một lần và ghi nhớ, không cần nhắc lại mỗi lượt chat.

  ---

  3. Lộ trình thực hiện tiếp theo (The Roadmap)

  Giai đoạn 1: Kết nối Dữ liệu (The Data Bridge) - ƯU TIÊN SỐ 1
   * Mục tiêu: Đưa "Hộp đen" từ RAM xuống Database một cách an toàn.
   * Công việc: 
       * Viết logic bắt sự kiện on_shutdown của Session.
       * Đóng gói toàn bộ event_log thành JSON.
       * Lưu vào cột raw_backup_json trong bảng SESSIONS.
       * Bắn tín hiệu (Message) vào RabbitMQ để báo cho Worker.

  Giai đoạn 2: Trí nhớ hội thoại (The Memory)
   * Mục tiêu: AI nói chuyện thông minh, nhớ được những gì đã nói ở câu trước.
   * Công việc: 
       * Tích hợp Redis để lưu Conversation History cho từng Session.
       * Cập nhật brain.py để nạp History này vào mỗi lượt trả lời.
       * Tối ưu Prompt để AI phản hồi ngắn gọn, tự nhiên như người bản xứ.

  Giai đoạn 3: Hội đồng chấm điểm (The Grading Worker)
   * Mục tiêu: Chấm điểm sư phạm sau khi cúp máy.
   * Công việc:
       * Xây dựng script grading_worker.py.
       * Kết nối Worker với RabbitMQ.
       * Thiết kế "Prompt Giám khảo": Đọc bản Raw, phân tích phát âm (ngập ngừng), ngữ pháp, từ vựng.
       * Lưu kết quả vào bảng GRADING_RESULTS.

  Giai đoạn 4: Đánh giá & Tăng cấp (The Evolution)
   * Mục tiêu: Hiển thị kết quả cho người dùng và tự động hóa lộ trình học.
   * Công việc:
       * Thiết kế API để App lấy kết quả chấm điểm.
       * Xây dựng logic Auto-leveling: Nếu 3 bài liên tiếp điểm > 80, gợi ý nâng Level.
