from __future__ import annotations

"""Answer generation for chat, quiz, flashcards, and summary modes."""

import json
from dataclasses import dataclass

from ai.clients import AIClient, complete
from ai.langchain_rag import format_documents_for_prompt
from agents.AnalysisAgent import AnalysisResult
from ui.citations import extract_page_citations, is_citation_only, strip_citation_tags

_PAGE_CITE = '[p{page}]'


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
        'You are Argus, a personal tutor. The student uploaded their textbooks. '
        'Always write a complete answer in your own words — paragraphs that explain and teach. '
        'Use the provided excerpts as your source material. '
        'Page references use [pN] where N is metadata.page from the source documents. '
        'Put 1–3 page refs at the end on a "References:" line — never make the whole reply just page tags. '
        'Never invent page numbers not shown in the excerpts.'
    )

    def _build_textbook_context(self, chunks: list[dict]) -> str:
        """Format retrieved chunks with LangChain metadata blocks."""
        return format_documents_for_prompt(chunks)

    def _fallback_from_chunks(self, query: str, chunks: list[dict]) -> str:
        """Build a tutor-style answer from retrieved excerpts when the model fails."""
        lines = [
            f'Here is an overview based on your textbook for: **{query.strip()}**\n',
        ]
        seen_pages: set[tuple[str, int]] = set()
        ref_pages: list[int] = []

        for chunk in chunks[:6]:
            title = chunk.get('document_title') or 'Textbook'
            page = int(chunk['page_number'])
            key = (title, page)
            if key in seen_pages:
                continue
            seen_pages.add(key)
            ref_pages.append(page)
            excerpt = (chunk.get('text') or '').strip()
            if len(excerpt) > 600:
                excerpt = excerpt[:597] + '…'
            lines.append(f'### {title} (page {page})\n\n{excerpt}\n')

        if ref_pages:
            refs = ', '.join(_PAGE_CITE.format(page=p) for p in dict.fromkeys(ref_pages))
            lines.append(f'\n**References:** {refs}')
        return '\n'.join(lines)

    def _ensure_substantive(self, text: str, query: str, chunks: list[dict]) -> str:
        """Replace citation-only or empty model output with excerpt-based answer."""
        if is_citation_only(text):
            return self._fallback_from_chunks(query, chunks)
        return text

    async def _generate_chat(
        self,
        *,
        analysis: AnalysisResult,
        ai_client: AIClient,
        conversation_history: list[dict] | None,
    ) -> str:
        textbook_context = self._build_textbook_context(analysis.chunks)
        user_prompt = (
            f'Student question: {analysis.query}\n\n'
            f'Textbook excerpts:\n{textbook_context}\n\n'
            'Write a helpful tutor answer in markdown.\n'
            '- Minimum 4 sentences of explanation in your own words.\n'
            '- Summarize topics, definitions, or lists clearly (use bullet points if helpful).\n'
            '- End with "References:" and 1–3 page tags like [p1] copied from excerpt headers.\n'
            '- NEVER reply with only [pN] tags.'
        )
        raw = await complete(
            ai_client,
            system=self.SYSTEM,
            user=user_prompt,
            temperature=0.4,
            max_tokens=4096,
            extra_messages=conversation_history,
        )
        raw = self._ensure_substantive(raw, analysis.query, analysis.chunks)
        if not is_citation_only(raw):
            return raw

        retry_prompt = (
            f'Student question: {analysis.query}\n\n'
            f'Textbook excerpts:\n{textbook_context}\n\n'
            'Write a full markdown answer listing and explaining the topics or content found in the excerpts. '
            'At least 6 sentences. No citation tags in the body. '
            'Optional last line: References: [pN] using pages from the excerpts.'
        )
        retry = await complete(
            ai_client,
            system='You summarize textbook excerpts clearly for students. Complete sentences only.',
            user=retry_prompt,
            temperature=0.5,
            max_tokens=4096,
            extra_messages=conversation_history,
        )
        return self._ensure_substantive(retry, analysis.query, analysis.chunks)

    async def run(
        self,
        analysis: AnalysisResult,
        mode: str,
        ai_client: AIClient,
        conversation_history: list[dict] | None = None,
    ) -> SynthesisResult:
        """Generate the final answer or structured study artifact."""
        if mode == 'chat':
            brief = await self._generate_chat(
                analysis=analysis,
                ai_client=ai_client,
                conversation_history=conversation_history,
            )
            return SynthesisResult(
                query=analysis.query,
                mode=mode,
                brief=brief,
                model_used=ai_client.model,
                provider=ai_client.provider,
                structured=None,
            )

        textbook_context = self._build_textbook_context(analysis.chunks)
        cite_example = '["[p12]"]'
        mode_prompt = {
            'quiz': (
                'Return JSON only with this schema: '
                f'{{"items":[{{"question":"...","answer":"...","citations":{cite_example}}}]}}'
            ),
            'flashcards': (
                'Return JSON only with this schema: '
                f'{{"items":[{{"front":"...","back":"...","citations":{cite_example}}}]}}. '
                'Create 5–8 concise cards grounded in the textbook.'
            ),
            'summary': (
                'Return JSON only with this schema: '
                f'{{"title":"...","outline":[{{"heading":"...","bullets":["..."]}}],"citations":{cite_example}}}'
            ),
        }.get(mode, 'Answer in markdown with [pN] page citations.')

        user_prompt = (
            f'User question: {analysis.query}\n\n'
            f'Textbook context:\n{textbook_context}\n\n'
            f'Mode: {mode}\n'
            f'{mode_prompt}'
        )

        raw = await complete(
            ai_client,
            system=self.SYSTEM,
            user=user_prompt,
            temperature=0.3,
            max_tokens=2000,
            json_mode=True,
        )

        structured = None
        brief = raw
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
