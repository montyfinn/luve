"""Dev-only manual smoke for the live Groq grading path (T6).

MANUAL / DEV ONLY. This makes ONE real call to the Groq API. Do NOT run it in
CI. It reuses the production GroqClient + llm_grade_with_client/parse path (it
does not duplicate the client), reads all config from the environment, never
prints the API key, and prints only a short safe summary — not the raw model
response or the full transcript.

Usage (from services/grading-worker/):
    GROQCLOUD_API_KEY=... [GROQ_MODEL=...] [GROQ_TIMEOUT_SECONDS=...] \\
        python scripts/groq_smoke.py

Exits non-zero WITHOUT calling Groq if GROQCLOUD_API_KEY is unset.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from src.evaluation_input_builder import build_evaluation_input
from src.grading_provider_client import GroqClient
from src.llm_grader import llm_grade_with_client

# Defaults mirror services/grading-worker/src/worker.py so the smoke exercises
# the same configuration the worker would use.
_DEFAULT_MODEL = "llama-3.1-8b-instant"
_DEFAULT_TIMEOUT_SECONDS = "20.0"

# A short canned dev transcript (≥1 student turn, with a deliberate grammar slip
# so the model has something to correct). Not real user data.
_CANNED_SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
_CANNED_RAW_BACKUP = [
    {"type": "USER_TURN", "payload": {"text": "Hello, my name is Monty and I am learning English."}},
    {"type": "AI_TURN", "payload": {"text": "Nice to meet you. What did you do today?"}},
    {"type": "USER_TURN", "payload": {"text": "Today I go to the market and I buyed some fruit with my friend."}},
    {"type": "AI_TURN", "payload": {"text": "Great. Tell me more about the fruit you bought."}},
    {"type": "USER_TURN", "payload": {"text": "I bought apples and bananas because they are cheap and delicious."}},
]


def _build_canned_input():
    session_row = {
        "id": _CANNED_SESSION_ID,
        "user_id": None,
        "lesson_id": None,
        "raw_backup_json": _CANNED_RAW_BACKUP,
    }
    return build_evaluation_input(session_row)


async def _run() -> int:
    api_key = os.getenv("GROQCLOUD_API_KEY", "").strip()
    if not api_key:
        print("Set GROQCLOUD_API_KEY to run live smoke.", file=sys.stderr)
        return 1

    model = os.getenv("GROQ_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    raw_timeout = (
        os.getenv("GROQ_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS).strip()
        or _DEFAULT_TIMEOUT_SECONDS
    )
    try:
        timeout = float(raw_timeout)
    except ValueError:
        print(
            f"GROQ_TIMEOUT_SECONDS is not a valid float: {raw_timeout!r}",
            file=sys.stderr,
        )
        return 2

    # Model/timeout are not secrets; the API key is never printed.
    print(
        f"groq_smoke: model={model} timeout={timeout}s "
        "(DEV-ONLY live call — do not run in CI)"
    )
    client = GroqClient(api_key=api_key, model=model, timeout_seconds=timeout)
    evaluation_input = _build_canned_input()

    result = await llm_grade_with_client(evaluation_input, client)

    print("groq_smoke: PASS — live Groq grading parsed successfully")
    print(f"  provider             = {result.provider}")
    print(f"  grader_version       = {result.grader_version}")
    print(f"  score_schema_version = {result.score_schema_version}")
    print(f"  overall_score        = {result.overall_score:.2f}")
    print(
        "  fluency/grammar/vocab= "
        f"{result.fluency_score:.2f}/{result.grammar_score:.2f}/{result.vocab_score:.2f}"
    )
    print(f"  summary_length       = {len(result.ai_summary_feedback)} chars")
    print(f"  corrections_count    = {len(result.detailed_corrections)}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
