from __future__ import annotations

"""Answer generation for chat, quiz, flashcards, and summary modes."""

import json
from dataclasses import dataclass

from ai.clients import AIClient, complete
from agents.AnalysisAgent import AnalysisResult


@dataclass
class SynthesisResult:
    query: str
    mode: str
    brief: str
    model_used: str
    provider: str
    structured: dict | None


class SynthesisAgent:
    """Build prompts and normalize model output for the selected mode."""
    SYSTEM = (
        'You are a precise study assistant grounded in textbook excerpts. '
        'Every factual claim must include one or more citation tags copied verbatim from context '
        'using the format [pX:sY]. Never invent page or sentence numbers. '
        'Use $...$ for inline math and $$...$$ for display math in markdown answers. '
        'If the textbook context does not contain enough evidence to answer, say so clearly.'
    )

    def _build_textbook_context(self, chunks: list[dict]) -> str:
        """Format retrieved chunks with explicit page and sentence tags."""
        lines: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            tagged = (
                f"[doc:{chunk['document_id']}] [p{chunk['page_number']}:s{chunk['sentence_start_idx']}] "
                f"to [p{chunk['page_number']}:s{chunk['sentence_end_idx']}]\n"
                f"{chunk['text']}"
            )
            lines.append(f'Chunk {idx}:\n{tagged}')
        return '\n\n'.join(lines) if lines else 'No textbook chunks were retrieved.'

    async def run(
        self,
        analysis: AnalysisResult,
        mode: str,
        ai_client: AIClient,
        conversation_history: list[dict] | None = None,
    ) -> SynthesisResult:
        """Generate the final answer or structured study artifact."""
        textbook_context = self._build_textbook_context(analysis.chunks)

        mode_prompt = {
            'chat': 'Answer naturally in markdown with concise explanations, LaTeX math where helpful, and explicit [pX:sY] citations.',
            'quiz': (
                'Return JSON only with this schema: '
                '{"items":[{"question":"...","answer":"...","citations":["[p12:s4]"]}]}'
            ),
            'flashcards': (
                'Return JSON only with this schema: '
                '{"items":[{"front":"...","back":"...","citations":["[p12:s4]"]}]}'
            ),
            'summary': (
                'Return JSON only with this schema: '
                '{"title":"...","outline":[{"heading":"...","bullets":["..."]}],"citations":["[p12:s4]"]}'
            ),
        }.get(mode, 'Answer in markdown with [pX:sY] citations.')

        user_prompt = (
            f'User question: {analysis.query}\n\n'
            f'Textbook context:\n{textbook_context}\n\n'
            f'Mode: {mode}\n'
            f'{mode_prompt}'
        )

        json_mode = mode in {'quiz', 'flashcards', 'summary'}
        raw = await complete(
            ai_client,
            system=self.SYSTEM,
            user=user_prompt,
            temperature=0.2,
            max_tokens=2000,
            json_mode=json_mode,
            extra_messages=conversation_history if mode == 'chat' else None,
        )

        structured = None
        brief = raw
        if json_mode:
            try:
                structured = json.loads(raw)
                brief = json.dumps(structured)
            except json.JSONDecodeError:
                structured = {'raw': raw}
                brief = raw

        return SynthesisResult(
            query=analysis.query,
            mode=mode,
            brief=brief,
            model_used=ai_client.model,
            provider=ai_client.provider,
            structured=structured,
        )
