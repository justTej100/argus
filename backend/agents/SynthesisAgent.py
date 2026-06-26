from __future__ import annotations

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
    SYSTEM = (
        'You are a precise study assistant grounded in textbook excerpts. '
        'Every factual claim must include one or more citation tags copied verbatim from context '
        'using the format [pX:sY]. Never invent page or sentence numbers. '
        'Never cite community context as textbook evidence.'
    )

    def _build_textbook_context(self, chunks: list[dict]) -> str:
        lines: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            tagged = (
                f"[doc:{chunk['document_id']}] [p{chunk['page_number']}:s{chunk['sentence_start_idx']}] "
                f"to [p{chunk['page_number']}:s{chunk['sentence_end_idx']}]\n"
                f"{chunk['text']}"
            )
            lines.append(f'Chunk {idx}:\n{tagged}')
        return '\n\n'.join(lines) if lines else 'No textbook chunks were retrieved.'

    def _build_community_context(self, items: list[dict]) -> str:
        if not items:
            return 'No community context configured for this scope.'
        snippets: list[str] = []
        for item in items[:12]:
            snippets.append(
                f"[{item.get('source', 'reddit')}:{item.get('subreddit', 'unknown')}] "
                f"{item.get('title', '')}\n{item.get('body', '')[:240]}"
            )
        return '\n\n'.join(snippets)

    async def run(
        self,
        analysis: AnalysisResult,
        community_context: list[dict],
        mode: str,
        ai_client: AIClient,
        conversation_history: list[dict] | None = None,
    ) -> SynthesisResult:
        textbook_context = self._build_textbook_context(analysis.chunks)
        community_text = self._build_community_context(community_context)

        mode_prompt = {
            'chat': 'Answer naturally in markdown with concise explanations and explicit [pX:sY] citations.',
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
            f'Community context (supplementary only, never as textbook citation):\n{community_text}\n\n'
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
