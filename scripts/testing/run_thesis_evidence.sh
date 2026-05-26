#!/usr/bin/env bash
# Thesis evidence runner — safe automated checks only.
# Never starts services. Never writes to DB. Never calls Groq. Never prints secrets.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPORT_DIR="${REPO_ROOT}/test-results"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="${REPORT_DIR}/${TIMESTAMP}-thesis-evidence.md"

WORKER_VENV="${REPO_ROOT}/services/grading-worker/venv"
WORKER_PY="${WORKER_VENV}/bin/python"
WORKER_SRC="${REPO_ROOT}/services/grading-worker/src"
WORKER_TESTS="${REPO_ROOT}/services/grading-worker/tests"

COREAPI_PY="${REPO_ROOT}/services/core-api/venv/bin/python3"
PYTHON_FOR_COMPILE="${WORKER_PY}"
if [ ! -x "${WORKER_PY}" ] && [ -x "${COREAPI_PY}" ]; then
    PYTHON_FOR_COMPILE="${COREAPI_PY}"
fi

PASS=0
FAIL=0

mkdir -p "${REPORT_DIR}"

# ── helpers ──────────────────────────────────────────────────────────────────

section() { printf '\n## %s\n\n' "$1" >> "${REPORT}"; }
append()  { printf '%s\n' "$1" >> "${REPORT}"; }
code_block_start() { printf '```\n' >> "${REPORT}"; }
code_block_end()   { printf '```\n' >> "${REPORT}"; }

run_check() {
    local label="$1"; shift
    local output exit_code

    output="$("$@" 2>&1)"
    exit_code=$?

    if [ "${exit_code}" -eq 0 ]; then
        append "**${label}:** PASS (exit ${exit_code})"
        PASS=$((PASS + 1))
    else
        append "**${label}:** FAIL (exit ${exit_code})"
        FAIL=$((FAIL + 1))
    fi

    if [ -n "${output}" ]; then
        code_block_start
        printf '%s\n' "${output}" >> "${REPORT}"
        code_block_end
    fi
}

# ── header ────────────────────────────────────────────────────────────────────

{
    printf '# Thesis Evidence Report\n\n'
    printf '**Generated:** %s\n\n' "${TIMESTAMP}"
    printf '**Runner:** %s\n\n' "${BASH_SOURCE[0]}"
    printf '---\n'
} > "${REPORT}"

# ── §1 git snapshot ───────────────────────────────────────────────────────────

section "1. Repository Snapshot"

append "**Git HEAD:**"
code_block_start
git -C "${REPO_ROOT}" log --oneline -5 >> "${REPORT}" 2>&1
code_block_end

append "**Git status:**"
code_block_start
git -C "${REPO_ROOT}" status --short >> "${REPORT}" 2>&1
code_block_end

# ── §2 system snapshot ────────────────────────────────────────────────────────

section "2. System Snapshot"

append "**Python (grading-worker venv):**"
code_block_start
if [ -x "${WORKER_PY}" ]; then
    "${WORKER_PY}" --version >> "${REPORT}" 2>&1
else
    printf 'venv not found: %s\n' "${WORKER_PY}" >> "${REPORT}"
fi
code_block_end

append "**NVIDIA GPU (nvidia-smi):**"
code_block_start
if command -v nvidia-smi > /dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free \
        --format=csv,noheader,nounits >> "${REPORT}" 2>&1
else
    printf 'nvidia-smi not available\n' >> "${REPORT}"
fi
code_block_end

append "**Docker containers (read-only ps):**"
code_block_start
if command -v docker > /dev/null 2>&1; then
    docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' >> "${REPORT}" 2>&1
else
    printf 'docker not available\n' >> "${REPORT}"
fi
code_block_end

# ── §3 Python compile checks ──────────────────────────────────────────────────

section "3. Python Syntax Checks (py_compile)"

if [ -x "${PYTHON_FOR_COMPILE}" ]; then
    run_check "TC-01 py_compile session_eligibility.py" \
        "${PYTHON_FOR_COMPILE}" -m py_compile "${WORKER_SRC}/session_eligibility.py"

    run_check "TC-02 py_compile grading_repository.py" \
        "${PYTHON_FOR_COMPILE}" -m py_compile "${WORKER_SRC}/grading_repository.py"

    run_check "TC-03 py_compile worker.py" \
        "${PYTHON_FOR_COMPILE}" -m py_compile "${WORKER_SRC}/worker.py"
else
    append "SKIP — no usable Python found (checked grading-worker and core-api venvs)"
    FAIL=$((FAIL + 3))
fi

# ── §4 pytest unit tests ──────────────────────────────────────────────────────

section "4. Unit Tests (pytest, mocked DB)"

if [ -x "${WORKER_PY}" ] && command -v "${WORKER_VENV}/bin/pytest" > /dev/null 2>&1; then
    PYTEST="${WORKER_VENV}/bin/pytest"

    run_check "TC-04 pytest test_grading_repository_patch7g8c.py" \
        "${PYTEST}" \
        "${WORKER_TESTS}/test_grading_repository_patch7g8c.py" \
        -v --tb=short

    run_check "TC-05 pytest test_worker_patch7g8c2.py" \
        "${PYTEST}" \
        "${WORKER_TESTS}/test_worker_patch7g8c2.py" \
        -v --tb=short
else
    append "SKIP — pytest not found in venv or venv missing"
    FAIL=$((FAIL + 2))
fi

# ── §5 manual / approved live evidence ───────────────────────────────────────

section "5. Manual / Approved Live Evidence"

append "> These items require explicit session approval before each run."
append "> Do NOT execute these from this script."
append ""
append "- [ ] **TC-06** Single-gateway realtime session — \`realtime_stress.py --mode short_english\`"
append "- [ ] **TC-07** Capacity gate 503 — second simultaneous offer to same gateway process"
append "- [ ] **TC-08** 2-gateway concurrent sessions — \`realtime_stress.py\` on :8081 and :8082 in parallel"
append "      *Prior evidence (2026-05-26):* \`/tmp/luve_concurrent2_a.log\`, \`/tmp/luve_concurrent2_b.log\`"
append "- [ ] **TC-09** DB grading_skip_log SELECT — \`SELECT * FROM grading_skip_log LIMIT 5;\`"
append "- [ ] **TC-10** RabbitMQ queue drain — management UI or rabbitmqctl list_queues"
append "- [ ] **TC-11** Frontend URL routing — open \`http://localhost:8081/control-center\` in browser"

# ── §6 summary ────────────────────────────────────────────────────────────────

section "6. Automated Check Summary"

TOTAL=$((PASS + FAIL))
append "| Result | Count |"
append "|--------|-------|"
append "| PASS   | ${PASS} |"
append "| FAIL   | ${FAIL} |"
append "| Total  | ${TOTAL} |"
append ""
if [ "${FAIL}" -eq 0 ]; then
    append "**All automated checks PASSED.**"
else
    append "**${FAIL} check(s) FAILED — review sections above.**"
fi

# ── done ──────────────────────────────────────────────────────────────────────

printf 'Report written: %s\n' "${REPORT}"
printf 'Automated: PASS=%d FAIL=%d\n' "${PASS}" "${FAIL}"
