#!/usr/bin/env bash
# Multi-gateway live smoke runner.
# Requires --i-understand-this-is-live.
# Assumes gateways and core-api are already running.
# Never starts services. Never runs docker compose up. Never prints secrets.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_PY="${REPO_ROOT}/services/core-api/venv/bin/python"
STRESS_SCRIPT="${REPO_ROOT}/services/core-api/scripts/realtime_stress.py"

# ── arg parsing ───────────────────────────────────────────────────────────────

LIVE_FLAG=0
ALLOW_DIRTY=0
N_GATEWAYS=""

usage() {
    printf 'Usage: %s --i-understand-this-is-live --gateways <2|4|6|8> [--allow-dirty]\n' \
        "$(basename "$0")"
    printf '\n'
    printf '  --i-understand-this-is-live   Required. Confirms you intend a live smoke run.\n'
    printf '  --gateways N                  Number of concurrent gateway processes (2, 4, 6, or 8).\n'
    printf '  --allow-dirty                 Allow run even if tracked files have uncommitted changes.\n'
    printf '\n'
    printf 'Assumes gateway processes on ports 8081..8081+(N-1) are already running.\n'
    printf 'Does not start services, docker, or gateways automatically.\n'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --i-understand-this-is-live) LIVE_FLAG=1 ;;
        --allow-dirty)               ALLOW_DIRTY=1 ;;
        --gateways)
            shift
            N_GATEWAYS="${1:-}"
            ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2; exit 2 ;;
    esac
    shift
done

# ── safety gates ──────────────────────────────────────────────────────────────

if [ "${LIVE_FLAG}" -eq 0 ]; then
    printf 'ERROR: --i-understand-this-is-live flag is required.\n' >&2
    printf 'This script runs live WebRTC sessions against real gateway processes.\n' >&2
    usage >&2
    exit 2
fi

if [ -z "${N_GATEWAYS}" ]; then
    printf 'ERROR: --gateways N is required.\n' >&2
    usage >&2
    exit 2
fi

case "${N_GATEWAYS}" in
    2|4|6|8) ;;
    *)
        printf 'ERROR: --gateways must be 2, 4, 6, or 8. Got: %s\n' "${N_GATEWAYS}" >&2
        exit 2 ;;
esac

if [ "${ALLOW_DIRTY}" -eq 0 ]; then
    DIRTY=$(git -C "${REPO_ROOT}" status --short | grep -v '^??' || true)
    if [ -n "${DIRTY}" ]; then
        printf 'ERROR: tracked files have uncommitted changes:\n%s\n' "${DIRTY}" >&2
        printf 'Pass --allow-dirty to run anyway.\n' >&2
        exit 2
    fi
fi

if [ ! -x "${VENV_PY}" ]; then
    printf 'ERROR: core-api venv not found: %s\n' "${VENV_PY}" >&2
    exit 1
fi

if [ ! -f "${STRESS_SCRIPT}" ]; then
    printf 'ERROR: stress script not found: %s\n' "${STRESS_SCRIPT}" >&2
    exit 1
fi

# ── setup ─────────────────────────────────────────────────────────────────────

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="${REPO_ROOT}/test-results"
REPORT="${REPORT_DIR}/${TIMESTAMP}-multigateway-${N_GATEWAYS}.md"
BASE_PORT=8081

mkdir -p "${REPORT_DIR}"

section() { printf '\n## %s\n\n' "$1" >> "${REPORT}"; }
append()  { printf '%s\n' "$1" >> "${REPORT}"; }
code_block_start() { printf '```\n' >> "${REPORT}"; }
code_block_end()   { printf '```\n' >> "${REPORT}"; }

# ── header ────────────────────────────────────────────────────────────────────

{
    printf '# Multi-Gateway Live Smoke Report\n\n'
    printf '**Generated:** %s\n\n' "${TIMESTAMP}"
    printf '**Gateways:** %s\n\n' "${N_GATEWAYS}"
    printf '**Runner:** %s\n\n' "${BASH_SOURCE[0]}"
    printf '%s\n' '---'
} > "${REPORT}"

# ── §1 repo snapshot ──────────────────────────────────────────────────────────

section "1. Repository Snapshot"

append "**Git HEAD:**"
code_block_start
git -C "${REPO_ROOT}" log --oneline -5 >> "${REPORT}" 2>&1
code_block_end

append "**Git status:**"
code_block_start
git -C "${REPO_ROOT}" status --short >> "${REPORT}" 2>&1
code_block_end

# ── §2 pre-run VRAM ───────────────────────────────────────────────────────────

section "2. Pre-Run System Snapshot"

append "**NVIDIA GPU (before):**"
code_block_start
if command -v nvidia-smi > /dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free \
        --format=csv,noheader,nounits >> "${REPORT}" 2>&1
else
    printf 'nvidia-smi not available\n' >> "${REPORT}"
fi
code_block_end

# ── §3 gateway pre-check ──────────────────────────────────────────────────────

section "3. Gateway Pre-Check"

PORTS=()
for i in $(seq 0 $((N_GATEWAYS - 1))); do
    PORTS+=($((BASE_PORT + i)))
done

append "**Ports under test:** ${PORTS[*]}"
append ""

ALL_HEALTHY=1
for port in "${PORTS[@]}"; do
    health=$(curl -s --max-time 3 "http://127.0.0.1:${port}/healthz" 2>/dev/null || true)
    if printf '%s' "${health}" | grep -q '"status":"ok"'; then
        append "- gw${port}: READY"
    else
        append "- gw${port}: NOT READY (response: ${health:-no response})"
        ALL_HEALTHY=0
    fi
done

if [ "${ALL_HEALTHY}" -eq 0 ]; then
    append ""
    append "**ABORT: one or more gateways not healthy. Start all ${N_GATEWAYS} gateway processes first.**"
    printf 'ABORT: not all gateways healthy. See report: %s\n' "${REPORT}" >&2
    exit 1
fi

# ── §4 run concurrent sessions ────────────────────────────────────────────────

section "4. Concurrent Stress Sessions"

LOG_DIR="/tmp"
PIDS=()
LOG_FILES=()

for port in "${PORTS[@]}"; do
    log_file="${LOG_DIR}/luve_mg_smoke_${TIMESTAMP}_${port}.log"
    LOG_FILES+=("${log_file}")
    "${VENV_PY}" "${STRESS_SCRIPT}" \
        --ten-url "http://127.0.0.1:${port}" \
        --mode short_english \
        > "${log_file}" 2>&1 &
    PIDS+=($!)
done

append "Launched ${N_GATEWAYS} concurrent stress sessions. Waiting for completion..."
printf 'Running %d concurrent sessions...\n' "${N_GATEWAYS}"

for pid in "${PIDS[@]}"; do
    wait "${pid}"
done

append ""
append "All sessions complete."

# ── §5 results per gateway ────────────────────────────────────────────────────

section "5. Results Per Gateway"

PASS_COUNT=0
FAIL_COUNT=0

for i in "${!PORTS[@]}"; do
    port="${PORTS[$i]}"
    log="${LOG_FILES[$i]}"

    append "### Gateway :${port}"
    append ""
    append "**Log:** \`${log}\`"
    append ""

    if [ ! -f "${log}" ]; then
        append "**Result:** FAIL (log file missing)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    summary_line=$(grep '"failures":' "${log}" | tail -1 || true)
    offer_200=$(grep -c 'offer.*200' "${log}" 2>/dev/null || true)

    if printf '%s' "${summary_line}" | grep -q '"failures": \[\]'; then
        append "**Result:** PASS"
        append ""
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        append "**Result:** FAIL"
        append ""
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi

    append "**Sessions with offer=200:** ${offer_200}"
    append ""
    append "**Stress summary line:**"
    code_block_start
    printf '%s\n' "${summary_line:-'(not found)'}" >> "${REPORT}"
    code_block_end

    append "**Session table (from log):**"
    code_block_start
    grep -E "^[0-9]+ [a-f0-9-]+ [0-9]" "${log}" 2>/dev/null >> "${REPORT}" || \
        printf '(no session rows found)\n' >> "${REPORT}"
    code_block_end
done

# ── §6 post-run health ────────────────────────────────────────────────────────

section "6. Post-Run Gateway Health"

for port in "${PORTS[@]}"; do
    health=$(curl -s --max-time 3 "http://127.0.0.1:${port}/rtc/health" 2>/dev/null || true)
    active=$(printf '%s' "${health}" | \
        python3 -c "import sys,json; d=json.load(sys.stdin); print(d['active_sessions'])" \
        2>/dev/null || printf '?')
    closed=$(printf '%s' "${health}" | \
        python3 -c "import sys,json; d=json.load(sys.stdin); print(d['closed_sessions_total'])" \
        2>/dev/null || printf '?')
    append "- gw${port}: active_sessions=${active} closed_sessions_total=${closed}"
done

# ── §7 post-run VRAM ──────────────────────────────────────────────────────────

section "7. Post-Run System Snapshot"

append "**NVIDIA GPU (after):**"
code_block_start
if command -v nvidia-smi > /dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free \
        --format=csv,noheader,nounits >> "${REPORT}" 2>&1
else
    printf 'nvidia-smi not available\n' >> "${REPORT}"
fi
code_block_end

# ── §8 stress log paths ───────────────────────────────────────────────────────

section "8. Stress Log Paths"

for log in "${LOG_FILES[@]}"; do
    append "- \`${log}\`"
done

# ── §9 caveats ────────────────────────────────────────────────────────────────

section "9. Caveats"

append "- Automated stress test using \`realtime_stress.py\`, not real browser WebRTC clients."
append "- Not a public production load test. Single development machine only."
append "- Each gateway process serves one session at a time (TEN_SINGLE_SESSION_CAPACITY=1)."
append "- Multi-user is achieved via N separate gateway processes on N ports, not single-process concurrency."
append "- Suppress events (probable_hallucination, low_average_logprob, etc.) are correct protective behavior, not failures."
append "- VRAM usage depends on lazy Whisper model loading; first-session latency is higher."

# ── §10 summary ───────────────────────────────────────────────────────────────

section "10. Summary"

TOTAL=$((PASS_COUNT + FAIL_COUNT))
append "| Result | Count |"
append "|--------|-------|"
append "| PASS   | ${PASS_COUNT} |"
append "| FAIL   | ${FAIL_COUNT} |"
append "| Total  | ${TOTAL} |"
append ""
if [ "${FAIL_COUNT}" -eq 0 ]; then
    append "**${N_GATEWAYS}-user multi-gateway smoke: PASS**"
else
    append "**${N_GATEWAYS}-user multi-gateway smoke: FAIL — ${FAIL_COUNT} gateway(s) failed.**"
fi

# ── done ──────────────────────────────────────────────────────────────────────

printf 'Report written: %s\n' "${REPORT}"
printf 'Result: PASS=%d FAIL=%d\n' "${PASS_COUNT}" "${FAIL_COUNT}"
