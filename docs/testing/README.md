# Testing Documentation — LUVE Project

This directory contains the software testing documentation for the LUVE thesis project.

## Directory Contents

| File | Purpose |
|---|---|
| `TEST_PLAN.md` | Overall strategy: safe automated evidence vs approved live smoke |
| `TEST_CASES.md` | Individual test cases with automation status |
| `TRACEABILITY_MATRIX.md` | Maps thesis requirements → test cases |
| `EVIDENCE_MATRIX.md` | Maps patch commits → test cases → generated reports |
| `TEST_ENVIRONMENT.md` | Hardware, runtime, and service configuration |

## Runners

### Safe Evidence Runner (no live services)

```
scripts/testing/run_thesis_evidence.sh
```

Generates a timestamped Markdown report in `test-results/`. Safe to run at any time — no live services started, no DB writes, no secrets printed. Runs `py_compile` and `pytest` (mocked DB) only.

### Live Multi-Gateway Smoke Runner (requires approval)

```
bash scripts/testing/run_multigateway_smoke.sh \
  --i-understand-this-is-live \
  --gateways <2|4|6|8>
```

Runs N concurrent `realtime_stress.py` sessions against N pre-running gateway processes (ports 8081–808N). Requires `--i-understand-this-is-live` flag. Refuses to run if tracked files are dirty (override with `--allow-dirty`). Does not start services or gateways automatically. Writes a timestamped report to `test-results/`. Maps to TC-MG-001.

## Constraints

- **Do not modify** `services/`, `infrastructure/`, `docs/ai/`, `.understand-anything/`
- **Do not run** the evidence script without reading `TEST_PLAN.md §3` first
- Generated reports in `test-results/` are gitignored by convention; commit only intentional evidence artifacts
