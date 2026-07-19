from __future__ import annotations

from ai.chunking import split_pages_to_chunks


def test_split_pages_preserves_metadata() -> None:
    chunks, _skipped = split_pages_to_chunks(
        [
            (1, 'Introduction to linear algebra. Vectors and matrices. ' * 20),
            (2, 'Eigenvalues and eigenvectors. ' * 20),
        ],
        document_id='doc-1',
        title='Linear Algebra',
        description='MATH 240',
        total_pages=2,
    )
    assert chunks
    assert chunks[0]['page_number'] == 1
    assert chunks[0]['metadata']['page'] == 1
    assert chunks[0]['metadata']['title'] == 'Linear Algebra'


def test_empty_pages_are_skipped() -> None:
    chunks, skipped = split_pages_to_chunks(
        [(1, 'A substantial page of textbook content about vectors. ' * 20), (2, '')],
        document_id='doc-1',
        title='Sample',
        total_pages=2,
    )
    assert chunks
    assert all(c['page_number'] == 1 for c in chunks)
    assert skipped >= 1
