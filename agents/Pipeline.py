from __future__ import annotations

"""Study pipeline orchestrator.

Wires ai.study_generate.run_study_chain() to EvalAgent citation checks and
formats sources for the React UI (including metadata dict per chunk).
"""

from dataclasses import dataclass
from typing import Any

from ai.chunking import chunk_metadata
from ai.study_generate import run_study_chain
from agents.EvalAgent import EvalAgent, EvalResult


@dataclass
class PipelineResult:
    query: str
    query_type: str
    brief: str
    eval: EvalResult
    sources: list[dict]
    meta: dict[str, Any]
    structured: dict | None


class ResearchPipeline:
    """Coordinate RAG retrieval, study synthesis, and eval."""

    def __init__(self) -> None:
        self.eval_agent = EvalAgent()

    async def run(
        self,
        query: str,
        query_type: str = 'study',
        *,
        document_id: str,
        mode: str = 'quiz',
        start_page: int | None = None,
        end_page: int | None = None,
        chapter_title: str = '',
        section_id: str | None = None,
    ) -> PipelineResult:
        chain_result = await run_study_chain(
            query=query,
            document_id=document_id,
            mode=mode,
            start_page=start_page,
            end_page=end_page,
            chapter_title=chapter_title,
        )

        eval_result = await self.eval_agent.run_on_chunks(
            brief=chain_result.brief,
            chunks=chain_result.chunks,
        )

        textbook_sources = [
            {
                'source_type': 'textbook',
                'document_id': chunk['document_id'],
                'document_title': chunk['document_title'],
                'description': chunk.get('description'),
                'page_number': chunk['page_number'],
                'chapter': chunk.get('chapter') or '',
                'sentence_start_idx': 0,
                'sentence_end_idx': 0,
                'text': chunk['text'],
                'similarity': float(chunk.get('similarity', 0)),
                'metadata': chunk_metadata(chunk),
            }
            for chunk in chain_result.chunks
        ]

        return PipelineResult(
            query=query,
            query_type=query_type,
            brief=chain_result.brief,
            eval=eval_result,
            sources=textbook_sources,
            structured=chain_result.structured,
            meta={
                'provider': chain_result.provider,
                'model': chain_result.model_used,
                'mode': mode,
                'document_id': document_id,
                'section_id': section_id,
                'chapter': chapter_title,
                'start_page': start_page,
                'end_page': end_page,
                'chunks_in_context': len(chain_result.chunks),
            },
        )
