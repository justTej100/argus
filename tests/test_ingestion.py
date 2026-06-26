from __future__ import annotations

from agents.IngestionAgent import _build_chunks, _segment_sentences, build_document_chunks


def test_segment_sentences_preserves_math_inline() -> None:
    sentences = _segment_sentences('Energy is given by $E=mc^2$ for rest mass.')
    assert any('$E=mc^2$' in sentence for sentence in sentences)


def test_build_chunks_from_markdown_sentences() -> None:
    sentences = _segment_sentences('Let $x$ be a variable. Then $x^2$ is non-negative.')
    chunks = _build_chunks(page_number=3, sentences=sentences, window_size=2, overlap=0)
    assert chunks
    assert chunks[0]['page_number'] == 3
    assert chunks[0]['sentence_start_idx'] == 0
    assert '$x$' in chunks[0]['text']


def test_build_document_chunks_marks_scan_warning_for_empty_pages() -> None:
    sentences, chunks, has_scan_warning = build_document_chunks([(1, 'A short page.'), (2, '')])
    assert sentences
    assert chunks
    assert has_scan_warning is True
