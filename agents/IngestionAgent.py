from __future__ import annotations

"""PDF ingestion: extract pages → junk filter → sections → chunk → embed (resumable).

Vectors go to argus_vectors via ai.vector_store.add_document_chunks().
On Gemini 429, pauses ~24h and resumes later.
"""

import logging
import re

import fitz
import pymupdf4llm

from agents.FeedAgent import generate_textbook_feed, seed_leetcode_accounts
from ai.chunking import (
    extract_sections_from_headings,
    extract_sections_from_toc,
    split_pages_to_chunks,
)
from ai.vector_store import EmbedPaused, add_document_chunks, delete_document_vectors
from db.client import get_document, update_document_status
from db.sections import replace_sections
from storage import download_pdf

logger = logging.getLogger(__name__)


def _normalize_markdown(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _page_number_from_chunk(chunk: dict, fallback: int) -> int:
    metadata = chunk.get('metadata') or {}
    for key in ('page', 'page_number', 'page_idx'):
        if key in metadata and metadata[key] is not None:
            page = int(metadata[key])
            return page + 1 if key == 'page' and page < fallback else page
    return fallback


def extract_pages_from_pdf(document: fitz.Document) -> list[tuple[int, str]]:
    """Extract per-page markdown via pymupdf4llm, with OCR fallback for empty pages."""
    page_chunks = pymupdf4llm.to_markdown(document, page_chunks=True, force_text=True)
    if not isinstance(page_chunks, list):
        page_chunks = [{'text': str(page_chunks), 'metadata': {'page': 0}}]

    pages: dict[int, str] = {}
    for index, chunk in enumerate(page_chunks, start=1):
        page_number = _page_number_from_chunk(chunk, index)
        text = _normalize_markdown(chunk.get('text') or '')
        if text:
            pages[page_number] = text

    total_pages = len(document)
    for page_number in range(1, total_pages + 1):
        if page_number in pages and pages[page_number]:
            continue
        page = document[page_number - 1]
        if not page.get_images() and not page.get_drawings() and page.get_text('text').strip():
            continue
        ocr_chunks = pymupdf4llm.to_markdown(
            document,
            pages=[page_number - 1],
            page_chunks=True,
            force_ocr=True,
        )
        if isinstance(ocr_chunks, list) and ocr_chunks:
            ocr_text = _normalize_markdown(ocr_chunks[0].get('text') or '')
            if ocr_text:
                pages[page_number] = ocr_text

    return sorted(pages.items())


async def _set_embed_progress(
    document_id: str,
    *,
    status: str,
    embed_done: int | None = None,
    embed_total: int | None = None,
    embed_resume_at=None,
    error_message: str | None = None,
    total_pages: int | None = None,
    has_scan_warning: bool | None = None,
    chunks_skipped: int | None = None,
) -> None:
    await update_document_status(
        document_id,
        status=status,
        total_pages=total_pages,
        has_scan_warning=has_scan_warning,
        error_message=error_message,
        embed_done=embed_done,
        embed_total=embed_total,
        embed_resume_at=embed_resume_at,
        chunks_skipped=chunks_skipped,
    )


async def ingest_document(document_id: str, storage_path: str, *, resume: bool = False) -> None:
    """Run PDF ingestion (or resume embedding) for one uploaded document."""
    document_row = await get_document(document_id)
    start_index = int((document_row or {}).get('embed_done') or 0) if resume else 0

    await _set_embed_progress(
        document_id,
        status='processing',
        error_message=None,
        embed_resume_at=None,
    )

    pdf_data = download_pdf(storage_path)
    document = fitz.open(stream=pdf_data, filetype='pdf')
    total_pages = len(document)

    page_texts = extract_pages_from_pdf(document)
    if not page_texts:
        await delete_document_vectors(document_id)
        await _set_embed_progress(
            document_id,
            status='error',
            total_pages=total_pages,
            has_scan_warning=True,
            error_message='No extractable text chunks found in PDF.',
            embed_done=0,
            embed_total=0,
        )
        return

    doc_title = (document_row or {}).get('title') or ''
    doc_description = (document_row or {}).get('description')

    toc = document.get_toc() or []
    sections = extract_sections_from_toc(toc, total_pages)
    if not sections:
        sections = extract_sections_from_headings(page_texts, total_pages)

    saved_sections = await replace_sections(document_id, sections)
    # Attach ids onto section dicts for chunk metadata
    section_map = {s['title']: s for s in saved_sections}

    all_chunks, skipped = split_pages_to_chunks(
        page_texts,
        document_id=document_id,
        title=doc_title,
        description=doc_description,
        sections=saved_sections,
        total_pages=total_pages,
    )
    # Ensure section_id on chunk metadata
    for chunk in all_chunks:
        meta = chunk.get('metadata') or {}
        chapter = meta.get('chapter') or ''
        if chapter and chapter in section_map:
            meta['section_id'] = section_map[chapter]['id']
            chunk['metadata'] = meta

    if not all_chunks:
        await delete_document_vectors(document_id)
        await _set_embed_progress(
            document_id,
            status='error',
            total_pages=total_pages,
            has_scan_warning=True,
            error_message='No embeddable content after filtering boilerplate.',
            chunks_skipped=skipped,
            embed_done=0,
            embed_total=0,
        )
        return

    logger.info(
        'Ingest %s: %d chunks (%d junk skipped), %d sections',
        document_id,
        len(all_chunks),
        skipped,
        len(saved_sections),
    )

    await _set_embed_progress(
        document_id,
        status='embedding',
        total_pages=total_pages,
        has_scan_warning=bool(skipped > len(page_texts) * 0.5),
        chunks_skipped=skipped,
        embed_total=len(all_chunks),
        embed_done=start_index,
    )

    async def on_progress(done: int, total: int) -> None:
        await _set_embed_progress(
            document_id,
            status='embedding',
            embed_done=done,
            embed_total=total,
            chunks_skipped=skipped,
            total_pages=total_pages,
        )

    try:
        await add_document_chunks(
            document_id,
            all_chunks,
            start_index=start_index,
            on_progress=on_progress,
            clear_existing=not resume or start_index == 0,
        )
    except EmbedPaused as paused:
        await _set_embed_progress(
            document_id,
            status='embedding_paused',
            embed_done=paused.done,
            embed_total=paused.total,
            embed_resume_at=paused.resume_at,
            chunks_skipped=skipped,
            total_pages=total_pages,
            error_message=f'Embedding rate-limited. Resuming after {paused.resume_at.isoformat()}.',
        )
        logger.warning('Embedding paused for %s at %s/%s', document_id, paused.done, paused.total)
        return

    await _set_embed_progress(
        document_id,
        status='ready',
        total_pages=total_pages,
        has_scan_warning=bool(skipped > len(page_texts) * 0.5),
        error_message=None,
        embed_done=len(all_chunks),
        embed_total=len(all_chunks),
        chunks_skipped=skipped,
        embed_resume_at=None,
    )

    try:
        await seed_leetcode_accounts()
        n = await generate_textbook_feed(document_id, doc_title or 'Textbook')
        logger.info('Feed: created %d posts for %s', n, document_id)
    except Exception as exc:
        logger.warning('Feed generation failed for %s: %s', document_id, exc)


async def resume_paused_embeddings() -> int:
    """Resume documents whose embed_resume_at has passed. Returns count started."""
    from db.client import list_documents
    from jobs import schedule_ingestion

    docs = await list_documents()
    started = 0
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for doc in docs:
        if doc.get('status') != 'embedding_paused':
            continue
        resume_at = doc.get('embed_resume_at')
        if resume_at is not None:
            if getattr(resume_at, 'tzinfo', None) is None:
                resume_at = resume_at.replace(tzinfo=timezone.utc)
            if resume_at > now:
                continue
        path = doc.get('storage_path') or ''
        if not path:
            continue
        schedule_ingestion(doc['id'], path, resume=True)
        started += 1
    return started
