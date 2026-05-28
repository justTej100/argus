"""
SearchAgent — fans out to all scrapers simultaneously.

The key technique here is asyncio.gather(). Instead of hitting Reddit,
then waiting for it to finish, then hitting HN, then waiting... we fire
all requests at the same time and wait for all of them to complete.

If Reddit takes 2s, HN takes 1.5s, and GitHub takes 1s, sequential would
take 4.5s total. Parallel takes 2s — the time of the slowest source.

This is one of the main reasons async Python is used here instead of
regular synchronous code.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx

from scrapers.sources import (
    SourceItem,
    scrape_reddit,
    scrape_hackernews,
    scrape_github,
    scrape_exa,
    scrape_social,
)


@dataclass
class SearchResult:
    """Output of SearchAgent — everything the AnalysisAgent needs."""
    query: str
    query_type: str
    items: list[SourceItem]    # all items from all sources, deduplicated
    sources_hit: list[str]     # which sources actually returned data
    duration_ms: float
    errors: list[str] = field(default_factory=list)  # per-source error messages


class SearchAgent:
    """
    Fans out to all configured scrapers simultaneously.

    Free sources (no key needed): reddit, hackernews, github
    Paid/keyed sources:           exa, tiktok, instagram
    """

    # These three run without any configuration — great for getting started.
    DEFAULT_SOURCES = ["reddit", "hackernews", "github"]

    async def run(
        self,
        query: str,
        query_type: str = "topic",
        sources: list[str] | None = None,
        limit_per_source: int = 12,
    ) -> SearchResult:
        t0 = time.time()
        active_sources = sources or self.DEFAULT_SOURCES
        errors: list[str] = []

        # A single shared httpx.AsyncClient is more efficient than creating
        # one per scraper — it reuses the underlying TCP connection pool.
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Build a dict of {source_name: coroutine} so we can map results
            # back to their source name after asyncio.gather runs them all.
            tasks = {}

            if "reddit"      in active_sources:
                tasks["reddit"]      = scrape_reddit(client, query, limit_per_source)
            if "hackernews"  in active_sources:
                tasks["hackernews"]  = scrape_hackernews(client, query, limit_per_source)
            if "github"      in active_sources:
                tasks["github"]      = scrape_github(client, query, limit_per_source)
            if "exa"         in active_sources:
                tasks["exa"]         = scrape_exa(client, query, limit_per_source)
            if "tiktok"      in active_sources:
                tasks["tiktok"]      = scrape_social(client, query, "tiktok", limit_per_source)
            if "instagram"   in active_sources:
                tasks["instagram"]   = scrape_social(client, query, "instagram", limit_per_source)

            # return_exceptions=True means if one scraper raises an exception,
            # the others still complete normally. Without this, a single
            # scraper failure would cancel all the others.
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        all_items: list[SourceItem] = []
        sources_hit: list[str] = []

        for source_name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                # Log the error but continue — partial results are better than none.
                errors.append(f"{source_name}: {result}")
            elif result:
                all_items.extend(result)
                sources_hit.append(source_name)

        # Deduplicate by URL — the same article can appear in multiple sources
        # (e.g. a GitHub repo linked from both Reddit and HN).
        seen_urls: set[str] = set()
        deduped: list[SourceItem] = []
        for item in all_items:
            if item.url not in seen_urls:
                seen_urls.add(item.url)
                deduped.append(item)

        return SearchResult(
            query=query,
            query_type=query_type,
            items=deduped,
            sources_hit=sources_hit,
            duration_ms=(time.time() - t0) * 1000,
            errors=errors,
        )
