from __future__ import annotations

"""Optional community context from configured subreddits."""

from dataclasses import dataclass


@dataclass
class ContextResult:
    items: list[dict]


class ContextAgent:
    """Fetch supplementary community context for scoped documents."""

    async def run(self, query: str, document_ids: list[str]) -> ContextResult:
        """Return community context items (stub — subreddit fetch not yet implemented)."""
        _ = query, document_ids
        return ContextResult(items=[])
