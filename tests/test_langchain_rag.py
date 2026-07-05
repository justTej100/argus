from __future__ import annotations

from ai.langchain_rag import (
    chunk_metadata,
    format_documents_for_prompt,
    pages_from_chunks,
    split_pages_to_chunks,
)


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
    assert chunks[0]['metadata']['document_id'] == 'doc-1'


def test_format_documents_for_prompt_includes_metadata() -> None:
    chunks = split_pages_to_chunks([(3, 'A theorem about limits.')], title='Calculus')
    prompt = format_documents_for_prompt(chunks)
    assert 'metadata:' in prompt
    assert 'page_content:' in prompt
    assert "'page': 3" in prompt or '"page": 3' in prompt


def test_chunk_metadata_from_retrieved_row() -> None:
    meta = chunk_metadata(
        {
            'page_number': 7,
            'document_id': 'abc',
            'document_title': 'Physics',
            'course': 'PHY 101',
        }
    )
    assert meta['page'] == 7
    assert meta['title'] == 'Physics'


def test_pages_from_chunks_dedupes() -> None:
    chunks = split_pages_to_chunks([(1, 'A ' * 400), (1, 'B ' * 400)])
    pages = pages_from_chunks(chunks)
    assert pages == [1]
