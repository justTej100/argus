"""
SearchAgent — fans out to all scrapers in parallel using asyncio.gather.
Returns a normalized list of SourceItems across all sources.
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
    query: str
    query_type: str
    items: list[SourceItem]
    sources_hit: list[str]
    duration_ms: float
    errors: list[str] = field(default_factory=list)


class SearchAgent:
    """
    Fans out to all configured scrapers simultaneously via asyncio.gather.
    Every scraper runs at the same time — not one after another.

    Free sources (no key needed): reddit, hackernews, github
    Paid sources: exa, tiktok, instagram
    """

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

        async with httpx.AsyncClient(follow_redirects=True) as client:
            tasks = {}

            if "reddit" in active_sources:
                tasks["reddit"] = scrape_reddit(client, query, limit_per_source)
            if "hackernews" in active_sources:
                tasks["hackernews"] = scrape_hackernews(client, query, limit_per_source)
            if "github" in active_sources:
                tasks["github"] = scrape_github(client, query, limit_per_source)
            if "exa" in active_sources:
                tasks["exa"] = scrape_exa(client, query, limit_per_source)
            if "tiktok" in active_sources:
                tasks["tiktok"] = scrape_social(client, query, "tiktok", limit_per_source)
            if "instagram" in active_sources:
                tasks["instagram"] = scrape_social(client, query, "instagram", limit_per_source)

            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        all_items: list[SourceItem] = []
        sources_hit: list[str] = []

        for source_name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                errors.append(f"{source_name}: {result}")
            elif result:
                all_items.extend(result)
                sources_hit.append(source_name)

        # Deduplicate by URL
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