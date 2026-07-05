from __future__ import annotations

"""Embedded PDF viewer for the study page."""

from typing import Callable
from urllib.parse import quote

from nicegui import ui

try:
    from nicegui_pdf import PdfViewer
except Exception:  # pragma: no cover
    PdfViewer = None  # type: ignore[misc, assignment]


class StudyPdfPanel:
    """Side-panel PDF viewer that tracks the active textbook and page."""

    def __init__(self, doc_titles: dict[str, str]) -> None:
        self.doc_titles = doc_titles
        self._container: ui.column | None = None
        self._viewer_slot: ui.column | None = None
        self._title_label: ui.label | None = None
        self._page_input: ui.number | None = None
        self._doc_select: ui.select | None = None
        self._viewer = None
        self._current_doc_id: str | None = None
        self._on_page_change: Callable[[int], None] | None = None

    def mount(self, parent: ui.element) -> None:
        """Build viewer chrome inside the study sidebar."""
        with parent:
            ui.label('Textbook PDF').classes('ice-section-title mb-2')
            if not self.doc_titles:
                ui.label('Upload a textbook to preview it here.').classes('text-sm ice-muted')
                return
            if PdfViewer is None:
                ui.label('PDF viewer unavailable (nicegui-pdf not installed).').classes('text-sm text-amber-300')
                return

            self._doc_select = ui.select(
                options=self.doc_titles,
                value=next(iter(self.doc_titles.keys()), None),
                label='Textbook',
            ).classes('w-full')
            with ui.row().classes('w-full items-center gap-2'):
                self._page_input = ui.number('Page', value=1, min=1, precision=0).classes('w-28')
                ui.button('Go', on_click=self._apply_page_input).props('flat color=primary')
            self._title_label = ui.label('').classes('text-xs ice-muted')
            self._viewer_slot = ui.column().classes('w-full ice-pdf-viewer-slot')
            self._container = parent

            self._doc_select.on_value_change(lambda: self.show(str(self._doc_select.value or ''), page=1))
            self._page_input.on('change', self._apply_page_input)

            first_doc = next(iter(self.doc_titles.keys()), None)
            if first_doc:
                self.show(first_doc, page=1)

    def show(self, document_id: str, page: int = 1) -> None:
        """Load or jump to a page in the selected textbook."""
        if not document_id or document_id not in self.doc_titles:
            return
        if PdfViewer is None or self._viewer_slot is None:
            return

        page = max(1, int(page))
        if self._doc_select is not None:
            self._doc_select.value = document_id
        if self._title_label is not None:
            self._title_label.text = self.doc_titles.get(document_id, 'Textbook')
        if self._page_input is not None:
            self._page_input.value = page

        if document_id != self._current_doc_id:
            self._current_doc_id = document_id
            self._viewer_slot.clear()
            with self._viewer_slot:
                file_url = f'/documents/{quote(document_id, safe="")}/file'
                self._viewer = PdfViewer(file_url).classes('w-full h-[min(52vh,520px)]')
        if self._viewer is not None:
            self._viewer.current_page = page

    def _apply_page_input(self) -> None:
        if self._page_input is None or self._current_doc_id is None or self._viewer is None:
            return
        try:
            page = max(1, int(self._page_input.value))
        except (TypeError, ValueError):
            return
        self._viewer.current_page = page
