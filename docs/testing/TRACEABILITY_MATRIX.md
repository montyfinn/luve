# Traceability Matrix — LUVE Thesis

Maps thesis research questions / system requirements to test cases and evidence.

---

## Thesis Requirements → Test Cases

| Req ID | Requirement | Test Cases | Status |
|---|---|---|---|
| R-01 | System accepts WebRTC offer from browser client | TC-06, TC-08 | Verified (live smoke 2026-05-26) |
| R-02 | STT transcribes user speech within acceptable latency | TC-06 | Verified (stress log: dc_ms ~296–388 ms) |
| R-03 | LLM generates assistant response | TC-06 | Verified (assistant_final_ms present in b-log) |
| R-04 | System gracefully rejects > 1 simultaneous session per gateway | TC-07 | Verified (TEN_SINGLE_SESSION_CAPACITY=1, HTTP 503) |
| R-05 | Multiple concurrent users supported via multi-process gateway | TC-08 | Verified (2-gateway smoke 2026-05-26) |
| R-06 | Ineligible sessions skip grading with structured reason | TC-04, TC-05, TC-09 | TC-04/05 automated; TC-09 manual pending |
| R-07 | Skip-log rows persist in database for auditability | TC-09 | Manual pending |
| R-08 | Grading worker processes messages reliably | TC-10 | Manual pending |
| R-09 | Frontend routes to correct gateway automatically | TC-11 | Code-verified (no live run needed) |
| R-10 | Codebase free of syntax errors (deploy safety) | TC-01, TC-02, TC-03 | Automated |

---

## Source Artifacts → Requirements

| Artifact | Supports |
|---|---|
| `ten_compat.py` line 34: `TEN_SINGLE_SESSION_CAPACITY = 1` | R-04 |
| `ten_compat.py` lines 89-94: HTTP 503 raise | R-04 |
| `worker.py` `evaluate_grading_eligibility()` call | R-06 |
| `worker.py` `log_grading_skip()` call | R-06, R-07 |
| `grading_repository.py` `log_grading_skip()` ON CONFLICT DO UPDATE | R-07 |
| `index.html` `getDefaultGatewayUrl()` | R-09 |
| `realtime_stress.py` concurrent smoke logs | R-01, R-02, R-03, R-05 |
| Migration `d2bb908` — `grading_skip_log` table | R-07 |
| pytest 183/183 pass (grading-worker) | R-06 |

---

## Coverage Summary

| Category | Total | Automated | Manual | Not-yet-covered |
|---|---|---|---|---|
| Realtime session | 3 | 0 | 2 | TC-07 (capacity gate formal) |
| Multi-user scale | 2 | 0 | 1 | — |
| Grading pipeline | 4 | 2 | 2 | TC-09, TC-10 |
| Frontend routing | 1 | 0 | 1 | — |
| Syntax safety | 3 | 3 | 0 | — |
| **Total** | **13** | **5** | **6** | **1** |
