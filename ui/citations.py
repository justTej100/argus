from __future__ import annotations

"""Citation parsing and link generation — page-level [pN] tags only."""

import re
from urllib.parse import quote

# Primary format: [p12]. Legacy [p12:s4] still parsed for old messages.
PAGE_CITATION_PATTERN = re.compile(r'\[p(\d+)\]')
LEGACY_CITATION_PATTERN = re.compile(r'\[p(\d+):s(\d+)\]')


def strip_citation_tags(text: str) -> str:
    """Remove page citation tags and collapse whitespace."""
    cleaned = LEGACY_CITATION_PATTERN.sub('', text or '')
    cleaned = PAGE_CITATION_PATTERN.sub('', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()


def is_citation_only(text: str, *, min_words: int = 18) -> bool:
    """True when the model returned mostly citation tags with no real explanation."""
    prose = strip_citation_tags(text)
    if not prose or prose.lower() in {'references:', 'references', 'refs:'}:
        return True
    return len(prose.split()) < min_words


def extract_page_citations(text: str) -> list[int]:
    """Return ordered unique page numbers from [pN] and legacy [pN:sM] tags."""
    pages: list[int] = []
    seen: set[int] = set()
    for pattern in (PAGE_CITATION_PATTERN, LEGACY_CITATION_PATTERN):
        for match in pattern.finditer(text or ''):
            page = int(match.group(1))
            if page not in seen:
                seen.add(page)
                pages.append(page)
    return pages


# Backward-compatible alias
def extract_citations(text: str) -> list[tuple[int, int]]:
    """Legacy API — returns (page, 0) pairs for page-only citations."""
    return [(page, 0) for page in extract_page_citations(text)]


def resolve_document_id(page: int, sources: list[dict], sentence: int = 0) -> str | None:
    """Pick the document that contains this page in the retrieved sources."""
    del sentence  # page-level citations only
    for source in sources:
        if source.get('page_number') == page:
            return source.get('document_id')
    for source in sources:
        try:
            if int(source.get('page_number', -1)) == page:
                return source.get('document_id')
        except (TypeError, ValueError):
            continue
    if sources:
        return sources[0].get('document_id')
    return None


def pdf_href(document_id: str, page: int) -> str:
    """Build a viewer URL for one page."""
    return f'/pdf/{quote(document_id, safe="")}?page={page}'


def linkify_citations(text: str, sources: list[dict]) -> str:
    """Turn [pN] tags into markdown links to the PDF viewer."""
    if not text or not sources:
        return text

    def replace_page(match: re.Match[str]) -> str:
        page = int(match.group(1))
        document_id = resolve_document_id(page, sources)
        if not document_id:
            return match.group(0)
        return f'[p{page}]({pdf_href(document_id, page)})'

    def replace_legacy(match: re.Match[str]) -> str:
        page = int(match.group(1))
        document_id = resolve_document_id(page, sources)
        if not document_id:
            return match.group(0)
        return f'[p{page}]({pdf_href(document_id, page)})'

    text = LEGACY_CITATION_PATTERN.sub(replace_legacy, text)
    return PAGE_CITATION_PATTERN.sub(replace_page, text)


def citation_links(pages: list[int], sources: list[dict]) -> list[dict]:
    """Build structured page citation metadata for UI chips."""
    links: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for page in pages:
        document_id = resolve_document_id(page, sources)
        if not document_id:
            continue
        key = (document_id, page)
        if key in seen:
            continue
        seen.add(key)
        title = next((s.get('document_title') for s in sources if s.get('document_id') == document_id), 'Textbook')
        links.append(
            {
                'document_id': document_id,
                'document_title': title,
                'page': page,
                'label': f'{title} · p{page}',
                'href': pdf_href(document_id, page),
            }
        )
    return links
