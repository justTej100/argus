from __future__ import annotations

from mail.gmail import build_flashcards_html, build_flashcards_plain


def test_build_flashcards_plain_includes_cards():
    text = build_flashcards_plain(
        topic='Eigenvalues',
        items=[{'front': 'What is an eigenvalue?', 'back': 'A scalar λ.', 'citations': ['[p2]']}],
    )
    assert 'Eigenvalues' in text
    assert 'What is an eigenvalue?' in text
    assert 'A scalar λ.' in text


def test_build_flashcards_html_includes_citation_link():
    html = build_flashcards_html(
        topic='Eigenvalues',
        items=[{'front': 'Q', 'back': 'A', 'citations': ['[p2:s1]']}],
        sources=[
            {
                'document_id': 'doc-1',
                'page_number': 2,
                'sentence_start_idx': 1,
                'sentence_end_idx': 1,
                'text': 'x',
            }
        ],
    )
    assert 'p2' in html
    assert 'p2:s1' not in html
    assert '/pdf/doc-1?page=2' in html
