"""
API key auth + in-memory rate limiting.

How it works:
  1. Every request must include an `x-api-key` header.
  2. `verify_api_key` is a FastAPI dependency — it runs before the route handler.
     If the key is missing, invalid, or over its daily limit, it raises an HTTP
     exception and the route handler never runs.
  3. Rate limiting uses a sliding 24-hour window: we keep a list of timestamps
     for each key and count how many fall within the last 24 hours.

Tradeoffs of this in-memory approach:
  ✅ Zero setup — no Redis or database needed to get started.
  ❌ Counts reset when the server restarts.
  ❌ Doesn't work across multiple server processes (use Redis in production).

To upgrade to Redis, replace `_log` with a Redis sorted set and `_keys`
with a database-backed store.
"""

from __future__ import annotations

import secrets
import time
from collections import defaultdict

from fastapi import Header, HTTPException

# ---------------------------------------------------------------------------
# In-memory key store
# ---------------------------------------------------------------------------

# Seed with the demo key so the app works immediately with no configuration.
# In production you'd store keys in Postgres and look them up here.
_keys: dict[str, dict] = {
    "demo-key-argus": {"plan": "free", "daily_limit": 10},
}

# Request log: key → list of unix timestamps for requests in the past 24 hours.
# defaultdict means accessing a missing key returns [] instead of raising KeyError.
_log: dict[str, list[float]] = defaultdict(list)


def _requests_today(key: str) -> int:
    """
    Count how many requests this key has made in the last 24 hours.

    We prune timestamps older than 24 hours as we go, so the list never
    grows unbounded — it stays at most `daily_limit` entries long.
    """
    cutoff = time.time() - 86_400      # unix timestamp 24 hours ago
    _log[key] = [t for t in _log[key] if t > cutoff]   # drop old ones
    return len(_log[key])


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def verify_api_key(
    # FastAPI reads the `x-api-key` header and passes it here automatically.
    # If the header is missing, x_api_key defaults to "".
    x_api_key: str = Header(default=""),
) -> dict:
    """
    Validate the API key and enforce the daily request limit.

    FastAPI calls this before the route handler via Depends(verify_api_key).
    Raising HTTPException here aborts the request — the route handler never runs.

    Returns rate-limit metadata that gets merged into the API response so
    clients can see how many requests they've used.
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

    # Log this request by recording the current timestamp.
    _log[x_api_key].append(time.time())

    return {
        "plan": meta["plan"],
        "requests_today": used + 1,      # +1 because we just counted the current request
        "daily_limit": meta["daily_limit"],
    }


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def generate_api_key(plan: str = "free") -> str:
    """
    Create a new API key and register it in the in-memory store.

    The key format `argus-fre-<hex>` encodes the plan in the prefix
    so you can visually identify the plan tier from the key string.
    """
    limits = {"free": 10, "pro": 1000}
    # token_hex(8) gives 16 hex characters — enough randomness for our purposes.
    key = f"argus-{plan[:3]}-{secrets.token_hex(8)}"
    _keys[key] = {"plan": plan, "daily_limit": limits.get(plan, 10)}
    return key
