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

## Evidence Runner

```
scripts/testing/run_thesis_evidence.sh
```

Generates a timestamped Markdown report in `test-results/`. Safe to run at any time — no live services started, no DB writes, no secrets printed.

## Constraints

- **Do not modify** `services/`, `infrastructure/`, `docs/ai/`, `.understand-anything/`
- **Do not run** the evidence script without reading `TEST_PLAN.md §3` first
- Generated reports in `test-results/` are gitignored by convention; commit only intentional evidence artifacts
