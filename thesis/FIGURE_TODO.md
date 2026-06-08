# FIGURE_TODO — figures the LUVE thesis still needs

> **INTERNAL STUDENT NOTES — DO NOT PRINT IN THE THESIS PDF.**
> This file is a preparation checklist only. Nothing here is typeset into
> the compiled thesis. Instructions for "what image to prepare" may be in
> Vietnamese; the thesis body itself stays in English.
>
> **Ghi chú nội bộ cho sinh viên — KHÔNG đưa vào file PDF luận văn.**
> Đây chỉ là danh sách chuẩn bị hình ảnh. Hướng dẫn "cần vẽ/chụp hình gì"
> có thể viết bằng tiếng Việt; phần thân luận văn vẫn để tiếng Anh.

Place final images under `thesis/fig/` and uncomment the matching
`\includegraphics` line in `main.tex`. Each entry maps to a
`% TODO-FIGURE [VI]:` marker in `main.tex`.

> Only draw what the system actually does. Do not illustrate claims the
> system does not support (see `LUVE_FACTS.md` truth constraints).

| Key | File (suggested) | Where (main.tex) | What it must show |
|---|---|---|---|
| architecture_overview | `fig/architecture_overview.png` | §3.3.1 `\label{fig:arch}` | core-api (`main.py` REST :8000 + `run_ten.py` gateway :8080), grading-worker, PostgreSQL, RabbitMQ. Show HTTP/WebRTC client-facing and control boundaries, PostgreSQL persistence, and RabbitMQ asynchronous grading work; do not describe the system as communicating only over HTTP + RabbitMQ. |
| realtime_pipeline | `fig/realtime_pipeline.png` | §3.3.1 `\label{fig:pipeline}` | Hot-path VAD → STT → LLM → TTS → WebRTC. Note single-session-per-node cap. |
| erd | `fig/erd.png` | §3.3.2 `\label{fig:erd}` | ERD of: USERS, LESSONS, SESSIONS, GRADING_RESULTS, GRADING_SKIP_LOG, SESSION_OUTBOX. |
| ui_login | `fig/ui_login.png` | §3.3.3 `\label{fig:ui-login}` | Baseline `main` authentication entry point (xem ghi chú [VI] bên dưới). |
| ui_practice | `fig/ui_practice.png` | §3.3.3 `\label{fig:ui-practice}` | Real practice screen from `main`. **Do NOT** use the unmerged "cat companion" UI (PR #2) as baseline. |
| ui_saved_session | `fig/ui_saved_session.png` | §3.3.3 `\label{fig:ui-saved-session}` | Saved-session review / grading-result screen from the baseline client (xem ghi chú [VI] bên dưới). |
| session_grading_flow | `fig/session_grading_flow.png` | §3.3.4 `\label{fig:session-grading-flow}` | On session end: commit SESSIONS + session_outbox in one transaction, then attempt inline publish of `session.completed`; grading is idempotent (dedup on `session_id`); outbox relay default-off. |
| realtime_sequence | `fig/realtime_sequence.png` | §3.3.4 `\label{fig:realtime-sequence}` | Sequence diagram of the real-time speaking flow (xem ghi chú [VI] bên dưới). |
| publish_failure_flow | `fig/publish_failure_flow.png` | §3.3.4 `\label{fig:publish-failure-flow}` | Flowchart xử lý lỗi publish RabbitMQ (xem ghi chú [VI] bên dưới). |
| demo_session | `fig/demo_session.png` | §4.3.1 `\label{fig:demo-session}` | Screenshot of a live practice session (real run). |
| demo_grading | `fig/demo_grading.png` | §4.3.1 `\label{fig:demo-grading}` | Saved-session grading panel (real run). |

## TABLE_TODO — tables the LUVE thesis still needs

Each row tracks one actionable `% TODO-TABLE [VI]:` marker in `main.tex`, in
order of appearance. Fill only with real, verified data — do not fabricate
numbers (see truth constraints in `LUVE_FACTS.md`). Numbers in **bold** are the
explicit `Bảng N` labels written in `main.tex`; the others are sequential
tracking labels assigned here for unnumbered markers.

| Marker | Where (main.tex) | What it must show |
|---|---|---|
| **Bảng 3.1** | §3.3.1 | Module responsibilities: core-api `main.py` (:8000), core-api `run_ten.py` (:8080), grading-worker — ports/interfaces, main duties. Show HTTP/WebRTC client-facing and control boundaries, PostgreSQL persistence, and RabbitMQ asynchronous grading work; do not describe the system as communicating only over HTTP + RabbitMQ. |
| Bảng 3.2 | §3.3.2 | Summary of the 6 core DB tables (USERS, LESSONS, SESSIONS, GRADING_RESULTS, GRADING_SKIP_LOG, SESSION_OUTBOX): purpose + key columns. |
| Bảng 4.1 | §4.1 | Technology & dev environment: language, framework, DB, broker, STT, client, container — name + role (do not fabricate versions). |
| **Bảng 4.2** | §4.1 | Demo STT/grading config: `small.en` + `forced_en` + second-pass off; `GRADING_PROVIDER=fake`, `GRADING_FAKE_FALLBACK` off, `OUTBOX_RELAY_ENABLED=false`. |
| Bảng 4.3 | §4.2.1 | Main module implementation: module, main file/service, responsibility, limitation note (core-api `main.py`/`run_ten.py`, grading-worker, etc.). |
| Bảng 4.4 | §4.2.2 | Main data-processing flow: data source, processing step, processing module, output data, limitation/caveat. |
| Bảng 4.5 | §4.3.1 | Achieved results at system level: capability, related module, demo evidence, limitation/caveat. |
| Bảng 4.6 | §4.4 | Testing / verification: item, how checked, expected result, status, limitation/caveat. Real results only. |
| **Bảng 5.1** | §5.3 | Limitations vs. future direction, one row per limitation from `LUVE_FACTS.md`. |
| **Bảng B.1** | Appendix B | Survey results (only if a real survey is run). |

## Ghi chú chuẩn bị hình §3.3.3 (nội bộ, tiếng Việt)

### `fig/ui_login.png` — `\label{fig:ui-login}`
- Chụp màn hình **điểm vào xác thực (authentication entry point)** của client.
- Ảnh BẮT BUỘC lấy từ baseline `main@6a61bc8`, **KHÔNG dùng UI "cat companion"
  của PR #2**.

### `fig/ui_practice.png` — `\label{fig:ui-practice}`
- Chụp màn hình **luyện nói thời gian thực** của client (baseline `main@6a61bc8`).
- **KHÔNG dùng UI "cat companion" của PR #2.**

### `fig/ui_saved_session.png` — `\label{fig:ui-saved-session}`
- Chụp màn hình **xem lại phiên đã lưu / hiển thị kết quả chấm điểm** của client.
- Thể hiện trạng thái chấm điểm **pending / available / skipped** nếu nhìn thấy
  được trong baseline.
- **KHÔNG dùng UI "cat companion" của PR #2.**

## Ghi chú chuẩn bị hình §3.3.4 (nội bộ, tiếng Việt)

### `fig/realtime_sequence.png` — `\label{fig:realtime-sequence}`
- Sequence diagram cho **luồng nói thời gian thực**:
  browser (audio/control) -> TEN/WebRTC gateway -> VAD/chunking (nếu có) ->
  STT `forced_en + small.en` -> realtime LLM tutor sinh câu phản hồi hội thoại ->
  đường ra TTS/WebRTC khi bật âm thanh trợ giảng (tutor audio).
- **KHÔNG** thể hiện chấm điểm/scoring thời gian thực trong hình này
  (realtime LLM chỉ sinh phản hồi hội thoại; chấm điểm là bất đồng bộ).

### `fig/publish_failure_flow.png` — `\label{fig:publish-failure-flow}`
- Flowchart xử lý lỗi publish RabbitMQ:
  transaction hoàn tất phiên ghi DB thành công -> ghi đồng thời session row và
  session_outbox row -> inline publish RabbitMQ THẤT BẠI -> ghi warning log ->
  outbox row vẫn còn -> khôi phục bằng relay/thủ công, relay mặc định TẮT
  (default-off) trừ khi được bật.
- Ghi nhãn đây là khôi phục theo hướng **at-least-once / idempotent (lũy đẳng)**,
  **KHÔNG** phải exactly-once.

## Notes
- Prefer vector/PNG screenshots from a **real** run; do not mock results.
- If a figure cannot be produced from the real system, remove its
  `\begin{figure}` block rather than faking it.
- Pronunciation visuals must be labelled as a **clarity estimate from STT
  confidence/uncertainty**, never as phoneme/acoustic scoring.
