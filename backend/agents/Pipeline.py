from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.AnalysisAgent import AnalysisAgent
from agents.ContextAgent import ContextAgent
from agents.EvalAgent import EvalAgent, EvalResult
from agents.SynthesisAgent import SynthesisAgent


@dataclass
class PipelineResult:
    query: str
    query_type: str
    brief: str
    eval: EvalResult
    sources: list[dict]
    community_context: list[dict]
    meta: dict[str, Any]
    structured: dict | None


class ResearchPipeline:
    def __init__(self) -> None:
        self.context_agent = ContextAgent()
        self.analysis_agent = AnalysisAgent()
        self.synthesis_agent = SynthesisAgent()
        self.eval_agent = EvalAgent()

    async def run(
        self,
        query: str,
        query_type: str = 'study',
        provider: str = 'deepseek',
        conversation_history: list[dict] | None = None,
        scope: dict | None = None,
        mode: str = 'chat',
    ) -> PipelineResult:
        from ai.clients import get_client

        ai_client = get_client(provider)  # type: ignore[arg-type]

        analysis = await self.analysis_agent.run(query=query, scope=scope)
        community = await self.context_agent.run(query=query, document_ids=analysis.document_ids)
        synthesis = await self.synthesis_agent.run(
            analysis=analysis,
            community_context=community.items,
            mode=mode,
            ai_client=ai_client,
            conversation_history=conversation_history,
        )
        eval_result = await self.eval_agent.run(synthesis=synthesis, analysis=analysis, ai_client=ai_client)

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
            community_context=community.items,
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
