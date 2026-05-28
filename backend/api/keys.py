"""
API key auth + in-memory rate limiting.

The demo key (demo-key-argus) is always valid and requires no setup.
In production, swap _keys for a Postgres/Redis-backed store and hook
up Stripe for billing.
"""

from __future__ import annotations

import secrets
import time
from collections import defaultdict

from fastapi import Header, HTTPException

# ---------------------------------------------------------------------------
# Key store — seed with the demo key
# ---------------------------------------------------------------------------

_keys: dict[str, dict] = {
    "demo-key-argus": {"plan": "free", "daily_limit": 10},
}

# In-memory request log: key → list of unix timestamps (today's requests)
_log: dict[str, list[float]] = defaultdict(list)


def _requests_today(key: str) -> int:
    cutoff = time.time() - 86_400
    _log[key] = [t for t in _log[key] if t > cutoff]
    return len(_log[key])


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def verify_api_key(x_api_key: str = Header(default="")) -> dict:
    """
    Reads the x-api-key header, validates it, and enforces the daily limit.
    Returns rate-limit metadata that gets merged into the response.
    """
    if x_api_key not in _keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key. Use 'demo-key-argus' or POST /keys/generate.",
        )

    meta = _keys[x_api_key]
    used = _requests_today(x_api_key)

    if used >= meta["daily_limit"]:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of {meta['daily_limit']} requests reached. Try again tomorrow.",
        )

    _log[x_api_key].append(time.time())

    return {
        "plan": meta["plan"],
        "requests_today": used + 1,
        "daily_limit": meta["daily_limit"],
    }


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def generate_api_key(plan: str = "free") -> str:
    limits = {"free": 10, "pro": 1000}
    key = f"argus-{plan[:3]}-{secrets.token_hex(8)}"
    _keys[key] = {"plan": plan, "daily_limit": limits.get(plan, 10)}
    return key
