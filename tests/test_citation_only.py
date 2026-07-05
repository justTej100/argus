from __future__ import annotations

from ui.citations import is_citation_only, strip_citation_tags


def test_is_citation_only_detects_page_tags_without_prose():
    assert is_citation_only('[p1] [p2] [p3]')
    assert is_citation_only('References: [p1] [p2]')


def test_is_citation_only_detects_legacy_sentence_tags():
    assert is_citation_only('[p1:s3] [p1:s6] [p1:s12]')


def test_is_citation_only_accepts_real_answer():
    text = (
        'This course covers algorithms, data structures, and systems topics including '
        'memory management and process scheduling across several units. See [p5] for the outline.'
    )
    assert not is_citation_only(text)


def test_strip_citation_tags_page_and_legacy():
    assert strip_citation_tags('Hello [p1] world [p2:s3]') == 'Hello world'
