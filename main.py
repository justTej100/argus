from __future__ import annotations

"""FastAPI backend for Argus — API routes + React SPA."""

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.responses import Response as FastAPIResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from typing import Literal

from agents.Pipeline import ResearchPipeline
from ai.clients import GeminiAPIError
from auth import (
    clear_session_cookie,
    get_session_email,
    is_admin_email,
    normalize_login_email,
    require_admin,
    require_session,
    set_session_cookie,
)
from db.client import create_document, delete_document, get_document, init_schema, list_documents, update_document_status
from jobs import schedule_ingestion
from mail.gmail import EmailNotConfiguredError, send_flashcards_email
from rate_limit import check_and_record_chat, get_chat_usage, usage_status
from storage import delete_pdf, download_pdf, supabase_dashboard_urls, upload_pdf

load_dotenv(Path(__file__).parent / '.env')

FRONTEND_DIST = Path(__file__).parent / 'frontend' / 'dist'


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_schema()
    from ai.langchain_store import ensure_vector_table

    await ensure_vector_table()
    yield


app = FastAPI(title='Argus Study Buddy', version='3.0.0', lifespan=lifespan)
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


class ChatMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str


class Scope(BaseModel):
    type: Literal['document', 'library'] = 'library'
    document_id: str | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    mode: Literal['chat', 'quiz', 'flashcards', 'summary'] = 'chat'
    scope: Scope = Scope()
    email_flashcards: bool = False


class FlashcardEmailRequest(BaseModel):
    topic: str
    items: list[dict]
    sources: list[dict] = []


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
    meta: dict
    structured: dict | None = None


@app.post('/flashcards/email', tags=['Study'], dependencies=[Depends(require_session)])
async def email_flashcards(request: Request, body: FlashcardEmailRequest) -> dict:
    recipient = get_session_email(request)
    if not recipient:
        raise HTTPException(status_code=401, detail='Login required.')
    if not body.items:
        raise HTTPException(status_code=400, detail='No flashcards to email.')
    try:
        send_flashcards_email(
            to_email=recipient,
            topic=body.topic,
            items=body.items,
            sources=body.sources,
        )
    except EmailNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'ok': True, 'to': recipient, 'count': len(body.items)}


@app.get('/health', tags=['Meta'])
def health() -> dict:
    return {'status': 'ok', 'timestamp': time.time()}


@app.get('/auth/google', tags=['Auth'])
async def auth_google(request: Request):
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
    if not redirect_uri:
        raise HTTPException(status_code=500, detail='GOOGLE_REDIRECT_URI is not configured.')
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get('/auth/google/callback', tags=['Auth'])
async def auth_google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get('userinfo')
        if not userinfo:
            userinfo = await oauth.google.parse_id_token(request, token)
        email = normalize_login_email(userinfo.get('email') if userinfo else None)
        response = RedirectResponse(url='/', status_code=302)
        set_session_cookie(response, email)
        return response
    except HTTPException as exc:
        if exc.status_code == 400:
            return RedirectResponse(url='/login?error=oauth_failed', status_code=302)
        raise
    except Exception:
        return RedirectResponse(url='/login?error=oauth_failed', status_code=302)


@app.get('/logout', tags=['Auth'])
def logout() -> RedirectResponse:
    response = RedirectResponse(url='/login', status_code=302)
    clear_session_cookie(response)
    return response


@app.get('/me', tags=['Auth'], dependencies=[Depends(require_session)])
async def me(request: Request) -> dict:
    email = get_session_email(request) or ''
    admin = is_admin_email(email)
    usage = await get_chat_usage(email) if email else {}
    return {
        'email': email,
        'is_admin': admin,
        'chat': usage_status(usage, is_admin=admin),
    }


@app.get('/documents', tags=['Documents'], dependencies=[Depends(require_session)])
async def documents() -> list[dict]:
    return await list_documents()


@app.post('/documents', tags=['Documents'], dependencies=[Depends(require_admin)])
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str | None = Form(None),
) -> dict:
    filename = file.filename or ''
    if file.content_type not in {'application/pdf', 'application/octet-stream'} and not filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail='Only PDF uploads are supported.')

    payload = await file.read()
    document_id = await create_document(
        title=title,
        description=description or None,
        status='processing',
        total_pages=0,
        storage_path='',
    )
    storage_path = upload_pdf(document_id, filename or f'{document_id}.pdf', payload)
    await update_document_status(document_id, status='processing', storage_path=storage_path)
    job_id = schedule_ingestion(document_id, storage_path)
    return {'id': document_id, 'status': 'processing', 'job_id': job_id}


@app.get('/documents/{document_id}/status', tags=['Documents'], dependencies=[Depends(require_session)])
async def document_status(document_id: str) -> dict:
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


@app.delete('/documents/{document_id}', tags=['Documents'], dependencies=[Depends(require_admin)])
async def remove_document(document_id: str) -> dict:
    document = await get_document(document_id)
    if document:
        delete_pdf(document.get('storage_path') or '')
    await delete_document(document_id)
    return {'ok': True}


@app.post('/documents/bulk-delete', tags=['Documents'], dependencies=[Depends(require_admin)])
async def bulk_remove_documents(body: BulkDeleteRequest) -> dict:
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
    from storage import StorageError

    document = await get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail='Document not found.')
    storage_path = document.get('storage_path') or ''
    if not storage_path:
        raise HTTPException(status_code=404, detail='PDF has not been stored yet.')
    try:
        blob = download_pdf(storage_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail='PDF file missing from storage. Set STORAGE_BACKEND=local or configure Supabase keys.',
        ) from None
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FastAPIResponse(content=blob, media_type='application/pdf')


@app.post('/chat', response_model=StudyResponse, tags=['Study'], dependencies=[Depends(require_session)])
async def chat(request: Request, body: ChatRequest) -> StudyResponse:
    user_messages = [m for m in body.messages if m.role == 'user']
    if not user_messages:
        raise HTTPException(status_code=400, detail='At least one user message is required.')

    email = get_session_email(request) or ''
    await check_and_record_chat(email, is_admin=is_admin_email(email))

    query = user_messages[-1].content
    history = [{'role': m.role, 'content': m.content} for m in body.messages[:-1]] or None
    scope = body.scope.model_dump()

    try:
        result = await pipeline.run(
            query=query,
            query_type='study',
            conversation_history=history,
            scope=scope,
            mode=body.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GeminiAPIError as exc:
        status_code = exc.status_code if exc.status_code in {429, 503, 502} else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    study_response = StudyResponse(
        query=result.query,
        type=result.query_type,
        brief=result.brief,
        eval=EvalResponse(**vars(result.eval)),
        sources=result.sources,
        meta=result.meta,
        structured=result.structured,
    )
    await _maybe_email_flashcards(request, body, study_response)
    return study_response


async def _maybe_email_flashcards(request: Request, body: ChatRequest, result: StudyResponse) -> None:
    if body.mode != 'flashcards' or not body.email_flashcards:
        return
    items = (result.structured or {}).get('items', [])
    if not items:
        return
    recipient = get_session_email(request)
    if not recipient:
        return
    topic = body.messages[-1].content if body.messages else 'Study topic'
    try:
        send_flashcards_email(to_email=recipient, topic=topic, items=items, sources=result.sources)
    except (EmailNotConfiguredError, ValueError):
        return


@app.post('/search', response_model=StudyResponse, tags=['Study'], dependencies=[Depends(require_session)])
async def search(request: Request, body: ChatRequest) -> StudyResponse:
    return await chat(request, body)


@app.get('/admin/config', tags=['Admin'], dependencies=[Depends(require_admin)])
async def admin_config() -> dict:
    urls = supabase_dashboard_urls()
    return {
        'supabaseTableUrl': urls.get('tableEditorUrl'),
        'storageUrl': urls.get('storageUrl'),
    }


@app.get('/admin/stats', tags=['Admin'], dependencies=[Depends(require_admin)])
async def admin_stats() -> dict:
    from ai.langchain_store import count_vectors, count_vectors_for_document

    docs = await list_documents()
    total_vectors = await count_vectors()
    per_doc = []
    for doc in docs:
        per_doc.append(
            {
                'id': doc['id'],
                'title': doc['title'],
                'description': doc.get('description'),
                'status': doc['status'],
                'total_pages': doc.get('total_pages'),
                'storage_path': doc.get('storage_path'),
                'chunk_count': await count_vectors_for_document(doc['id']),
            }
        )
    return {
        'document_count': len(docs),
        'total_vectors': total_vectors,
        'documents': per_doc,
    }


@app.get('/admin/documents/{document_id}/chunks', tags=['Admin'], dependencies=[Depends(require_admin)])
async def admin_document_chunks(document_id: str, limit: int = 5) -> dict:
    from ai.langchain_store import sample_vectors

    document = await get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail='Document not found.')
    chunks = await sample_vectors(document_id, limit=min(limit, 20))
    return {'document_id': document_id, 'title': document['title'], 'chunks': chunks}


def _spa_index() -> FileResponse:
    index = FRONTEND_DIST / 'index.html'
    if not index.is_file():
        raise HTTPException(
            status_code=503,
            detail='Frontend not built. Run: cd frontend && npm install && npm run build',
        )
    return FileResponse(index)


@app.get('/')
async def spa_home() -> FileResponse:
    return _spa_index()


@app.get('/login')
async def spa_login() -> FileResponse:
    return _spa_index()


@app.get('/study')
async def spa_study() -> FileResponse:
    return _spa_index()


@app.get('/admin')
async def spa_admin() -> FileResponse:
    return _spa_index()


_assets_dir = FRONTEND_DIST / 'assets'
if _assets_dir.is_dir():
    app.mount('/assets', StaticFiles(directory=_assets_dir), name='frontend_assets')
