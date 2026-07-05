from __future__ import annotations

"""Reusable NiceGUI blocks for the study experience."""

from typing import Callable

from nicegui import ui

from ui.citations import citation_links, extract_page_citations
from ui.theme import render_ice_markdown


def render_inline_citations(text: str, sources: list[dict], on_open_pdf: Callable[[str, int], None] | None) -> None:
    """Render the full tutor answer; citation chips below handle PDF jumps."""
    if not (text or '').strip():
        ui.label('No answer text returned.').classes('text-sm ice-muted')
        return
    # Always render the complete markdown answer so explanations are never dropped.
    render_ice_markdown(text)


def scroll_study_thread() -> None:
    """Scroll the conversation column to the latest message."""
    ui.run_javascript(
        """
        (() => {
          const el = document.querySelector('.ice-thread-scroll');
          if (el) el.scrollTop = el.scrollHeight;
        })();
        """
    )


def render_citation_chips(
    pages: list[int],
    sources: list[dict],
    on_open_pdf: Callable[[str, int], None] | None = None,
) -> None:
    """Render collapsible page links — secondary to the main answer."""
    if not pages:
        return
    links = citation_links(pages, sources)
    if not links:
        return
    with ui.expansion('Jump to page in PDF', icon='menu_book').classes('w-full mt-2 text-sm'):
        with ui.row().classes('gap-2 flex-wrap pt-1'):
            for link in links:
                short = f"p{link['page']}"
                if on_open_pdf:
                    ui.button(
                        short,
                        on_click=lambda d=link['document_id'], p=link['page']: on_open_pdf(d, p),
                    ).props('flat dense no-caps').classes('ice-citation')
                else:
                    ui.link(short, link['href']).classes('ice-citation underline text-xs')


def render_sources_panel(
    sources_box,
    sources: list[dict],
    on_open_pdf: Callable[[str, int], None] | None = None,
) -> None:
    """Fill the right-hand sources panel with retrieved book excerpts."""
    sources_box.clear()
    with sources_box:
        ui.label('Book passages').classes('ice-section-title mb-2')
        if not sources:
            ui.label('Ask a question to see the textbook excerpts Argus used.').classes('text-sm ice-muted')
            return
        for index, source in enumerate(sources[:8], start=1):
            title = source.get('document_title') or 'Textbook'
            page = source.get('page_number', '?')
            start = source.get('sentence_start_idx', 0)
            end = source.get('sentence_end_idx', start)
            doc_id = source.get('document_id', '')
            excerpt = (source.get('text') or '').strip()
            if len(excerpt) > 320:
                excerpt = excerpt[:317] + '…'
            with ui.card().classes('w-full p-3 ice-source-card'):
                with ui.row().classes('w-full items-center justify-between gap-2'):
                    ui.label(f'{index}. {title}').classes('text-sm font-semibold')
                    if doc_id:
                        if on_open_pdf:
                            ui.button(
                                f'p{page}',
                                on_click=lambda d=doc_id, p=int(page) if str(page).isdigit() else 1: on_open_pdf(d, p),
                            ).props('flat dense').classes('ice-citation text-xs')
                        else:
                            ui.link(f'p{page}', f'/pdf/{doc_id}?page={page}').classes('ice-citation text-xs')
                ui.label(f'page {page}').classes('text-xs ice-muted mb-1')
                ui.label(excerpt).classes('text-sm leading-relaxed')


def render_tutor_answer(
    thread,
    answer: str,
    sources: list[dict],
    eval_result: dict | None = None,
    on_open_pdf: Callable[[str, int], None] | None = None,
) -> None:
    """Render a tutor reply with linked citations and optional grounding warning."""
    citations = extract_page_citations(answer)
    with thread:
        with ui.card().classes('w-full p-4 ice-bubble-assistant'):
            ui.label('Argus · Tutor').classes('ice-hud-label mb-2')
            if eval_result and not eval_result.get('passed', True):
                ui.label('Answer may be incomplete — see excerpts on the right.').classes('text-xs text-amber-300 mb-2')
            render_inline_citations(answer, sources, on_open_pdf)
            if citations:
                render_citation_chips(citations, sources, on_open_pdf)
    scroll_study_thread()


def render_quiz_items(
    thread,
    items: list[dict],
    sources: list[dict],
    on_open_pdf: Callable[[str, int], None] | None = None,
) -> None:
    """Render quiz Q&A cards with linked citations."""
    with thread:
        for item in items:
            with ui.card().classes('w-full p-3 ice-card'):
                ui.label(item.get('question', '')).classes('font-semibold')
                ui.separator()
                render_inline_citations(item.get('answer', ''), sources, on_open_pdf)
                tags = item.get('citations') or []
                if tags:
                    pages = extract_page_citations(' '.join(tags))
                    render_citation_chips(pages, sources, on_open_pdf)
    scroll_study_thread()


def render_flashcard_items(
    thread,
    items: list[dict],
    sources: list[dict],
    on_open_pdf: Callable[[str, int], None] | None = None,
) -> ui.row | None:
    """Render flashcards and return an action row for follow-up buttons."""
    with thread:
        for item in items:
            with ui.expansion(item.get('front', 'Flashcard')).classes('w-full ice-card'):
                render_inline_citations(item.get('back', ''), sources, on_open_pdf)
                tags = item.get('citations') or []
                if tags:
                    pages = extract_page_citations(' '.join(tags))
                    render_citation_chips(pages, sources, on_open_pdf)
        action_row = ui.row().classes('w-full gap-2 mt-2')
    scroll_study_thread()
    return action_row


def render_summary_block(
    thread,
    summary: dict,
    sources: list[dict],
    on_open_pdf: Callable[[str, int], None] | None = None,
) -> None:
    """Render a structured summary with linked citations."""
    lines: list[str] = []
    if summary.get('title'):
        lines.append(f"# {summary['title']}")
    for section in summary.get('outline', []):
        lines.append(f"## {section.get('heading', '')}")
        for bullet in section.get('bullets', []):
            lines.append(f'- {bullet}')
    body = '\n'.join(lines)
    if summary.get('citations'):
        body += '\n\nCitations: ' + ', '.join(summary['citations'])
    with thread:
        render_inline_citations(body, sources, on_open_pdf)
    scroll_study_thread()
