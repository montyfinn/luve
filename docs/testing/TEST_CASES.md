# Test Cases — LUVE Thesis Evidence

Legend: **[A]** = Automated by `run_thesis_evidence.sh` | **[M]** = Manual / approved live

---

## TC-01: Python compile — session_eligibility.py [A]

**Purpose:** Verify the eligibility gate module has no syntax errors.  
**Command:** `python -m py_compile services/grading-worker/src/session_eligibility.py`  
**Pass:** Exit code 0, no stderr output.  
**Fail:** Any SyntaxError or ImportError printed to stderr.

---

## TC-02: Python compile — grading_repository.py [A]

**Purpose:** Verify repository layer has no syntax errors.  
**Command:** `python -m py_compile services/grading-worker/src/grading_repository.py`  
**Pass:** Exit code 0.  
**Fail:** Any SyntaxError.

---

## TC-03: Python compile — worker.py [A]

**Purpose:** Verify worker entrypoint has no syntax errors.  
**Command:** `python -m py_compile services/grading-worker/src/worker.py`  
**Pass:** Exit code 0.  
**Fail:** Any SyntaxError.

---

## TC-04: Unit tests — grading_repository Patch 7G-8C-1 [A]

**Purpose:** Verify `log_grading_skip()` correctly writes to DB (mocked).  
**Command:** `pytest services/grading-worker/tests/test_grading_repository_patch7g8c.py -v`  
**Pass:** All collected tests PASSED, 0 failures.  
**Fail:** Any FAILED or ERROR result.  
**Commit evidence:** cb79155

---

## TC-05: Unit tests — worker Patch 7G-8C-2 [A]

**Purpose:** Verify worker calls `log_grading_skip()` on ineligible sessions.  
**Command:** `pytest services/grading-worker/tests/test_worker_patch7g8c2.py -v`  
**Pass:** All collected tests PASSED, 0 failures.  
**Fail:** Any FAILED or ERROR result.  
**Commit evidence:** 85ce409

---

## TC-06: Single-gateway realtime session [M]

**Purpose:** Verify end-to-end WebRTC offer → STT → LLM → TTS on single gateway (port 8080).  
**Pre-condition:** Gateway running, `GROQ_API_KEY` set, microphone audio file available.  
**Command:** `realtime_stress.py --ten-url http://127.0.0.1:8080 --mode short_english`  
**Pass:** `"failures": []`, `offer` column = 200, `stt_final_ms` populated.  
**Evidence artifact:** `.tmp/realtime_stress_YYYYMMDD_HHMMSS.json`

---

## TC-07: Capacity gate — 503 on second connection [M]

**Purpose:** Verify `TEN_SINGLE_SESSION_CAPACITY=1` returns HTTP 503 on second simultaneous connection to the same gateway process.  
**Pre-condition:** One session already active on gateway.  
**Method:** Issue a second `/rtc/offer` POST while first session is live.  
**Pass:** Second request returns 503 with `"WebRTC capacity reached"` detail.

---

## TC-08: 2-gateway concurrent sessions [M]

**Purpose:** Verify two independent users can hold simultaneous sessions on separate gateway processes (ports 8081, 8082).  
**Pre-condition:** Two uvicorn processes started, core-api on :8000, Postgres and RabbitMQ up.  
**Command:** Parallel `realtime_stress.py` targeting :8081 and :8082.  
**Pass:** Both sessions: `offer=200`, no `error` field, `stt_final_ms` or `suppress` present.  
**Evidence artifact:** `/tmp/luve_concurrent2_a.log`, `/tmp/luve_concurrent2_b.log` (captured 2026-05-26)

---

## TC-09: grading_skip_log DB persistence [M]

**Purpose:** Verify rows appear in `grading_skip_log` for ineligible sessions after worker processing.  
**Pre-condition:** Postgres running, worker processed at least one ineligible session.  
**Command:** `SELECT * FROM grading_skip_log ORDER BY created_at DESC LIMIT 5;`  
**Pass:** At least 1 row with expected `reason` code.

---

## TC-10: RabbitMQ queue drain [M]

**Purpose:** Verify `luve.session.completed` queue reaches 0 messages after worker processes all pending.  
**Method:** RabbitMQ Management UI at :15672 or `rabbitmqctl list_queues`.  
**Pass:** Queue depth = 0 after worker run.

---

## TC-11: Frontend multi-gateway URL routing [M]

**Purpose:** Verify browser automatically points to correct gateway based on URL port.  
**Method:** Open `http://localhost:8081/control-center` in browser.  
**Pass:** `<input id="gateway-url">` pre-filled with `http://localhost:8081`.  
**Source:** `src/static/index.html` `getDefaultGatewayUrl()`.
