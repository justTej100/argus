from __future__ import annotations

"""LangChain document splitting and metadata formatting for RAG."""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

_TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=150,
    length_function=len,
)


def split_pages_to_chunks(
    page_texts: list[tuple[int, str]],
    *,
    document_id: str = '',
    title: str = '',
    course: str | None = None,
) -> list[dict]:
    """Split PDF pages into chunks with LangChain metadata (page, source, title)."""
    chunks: list[dict] = []
    for page_number, text in page_texts:
        cleaned = (text or '').strip()
        if not cleaned:
            continue
        page_doc = Document(
            page_content=cleaned,
            metadata={
                'page': page_number,
                'page_number': page_number,
                'document_id': document_id,
                'title': title,
                'source': title or document_id,
                'course': course or '',
            },
        )
        for split in _TEXT_SPLITTER.split_documents([page_doc]):
            chunks.append(langchain_doc_to_chunk(split))
    return chunks


def langchain_doc_to_chunk(doc: Document) -> dict:
    """Map a LangChain Document to our Postgres chunk row shape."""
    meta = dict(doc.metadata or {})
    page = int(meta.get('page') or meta.get('page_number') or 1)
    return {
        'page_number': page,
        'sentence_start_idx': 0,
        'sentence_end_idx': 0,
        'text': doc.page_content,
        'bbox': None,
        'metadata': meta,
    }


def chunk_metadata(chunk: dict) -> dict:
    """Normalize metadata from a retrieved chunk (DB or memory)."""
    if chunk.get('metadata'):
        return dict(chunk['metadata'])
    return {
        'page': chunk.get('page_number'),
        'page_number': chunk.get('page_number'),
        'document_id': chunk.get('document_id'),
        'title': chunk.get('document_title'),
        'source': chunk.get('document_title') or chunk.get('document_id'),
        'course': chunk.get('course') or '',
    }


def format_documents_for_prompt(chunks: list[dict]) -> str:
    """Format retrieved chunks the LangChain way — content + metadata for citations."""
    if not chunks:
        return 'No textbook excerpts were retrieved.'

    blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        meta = chunk_metadata(chunk)
        page = meta.get('page') or meta.get('page_number')
        blocks.append(
            f'Document {index}\n'
            f'metadata: {meta}\n'
            f'page_content:\n{chunk.get("text", "")}'
        )
    return '\n\n---\n\n'.join(blocks)


def pages_from_chunks(chunks: list[dict]) -> list[int]:
    """Unique page numbers from chunk metadata (for UI / citations)."""
    pages: list[int] = []
    seen: set[int] = set()
    for chunk in chunks:
        meta = chunk_metadata(chunk)
        try:
            page = int(meta.get('page') or meta.get('page_number') or chunk.get('page_number'))
        except (TypeError, ValueError):
            continue
        if page not in seen:
            seen.add(page)
            pages.append(page)
    return pages
