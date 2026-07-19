from __future__ import annotations

"""Study material generation: retrieve chapter-scoped chunks → Gemini JSON.

Modes: quiz / flashcards / summary (no free-text chat).
"""

import json
import os
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ai.chunking import format_documents_for_prompt
from ai.llm import get_chat_model
from ai.vector_store import documents_to_chunk_dicts, similarity_search

SYSTEM = (
    'You are Argus, a personal study assistant. The student uploaded their textbooks. '
    'Generate study materials grounded only in the provided excerpts. '
    'Page references use [pN] where N is metadata.page from the source documents. '
    'Include citations on every item. Never invent page numbers not shown in the excerpts. '
    'Prefer content from the requested chapter/section.'
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


async def _retrieve(
    query: str,
    *,
    document_id: str,
    start_page: int | None,
    end_page: int | None,
    limit: int = 14,
) -> list[dict]:
    results = await similarity_search(
        query,
        [document_id],
        limit=limit,
        start_page=start_page,
        end_page=end_page,
    )
    return documents_to_chunk_dicts(results)


async def run_study_chain(
    *,
    query: str,
    document_id: str,
    mode: str = 'quiz',
    start_page: int | None = None,
    end_page: int | None = None,
    chapter_title: str = '',
) -> ChainResult:
    """Run retrieval + generation for one study request."""
    if mode not in {'quiz', 'flashcards', 'summary'}:
        raise ValueError(f'Unsupported study mode: {mode}')

    chunks = await _retrieve(
        query,
        document_id=document_id,
        start_page=start_page,
        end_page=end_page,
    )
    if not chunks:
        raise ValueError(
            'No matching passages found for this chapter. Try another section or wait until the textbook is fully embedded.'
        )

    context = format_documents_for_prompt(chunks)
    model_name = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
    cite_example = '["[p12]"]'
    scope_note = ''
    if chapter_title:
        scope_note = f'Focus on chapter/section: {chapter_title}. '
    if start_page and end_page:
        scope_note += f'Prefer pages {start_page}–{end_page}. '

    mode_instructions = {
        'quiz': (
            f'Return JSON only: {{"items":[{{"question":"...","answer":"...","citations":{cite_example}}}]}}. '
            'Create 5–8 quiz questions that test understanding.'
        ),
        'flashcards': (
            f'Return JSON only: {{"items":[{{"front":"...","back":"...","citations":{cite_example}}}]}}. '
            'Create 5–8 concise cards.'
        ),
        'summary': (
            f'Return JSON only: {{"title":"...","outline":[{{"heading":"...","bullets":["..."]}}],'
            f'"citations":{cite_example}}}'
        ),
    }[mode]

    llm = get_chat_model(temperature=0.3, json_mode=True)
    raw_msg = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM),
            HumanMessage(
                content=(
                    f'Topic / focus: {query}\n'
                    f'{scope_note}\n'
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
