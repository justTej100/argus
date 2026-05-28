"""
Scrapers — async, parallel, normalized.

Each scraper hits one data source and returns a list of SourceItem objects.
Every scraper returns the exact same SourceItem shape, regardless of where
the data came from. This normalization is what lets AnalysisAgent treat a
Reddit post and a GitHub repo identically — it just sees a list of items
with titles, bodies, and engagement numbers.

The SearchAgent runs all scrapers simultaneously using asyncio.gather, so
hitting Reddit, HN, and GitHub in parallel takes roughly the same time as
hitting just one of them sequentially.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

import httpx

# How long to wait for a single HTTP request before giving up.
# 12 seconds is generous — if a source is slow, we don't want it to block
# the whole pipeline indefinitely.
TIMEOUT = httpx.Timeout(12.0)

# Only include posts from the last 30 days to keep results fresh.
DAYS_BACK = 30


@dataclass
class SourceItem:
    """
    One piece of retrieved content — a Reddit post, HN story, GitHub repo, etc.

    Every scraper maps its raw API response to this shape. The common schema
    is what makes the RAG pipeline source-agnostic: AnalysisAgent doesn't need
    to know where an item came from to embed and rank it.
    """
    item_id: str               # stable dedup key (MD5 of source + url)
    source: str                # "reddit", "hackernews", "github", etc.
    title: str
    body: str                  # post text, repo description, story text
    url: str
    author: str | None = None
    container: str | None = None          # subreddit, GitHub org, "HackerNews"
    published_at: str | None = None       # unix timestamp string or ISO date
    engagement: dict[str, int | float] = field(default_factory=dict)   # upvotes, stars, etc.
    metadata: dict[str, Any] = field(default_factory=dict)             # source-specific extras
    embedding: list[float] | None = None  # populated later by AnalysisAgent

    def text_for_embedding(self) -> str:
        """
        Build the string that gets turned into an embedding vector.

        We concatenate title + body snippet + container because all three
        contribute to the item's meaning. For example, a post titled "Rust is great"
        in r/rust means something different than the same title in r/unpopularopinion.
        We cap body at 500 chars to keep embedding costs reasonable.
        """
        parts = [self.title]
        if self.body:
            parts.append(self.body[:500])
        if self.container:
            parts.append(self.container)
        return " ".join(parts)

    def total_engagement(self) -> int:
        """Sum of all engagement numbers — useful for a quick popularity signal."""
        return sum(int(v) for v in self.engagement.values())


def _item_id(source: str, url: str) -> str:
    """
    Create a stable 12-character ID for an item using MD5.

    Including the source name means a Reddit post and an HN story with the
    same URL (unlikely but possible) won't collide. The [:12] slice keeps
    IDs short while still being effectively collision-free for our data volumes.
    """
    return hashlib.md5(f"{source}:{url}".encode()).hexdigest()[:12]


def _is_recent(ts: float) -> bool:
    """Return True if the unix timestamp is within the last DAYS_BACK days."""
    return (time.time() - ts) < DAYS_BACK * 86_400


# ---------------------------------------------------------------------------
# Reddit  (public JSON API — no authentication needed)
# ---------------------------------------------------------------------------

async def scrape_reddit(client: httpx.AsyncClient, query: str, limit: int = 15) -> list[SourceItem]:
    """
    Search Reddit's public JSON API.

    Reddit's search endpoint returns posts sorted by relevance or top score.
    We use sort=top&t=month to get the most upvoted posts about the topic
    in the last month — these tend to have the richest discussion threads.

    No API key needed. Reddit's public .json endpoints are rate-limited by IP
    (~60 req/min), which is plenty for our use case.
    """
    items = []
    try:
        url = (
            f"https://www.reddit.com/search.json"
            f"?q={quote_plus(query)}&sort=top&t=month&limit={limit}"
        )
        # Reddit blocks requests with the default Python user-agent.
        # Any descriptive string works — we're not pretending to be a browser.
        r = await client.get(url, headers={"User-Agent": "superscraper/1.0"}, timeout=TIMEOUT)
        r.raise_for_status()
        for post in r.json().get("data", {}).get("children", []):
            p = post.get("data", {})
            # Skip posts older than DAYS_BACK to keep results fresh.
            if not _is_recent(p.get("created_utc", 0)):
                continue
            items.append(SourceItem(
                item_id=_item_id("reddit", p.get("permalink", "")),
                source="reddit",
                title=p.get("title", ""),
                body=p.get("selftext", "")[:600],   # cap body so embeds stay cheap
                url=f"https://reddit.com{p.get('permalink', '')}",
                author=p.get("author"),
                container=p.get("subreddit_name_prefixed"),  # e.g. "r/MachineLearning"
                published_at=str(int(p.get("created_utc", 0))),   # unix timestamp
                engagement={
                    "upvotes": p.get("score", 0),
                    "comments": p.get("num_comments", 0),
                },
                metadata={"upvote_ratio": p.get("upvote_ratio", 0)},
            ))
    except Exception as exc:
        # We never let one scraper crash the whole pipeline.
        # Errors are printed for debugging but the pipeline continues with
        # whatever the other scrapers returned.
        print(f"[reddit] {exc}")
    return items


# ---------------------------------------------------------------------------
# HackerNews  (Algolia search API — zero auth)
# ---------------------------------------------------------------------------

async def scrape_hackernews(client: httpx.AsyncClient, query: str, limit: int = 10) -> list[SourceItem]:
    """
    Search HackerNews via Algolia's HN search API (hn.algolia.com).

    HN's official search API is free, fast, and supports date filtering.
    We filter to only `story` type (not comments/jobs/polls) and to posts
    within the last DAYS_BACK days using the `numericFilters` parameter.
    """
    items = []
    try:
        # Calculate the cutoff unix timestamp for the date filter.
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
                body=hit.get("story_text") or "",   # HN stories often have no body text
                # Some HN posts link to external URLs; others are ask/show HN with
                # only a discussion thread. Fall back to the HN thread URL.
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
# GitHub  (public REST API — optional token for higher rate limits)
# ---------------------------------------------------------------------------

async def scrape_github(client: httpx.AsyncClient, query: str, limit: int = 8) -> list[SourceItem]:
    """
    Search GitHub repositories via the public REST API.

    Without a token: 60 requests/hour (usually enough for development).
    With GITHUB_TOKEN set: 5000 requests/hour.

    We search repos (not issues or code) sorted by stars, which surfaces the
    most established projects related to the query.
    """
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
                    title=repo.get("full_name", ""),     # e.g. "owner/repo-name"
                    body=repo.get("description") or "",
                    url=repo.get("html_url", ""),
                    author=repo.get("owner", {}).get("login"),
                    container=repo.get("language"),      # primary programming language
                    published_at=repo.get("pushed_at"), # ISO date of last push
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
# Exa AI  (semantic web search — requires EXA_API_KEY)
# ---------------------------------------------------------------------------

async def scrape_exa(client: httpx.AsyncClient, query: str, limit: int = 8) -> list[SourceItem]:
    """
    Semantic web search via the Exa API.

    Unlike keyword search, Exa uses embeddings to find pages that are
    semantically related to the query — good for catching relevant content
    that doesn't use the exact query words.

    Requires EXA_API_KEY. Returns [] silently if the key isn't set so the
    pipeline works without it.
    """
    items = []
    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        return items   # optional source — skip without a key
    try:
        r = await client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={
                "query": query,
                "numResults": limit,
                "useAutoprompt": True,   # Exa rewrites the query for better semantic search
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
# ScrapeCreators  (paid API — TikTok, Instagram, X, etc.)
# ---------------------------------------------------------------------------

async def scrape_social(client: httpx.AsyncClient, query: str, platform: str = "tiktok", limit: int = 10) -> list[SourceItem]:
    """
    Search social platforms via ScrapeCreators.

    One function covers multiple platforms (TikTok, Instagram, X) because
    ScrapeCreators uses the same API shape for all of them — only the
    URL path changes.

    Requires SCRAPECREATORS_API_KEY. Returns [] silently without it.
    """
    items = []
    api_key = os.environ.get("SCRAPECREATORS_API_KEY")
    if not api_key:
        return items   # optional source — skip without a key
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
                # Author can be a nested object or a plain string depending on the platform.
                author=post.get("author", {}).get("username") if isinstance(post.get("author"), dict) else post.get("author"),
                engagement={
                    # TikTok uses diggCount/commentCount/shareCount; other platforms
                    # use likes/comments/shares. We check both field names.
                    "likes":   post.get("likes",   post.get("diggCount",    0)),
                    "comments": post.get("comments", post.get("commentCount", 0)),
                    "shares":  post.get("shares",  post.get("shareCount",   0)),
                },
                published_at=str(post.get("createTime", "")),
            ))
    except Exception as exc:
        print(f"[{platform}] {exc}")
    return items
