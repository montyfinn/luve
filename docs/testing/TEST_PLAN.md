# Test Plan — LUVE Thesis Evidence

**Project:** LUVE (AI-Assisted English Speaking Practice)  
**Author:** Thesis author  
**Status:** Active — Patch 7G series (grading pipeline integrity)

---

## 1. Scope

This test plan covers thesis-relevant verification of the LUVE system:

1. **Grading pipeline correctness** — eligibility gate, skip-log persistence, repository layer
2. **WebRTC gateway capacity** — single-session enforcement, multi-process scale-out
3. **Realtime session flow** — offer/ICE/STT/LLM/TTS end-to-end latency

Out of scope: frontend UI unit tests, infrastructure provisioning, production deployment.

---

## 2. Test Categories

### 2A. Safe Automated Evidence (run by `run_thesis_evidence.sh`)

These checks produce reproducible, artifact-captured output without touching live services.

| Category | Mechanism | Safe? |
|---|---|---|
| Python syntax / compile check | `python -m py_compile` | Yes |
| Grading repository unit tests | `pytest` (mocked DB) | Yes |
| Worker eligibility unit tests | `pytest` (mocked DB) | Yes |
| Git HEAD / status snapshot | `git log` / `git status` | Yes |
| VRAM snapshot | `nvidia-smi` (read-only) | Yes |
| Docker container listing | `docker ps` (read-only) | Yes |

### 2B. Approved Live Smoke Tests (manual, pre-approved)

These require explicit session approval before each run.

| Scenario | Command / Method | Evidence artifact |
|---|---|---|
| Single-gateway session | `realtime_stress.py --mode short_english` | `.tmp/realtime_stress_*.json` |
| 2-gateway concurrent | Two parallel `realtime_stress.py` on ports 8081/8082 | Two JSON artifacts + log files |
| UI screenshot (multi-user) | Browser at localhost:8081 + 8082 | Screenshot file |
| DB grading_skip_log SELECT | `psql` read-only SELECT | Copy-pasted query result |
| RabbitMQ queue inspect | Management UI or `rabbitmqctl` | Screenshot or text output |

### 2C. Rejected / Forbidden (never run without explicit re-approval)

- `docker compose up` / `docker compose down`
- `psql` with UPDATE/DELETE/DROP
- Any `--execute` flag on scanner/backfill scripts
- Live Groq/Gemini API calls outside of approved realtime sessions
- Opening browser tabs programmatically

---

## 3. Evidence Capture Protocol

1. Run `bash scripts/testing/run_thesis_evidence.sh` → creates `test-results/YYYYMMDD_HHMMSS-thesis-evidence.md`
2. Review report; confirm all automated checks PASS
3. For live smoke: obtain explicit approval, run, append artifact paths to `EVIDENCE_MATRIX.md`
4. Stage and commit only intentional evidence references, not raw `test-results/` reports

---

## 4. Pass/Fail Criteria

| Check | Pass condition |
|---|---|
| `py_compile` | Exit code 0, no output |
| `pytest` unit | All collected tests pass (0 failures) |
| `pytest` skip reason | No test skipped without explicit mark |
| Realtime stress | `"failures": []` in JSON artifact |
| 2-gateway concurrent | Both sessions: `offer 200`, no `error` field set |
| grading_skip_log | At least 1 row visible for known-ineligible session |

---

## 5. Patch Coverage

| Patch | Feature | Test file(s) |
|---|---|---|
| 7G-8A | Migration SQL | Manual: `psql \d grading_skip_log` |
| 7G-8B | Migration applied | `git log` shows commit d2bb908 |
| 7G-8C-1 | `log_grading_skip()` repository | `test_grading_repository_patch7g8c.py` |
| 7G-8C-2 | Worker skip-log write | `test_worker_patch7g8c2.py` |
| 7G-8C-3 | Scanner/backfill (deferred) | Placeholder — not yet implemented |
| 7G-8C-4 | `/grading/status` LEFT JOIN | Placeholder — not yet implemented |
