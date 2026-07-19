from __future__ import annotations

from ai.chunking import (
    chunk_metadata,
    format_documents_for_prompt,
    is_junk_text,
    pages_from_chunks,
    split_pages_to_chunks,
)


def test_split_pages_preserves_metadata() -> None:
    chunks, skipped = split_pages_to_chunks(
        [
            (1, 'Introduction to linear algebra. Vectors and matrices. ' * 20),
            (2, 'Eigenvalues and eigenvectors. ' * 20),
        ],
        document_id='doc-1',
        title='Linear Algebra',
        description='MATH 240',
        sections=[
            {
                'id': 'sec-1',
                'title': 'Chapter 1: Intro',
                'level': 1,
                'start_page': 1,
                'end_page': 2,
                'sort_key': 0,
            }
        ],
        total_pages=2,
    )
    assert chunks
    assert skipped == 0
    assert chunks[0]['page_number'] == 1
    assert chunks[0]['metadata']['page'] == 1
    assert chunks[0]['metadata']['title'] == 'Linear Algebra'
    assert chunks[0]['metadata']['document_id'] == 'doc-1'
    assert chunks[0]['metadata']['chapter'] == 'Chapter 1: Intro'


def test_junk_license_filtered() -> None:
    assert is_junk_text('Copyright © 2025 All rights reserved. License agreement.', page_number=2, total_pages=200)
    chunks, skipped = split_pages_to_chunks(
        [
            (1, 'Copyright © 2025 Publisher. All rights reserved. ISBN 978-1-234.'),
            (2, 'Linear algebra is the study of vectors and linear maps. ' * 30),
        ],
        title='Book',
        total_pages=2,
    )
    assert skipped >= 1
    assert all(c['page_number'] != 1 for c in chunks)


def test_format_documents_for_prompt_includes_metadata() -> None:
    chunks, _ = split_pages_to_chunks([(3, 'A theorem about limits. ' * 20)], title='Calculus', total_pages=3)
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
            'description': 'PHY 101',
        }
    )
    assert meta['page'] == 7
    assert meta['title'] == 'Physics'


def test_pages_from_chunks_dedupes() -> None:
    chunks, _ = split_pages_to_chunks(
        [(1, 'Vectors span a space when every vector is a linear combination. ' * 12)],
        total_pages=1,
    )
    pages = pages_from_chunks(chunks)
    assert pages == [1]
