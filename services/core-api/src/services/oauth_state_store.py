"""Redis-backed transient stores for the Google OAuth flow.

Two short-lived, single-use stores:

* ``tx``   — the per-login transaction (CSRF ``state`` -> ``nonce``), 600s TTL.
* ``code`` — the one-time handoff code (``google_code`` -> Luve JWT), 60s TTL.

Both reads use ``GETDEL`` so a value can be consumed exactly once. The Redis
client is supplied by the caller (built with the same ``redis.asyncio`` pattern
as ``api/v1/stream.py``); this module never opens or closes connections.
"""
from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

_TX_PREFIX = "oauth:google:tx:"
_CODE_PREFIX = "oauth:google:code:"

TX_TTL_SECONDS = 600
CODE_TTL_SECONDS = 60


async def store_tx(redis: Redis, state: str, *, nonce: str) -> None:
    """Persist the login transaction keyed by the CSRF state token."""
    await redis.set(_TX_PREFIX + state, json.dumps({"nonce": nonce}), ex=TX_TTL_SECONDS)


async def pop_tx(redis: Redis, state: str) -> dict[str, Any] | None:
    """Atomically fetch-and-delete the login transaction. Single use."""
    raw = await redis.getdel(_TX_PREFIX + state)
    if raw is None:
        return None
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return decoded if isinstance(decoded, dict) else None


async def store_code(redis: Redis, code: str, token: str) -> None:
    """Persist the minted Luve JWT under a one-time handoff code."""
    await redis.set(_CODE_PREFIX + code, token, ex=CODE_TTL_SECONDS)


async def pop_code(redis: Redis, code: str) -> str | None:
    """Atomically fetch-and-delete the Luve JWT for a handoff code. Single use."""
    return await redis.getdel(_CODE_PREFIX + code)
