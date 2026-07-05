from __future__ import annotations

from agents.IngestionAgent import build_document_chunks, extract_pages_from_pdf
from ai.langchain_rag import split_pages_to_chunks


def test_split_pages_preserves_metadata() -> None:
    chunks = split_pages_to_chunks(
        [(1, 'Introduction to linear algebra. Vectors and matrices.'), (2, 'Eigenvalues and eigenvectors.')],
        document_id='doc-1',
        title='Linear Algebra',
        course='MATH 240',
    )
    assert chunks
    assert chunks[0]['page_number'] == 1
    assert chunks[0]['metadata']['page'] == 1
    assert chunks[0]['metadata']['title'] == 'Linear Algebra'


def test_build_document_chunks_marks_scan_warning_for_empty_pages() -> None:
    chunks, has_scan_warning = build_document_chunks(
        [(1, 'A short page.'), (2, '')],
        document_id='doc-1',
        title='Sample',
    )
    assert chunks
    assert chunks[0]['metadata']['page'] == 1
    assert has_scan_warning is True
