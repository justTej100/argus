from __future__ import annotations

"""Document chapter/section rows for Study scoping and feed personas."""

import uuid
from typing import Any

from db.client import get_pool

_memory_sections: dict[str, list[dict[str, Any]]] = {}


async def replace_sections(document_id: str, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace all sections for a document. Assigns ids. Returns saved rows."""
    saved: list[dict[str, Any]] = []
    for i, sec in enumerate(sections):
        row = {
            'id': str(sec.get('id') or uuid.uuid4()),
            'document_id': document_id,
            'title': str(sec['title'])[:200],
            'level': int(sec.get('level') or 1),
            'start_page': int(sec['start_page']),
            'end_page': int(sec['end_page']),
            'sort_key': int(sec.get('sort_key', i)),
        }
        saved.append(row)

    pool = await get_pool()
    if pool is None:
        _memory_sections[document_id] = saved
        return saved

    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM document_sections WHERE document_id = $1::uuid', document_id)
        for row in saved:
            await conn.execute(
                """
                INSERT INTO document_sections (id, document_id, title, level, start_page, end_page, sort_key)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7)
                """,
                row['id'],
                document_id,
                row['title'],
                row['level'],
                row['start_page'],
                row['end_page'],
                row['sort_key'],
            )
    return saved


async def list_sections(document_id: str) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return list(_memory_sections.get(document_id, []))
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id::text, document_id::text, title, level, start_page, end_page, sort_key
            FROM document_sections
            WHERE document_id = $1::uuid
            ORDER BY sort_key ASC, start_page ASC
            """,
            document_id,
        )
    return [dict(r) for r in rows]


async def get_section(section_id: str) -> dict[str, Any] | None:
    pool = await get_pool()
    if pool is None:
        for secs in _memory_sections.values():
            for s in secs:
                if s['id'] == section_id:
                    return dict(s)
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text, document_id::text, title, level, start_page, end_page, sort_key
            FROM document_sections
            WHERE id = $1::uuid
            """,
            section_id,
        )
    return dict(row) if row else None


async def delete_sections_for_document(document_id: str) -> None:
    pool = await get_pool()
    if pool is None:
        _memory_sections.pop(document_id, None)
        return
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM document_sections WHERE document_id = $1::uuid', document_id)
