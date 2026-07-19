from __future__ import annotations

"""Document splitting, junk filtering, and chapter metadata for RAG.

Ingestion flow:
  PDF page text → junk filter → chapter map → Document + metadata
  → RecursiveCharacterTextSplitter → chunks for PGVectorStore
"""

import re
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

_TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=150,
    length_function=len,
)

_JUNK_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r'\ball\s+rights\s+reserved\b',
        r'\bcopyright\b.{0,40}\b(©|\(c\)|\d{4})\b',
        r'\blicense[d]?\s+(agreement|terms)\b',
        r'\bterms\s+of\s+(use|service)\b',
        r'\bisbn[\s\-:]+\d',
        r'\bprinted\s+in\s+the\s+(united\s+states|usa|u\.s\.a)\b',
        r'\bthis\s+page\s+intentionally\s+left\s+blank\b',
        r'\bpublisher[\'s]?\s+(notice|catalog)\b',
        r'\bpermission\s+to\s+reproduce\b',
        r'\bdoi\s*:\s*10\.\d+',
    )
]

_CHAPTER_HEADING = re.compile(
    r'^(?:#{1,3}\s*)?(?:chapter|unit|part|section)\s+([0-9ivxlcdm]+)[:.\s—–-]+(.+)$',
    re.I | re.M,
)
_GENERIC_HEADING = re.compile(r'^#{1,2}\s+(.+)$', re.M)


def is_junk_text(text: str, *, page_number: int = 1, total_pages: int = 1) -> bool:
    """Return True if page/chunk text is boilerplate that should not be embedded."""
    cleaned = (text or '').strip()
    if len(cleaned) < 40:
        return True

    lower = cleaned.lower()
    for pat in _JUNK_PATTERNS:
        if pat.search(cleaned):
            # Allow if the page also has substantial non-legal content
            if len(cleaned) < 600 or cleaned.count('\n') < 4:
                return True
            # Front/back matter with license keywords
            if page_number <= 8 or (total_pages and page_number >= max(1, total_pages - 3)):
                return True

    tokens = re.findall(r'[a-zA-Z]{3,}', lower)
    if len(tokens) < 12:
        return True

    # Only flag low-diversity text when the page is short (boilerplate),
    # not when a textbook repeats definitions on a long page.
    unique_ratio = len(set(tokens)) / max(len(tokens), 1)
    if len(cleaned) < 280 and unique_ratio < 0.2:
        return True

    # Mostly digits / ISBN / page numbers
    alpha = sum(1 for c in cleaned if c.isalpha())
    if alpha < 30:
        return True

    return False


def extract_sections_from_toc(toc: list[list], total_pages: int) -> list[dict[str, Any]]:
    """Build section rows from PyMuPDF TOC: [level, title, page]."""
    if not toc:
        return []
    entries: list[tuple[int, str, int]] = []
    for item in toc:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        level, title, page = int(item[0]), str(item[1]).strip(), int(item[2])
        if not title or page < 1:
            continue
        if re.search(r'copyright|license|index|bibliography|preface|^contents$', title, re.I):
            continue
        entries.append((level, title, page))

    if not entries:
        return []

    # Prefer level-1 chapter-like entries; fall back to all
    level1 = [e for e in entries if e[0] == 1]
    use = level1 or entries

    sections: list[dict[str, Any]] = []
    for i, (level, title, start) in enumerate(use):
        end = (use[i + 1][2] - 1) if i + 1 < len(use) else total_pages
        end = max(start, min(end, total_pages or start))
        sections.append(
            {
                'title': title[:200],
                'level': level,
                'start_page': start,
                'end_page': end,
                'sort_key': i,
            }
        )
    return sections


def extract_sections_from_headings(
    page_texts: list[tuple[int, str]],
    total_pages: int,
) -> list[dict[str, Any]]:
    """Fallback chapter detection from markdown/page headings."""
    found: list[tuple[int, str]] = []
    for page_number, text in page_texts:
        for match in _CHAPTER_HEADING.finditer(text or ''):
            title = f'Chapter {match.group(1)}: {match.group(2).strip()}'
            found.append((page_number, title[:200]))
            break
        else:
            # First H1 on early-ish pages sometimes marks chapters
            m = _GENERIC_HEADING.search(text or '')
            if m and page_number > 1:
                heading = m.group(1).strip()
                if re.search(r'chapter|unit|part\b', heading, re.I):
                    found.append((page_number, heading[:200]))

    if not found:
        # Bucket into ~equal page ranges as synthetic chapters
        if total_pages <= 0:
            return []
        bucket = max(15, total_pages // 8)
        sections = []
        start = 1
        idx = 0
        while start <= total_pages:
            end = min(total_pages, start + bucket - 1)
            sections.append(
                {
                    'title': f'Pages {start}–{end}',
                    'level': 1,
                    'start_page': start,
                    'end_page': end,
                    'sort_key': idx,
                }
            )
            idx += 1
            start = end + 1
        return sections

    # Dedupe by page
    by_page: dict[int, str] = {}
    for page, title in found:
        by_page.setdefault(page, title)
    ordered = sorted(by_page.items())
    sections = []
    for i, (start, title) in enumerate(ordered):
        end = (ordered[i + 1][0] - 1) if i + 1 < len(ordered) else total_pages
        sections.append(
            {
                'title': title,
                'level': 1,
                'start_page': start,
                'end_page': max(start, end),
                'sort_key': i,
            }
        )
    return sections


def chapter_for_page(sections: list[dict[str, Any]], page_number: int) -> str:
    for sec in sections:
        if int(sec['start_page']) <= page_number <= int(sec['end_page']):
            return str(sec['title'])
    return ''


def filter_page_texts(
    page_texts: list[tuple[int, str]],
    *,
    total_pages: int,
) -> tuple[list[tuple[int, str]], int]:
    """Drop junk pages. Returns (kept pages, skipped count)."""
    kept: list[tuple[int, str]] = []
    skipped = 0
    for page_number, text in page_texts:
        if is_junk_text(text, page_number=page_number, total_pages=total_pages):
            skipped += 1
            continue
        kept.append((page_number, text))
    return kept, skipped


def split_pages_to_chunks(
    page_texts: list[tuple[int, str]],
    *,
    document_id: str = '',
    title: str = '',
    description: str | None = None,
    sections: list[dict[str, Any]] | None = None,
    total_pages: int = 0,
) -> tuple[list[dict], int]:
    """Split pages into chunks with page + chapter metadata. Returns (chunks, skipped_junk)."""
    if not total_pages and page_texts:
        total_pages = max(p for p, _ in page_texts)

    kept, skipped = filter_page_texts(page_texts, total_pages=total_pages or 1)
    sections = sections or []

    chunks: list[dict] = []
    for page_number, text in kept:
        cleaned = (text or '').strip()
        if not cleaned:
            skipped += 1
            continue
        chapter = chapter_for_page(sections, page_number)
        section_id = ''
        for sec in sections:
            if int(sec['start_page']) <= page_number <= int(sec['end_page']):
                section_id = str(sec.get('id') or '')
                break

        page_doc = Document(
            page_content=cleaned,
            metadata={
                'page': page_number,
                'page_number': page_number,
                'document_id': document_id,
                'title': title,
                'source': title or document_id,
                'description': description or '',
                'chapter': chapter,
                'section_id': section_id,
            },
        )
        for split in _TEXT_SPLITTER.split_documents([page_doc]):
            content = (split.page_content or '').strip()
            if len(content) < 40:
                skipped += 1
                continue
            # Keep pattern-only check on splits (avoid unique-ratio false positives)
            if any(pat.search(content) for pat in _JUNK_PATTERNS) and len(content) < 500:
                skipped += 1
                continue
            chunks.append(doc_to_chunk(split))
    return chunks, skipped


def doc_to_chunk(doc: Document) -> dict:
    """Map a LangChain Document to our chunk row shape."""
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
        'description': chunk.get('description') or '',
        'chapter': chunk.get('chapter') or '',
        'section_id': chunk.get('section_id') or '',
    }


def format_documents_for_prompt(chunks: list[dict]) -> str:
    """Format retrieved chunks — content + metadata for citations."""
    if not chunks:
        return 'No textbook excerpts were retrieved.'

    blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        meta = chunk_metadata(chunk)
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
