# Chương 2: Cơ Sở Lý Thuyết

---

## 2.1 Tổng Quan Hệ Thống Luyện Nói Tiếng Anh Bằng AI

### 2.1.1 Bài toán luyện nói và vai trò phản hồi tức thì

Trong lĩnh vực dạy học ngoại ngữ, *corrective feedback* — phản hồi sửa lỗi kịp thời — được xem là yếu tố quan trọng trong quá trình luyện tập. Người học nói tiếng Anh tại môi trường phi bản ngữ thường thiếu cơ hội nhận phản hồi tức thì: giáo viên không phải lúc nào cũng sẵn có, và các ứng dụng học truyền thống chủ yếu tập trung vào từ vựng — ngữ pháp theo dạng bài tập tĩnh.

Một hệ thống luyện nói AI theo thời gian thực nhằm thu hẹp khoảng cách đó: người học nói bằng giọng thật, hệ thống lắng nghe, phản hồi bằng ngôn ngữ tự nhiên trong vài giây, và ghi lại bản ghi hội thoại để đánh giá chất lượng ngôn ngữ sau phiên.

### 2.1.2 Các thành phần cốt lõi của một hệ thống hội thoại giọng nói

Một hệ thống hội thoại giọng nói thời gian thực thường gồm năm thành phần chính:

| Thành phần | Vai trò |
|-----------|---------|
| Vận chuyển audio (Transport) | Đưa luồng audio từ client đến server với độ trễ thấp |
| Phát hiện hoạt động giọng nói (VAD) | Xác định thời điểm người dùng bắt đầu và kết thúc nói |
| Nhận dạng giọng nói (STT) | Chuyển đổi audio thành văn bản |
| Sinh phản hồi (LLM) | Tạo câu trả lời hội thoại tự nhiên |
| Tổng hợp giọng nói (TTS) | Chuyển văn bản phản hồi thành audio phát lại cho người dùng |

Ngoài luồng thời gian thực, các hệ thống luyện nói còn cần một thành phần đánh giá chất lượng ngôn ngữ — thường được thực hiện sau phiên để không ảnh hưởng đến độ trễ hội thoại.

### 2.1.3 Thách thức kỹ thuật chính

- **Độ trễ tích lũy**: Mỗi bước VAD → STT → LLM → TTS đều thêm độ trễ. Tổng độ trễ phải đủ thấp để người dùng không cảm thấy gián đoạn.
- **Chất lượng nhận dạng dưới điều kiện tải**: GPU chia sẻ giữa nhiều người dùng gây suy giảm thời gian inference.
- **Cô lập người dùng**: Mỗi người dùng cần tài nguyên độc lập để tránh can thiệp lẫn nhau.
- **Đánh giá không đồng bộ**: Chấm điểm ngôn ngữ bằng LLM tốn thời gian và không nên nằm trong luồng realtime.

Chương 3 mô tả cách LUVE giải quyết các thách thức này; Chương 4 trình bày kết quả đo lường thực nghiệm.

---

## 2.2 WebRTC và Truyền Thông Thời Gian Thực

### 2.2.1 Khái niệm WebRTC

WebRTC (*Web Real-Time Communication*) là tập hợp các chuẩn và API cho phép truyền audio, video và dữ liệu trực tiếp giữa hai điểm cuối (peer-to-peer hoặc client-server) với độ trễ thấp, không cần plugin trình duyệt. WebRTC bao gồm các giao thức chính:

- **ICE** (*Interactive Connectivity Establishment*): thu thập và kiểm tra các candidate địa chỉ mạng để tìm đường kết nối tốt nhất giữa hai điểm cuối.
- **SDP** (*Session Description Protocol*): mô tả thông số phiên (codec, địa chỉ mạng, định dạng media) được trao đổi qua signaling.
- **DTLS** (*Datagram Transport Layer Security*): mã hóa và xác thực danh tính trên UDP.
- **SRTP** (*Secure Real-time Transport Protocol*): đóng gói và bảo mật luồng audio/video.

Quá trình thiết lập kết nối WebRTC gồm hai bước chính: *SDP offer/answer* (trao đổi thông số phiên) và *ICE negotiation* (thương lượng địa chỉ mạng). Sau khi hoàn thành, audio được truyền liên tục theo thời gian thực.

### 2.2.2 aiortc — triển khai WebRTC thuần Python

**aiortc** là thư viện Python mã nguồn mở triển khai đầy đủ stack WebRTC, bao gồm ICE, DTLS, SRTP, và codec audio/video. aiortc cho phép xây dựng WebRTC server thuần Python mà không cần phụ thuộc vào runtime ngoại vi hay ngôn ngữ biên dịch.

Lợi thế của aiortc trong bối cảnh LUVE:
- Kiểm soát toàn bộ vòng đời phiên trong cùng một tiến trình Python với các thành phần STT, LLM, TTS.
- Dễ tích hợp với asyncio — mô hình lập trình bất đồng bộ phù hợp với xử lý audio stream.
- Không cần cài đặt media server riêng biệt.

Trong LUVE, gateway WebRTC được xây dựng hoàn toàn bằng aiortc. Tên file cấu hình (`graph.json`, `manifest.json`, `property.json`) lấy cảm hứng từ định dạng TEN framework nhưng không được thực thi bởi TEN runtime — gateway là một triển khai aiortc tùy chỉnh.

### 2.2.3 Signaling và độ trễ thiết lập

Signaling — quá trình trao đổi SDP và ICE candidate — là bước trước khi audio bắt đầu chảy. Thời gian thiết lập DataChannel (`dc_ms` trong LUVE) phụ thuộc vào tốc độ hoàn thành ICE và tải CPU khi đó. Ở mức tải thấp, `dc_ms` thường dưới 400 ms; ở mức tải cao (6 tiến trình gateway đồng thời), spike có thể đạt trên 1.200 ms trong vòng đầu khi các mô hình Whisper đang tải.

---

## 2.3 Nhận Dạng Giọng Nói Tự Động (STT) và Whisper

### 2.3.1 Nguyên lý nhận dạng giọng nói tự động

Nhận dạng giọng nói tự động (ASR/STT) là bài toán ánh xạ tín hiệu audio sang chuỗi ký tự văn bản. Các hệ thống ASR hiện đại dựa trên kiến trúc end-to-end, sử dụng mạng nơ-ron học trực tiếp từ cặp (audio, transcript) mà không cần mô hình âm vị học hoặc ngôn ngữ học rời rạc.

Trước khi đưa vào mô hình ASR, tín hiệu audio thường đi qua bước **VAD** (*Voice Activity Detection*): phân loại từng đoạn audio là "giọng nói" hay "không giọng nói". VAD giúp tránh gửi khoảng lặng hoặc nhiễu nền vào mô hình STT, tiết kiệm tài nguyên tính toán và giảm xác suất hallucination.

### 2.3.2 Whisper và Faster-Whisper

**Whisper** của OpenAI là mô hình ASR đa ngôn ngữ dựa trên kiến trúc Transformer encoder-decoder, được huấn luyện trên lượng lớn dữ liệu audio có nhãn thu thập từ nhiều nguồn khác nhau. Whisper đạt độ chính xác cao cho tiếng Anh ở nhiều giọng vùng miền và chất lượng audio khác nhau.

**Faster-Whisper** là triển khai lại của Whisper sử dụng thư viện CTranslate2, cho phép chạy mô hình với lượng tử hóa int8 hoặc int8_float16 trên GPU, giảm đáng kể thời gian inference và mức tiêu thụ VRAM so với triển khai gốc.

LUVE sử dụng `Whisper small.en` (tối ưu cho tiếng Anh) với lượng tử hóa `int8_float16` trên GPU. Mỗi tiến trình gateway duy trì một **singleton** `WhisperInference._instance` — nạp mô hình lần đầu khi có inference, giữ trong bộ nhớ GPU cho các inference tiếp theo. Chi phí VRAM đo được: khoảng **466 MiB** mỗi instance trên RTX 3050 Ti.

### 2.3.3 Bộ lọc chất lượng đầu ra STT

Whisper có thể sinh ra văn bản ngay cả với audio chất lượng thấp hoặc khoảng lặng — hiện tượng gọi là *hallucination*. LUVE áp dụng các bộ lọc sau trên kết quả Whisper:

- `probable_hallucination`: phát hiện khuôn mẫu văn bản lặp đặc trưng của hallucination.
- `low_average_logprob`: lọc transcript có xác suất log trung bình dưới ngưỡng — thường là audio nhiễu.
- `short_speech`: bỏ qua lượt nói quá ngắn để tránh xử lý ngắn gián không có nội dung.

Khi bộ lọc kích hoạt, lượt nói bị *suppress* — không được đưa vào LLM. Đây là hành vi bảo vệ đúng, không phải lỗi hệ thống.

---

## 2.4 Mô Hình Ngôn Ngữ Lớn Trong Hội Thoại

### 2.4.1 Vai trò của LLM trong hệ thống luyện nói

Mô hình ngôn ngữ lớn (LLM) đóng vai trò kép trong LUVE:

1. **Sinh phản hồi hội thoại**: Nhận văn bản từ Whisper và sinh ra phản hồi tiếng Anh tự nhiên, đóng vai trò đối tác hội thoại AI.
2. **Chấm điểm ngôn ngữ**: Phân tích bản ghi hội thoại sau phiên để đánh giá phát âm, từ vựng, ngữ pháp, và mạch lạc.

### 2.4.2 Triển khai LLM trong hệ thống realtime

Gọi LLM trong luồng thời gian thực đặt ra yêu cầu về độ trễ: người dùng không muốn chờ quá vài giây để nhận phản hồi. Các lựa chọn triển khai phổ biến:

- **API đám mây với tốc độ cao** (ví dụ: Groq API): phù hợp cho prototype, độ trễ thấp nhờ phần cứng chuyên dụng, nhưng phụ thuộc vào kết nối mạng và giới hạn API.
- **Mô hình cục bộ**: không phụ thuộc mạng, nhưng yêu cầu GPU và RAM đủ mạnh.

LUVE hỗ trợ cả hai lựa chọn qua biến môi trường. Trong kiểm thử, Groq API (Llama-3) được sử dụng cho luồng realtime; chấm điểm sau phiên có thể dùng cùng API hoặc mô hình khác.

### 2.4.3 LLM cho chấm điểm ngôn ngữ

Chấm điểm ngôn ngữ bằng LLM là hướng tiếp cận mới so với các phương pháp truyền thống (so sánh transcript với chuỗi tham chiếu, đo WER). LLM có thể đánh giá theo nhiều chiều — phát âm (qua transcript), từ vựng, ngữ pháp, mạch lạc — và sinh ra phản hồi văn bản giải thích cho người học.

Tuy nhiên, độ chính xác của điểm số LLM phụ thuộc nhiều vào thiết kế prompt và calibration. Đây là lĩnh vực đang phát triển và vẫn cần kiểm chứng bằng đánh giá chuyên gia ngôn ngữ.

---

## 2.5 Text-to-Speech Trong Hệ Thống Luyện Nói

### 2.5.1 Vai trò của TTS

Text-to-Speech (TTS) chuyển đổi văn bản phản hồi từ LLM thành tín hiệu audio phát lại cho người học. Trong hệ thống luyện nói, chất lượng TTS ảnh hưởng trực tiếp đến trải nghiệm người học: giọng nói tự nhiên giúp người học dễ nghe và học theo mẫu phát âm của AI.

### 2.5.2 edge-tts

**edge-tts** là thư viện Python giao tiếp với dịch vụ TTS của Microsoft Edge, cung cấp giọng đọc chất lượng cao với độ trễ thấp và không cần GPU. edge-tts hỗ trợ nhiều giọng tiếng Anh (US, UK, AU) và cho phép điều chỉnh tốc độ, âm điệu.

Trong LUVE, edge-tts là bước cuối cùng của luồng realtime: sau khi LLM sinh văn bản phản hồi, edge-tts tổng hợp audio và gateway phát lại cho người dùng qua WebRTC track.

### 2.5.3 Cân nhắc cho hệ thống luyện nói

Ngoài chất lượng audio, hai yếu tố quan trọng khi chọn TTS cho hệ thống luyện nói:

- **Độ trễ đầu tiên** (*first audio latency*): thời gian từ khi gọi TTS đến khi byte audio đầu tiên sẵn sàng. Độ trễ thấp cho phép streaming audio từng đoạn thay vì chờ toàn bộ câu.
- **Độ tự nhiên**: TTS quá "robot" giảm hiệu quả mô hình hóa phát âm cho người học.

---

## 2.6 Kiến Trúc Bất Đồng Bộ Với Hàng Đợi Thông Điệp

### 2.6.1 Lý do tách biệt luồng chấm điểm

Chấm điểm một phiên hội thoại bằng LLM thường mất vài giây — không thể thực hiện đồng bộ trong luồng WebRTC mà không tăng độ trễ người dùng. Kiến trúc bất đồng bộ giải quyết điều này bằng cách: luồng realtime kết thúc ngay sau phiên, gửi sự kiện vào hàng đợi, và một worker xử lý chấm điểm độc lập.

Lợi ích của hướng tiếp cận này:
- Độ trễ của luồng realtime không bị ảnh hưởng bởi tác vụ nặng.
- Nếu chấm điểm thất bại, phiên nói đã hoàn thành vẫn được bảo toàn.
- Worker có thể scale ngang: nhiều instance xử lý song song.

### 2.6.2 RabbitMQ và giao thức AMQP

**RabbitMQ** là message broker mã nguồn mở triển khai giao thức AMQP (*Advanced Message Queuing Protocol*). Các khái niệm chính:

- **Producer**: thành phần gửi tin nhắn vào hàng đợi (trong LUVE: gateway WebRTC).
- **Queue**: bộ đệm bền vững lưu tin nhắn cho đến khi consumer xử lý.
- **Consumer**: thành phần nhận và xử lý tin nhắn (trong LUVE: grading worker).
- **Acknowledgment (ACK)**: consumer xác nhận xử lý thành công; nếu không ACK, tin nhắn được gửi lại.
- **prefetch_count**: giới hạn số tin nhắn chưa ACK mà consumer nhận tại một thời điểm; giá trị 1 đảm bảo mỗi worker xử lý tuần tự từng phiên.

### 2.6.3 Ứng dụng trong LUVE

LUVE sử dụng hàng đợi `luve.session.completed`. Khi một phiên WebRTC kết thúc, gateway publish sự kiện chứa `session_id`. Grading worker tiêu thụ hàng đợi với `prefetch_count=1`, kiểm tra điều kiện đủ tư cách, và ghi kết quả vào PostgreSQL. Cơ chế `ON CONFLICT DO UPDATE` trong `log_grading_skip()` đảm bảo idempotency — worker có thể xử lý lại cùng một tin nhắn mà không tạo bản ghi trùng lặp.

---

## 2.7 Kiến Trúc Scale-Out Và Xử Lý Nhiều Người Dùng

### 2.7.1 Mở rộng dọc và mở rộng ngang

Có hai hướng mở rộng hệ thống khi nhu cầu tăng:

- **Mở rộng dọc** (*vertical scaling*): tăng tài nguyên (RAM, CPU, GPU) của một máy. Đơn giản nhưng bị giới hạn bởi phần cứng tối đa và không tăng khả năng chịu lỗi.
- **Mở rộng ngang** (*horizontal scaling*): chạy nhiều instance của cùng một dịch vụ trên nhiều máy hoặc nhiều tiến trình. Linh hoạt hơn nhưng đòi hỏi thiết kế kiến trúc phù hợp (stateless, cô lập tài nguyên).

### 2.7.2 Cô lập tiến trình và tài nguyên GPU

Khi một ứng dụng cần GPU (ví dụ: inference mô hình học sâu), cô lập theo tiến trình có lợi thế rõ ràng: mỗi tiến trình có không gian bộ nhớ GPU riêng, tránh tranh chấp mutex cấp thư viện, và lỗi trong một tiến trình không ảnh hưởng tiến trình khác.

Trong bối cảnh WebRTC, mô hình một tiến trình một phiên (*one process, one session*) còn đơn giản hóa việc quản lý vòng đời tài nguyên: khi phiên kết thúc, tiến trình giải phóng tài nguyên tự nhiên mà không cần garbage collection phức tạp.

### 2.7.3 Ứng dụng trong LUVE

LUVE đạt được hỗ trợ đa người dùng bằng cách chạy **N tiến trình uvicorn độc lập** trên N cổng khác nhau (8081, 8082, ..., 808N). Mỗi tiến trình áp đặt giới hạn cứng `TEN_SINGLE_SESSION_CAPACITY = 1`: chỉ một phiên WebRTC tại một thời điểm. Tiến trình thứ hai xin kết nối nhận HTTP 503.

Thiết kế này có một số đặc điểm quan trọng:
- Không cần thay đổi code để mở rộng; chỉ cần khởi động thêm tiến trình.
- Mỗi tiến trình nạp một instance Whisper riêng (~466 MiB VRAM) khi có inference đầu tiên.
- Tất cả tiến trình gateway chia sẻ một Core API, một PostgreSQL, một RabbitMQ — các dịch vụ này là *shared stateful*.
- Giới hạn thực tế trên một máy đơn bị quyết định bởi ngân sách VRAM và tải CPU/GPU.

Trên RTX 3050 Ti (4 GiB VRAM), 6 tiến trình (tức 6 người dùng đồng thời) sử dụng khoảng 2.398 MiB VRAM — còn lại 1.373 MiB. Kịch bản 8 tiến trình không được kiểm thử do rủi ro CUDA OOM khi 8 inference đồng thời đạt đỉnh.

---

## 2.8 Kiểm Thử Phần Mềm Và Traceability Trong Hệ Thống AI Realtime

### 2.8.1 Thách thức kiểm thử hệ thống AI realtime

Kiểm thử hệ thống tích hợp AI đặt ra những thách thức không có trong phần mềm truyền thống:

- **Không xác định**: Kết quả của LLM, STT, hay VAD không hoàn toàn tất định — cùng input có thể cho output khác nhau theo điều kiện phần cứng và phiên bản mô hình.
- **Phụ thuộc dịch vụ ngoài**: Nhiều thành phần cần GPU, database, API bên ngoài — không thể chạy trong môi trường CI thông thường.
- **Khó tái hiện kết quả**: Các lỗi liên quan đến race condition hoặc tải GPU có thể không tái hiện trong môi trường kiểm thử đơn giản.

### 2.8.2 Kiểm thử theo lớp

Chiến lược kiểm thử theo lớp phân tách các kiểm thử theo mức độ rủi ro và yêu cầu tài nguyên:

- **Lớp 1 — Kiểm thử đơn vị an toàn**: Kiểm tra từng module riêng lẻ với các dependency được thay thế bằng mock (giả lập). Không cần dịch vụ thật, chạy nhanh và có thể tự động hóa hoàn toàn. Phù hợp để kiểm tra logic nghiệp vụ (eligibility gate, repository).
- **Lớp 2 — Kiểm thử tích hợp / smoke live**: Kiểm tra toàn bộ hệ thống với dịch vụ thật. Cần phê duyệt từng lần, yêu cầu GPU và tất cả dịch vụ đang chạy. Phù hợp để kiểm tra luồng end-to-end và hành vi dưới tải.

### 2.8.3 Traceability — truy vết yêu cầu đến bằng chứng

*Traceability* là khả năng truy ngược từ một test case đến yêu cầu hệ thống mà nó kiểm chứng, và từ yêu cầu đến bằng chứng đã thu thập. Trong hệ thống AI, traceability quan trọng vì:
- Không thể kiểm thử toàn bộ không gian đầu vào; cần chứng minh *yêu cầu gì* đã được kiểm chứng.
- Bằng chứng dạng artifact (log, report) có thể xem lại độc lập với môi trường chạy.

LUVE tổ chức traceability qua ba tầng: yêu cầu (R-01..R-10) → test case (TC-01..TC-MG-001) → artifact bằng chứng (committed reports, commit history). Ma trận traceability được duy trì tại `docs/testing/TRACEABILITY_MATRIX.md`.

### 2.8.4 Mock database trong kiểm thử đơn vị

Grading worker của LUVE phụ thuộc vào PostgreSQL để đọc dữ liệu phiên và ghi kết quả. Trong unit test, các lời gọi database được thay thế bằng mock objects — đối tượng giả lập trả về giá trị định trước. Điều này cho phép kiểm tra logic nghiệp vụ (ví dụ: `evaluate_grading_eligibility()` với bốn trường hợp bỏ qua) mà không cần PostgreSQL đang chạy.

Tuy nhiên, mock database không thể kiểm chứng hành vi ON CONFLICT DO UPDATE hay các constraint cơ sở dữ liệu thực tế — đây là lý do kiểm thử tích hợp với database thật (TC-09) vẫn cần thiết.

---

## 2.9 Tổng Kết Chương

Chương này đã trình bày nền tảng lý thuyết và kỹ thuật cho hệ thống LUVE, bao gồm:

- **WebRTC và aiortc**: giao thức và thư viện cho phép truyền audio thời gian thực; LUVE sử dụng aiortc thuần Python thay vì TEN native SDK.
- **Whisper và Faster-Whisper**: mô hình STT hiện đại với chi phí VRAM xác định (~466 MiB/instance) và cơ chế lazy loading per-process.
- **LLM**: vai trò kép trong LUVE — sinh phản hồi hội thoại và chấm điểm ngôn ngữ sau phiên; vấn đề calibration điểm số là hướng mở trong tương lai.
- **edge-tts**: TTS chất lượng cao, không cần GPU, là bước cuối luồng realtime.
- **RabbitMQ**: hàng đợi thông điệp bền vững tách biệt luồng chấm điểm khỏi luồng thời gian thực; `prefetch_count=1` và ON CONFLICT DO UPDATE đảm bảo xử lý tin cậy và idempotent.
- **Scale-out đa tiến trình**: N tiến trình trên N cổng — không thay đổi code, cô lập VRAM, giới hạn bởi ngân sách phần cứng.
- **Kiểm thử theo lớp và traceability**: chiến lược phân tách kiểm thử an toàn và smoke live, truy vết yêu cầu đến bằng chứng.

Chương 3 áp dụng các khái niệm này vào thiết kế cụ thể của hệ thống LUVE. Chương 4 trình bày kết quả kiểm thử thực nghiệm xác nhận tính khả thi của kiến trúc trong phạm vi môi trường phát triển cục bộ.
