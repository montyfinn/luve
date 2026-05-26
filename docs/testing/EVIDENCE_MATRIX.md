# Evidence Matrix — LUVE Thesis

Maps patch commits → test cases → captured artifacts.

---

## Patch Commit Evidence

| Patch | Commit | Feature | Automated Test | Live Evidence |
|---|---|---|---|---|
| 7G-8A | d2bb908 | `grading_skip_log` migration SQL | — (SQL file) | `psql \d grading_skip_log` (pending) |
| 7G-8B | 2d9dbf6 | Migration applied to dev DB | — | DB schema screenshot (pending) |
| 7G-8C-1 | cb79155 | `log_grading_skip()` repository method | `test_grading_repository_patch7g8c.py` | — |
| 7G-8C-2 | 85ce409 | Worker writes skip-log on ineligible session | `test_worker_patch7g8c2.py` | DB SELECT (pending) |
| 7G-8C-3 | — | Scanner/backfill skip-log writes | Placeholder | — |
| 7G-8C-4 | — | `/grading/status` LEFT JOIN skip-log | Placeholder | — |

---

## Live Smoke Evidence (Captured)

| Date | Scenario | Log / Artifact | Key Metrics | Status |
|---|---|---|---|---|
| 2026-05-26 | Single gateway, session A | `/tmp/luve_concurrent2_a.log` | offer=200, dc_ms=296, suppress=probable_hallucination | PASS |
| 2026-05-26 | Single gateway, session B | `/tmp/luve_concurrent2_b.log` | offer=200, dc_ms=388, stt_final_ms=6716, no error | PASS |
| 2026-05-26 | JSON artifact (shared) | `.tmp/realtime_stress_20260526_203427.json` | failures=[] | PASS |

---

## Generated Reports (run_thesis_evidence.sh)

Reports are written to `test-results/YYYYMMDD_HHMMSS-thesis-evidence.md`.  
Add a row here after each meaningful run:

| Run timestamp | Automated checks | Notable results | Report file |
|---|---|---|---|
| _(not yet run)_ | — | — | — |

---

## Pending Evidence Checklist

- [ ] `psql`: `SELECT * FROM grading_skip_log LIMIT 5;` — confirm rows after ineligible session
- [ ] `psql`: `\d grading_skip_log` — confirm schema matches migration
- [ ] Screenshot: browser at `http://localhost:8081/control-center` showing auto-routed gateway URL
- [ ] Screenshot: RabbitMQ management queue depth = 0 after worker drain
- [ ] Run `run_thesis_evidence.sh` and attach report to this matrix
