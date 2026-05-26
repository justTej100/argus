"""
Scrapers — async, parallel, normalized.

Every scraper returns List[SourceItem]. Same shape regardless of source.
The SearchAgent fans these out concurrently via asyncio.gather.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

import httpx

TIMEOUT = httpx.Timeout(12.0)
DAYS_BACK = 30


@dataclass
class SourceItem:
    """Normalized evidence item. Every source maps to this."""
    item_id: str
    source: str
    title: str
    body: str
    url: str
    author: str | None = None
    container: str | None = None       # subreddit, org, channel, etc.
    published_at: str | None = None
    engagement: dict[str, int | float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None   # populated by RAG layer

    def text_for_embedding(self) -> str:
        """Concatenated text used to generate the embedding vector."""
        parts = [self.title]
        if self.body:
            parts.append(self.body[:500])
        if self.container:
            parts.append(self.container)
        return " ".join(parts)

    def total_engagement(self) -> int:
        return sum(int(v) for v in self.engagement.values())


def _item_id(source: str, url: str) -> str:
    return hashlib.md5(f"{source}:{url}".encode()).hexdigest()[:12]


def _is_recent(ts: float) -> bool:
    return (time.time() - ts) < DAYS_BACK * 86_400


# ---------------------------------------------------------------------------
# Reddit  (public JSON — zero auth)
# ---------------------------------------------------------------------------

async def scrape_reddit(client: httpx.AsyncClient, query: str, limit: int = 15) -> list[SourceItem]:
    items = []
    try:
        url = (
            f"https://www.reddit.com/search.json"
            f"?q={quote_plus(query)}&sort=top&t=month&limit={limit}"
        )
        r = await client.get(url, headers={"User-Agent": "superscraper/1.0"}, timeout=TIMEOUT)
        r.raise_for_status()
        for post in r.json().get("data", {}).get("children", []):
            p = post.get("data", {})
            if not _is_recent(p.get("created_utc", 0)):
                continue
            items.append(SourceItem(
                item_id=_item_id("reddit", p.get("permalink", "")),
                source="reddit",
                title=p.get("title", ""),
                body=p.get("selftext", "")[:600],
                url=f"https://reddit.com{p.get('permalink', '')}",
                author=p.get("author"),
                container=p.get("subreddit_name_prefixed"),
                published_at=str(int(p.get("created_utc", 0))),
                engagement={
                    "upvotes": p.get("score", 0),
                    "comments": p.get("num_comments", 0),
                },
                metadata={"upvote_ratio": p.get("upvote_ratio", 0)},
            ))
    except Exception as exc:
        print(f"[reddit] {exc}")
    return items


# ---------------------------------------------------------------------------
# HackerNews  (Algolia API — zero auth)
# ---------------------------------------------------------------------------

async def scrape_hackernews(client: httpx.AsyncClient, query: str, limit: int = 10) -> list[SourceItem]:
    items = []
    try:
        since = int(time.time()) - DAYS_BACK * 86_400
        url = (
            f"https://hn.algolia.com/api/v1/search"
            f"?query={quote_plus(query)}"
            f"&numericFilters=created_at_i>{since}"
            f"&hitsPerPage={limit}&tags=story"
        )
        r = await client.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        for hit in r.json().get("hits", []):
            items.append(SourceItem(
                item_id=_item_id("hn", hit.get("objectID", "")),
                source="hackernews",
                title=hit.get("title", ""),
                body=hit.get("story_text") or "",
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                author=hit.get("author"),
                container="HackerNews",
                published_at=str(hit.get("created_at_i", "")),
                engagement={
                    "points": hit.get("points", 0),
                    "comments": hit.get("num_comments", 0),
                },
            ))
    except Exception as exc:
        print(f"[hn] {exc}")
    return items


# ---------------------------------------------------------------------------
# GitHub  (public API — token optional for higher rate limits)
# ---------------------------------------------------------------------------

async def scrape_github(client: httpx.AsyncClient, query: str, limit: int = 8) -> list[SourceItem]:
    items = []
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        r = await client.get(
            f"https://api.github.com/search/repositories"
            f"?q={quote_plus(query)}&sort=stars&per_page={limit}",
            headers=headers, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            for repo in r.json().get("items", []):
                items.append(SourceItem(
                    item_id=_item_id("github", repo.get("html_url", "")),
                    source="github",
                    title=repo.get("full_name", ""),
                    body=repo.get("description") or "",
                    url=repo.get("html_url", ""),
                    author=repo.get("owner", {}).get("login"),
                    container=repo.get("language"),
                    published_at=repo.get("pushed_at"),
                    engagement={
                        "stars": repo.get("stargazers_count", 0),
                        "forks": repo.get("forks_count", 0),
                    },
                    metadata={"open_issues": repo.get("open_issues_count", 0)},
                ))
    except Exception as exc:
        print(f"[github] {exc}")
    return items


# ---------------------------------------------------------------------------
# Exa AI  (semantic web search — requires BRAVE_API_KEY or EXA_API_KEY)
# ---------------------------------------------------------------------------

async def scrape_exa(client: httpx.AsyncClient, query: str, limit: int = 8) -> list[SourceItem]:
    items = []
    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        return items
    try:
        r = await client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={
                "query": query,
                "numResults": limit,
                "useAutoprompt": True,
                "contents": {"text": {"maxCharacters": 500}},
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        for result in r.json().get("results", []):
            items.append(SourceItem(
                item_id=_item_id("exa", result.get("url", "")),
                source="exa",
                title=result.get("title", ""),
                body=result.get("text", "")[:600],
                url=result.get("url", ""),
                published_at=result.get("publishedDate"),
                engagement={},
                metadata={"score": result.get("score", 0)},
            ))
    except Exception as exc:
        print(f"[exa] {exc}")
    return items


# ---------------------------------------------------------------------------
# ScrapeCreators  (paid — TikTok, Instagram, X, etc.)
# ---------------------------------------------------------------------------

async def scrape_social(client: httpx.AsyncClient, query: str, platform: str = "tiktok", limit: int = 10) -> list[SourceItem]:
    """Generic ScrapeCreators connector. Requires SCRAPECREATORS_API_KEY."""
    items = []
    api_key = os.environ.get("SCRAPECREATORS_API_KEY")
    if not api_key:
        return items
    try:
        r = await client.get(
            f"https://api.scrapecreators.com/v1/{platform}/search",
            headers={"x-api-key": api_key},
            params={"query": query, "limit": limit},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        for post in r.json().get("data", [])[:limit]:
            items.append(SourceItem(
                item_id=_item_id(platform, post.get("url", "") or post.get("id", "")),
                source=platform,
                title=post.get("text", post.get("title", ""))[:200],
                body=post.get("description", "")[:400],
                url=post.get("url", ""),
                author=post.get("author", {}).get("username") if isinstance(post.get("author"), dict) else post.get("author"),
                engagement={
                    "likes": post.get("likes", post.get("diggCount", 0)),
                    "comments": post.get("comments", post.get("commentCount", 0)),
                    "shares": post.get("shares", post.get("shareCount", 0)),
                },
                published_at=str(post.get("createTime", "")),
            ))
    except Exception as exc:
        print(f"[{platform}] {exc}")
    return items