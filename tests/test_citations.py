from __future__ import annotations

from citations import (
    citation_links,
    extract_page_citations,
    is_citation_only,
    linkify_citations,
    resolve_document_id,
    strip_citation_tags,
)


def test_linkify_page_citations():
    sources = [
        {
            'document_id': 'doc-a',
            'document_title': 'Algebra',
            'page_number': 12,
            'text': 'sample',
        },
    ]
    linked = linkify_citations('See [p12] for details.', sources)
    assert '[p12](/pdf/doc-a?page=12)' in linked


def test_resolve_document_id_by_page():
    sources = [
        {'document_id': 'doc-a', 'page_number': 3},
        {'document_id': 'doc-b', 'page_number': 5},
    ]
    assert resolve_document_id(3, sources) == 'doc-a'


def test_citation_links_page_only():
    sources = [
        {
            'document_id': 'doc-1',
            'document_title': 'Linear Algebra',
            'page_number': 1,
            'text': 'vectors',
        }
    ]
    links = citation_links([1], sources)
    assert links[0]['document_title'] == 'Linear Algebra'
    assert links[0]['href'] == '/pdf/doc-1?page=1'
    assert links[0]['label'] == 'Linear Algebra · p1'


def test_extract_page_citations_dedupes():
    assert extract_page_citations('[p1] text [p1] [p2]') == [1, 2]
