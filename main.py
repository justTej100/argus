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
from db.subscriptions import (
    list_flashcard_offers,
    list_subscriber_emails,
    set_flashcards_open,
    subscribe as subscribe_flashcards,
    unsubscribe as unsubscribe_flashcards,
)
from jobs import schedule_ingestion
from mail.gmail import EmailNotConfiguredError, send_flashcards_email, send_study_email
from rate_limit import check_and_record_study, get_study_usage, usage_status
from storage import delete_pdf, download_pdf, supabase_dashboard_urls, upload_pdf

load_dotenv(Path(__file__).parent / '.env')

FRONTEND_DIST = Path(__file__).parent / 'frontend' / 'dist'


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_schema()
    try:
        from ai.vector_store import ensure_vector_table

        await ensure_vector_table()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning('Vector table init skipped: %s', exc)
    try:
        from agents.FeedAgent import seed_leetcode_accounts
        from agents.IngestionAgent import resume_paused_embeddings

        await seed_leetcode_accounts()
        await resume_paused_embeddings()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning('Feed/resume bootstrap skipped: %s', exc)
    yield


app = FastAPI(title='Argus', version='4.0.0', lifespan=lifespan)
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


class StudyRequest(BaseModel):
    document_id: str
    section_id: str | None = None
    mode: Literal['quiz', 'flashcards', 'summary'] = 'quiz'
    email: bool = False


class FlashcardEmailRequest(BaseModel):
    topic: str
    items: list[dict]
    sources: list[dict] = []


class FlashcardSubscribeRequest(BaseModel):
    document_id: str


class FlashcardOpenRequest(BaseModel):
    enabled: bool


class FlashcardBroadcastRequest(BaseModel):
    document_id: str
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


@app.get('/flashcards/offers', tags=['Flashcards'], dependencies=[Depends(require_session)])
async def flashcard_offers(request: Request) -> list[dict]:
    email = get_session_email(request)
    return await list_flashcard_offers(email)


@app.post('/flashcards/subscribe', tags=['Flashcards'], dependencies=[Depends(require_session)])
async def flashcard_subscribe(request: Request, body: FlashcardSubscribeRequest) -> dict:
    email = get_session_email(request)
    if not email:
        raise HTTPException(status_code=401, detail='Login required.')
    try:
        await subscribe_flashcards(email, body.document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'ok': True, 'document_id': body.document_id, 'subscribed': True}


@app.post('/flashcards/unsubscribe', tags=['Flashcards'], dependencies=[Depends(require_session)])
async def flashcard_unsubscribe(request: Request, body: FlashcardSubscribeRequest) -> dict:
    email = get_session_email(request)
    if not email:
        raise HTTPException(status_code=401, detail='Login required.')
    await unsubscribe_flashcards(email, body.document_id)
    return {'ok': True, 'document_id': body.document_id, 'subscribed': False}


@app.patch('/documents/{document_id}/flashcards-open', tags=['Documents'], dependencies=[Depends(require_admin)])
async def document_flashcards_open(document_id: str, body: FlashcardOpenRequest) -> dict:
    document = await set_flashcards_open(document_id, body.enabled)
    if not document:
        raise HTTPException(status_code=404, detail='Document not found.')
    return {
        'id': document['id'],
        'flashcards_open': bool(document.get('flashcards_open')),
        'title': document.get('title'),
    }


@app.post('/flashcards/broadcast', tags=['Flashcards'], dependencies=[Depends(require_admin)])
async def flashcard_broadcast(body: FlashcardBroadcastRequest) -> dict:
    document = await get_document(body.document_id)
    if not document:
        raise HTTPException(status_code=404, detail='Document not found.')
    if not body.items:
        raise HTTPException(status_code=400, detail='No flashcards to email.')
    recipients = await list_subscriber_emails(body.document_id)
    if not recipients:
        return {'ok': True, 'sent': 0, 'failed': 0, 'recipients': []}

    sent = 0
    failed = 0
    for recipient in recipients:
        try:
            send_flashcards_email(
                to_email=recipient,
                topic=body.topic,
                items=body.items,
                sources=body.sources,
            )
            sent += 1
        except EmailNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception:
            failed += 1
    return {'ok': True, 'sent': sent, 'failed': failed, 'recipients': recipients}


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
    usage = await get_study_usage(email) if email else {}
    return {
        'email': email,
        'is_admin': admin,
        'study': usage_status(usage, is_admin=admin),
    }


@app.get('/feed', tags=['Feed'], dependencies=[Depends(require_session)])
async def feed(limit: int = 40, cursor: str | None = None) -> dict:
    from db.feed import list_feed

    posts = await list_feed(limit=limit, cursor=cursor)
    return {'posts': posts}


@app.get('/news', tags=['Feed'], dependencies=[Depends(require_session)])
async def news() -> dict:
    """Right-rail news: recent textbooks + embedding status."""
    docs = await list_documents()
    items: list[dict] = []
    for doc in docs[:8]:
        status = doc.get('status')
        if status == 'ready':
            items.append(
                {
                    'kind': 'ready',
                    'title': doc.get('title'),
                    'body': f'{doc.get("total_pages") or "?"} pages ready for the feed.',
                    'document_id': doc['id'],
                }
            )
        elif status == 'embedding_paused':
            items.append(
                {
                    'kind': 'paused',
                    'title': doc.get('title'),
                    'body': doc.get('error_message')
                    or f'Embedding paused ({doc.get("embed_done")}/{doc.get("embed_total")}). Resumes automatically.',
                    'document_id': doc['id'],
                }
            )
        elif status in {'processing', 'embedding'}:
            items.append(
                {
                    'kind': 'processing',
                    'title': doc.get('title'),
                    'body': f'Embedding {doc.get("embed_done") or 0}/{doc.get("embed_total") or "?"}…',
                    'document_id': doc['id'],
                }
            )
    if not items:
        items.append(
            {
                'kind': 'tip',
                'title': 'Welcome to Argus',
                'body': 'Upload a textbook from Library. Chapter accounts will start posting to your feed.',
                'document_id': None,
            }
        )
    return {'items': items}


@app.get('/documents/{document_id}/sections', tags=['Documents'], dependencies=[Depends(require_session)])
async def document_sections(document_id: str) -> list[dict]:
    document = await get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail='Document not found.')
    from db.sections import list_sections

    return await list_sections(document_id)


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


@app.post('/study', response_model=StudyResponse, tags=['Study'], dependencies=[Depends(require_session)])
async def study(request: Request, body: StudyRequest) -> StudyResponse:
    email = get_session_email(request) or ''
    await check_and_record_study(email, is_admin=is_admin_email(email))

    document = await get_document(body.document_id)
    if not document:
        raise HTTPException(status_code=404, detail='Document not found.')
    if document.get('status') != 'ready':
        raise HTTPException(status_code=400, detail='Textbook is not ready yet. Wait for embedding to finish.')

    from db.sections import get_section, list_sections

    start_page: int | None = None
    end_page: int | None = None
    chapter_title = ''
    section_id = body.section_id

    if section_id:
        section = await get_section(section_id)
        if not section or section.get('document_id') != body.document_id:
            raise HTTPException(status_code=404, detail='Section not found.')
        start_page = int(section['start_page'])
        end_page = int(section['end_page'])
        chapter_title = str(section['title'])
    else:
        sections = await list_sections(body.document_id)
        if sections:
            raise HTTPException(status_code=400, detail='Choose a chapter/section for this textbook.')
        chapter_title = str(document.get('title') or 'Textbook')

    query = chapter_title or document.get('title') or 'Study this chapter'

    try:
        result = await pipeline.run(
            query=query,
            query_type='study',
            document_id=body.document_id,
            mode=body.mode,
            start_page=start_page,
            end_page=end_page,
            chapter_title=chapter_title,
            section_id=section_id,
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

    if body.email and study_response.structured:
        recipient = get_session_email(request)
        if recipient:
            try:
                send_study_email(
                    to_email=recipient,
                    topic=chapter_title,
                    mode=body.mode,
                    structured=study_response.structured,
                    sources=study_response.sources,
                )
            except EmailNotConfiguredError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except ValueError:
                pass

    return study_response


@app.get('/admin/config', tags=['Admin'], dependencies=[Depends(require_admin)])
async def admin_config() -> dict:
    urls = supabase_dashboard_urls()
    return {
        'supabaseTableUrl': urls.get('tableEditorUrl'),
        'storageUrl': urls.get('storageUrl'),
    }


@app.get('/admin/stats', tags=['Admin'], dependencies=[Depends(require_admin)])
async def admin_stats() -> dict:
    from ai.vector_store import count_vectors, count_vectors_for_document

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
    from ai.vector_store import sample_vectors

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


@app.get('/library')
async def spa_library() -> FileResponse:
    return _spa_index()


@app.get('/admin')
async def spa_admin() -> FileResponse:
    return _spa_index()


_assets_dir = FRONTEND_DIST / 'assets'
if _assets_dir.is_dir():
    app.mount('/assets', StaticFiles(directory=_assets_dir), name='frontend_assets')
