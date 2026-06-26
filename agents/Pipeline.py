from __future__ import annotations

"""End-to-end orchestration for the study buddy agent pipeline."""

from dataclasses import dataclass
from typing import Any

from agents.AnalysisAgent import AnalysisAgent
from agents.EvalAgent import EvalAgent, EvalResult
from agents.SynthesisAgent import SynthesisAgent


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
    """Coordinate retrieval, synthesis, and eval."""
    def __init__(self) -> None:
        self.analysis_agent = AnalysisAgent()
        self.synthesis_agent = SynthesisAgent()
        self.eval_agent = EvalAgent()

    async def run(
        self,
        query: str,
        query_type: str = 'study',
        conversation_history: list[dict] | None = None,
        scope: dict | None = None,
        mode: str = 'chat',
    ) -> PipelineResult:
        """Execute the full question-answering flow for one prompt."""
        from ai.clients import get_client

        ai_client = get_client()

        analysis = await self.analysis_agent.run(query=query, scope=scope)
        if not analysis.document_ids:
            raise ValueError(
                'No ready textbooks in this scope. Upload a PDF on the Library page and wait until status is Ready.'
            )
        if not analysis.chunks:
            raise ValueError(
                'No matching passages found for this question. Try rephrasing or widening the scope.'
            )

        synthesis = await self.synthesis_agent.run(
            analysis=analysis,
            mode=mode,
            ai_client=ai_client,
            conversation_history=conversation_history,
        )
        eval_result = await self.eval_agent.run(synthesis=synthesis, analysis=analysis)

        textbook_sources = [
            {
                'source_type': 'textbook',
                'document_id': chunk['document_id'],
                'document_title': chunk['document_title'],
                'course': chunk.get('course'),
                'page_number': chunk['page_number'],
                'sentence_start_idx': chunk['sentence_start_idx'],
                'sentence_end_idx': chunk['sentence_end_idx'],
                'text': chunk['text'],
                'similarity': float(chunk['similarity']),
            }
            for chunk in analysis.chunks
        ]

        return PipelineResult(
            query=query,
            query_type=query_type,
            brief=synthesis.brief,
            eval=eval_result,
            sources=textbook_sources,
            structured=synthesis.structured,
            meta={
                'provider': ai_client.provider,
                'model': ai_client.model,
                'scope': scope or {'type': 'library'},
                'mode': mode,
                'documents_in_scope': len(analysis.document_ids),
                'chunks_in_context': len(analysis.chunks),
            },
        )
