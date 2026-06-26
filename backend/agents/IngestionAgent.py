from __future__ import annotations

import asyncio

import fitz
import spacy

from ai.clients import embed
from db.client import replace_document_content, update_document_status
from storage import download_pdf


def _segment_sentences(text: str) -> list[str]:
    nlp = spacy.blank('en')
    nlp.add_pipe('sentencizer')
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]


def _build_chunks(page_number: int, sentences: list[str], window_size: int = 4, overlap: int = 1) -> list[dict]:
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


async def ingest_document(document_id: str, storage_path: str) -> None:
    await update_document_status(document_id, status='processing', error_message=None)

    pdf_data = download_pdf(storage_path)
    document = fitz.open(stream=pdf_data, filetype='pdf')

    all_sentences: list[dict] = []
    all_chunks: list[dict] = []
    has_scan_warning = False

    for page_number, page in enumerate(document, start=1):
        text = page.get_text('text').strip()
        if not text and (page.get_images() or page.get_drawings()):
            has_scan_warning = True
            continue

        sentences = _segment_sentences(text)
        for sentence_idx, sentence in enumerate(sentences):
            all_sentences.append(
                {
                    'page_number': page_number,
                    'sentence_idx': sentence_idx,
                    'text': sentence,
                }
            )

        page_chunks = _build_chunks(page_number, sentences)
        all_chunks.extend(page_chunks)

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
