from __future__ import annotations

"""Optional subreddit context for scope-aware supplementary sources."""

from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx

from db.client import get_scope_subreddits


@dataclass
class ContextResult:
    items: list[dict]


class ContextAgent:
    """Fetch Reddit snippets only when a scope has subreddit settings."""
    async def _fetch_subreddit(self, client: httpx.AsyncClient, subreddit: str, query: str, limit: int) -> list[dict]:
        url = (
            f'https://www.reddit.com/r/{subreddit}/search.json'
            f'?q={quote_plus(query)}&restrict_sr=1&sort=relevance&t=year&limit={limit}'
        )
        response = await client.get(
            url,
            headers={'User-Agent': 'argus-study-buddy/1.0'},
            timeout=15,
        )
        response.raise_for_status()

        results: list[dict] = []
        for child in response.json().get('data', {}).get('children', []):
            data = child.get('data', {})
            permalink = data.get('permalink')
            if not permalink:
                continue
            results.append(
                {
                    'source_type': 'community',
                    'source': 'reddit',
                    'subreddit': subreddit,
                    'title': data.get('title', ''),
                    'body': data.get('selftext', '')[:500],
                    'url': f'https://reddit.com{permalink}',
                    'engagement': {
                        'upvotes': data.get('score', 0),
                        'comments': data.get('num_comments', 0),
                    },
                }
            )
        return results

    async def run(self, query: str, document_ids: list[str], limit_per_subreddit: int = 3) -> ContextResult:
        subreddits = await get_scope_subreddits(document_ids)
        if not subreddits:
            return ContextResult(items=[])

        items: list[dict] = []
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for subreddit in subreddits:
                try:
                    items.extend(await self._fetch_subreddit(client, subreddit, query, limit_per_subreddit))
                except Exception:
                    continue

        return ContextResult(items=items)
