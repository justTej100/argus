from __future__ import annotations

"""PDF ingestion job used by the background RQ worker."""

import asyncio
import re

import fitz
import pymupdf4llm
import spacy
from ai.clients import embed
from db.client import replace_document_content, update_document_status
from storage import download_pdf


def _segment_sentences(text: str) -> list[str]:
    """Split page text into sentence strings with a blank spaCy pipeline."""
    if not text.strip():
        return []
    nlp = spacy.blank('en')
    nlp.add_pipe('sentencizer')
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]


def _build_chunks(page_number: int, sentences: list[str], window_size: int = 4, overlap: int = 1) -> list[dict]:
    """Build overlapping sentence windows for retrieval and embedding."""
    chunks: list[dict] = []
    if not sentences:
        return chunks

    step = max(1, window_size - overlap)
    for start in range(0, len(sentences), step):
        end = min(len(sentences), start + window_size)
        text = ' '.join(sentences[start:end]).strip()
        if not text:
            continue
        chunks.append(
            {
                'page_number': page_number,
                'sentence_start_idx': start,
                'sentence_end_idx': end - 1,
                'text': text,
                'bbox': None,
            }
        )
        if end == len(sentences):
            break
    return chunks


def _normalize_markdown(text: str) -> str:
    """Collapse noisy markdown whitespace while preserving math delimiters."""
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


def build_document_chunks(page_texts: list[tuple[int, str]]) -> tuple[list[dict], list[dict], bool]:
    """Turn extracted page markdown into sentence rows and retrieval chunks."""
    all_sentences: list[dict] = []
    all_chunks: list[dict] = []
    has_scan_warning = False
    expected_pages = {page for page, _ in page_texts}
    extracted_pages = set()

    for page_number, text in page_texts:
        extracted_pages.add(page_number)
        sentences = _segment_sentences(text)
        if not sentences:
            has_scan_warning = True
            continue
        for sentence_idx, sentence in enumerate(sentences):
            all_sentences.append(
                {
                    'page_number': page_number,
                    'sentence_idx': sentence_idx,
                    'text': sentence,
                }
            )
        all_chunks.extend(_build_chunks(page_number, sentences))

    if expected_pages and extracted_pages != expected_pages:
        has_scan_warning = True

    return all_sentences, all_chunks, has_scan_warning


async def ingest_document(document_id: str, storage_path: str) -> None:
    """Run the full PDF ingestion pipeline for one uploaded document."""
    await update_document_status(document_id, status='processing', error_message=None)

    pdf_data = download_pdf(storage_path)
    document = fitz.open(stream=pdf_data, filetype='pdf')

    page_texts = extract_pages_from_pdf(document)
    if not page_texts:
        await replace_document_content(document_id, chunks=[], sentences=[])
        await update_document_status(
            document_id,
            status='error',
            total_pages=len(document),
            has_scan_warning=True,
            error_message='No extractable text chunks found in PDF.',
        )
        return

    all_sentences, all_chunks, has_scan_warning = build_document_chunks(page_texts)

    if not all_chunks:
        await replace_document_content(document_id, chunks=[], sentences=all_sentences)
        await update_document_status(
            document_id,
            status='error',
            total_pages=len(document),
            has_scan_warning=has_scan_warning,
            error_message='No extractable text chunks found in PDF.',
        )
        return

    embeddings = await asyncio.gather(*(embed(chunk['text']) for chunk in all_chunks))
    for chunk, chunk_embedding in zip(all_chunks, embeddings):
        chunk['embedding'] = chunk_embedding

    await replace_document_content(document_id, chunks=all_chunks, sentences=all_sentences)
    await update_document_status(
        document_id,
        status='ready',
        total_pages=len(document),
        has_scan_warning=has_scan_warning,
        error_message=None,
    )


def ingest_document_job(document_id: str, storage_path: str) -> None:
    """Synchronous entrypoint used by RQ worker processes."""
    try:
        asyncio.run(ingest_document(document_id, storage_path))
    except Exception as exc:
        asyncio.run(
            update_document_status(
                document_id,
                status='error',
                error_message=str(exc),
            )
        )
