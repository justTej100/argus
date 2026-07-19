from __future__ import annotations

"""Generate textbook persona accounts + posts after a document is ready.

Also seeds LeetCode personas (idempotent).
"""

import logging
import re
from typing import Any

from db.feed import create_post, delete_posts_for_document, upsert_account
from db.sections import list_sections
from ai.vector_store import sample_vectors

logger = logging.getLogger(__name__)

_LEETCODE_SEED = [
    {
        'handle': 'neetcode',
        'display_name': 'NeetCode',
        'bio': 'Patterns over grinding. Classic DSA.',
        'posts': [
            {
                'body': 'Two Sum — hash map beats nested loops every time. Warm up, then go deeper.',
                'url': 'https://leetcode.com/problems/two-sum/',
            },
            {
                'body': 'Valid Parentheses — stack discipline. If you can explain why O(n), you own it.',
                'url': 'https://leetcode.com/problems/valid-parentheses/',
            },
            {
                'body': 'Number of Islands — flood fill / BFS. Grid problems are just graphs in disguise.',
                'url': 'https://leetcode.com/problems/number-of-islands/',
            },
        ],
    },
    {
        'handle': 'blind75',
        'display_name': 'Blind 75',
        'bio': 'The shortlist. One problem a day compounds.',
        'posts': [
            {
                'body': 'Contains Duplicate — set membership. Simple, but interviewers still ask it.',
                'url': 'https://leetcode.com/problems/contains-duplicate/',
            },
            {
                'body': 'Best Time to Buy and Sell Stock — one pass, track the floor.',
                'url': 'https://leetcode.com/problems/best-time-to-buy-and-sell-stock/',
            },
            {
                'body': 'Maximum Subarray — Kadane. Know the invariant, not just the code.',
                'url': 'https://leetcode.com/problems/maximum-subarray/',
            },
        ],
    },
]


def _handle_from_title(title: str, document_id: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_')
    slug = (slug or 'chapter')[:28]
    suffix = document_id.replace('-', '')[:6]
    return f'{slug}_{suffix}'


async def seed_leetcode_accounts() -> None:
    """Idempotent LeetCode persona seed."""
    for persona in _LEETCODE_SEED:
        account = await upsert_account(
            handle=persona['handle'],
            display_name=persona['display_name'],
            bio=persona['bio'],
            kind='leetcode',
            avatar_key=persona['handle'][:2].upper(),
        )
        # Only seed posts if this account has none yet — check via creating carefully
        # Simple approach: try create; duplicates are fine for MVP if we wipe leetcode rarely
        from db.feed import list_feed

        feed = await list_feed(limit=80)
        existing_bodies = {
            p['body'] for p in feed if (p.get('account') or {}).get('handle') == persona['handle']
        }
        for post in persona['posts']:
            if post['body'] in existing_bodies:
                continue
            await create_post(
                account_id=account['id'],
                body=post['body'],
                leetcode_url=post['url'],
            )


async def generate_textbook_feed(document_id: str, document_title: str) -> int:
    """Create chapter personas + excerpt posts for a ready textbook. Returns post count."""
    await delete_posts_for_document(document_id)
    sections = await list_sections(document_id)
    samples = await sample_vectors(document_id, limit=40)
    if not sections and not samples:
        return 0

    # Group sample chunks by chapter title from metadata
    by_chapter: dict[str, list[dict[str, Any]]] = {}
    for row in samples:
        meta = row.get('metadata') or {}
        chapter = (meta.get('chapter') or '').strip() or f"Page {row.get('page_number') or meta.get('page') or '?'}"
        by_chapter.setdefault(chapter, []).append(row)

    # Prefer section titles for accounts
    created = 0
    if sections:
        for sec in sections[:12]:
            title = sec['title']
            handle = _handle_from_title(title, document_id)
            account = await upsert_account(
                handle=handle,
                display_name=title[:80],
                bio=f'{document_title} · pp. {sec["start_page"]}–{sec["end_page"]}',
                kind='textbook',
                document_id=document_id,
                topic=title,
                avatar_key=re.sub(r'[^A-Za-z0-9]', '', title)[:2].upper() or 'CH',
            )
            # Find sample chunks in page range
            in_range = [
                r
                for r in samples
                if int(sec['start_page']) <= int(r.get('page_number') or 0) <= int(sec['end_page'])
            ][:3]
            if not in_range:
                # Synthetic teaser from section metadata
                await create_post(
                    account_id=account['id'],
                    body=(
                        f'New drop from **{title}** in _{document_title}_. '
                        f'Pages {sec["start_page"]}–{sec["end_page"]} are live — open the PDF and scroll the doomfeed.'
                    ),
                    document_id=document_id,
                    page_number=int(sec['start_page']),
                )
                created += 1
                continue
            for row in in_range:
                excerpt = (row.get('text') or '').strip().replace('\n', ' ')
                if len(excerpt) > 220:
                    excerpt = excerpt[:217] + '…'
                page = int(row.get('page_number') or sec['start_page'])
                await create_post(
                    account_id=account['id'],
                    body=f'{excerpt}\n\n— from _{document_title}_',
                    document_id=document_id,
                    page_number=page,
                )
                created += 1
        return created

    # Fallback: one account per chapter bucket from chunk metadata
    for i, (chapter, rows) in enumerate(list(by_chapter.items())[:12]):
        handle = _handle_from_title(chapter, document_id)
        account = await upsert_account(
            handle=handle,
            display_name=chapter[:80],
            bio=f'{document_title}',
            kind='textbook',
            document_id=document_id,
            topic=chapter,
            avatar_key=f'C{i+1}'[:2],
        )
        for row in rows[:2]:
            excerpt = (row.get('text') or '').strip().replace('\n', ' ')
            if len(excerpt) > 220:
                excerpt = excerpt[:217] + '…'
            page = int(row.get('page_number') or 1)
            await create_post(
                account_id=account['id'],
                body=f'{excerpt}\n\n— from _{document_title}_',
                document_id=document_id,
                page_number=page,
            )
            created += 1
    return created
