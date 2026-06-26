from __future__ import annotations

"""FastAPI app and NiceGUI pages for the Argus study buddy.

This file is the single-process entrypoint. It defines the HTTP API, the
session login flow, document routes, and the browser UI pages that NiceGUI
mounts onto the same FastAPI instance.
"""

import re
import time
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.responses import Response as FastAPIResponse
from nicegui import ui
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from agents.Pipeline import ResearchPipeline
from auth import clear_session_cookie, require_session, session_is_valid, set_session_cookie, verify_admin_email
from db.client import create_document, delete_document, get_document, init_schema, list_documents, update_document_status
from jobs import schedule_ingestion
from storage import delete_pdf, download_pdf, upload_pdf
from ui.theme import apply_ice_theme, ice_shell, render_ice_markdown

load_dotenv(Path(__file__).parent / '.env')


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize persistence on startup."""
    await init_schema()
    yield


app = FastAPI(title='Argus Study Buddy', version='2.0.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
    allow_credentials=True,
)
app.add_middleware(SessionMiddleware, secret_key=os.environ.get('SECRET_KEY', 'dev-argus-secret'))

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

pipeline = ResearchPipeline()

try:
    from nicegui_pdf import PdfViewer
except Exception:  # pragma: no cover
    PdfViewer = None  # type: ignore


class ChatMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str


class Scope(BaseModel):
    type: Literal['document', 'course', 'library'] = 'library'
    document_id: str | None = None
    course: str | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    provider: Literal['deepseek', 'gemini'] = 'deepseek'
    mode: Literal['chat', 'quiz', 'flashcards', 'summary'] = 'chat'
    scope: Scope = Scope()


class BulkDeleteRequest(BaseModel):
    document_ids: list[str]


class EvalResponse(BaseModel):
    passed: bool
    score: float
    claims_checked: int
    claims_grounded: int
    ungrounded_claims: list[str]
    explanation: str
    citation_errors: list[str]


class StudyResponse(BaseModel):
    query: str
    type: str
    brief: str
    eval: EvalResponse
    sources: list[dict]
    community_context: list[dict]
    meta: dict
    structured: dict | None = None


def _ensure_ui_session(request: Request) -> bool:
    """Redirect unauthenticated browser requests to /login."""
    if session_is_valid(request):
        return True
    ui.navigate.to('/login')
    return False


def _extract_citations(text: str) -> list[tuple[int, int]]:
    """Extract page/sentence citation tags from generated text."""
    pattern = re.compile(r'\[p(\d+):s(\d+)\]')
    return [(int(m.group(1)), int(m.group(2))) for m in pattern.finditer(text)]


@app.get('/health', tags=['Meta'])
def health() -> dict:
    """Return a tiny payload for deployment health checks."""
    return {'status': 'ok', 'timestamp': time.time()}


@app.get('/auth/google', tags=['Auth'])
async def auth_google(request: Request):
    """Redirect the browser to Google's OAuth consent screen."""
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
    if not redirect_uri:
        raise HTTPException(status_code=500, detail='GOOGLE_REDIRECT_URI is not configured.')
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get('/auth/google/callback', tags=['Auth'])
async def auth_google_callback(request: Request):
    """Exchange the OAuth code, verify admin email, and set the session cookie."""
    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get('userinfo')
        if not userinfo:
            userinfo = await oauth.google.parse_id_token(request, token)
        email = verify_admin_email(userinfo.get('email'))
        response = RedirectResponse(url='/', status_code=302)
        set_session_cookie(response, email)
        return response
    except HTTPException as exc:
        if exc.status_code == 403:
            return RedirectResponse(url='/login?error=unauthorized', status_code=302)
        raise
    except Exception:
        return RedirectResponse(url='/login?error=oauth_failed', status_code=302)


@app.get('/logout', tags=['Auth'])
def logout() -> RedirectResponse:
    """Clear the session cookie and return to the login page."""
    response = RedirectResponse(url='/login', status_code=302)
    clear_session_cookie(response)
    return response


@app.get('/documents', tags=['Documents'])
async def documents(course: str | None = None) -> list[dict]:
    """List documents, optionally filtered by course."""
    return await list_documents(course=course)


@app.post('/documents', tags=['Documents'], dependencies=[Depends(require_session)])
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    course: str | None = Form(None),
    subreddits: str | None = Form(None),
) -> dict:
    """Upload a PDF, create its row, and enqueue background ingestion."""
    filename = file.filename or ''
    if file.content_type not in {'application/pdf', 'application/octet-stream'} and not filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail='Only PDF uploads are supported.')

    payload = await file.read()
    subreddit_list = [s.strip().removeprefix('r/') for s in (subreddits or '').split(',') if s.strip()]

    document_id = await create_document(
        title=title,
        course=course or None,
        status='processing',
        total_pages=0,
        storage_path='',
        subreddits=subreddit_list or None,
    )
    storage_path = upload_pdf(document_id, filename or f'{document_id}.pdf', payload)
    await update_document_status(document_id, status='processing', storage_path=storage_path)
    job_id = schedule_ingestion(document_id, storage_path)
    return {'id': document_id, 'status': 'processing', 'job_id': job_id}


@app.get('/documents/{document_id}/status', tags=['Documents'])
async def document_status(document_id: str) -> dict:
    """Return ingestion status for UI polling."""
    document = await get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail='Document not found.')
    return {
        'id': document['id'],
        'status': document['status'],
        'total_pages': document.get('total_pages'),
        'has_scan_warning': document.get('has_scan_warning', False),
        'error_message': document.get('error_message'),
    }


@app.delete('/documents/{document_id}', tags=['Documents'], dependencies=[Depends(require_session)])
async def remove_document(document_id: str) -> dict:
    """Delete a document row and its stored PDF."""
    document = await get_document(document_id)
    if document:
        delete_pdf(document.get('storage_path') or '')
    await delete_document(document_id)
    return {'ok': True}


@app.post('/documents/bulk-delete', tags=['Documents'], dependencies=[Depends(require_session)])
async def bulk_remove_documents(body: BulkDeleteRequest) -> dict:
    """Delete multiple documents, their PDFs, and all dependent chunks."""
    deleted: list[str] = []
    for document_id in body.document_ids:
        document = await get_document(document_id)
        if not document:
            continue
        delete_pdf(document.get('storage_path') or '')
        await delete_document(document_id)
        deleted.append(document_id)
    return {'deleted': len(deleted), 'ids': deleted}


@app.get('/documents/{document_id}/file', dependencies=[Depends(require_session)], tags=['Documents'])
async def get_document_file(document_id: str) -> FastAPIResponse:
    """Stream the original PDF back to the PDF viewer."""
    document = await get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail='Document not found.')
    blob = download_pdf(document['storage_path'])
    return FastAPIResponse(content=blob, media_type='application/pdf')


@app.post('/chat', response_model=StudyResponse, tags=['Study'], dependencies=[Depends(require_session)])
async def chat(body: ChatRequest) -> StudyResponse:
    """Run the full study pipeline for one user question."""
    user_messages = [m for m in body.messages if m.role == 'user']
    if not user_messages:
        raise HTTPException(status_code=400, detail='At least one user message is required.')

    query = user_messages[-1].content
    history = [{'role': m.role, 'content': m.content} for m in body.messages[:-1]] or None
    result = await pipeline.run(
        query=query,
        query_type='study',
        provider=body.provider,
        conversation_history=history,
        scope=body.scope.model_dump(),
        mode=body.mode,
    )

    return StudyResponse(
        query=result.query,
        type=result.query_type,
        brief=result.brief,
        eval=EvalResponse(**vars(result.eval)),
        sources=result.sources,
        community_context=result.community_context,
        meta=result.meta,
        structured=result.structured,
    )


@app.post('/search', response_model=StudyResponse, tags=['Study'], dependencies=[Depends(require_session)])
async def search(body: ChatRequest) -> StudyResponse:
    """Compatibility alias that reuses the chat pipeline."""
    return await chat(body)


@ui.page('/')
async def library_page(request: Request) -> None:
    """Render the library page with upload, status, and delete actions."""
    if not _ensure_ui_session(request):
        return

    with ui.column().classes('w-full max-w-6xl mx-auto px-4 py-6'):
        ice_shell(active='/')
        ui.label('Library').classes('ice-heading mb-2')
        ui.label('Deposit textbook PDFs into the glacial core.').classes('ice-subheading mb-6')

        docs_table = ui.column().classes('w-full gap-2')
        selection: dict = {'ids': set(), 'docs_by_id': {}}

        delete_selected_btn = ui.button('Delete selected (0)').props('flat color=negative')
        delete_selected_btn.disable()

        with ui.dialog() as confirm_dialog, ui.card().classes('ice-card p-6 gap-4 w-full max-w-lg'):
            ui.label('Delete selected textbooks?').classes('text-xl font-semibold')
            confirm_summary = ui.label('').classes('ice-muted')
            confirm_list = ui.column().classes('gap-1 max-h-48 overflow-y-auto')
            ui.label('This removes PDFs and all embeddings. Cannot be undone.').classes('text-sm text-red-300')
            pending_delete: dict = {'ids': []}

            async def confirm_bulk_delete() -> None:
                ids = pending_delete['ids']
                if not ids:
                    return
                await bulk_remove_documents(BulkDeleteRequest(document_ids=ids))
                selection['ids'].clear()
                confirm_dialog.close()
                await refresh_documents(filter_input.value or None)

            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=confirm_dialog.close).props('flat')
                ui.button('Delete', on_click=confirm_bulk_delete).props('color=negative')

        def update_delete_button() -> None:
            count = len(selection['ids'])
            delete_selected_btn.text = f'Delete selected ({count})'
            delete_selected_btn.enable() if count else delete_selected_btn.disable()

        def toggle_selection(document_id: str, selected: bool) -> None:
            if selected:
                selection['ids'].add(document_id)
            else:
                selection['ids'].discard(document_id)
            update_delete_button()

        async def refresh_documents(course_filter: str | None = None) -> None:
            docs_table.clear()
            docs = await list_documents(course_filter or None)
            selection['docs_by_id'] = {doc['id']: doc for doc in docs}
            selection['ids'] &= set(selection['docs_by_id'])
            update_delete_button()
            with docs_table:
                if not docs:
                    ui.label('No documents uploaded yet.').classes('ice-muted')
                    return
                for doc in docs:
                    with ui.row().classes('w-full items-center justify-between ice-row p-3'):
                        with ui.row().classes('items-center gap-3'):
                            ui.checkbox(
                                value=doc['id'] in selection['ids'],
                                on_change=lambda e, d=doc['id']: toggle_selection(d, e.value),
                            )
                            with ui.column().classes('gap-0'):
                                ui.label(doc['title']).classes('font-semibold')
                                ui.label(f"Course: {doc.get('course') or 'none'}").classes('text-sm ice-muted')
                                ui.label(f"Status: {doc['status']}").classes('text-xs uppercase ice-muted')
                        ui.button('Delete', on_click=lambda d=doc['id']: delete_and_refresh(d)).props('flat color=negative')

        async def delete_and_refresh(document_id: str) -> None:
            await remove_document(document_id)
            selection['ids'].discard(document_id)
            await refresh_documents(filter_input.value or None)

        async def select_all_visible() -> None:
            selection['ids'] = set(selection['docs_by_id'])
            await refresh_documents(filter_input.value or None)

        async def clear_selection() -> None:
            selection['ids'].clear()
            update_delete_button()
            await refresh_documents(filter_input.value or None)

        async def open_confirm_dialog() -> None:
            pending_delete['ids'] = [doc_id for doc_id in selection['ids'] if doc_id in selection['docs_by_id']]
            ids = pending_delete['ids']
            if not ids:
                return
            titles = [selection['docs_by_id'][doc_id]['title'] for doc_id in ids]
            confirm_summary.text = f'{len(titles)} textbook(s) will be permanently deleted.'
            confirm_list.clear()
            with confirm_list:
                shown = titles[:10]
                for title in shown:
                    ui.label(f'• {title}').classes('text-sm')
                if len(titles) > 10:
                    ui.label(f'…and {len(titles) - 10} more').classes('text-sm ice-muted')
            confirm_dialog.open()

        delete_selected_btn.on_click(open_confirm_dialog)

        selected_file: dict[str, bytes | str] = {}

        with ui.card().classes('w-full ice-card p-6 gap-4'):
            ui.label('Upload textbook PDF').classes('text-xl font-semibold')
            title_input = ui.input('Title').classes('w-full')
            course_input = ui.input('Course (optional)').classes('w-full')
            subreddit_input = ui.input('Subreddits (comma separated, optional)').classes('w-full')
            status_label = ui.label('').classes('text-sm ice-muted')

            def on_upload(e) -> None:
                payload = e.content.read()
                selected_file['name'] = e.name
                selected_file['content_type'] = e.type
                selected_file['payload'] = payload
                status_label.text = f'Selected file: {e.name}'

            ui.upload(label='Choose PDF', auto_upload=True, on_upload=on_upload).props('accept=.pdf color=primary')

            async def poll_status(document_id: str) -> None:
                while True:
                    status = await document_status(document_id)
                    status_label.text = f"Document status: {status['status']}"
                    if status['status'] in {'ready', 'error'}:
                        await refresh_documents(course_input.value)
                        break
                    await asyncio.sleep(2)

            async def submit_upload() -> None:
                if 'payload' not in selected_file:
                    status_label.text = 'Select a PDF file first.'
                    return

                from starlette.datastructures import UploadFile as StarletteUploadFile
                import io

                upload = StarletteUploadFile(
                    filename=str(selected_file['name']),
                    file=io.BytesIO(selected_file['payload']),
                    headers={'content-type': str(selected_file.get('content_type') or 'application/pdf')},
                )
                result = await upload_document(
                    file=upload,
                    title=title_input.value or str(selected_file['name']),
                    course=course_input.value or None,
                    subreddits=subreddit_input.value or None,
                )
                status_label.text = f"Queued ingestion job {result['job_id']}"
                await poll_status(result['id'])

            ui.button('Upload and process', on_click=submit_upload).props('color=primary')

        with ui.row().classes('w-full items-center gap-3 mt-6 flex-wrap'):
            filter_input = ui.input('Filter by course').classes('w-72')
            ui.button('Refresh', on_click=lambda: refresh_documents(filter_input.value)).props('flat')
            ui.button('Select all', on_click=select_all_visible).props('flat')
            ui.button('Clear selection', on_click=clear_selection).props('flat')
            delete_selected_btn
            ui.button('Go to Study View', on_click=lambda: ui.navigate.to('/chat')).props('color=secondary')

        await refresh_documents()


@ui.page('/chat')
async def chat_page(request: Request) -> None:
    """Render the study view for chat, quiz, flashcards, and summary."""
    if not _ensure_ui_session(request):
        return

    docs = await list_documents()
    doc_choices = {doc['id']: doc['title'] for doc in docs}
    course_choices = sorted({doc.get('course') for doc in docs if doc.get('course')})

    state: dict = {'messages': []}

    with ui.column().classes('w-full max-w-6xl mx-auto px-4 py-6'):
        ice_shell(active='/chat')
        ui.label('Study View').classes('ice-heading mb-2')
        ui.label('Ask grounded questions across your library.').classes('ice-subheading mb-6')

        with ui.row().classes('w-full gap-4 flex-wrap'):
            scope_type = ui.select(
                options={'library': 'Whole library', 'course': 'This course', 'document': 'This document'},
                value='library',
                label='Scope',
            ).classes('w-48')
            course_select = ui.select(options=course_choices, value=course_choices[0] if course_choices else None, label='Course').classes('w-64')
            doc_select = ui.select(options=doc_choices, value=next(iter(doc_choices.keys()), None), label='Document').classes('w-72')
            mode_select = ui.select(
                options={'chat': 'Chat', 'quiz': 'Quiz', 'flashcards': 'Flashcards', 'summary': 'Summary'},
                value='chat',
                label='Mode',
            ).classes('w-48')

        thread = ui.column().classes('w-full ice-thread p-4 gap-3 min-h-[320px]')

        prompt = ui.textarea('Ask your textbook question').classes('w-full')

        async def render_chat_answer(answer: str, sources: list[dict]) -> None:
            citations = _extract_citations(answer)
            with thread:
                render_ice_markdown(answer)
                if citations:
                    with ui.row().classes('gap-2 flex-wrap'):
                        for page_number, sentence_idx in citations:
                            target_doc = sources[0]['document_id'] if sources else None
                            if not target_doc:
                                continue
                            label = f'[p{page_number}:s{sentence_idx}]'
                            ui.link(label, f"/pdf/{target_doc}?page={page_number}").classes('ice-citation underline')

        async def render_quiz(items: list[dict]) -> None:
            with thread:
                for item in items:
                    with ui.card().classes('w-full p-3 ice-card'):
                        ui.label(item.get('question', '')).classes('font-semibold')
                        ui.separator()
                        render_ice_markdown(item.get('answer', ''))
                        ui.label(', '.join(item.get('citations', []))).classes('text-xs ice-muted')

        async def render_flashcards(items: list[dict]) -> None:
            with thread:
                for item in items:
                    with ui.expansion(item.get('front', 'Flashcard')).classes('w-full ice-card'):
                        render_ice_markdown(item.get('back', ''))
                        ui.label(', '.join(item.get('citations', []))).classes('text-xs ice-muted')

        async def render_summary(summary: dict) -> None:
            lines: list[str] = []
            if summary.get('title'):
                lines.append(f"# {summary['title']}")
            for section in summary.get('outline', []):
                lines.append(f"## {section.get('heading', '')}")
                for bullet in section.get('bullets', []):
                    lines.append(f'- {bullet}')
            if summary.get('citations'):
                lines.append('')
                lines.append('Citations: ' + ', '.join(summary['citations']))
            with thread:
                render_ice_markdown('\n'.join(lines))

        async def submit_question() -> None:
            if not prompt.value:
                return

            scope_payload = {'type': scope_type.value}
            if scope_type.value == 'document':
                scope_payload['document_id'] = doc_select.value
            if scope_type.value == 'course':
                scope_payload['course'] = course_select.value

            state['messages'].append({'role': 'user', 'content': prompt.value})
            body = ChatRequest(
                messages=[ChatMessage(**m) for m in state['messages']],
                provider='deepseek',
                mode=mode_select.value,
                scope=Scope(**scope_payload),
            )
            result = await chat(body)

            with thread:
                ui.label(f"You: {prompt.value}").classes('text-sm ice-muted')

            if mode_select.value == 'chat':
                await render_chat_answer(result.brief, result.sources)
                state['messages'].append({'role': 'assistant', 'content': result.brief})
            elif mode_select.value == 'quiz':
                await render_quiz((result.structured or {}).get('items', []))
            elif mode_select.value == 'flashcards':
                await render_flashcards((result.structured or {}).get('items', []))
            else:
                await render_summary(result.structured or {})

            prompt.value = ''

        ui.button('Send', on_click=submit_question).props('color=primary')


@ui.page('/pdf/{document_id}')
async def pdf_page(request: Request, document_id: str) -> None:
    """Render the PDF viewer for one uploaded document."""
    if not _ensure_ui_session(request):
        return

    document = await get_document(document_id)
    if not document:
        ui.label('Document not found').classes('text-red-400')
        return

    query = dict(request.query_params)
    try:
        starting_page = int(query.get('page', '1'))
    except ValueError:
        starting_page = 1

    with ui.column().classes('w-full max-w-6xl mx-auto px-4 py-6'):
        ice_shell()
        ui.label(document['title']).classes('ice-heading mb-2')
        ui.label('Citation deep-link viewer').classes('ice-subheading mb-4')
        page_number = ui.number('Page', value=starting_page, min=1, precision=0).classes('w-32')

        file_url = f"/documents/{quote(document_id)}/file"
        if PdfViewer is None:
            ui.label('nicegui-pdf is not installed correctly.').classes('text-red-400')
            return

        viewer = PdfViewer(file_url, page=starting_page).classes('w-full h-[80vh] ice-card')

        def on_page_change() -> None:
            try:
                viewer.page = int(page_number.value)
            except Exception:
                pass

        page_number.on('change', on_page_change)


@ui.page('/login')
def login_page(request: Request) -> None:
    """Render the Google OAuth login screen."""
    error_messages = {
        'unauthorized': 'Your Google account is not authorized.',
        'oauth_failed': 'Google sign-in failed. Please try again.',
    }
    error_code = request.query_params.get('error')

    with ui.column().classes('absolute-center items-center w-full max-w-md px-4'):
        with ui.card().classes('w-full ice-card ice-login-card p-8 gap-5 items-center'):
            with ui.element('div').classes('ice-login-icon'):
                ui.icon('fingerprint', size='lg')
            ui.label('ARGUS').classes('text-3xl font-bold tracking-[0.2em] text-center')
            ui.label('Study Buddy').classes('ice-subheading text-center')
            if error_code in error_messages:
                ui.label(error_messages[error_code]).classes('text-sm text-red-300 text-center')
            ui.button(
                'Sign in with Google',
                on_click=lambda: ui.navigate.to('/auth/google'),
            ).props('unelevated').classes('w-full ice-google-btn')
            ui.label('PROTOCOL: GOOGLE-OAUTH').classes('ice-footer text-center mt-2')

if os.environ.get('ARGUS_ENABLE_NICEGUI', '1') == '1':
    apply_ice_theme()
    ui.run_with(app, title='Argus Study Buddy')
