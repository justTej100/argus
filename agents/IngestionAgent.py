from __future__ import annotations

"""PDF ingestion — extract pages, LangChain split, PGVectorStore embed."""

import re

import fitz
import pymupdf4llm

from ai.langchain_rag import split_pages_to_chunks
from ai.langchain_store import add_document_chunks, delete_document_vectors
from db.client import get_document, update_document_status
from storage import download_pdf


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


def build_document_chunks(
    page_texts: list[tuple[int, str]],
    *,
    document_id: str = '',
    title: str = '',
    course: str | None = None,
) -> tuple[list[dict], bool]:
    """Split pages into LangChain metadata chunks."""
    has_scan_warning = False
    expected_pages = {page for page, _ in page_texts}
    extracted_pages = set()

    for page_number, text in page_texts:
        extracted_pages.add(page_number)
        if not (text or '').strip():
            has_scan_warning = True

    all_chunks = split_pages_to_chunks(
        page_texts,
        document_id=document_id,
        title=title,
        course=course,
    )
    if not all_chunks:
        has_scan_warning = True
    if expected_pages and extracted_pages != expected_pages:
        has_scan_warning = True

    return all_chunks, has_scan_warning


async def ingest_document(document_id: str, storage_path: str) -> None:
    """Run the full PDF ingestion pipeline for one uploaded document."""
    await update_document_status(document_id, status='processing', error_message=None)

    pdf_data = download_pdf(storage_path)
    document = fitz.open(stream=pdf_data, filetype='pdf')

    page_texts = extract_pages_from_pdf(document)
    if not page_texts:
        await delete_document_vectors(document_id)
        await update_document_status(
            document_id,
            status='error',
            total_pages=len(document),
            has_scan_warning=True,
            error_message='No extractable text chunks found in PDF.',
        )
        return

    document_row = await get_document(document_id)
    doc_title = (document_row or {}).get('title') or ''
    doc_course = (document_row or {}).get('course')

    all_chunks, has_scan_warning = build_document_chunks(
        page_texts,
        document_id=document_id,
        title=doc_title,
        course=doc_course,
    )

    if not all_chunks:
        await delete_document_vectors(document_id)
        await update_document_status(
            document_id,
            status='error',
            total_pages=len(document),
            has_scan_warning=has_scan_warning,
            error_message='No extractable text chunks found in PDF.',
        )
        return

    await add_document_chunks(document_id, all_chunks)
    await update_document_status(
        document_id,
        status='ready',
        total_pages=len(document),
        has_scan_warning=has_scan_warning,
        error_message=None,
    )
