from __future__ import annotations

"""LCEL RAG chain: retrieve scoped chunks → format context → Gemini → answer.

Modes:
  - chat: markdown tutor answer with [pN] references
  - quiz / flashcards / summary: JSON structured output

Falls back to excerpt-based answers when the model returns citation-only text.
"""

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from ai.langchain_llm import get_chat_model
from ai.langchain_rag import format_documents_for_prompt
from ai.langchain_store import documents_to_chunk_dicts, similarity_search
from db.client import get_scope_document_ids
from citations import is_citation_only

_PAGE_CITE = '[p{page}]'

SYSTEM = (
    'You are Argus, a personal tutor. The student uploaded their textbooks. '
    'Always write a complete answer in your own words — paragraphs that explain and teach. '
    'Use the provided excerpts as your source material. '
    'Page references use [pN] where N is metadata.page from the source documents. '
    'Put 1–3 page refs at the end on a "References:" line — never make the whole reply just page tags. '
    'Never invent page numbers not shown in the excerpts.'
)


@dataclass
class ChainResult:
    query: str
    mode: str
    brief: str
    chunks: list[dict]
    structured: dict | None
    model_used: str
    provider: str


def _fallback_from_chunks(query: str, chunks: list[dict]) -> str:
    lines = [f'Here is an overview based on your textbook for: **{query.strip()}**\n']
    seen: set[tuple[str, int]] = set()
    ref_pages: list[int] = []

    for chunk in chunks[:6]:
        title = chunk.get('document_title') or 'Textbook'
        page = int(chunk['page_number'])
        key = (title, page)
        if key in seen:
            continue
        seen.add(key)
        ref_pages.append(page)
        excerpt = (chunk.get('text') or '').strip()
        if len(excerpt) > 600:
            excerpt = excerpt[:597] + '…'
        lines.append(f'### {title} (page {page})\n\n{excerpt}\n')

    if ref_pages:
        refs = ', '.join(_PAGE_CITE.format(page=p) for p in dict.fromkeys(ref_pages))
        lines.append(f'\n**References:** {refs}')
    return '\n'.join(lines)


def _ensure_substantive(text: str, query: str, chunks: list[dict]) -> str:
    if is_citation_only(text):
        return _fallback_from_chunks(query, chunks)
    return text


def _history_to_messages(history: list[dict] | None) -> list:
    if not history:
        return []
    out = []
    for msg in history:
        if msg['role'] == 'user':
            out.append(HumanMessage(content=msg['content']))
        elif msg['role'] == 'assistant':
            out.append(AIMessage(content=msg['content']))
    return out


async def _retrieve(query: str, scope: dict | None, limit: int = 12) -> list[dict]:
    document_ids = await get_scope_document_ids(scope)
    if not document_ids:
        return []
    results = await similarity_search(query, document_ids, limit=limit)
    return documents_to_chunk_dicts(results)


async def run_study_chain(
    *,
    query: str,
    scope: dict | None = None,
    mode: str = 'chat',
    conversation_history: list[dict] | None = None,
) -> ChainResult:
    """Run retrieval + generation for one study request."""
    chunks = await _retrieve(query, scope)
    if not chunks:
        doc_ids = await get_scope_document_ids(scope)
        if not doc_ids:
            raise ValueError(
                'No ready textbooks in this scope. Upload a PDF on the Library page and wait until status is Ready.'
            )
        raise ValueError('No matching passages found for this question. Try rephrasing or widening the scope.')

    context = format_documents_for_prompt(chunks)
    model_name = __import__('os').environ.get('GEMINI_MODEL', 'gemini-2.5-flash')

    if mode == 'chat':
        llm = get_chat_model(temperature=0.4)
        prompt = ChatPromptTemplate.from_messages(
            [
                ('system', SYSTEM),
                MessagesPlaceholder('history', optional=True),
                (
                    'human',
                    'Student question: {question}\n\n'
                    'Textbook excerpts:\n{context}\n\n'
                    'Write a helpful tutor answer in markdown.\n'
                    '- Minimum 4 sentences of explanation in your own words.\n'
                    '- Summarize topics clearly (bullet points if helpful).\n'
                    '- End with "References:" and 1–3 page tags like [p1] from excerpt metadata.\n'
                    '- NEVER reply with only [pN] tags.',
                ),
            ]
        )
        chain = prompt | llm
        raw_msg = await chain.ainvoke(
            {
                'question': query,
                'context': context,
                'history': _history_to_messages(conversation_history),
            }
        )
        raw = raw_msg.content if hasattr(raw_msg, 'content') else str(raw_msg)
        brief = _ensure_substantive(str(raw), query, chunks)

        if is_citation_only(brief):
            retry_llm = get_chat_model(temperature=0.5)
            retry = await retry_llm.ainvoke(
                [
                    SystemMessage(content='You summarize textbook excerpts clearly for students.'),
                    HumanMessage(
                        content=(
                            f'Student question: {query}\n\n'
                            f'Textbook excerpts:\n{context}\n\n'
                            'Write a full markdown answer. At least 6 sentences. '
                            'Optional last line: References: [pN].'
                        )
                    ),
                ]
            )
            brief = _ensure_substantive(str(retry.content), query, chunks)

        return ChainResult(
            query=query,
            mode=mode,
            brief=brief,
            chunks=chunks,
            structured=None,
            model_used=model_name,
            provider='gemini',
        )

    cite_example = '["[p12]"]'
    mode_instructions = {
        'quiz': f'Return JSON only: {{"items":[{{"question":"...","answer":"...","citations":{cite_example}}}]}}',
        'flashcards': (
            f'Return JSON only: {{"items":[{{"front":"...","back":"...","citations":{cite_example}}}]}}. '
            'Create 5–8 concise cards.'
        ),
        'summary': (
            f'Return JSON only: {{"title":"...","outline":[{{"heading":"...","bullets":["..."]}}],"citations":{cite_example}}}'
        ),
    }.get(mode, 'Answer in markdown with [pN] citations.')

    llm = get_chat_model(temperature=0.3, json_mode=True)
    raw_msg = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM),
            HumanMessage(
                content=(
                    f'User question: {query}\n\n'
                    f'Textbook context:\n{context}\n\n'
                    f'Mode: {mode}\n{mode_instructions}'
                )
            ),
        ]
    )
    raw = str(raw_msg.content)
    structured: dict[str, Any] | None = None
    brief = raw
    try:
        structured = json.loads(raw)
        brief = json.dumps(structured)
    except json.JSONDecodeError:
        structured = {'raw': raw}

    return ChainResult(
        query=query,
        mode=mode,
        brief=brief,
        chunks=chunks,
        structured=structured,
        model_used=model_name,
        provider='gemini',
    )
