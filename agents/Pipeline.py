from __future__ import annotations

"""Study pipeline orchestrator.

Wires langchain_chain.run_study_chain() to EvalAgent citation checks and
formats sources for the React UI (including metadata dict per chunk).
"""

from dataclasses import dataclass
from typing import Any

from ai.langchain_chain import run_study_chain
from ai.langchain_rag import chunk_metadata
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
    """Coordinate LangChain RAG retrieval, synthesis, and eval."""

    def __init__(self) -> None:
        self.eval_agent = EvalAgent()

    async def run(
        self,
        query: str,
        query_type: str = 'study',
        conversation_history: list[dict] | None = None,
        scope: dict | None = None,
        mode: str = 'chat',
    ) -> PipelineResult:
        chain_result = await run_study_chain(
            query=query,
            scope=scope,
            mode=mode,
            conversation_history=conversation_history,
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
                'scope': scope or {'type': 'library'},
                'mode': mode,
                'documents_in_scope': len({c['document_id'] for c in chain_result.chunks}),
                'chunks_in_context': len(chain_result.chunks),
            },
        )
