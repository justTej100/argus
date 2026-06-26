from __future__ import annotations

"""Grounding and citation verification for generated answers."""

import json
import re
from dataclasses import dataclass

from ai.clients import AIClient, complete
from agents.AnalysisAgent import AnalysisResult
from agents.SynthesisAgent import SynthesisResult
from db.client import get_sentence


@dataclass
class EvalResult:
    passed: bool
    score: float
    claims_checked: int
    claims_grounded: int
    ungrounded_claims: list[str]
    explanation: str
    citation_errors: list[str]


class EvalAgent:
    """Check whether the generated answer is grounded and cited correctly."""
    EVAL_SYSTEM = (
        'You are a strict grounding evaluator. Return JSON only with keys '
        'claims (array), grounding_score (0-1), explanation (string). '
        'Each claim item must have: claim and grounded.'
    )

    CITATION_RE = re.compile(r'\[p(\d+):s(\d+)\]')

    async def _verify_citations(self, answer_text: str, analysis: AnalysisResult) -> list[str]:
        """Verify every citation tag against the stored sentence table."""
        errors: list[str] = []
        matches = list(self.CITATION_RE.finditer(answer_text))
        if not matches:
            errors.append('No citation tags found in answer.')
            return errors

        chunk_by_page: dict[int, dict] = {}
        for chunk in analysis.chunks:
            page = int(chunk['page_number'])
            if page not in chunk_by_page:
                chunk_by_page[page] = chunk

        for match in matches:
            page = int(match.group(1))
            sentence_idx = int(match.group(2))
            chunk = chunk_by_page.get(page)
            if not chunk:
                errors.append(f'Citation [p{page}:s{sentence_idx}] references a page outside retrieved chunks.')
                continue

            sentence = await get_sentence(chunk['document_id'], page, sentence_idx)
            if not sentence:
                errors.append(f'Citation [p{page}:s{sentence_idx}] does not map to a stored sentence.')
                continue

            citation_token = match.group(0)
            line_start = answer_text.rfind('\n', 0, match.start()) + 1
            line_end = answer_text.find('\n', match.end())
            if line_end == -1:
                line_end = len(answer_text)
            line_text = answer_text[line_start:line_end].replace(citation_token, '').strip()
            if line_text:
                words = {w.lower() for w in re.findall(r'[A-Za-z]{4,}', line_text)}
                supported = any(word in sentence.lower() for word in words)
                if not supported:
                    errors.append(
                        f'Citation [p{page}:s{sentence_idx}] may not support claim: "{line_text[:160]}"'
                    )

        return errors

    async def run(
        self,
        synthesis: SynthesisResult,
        analysis: AnalysisResult,
        ai_client: AIClient,
    ) -> EvalResult:
        """Run grounding evaluation and citation verification."""
        source_summary = '\n'.join(
            (
                f"[doc:{chunk['document_id']}] [p{chunk['page_number']}:s{chunk['sentence_start_idx']}] "
                f"{chunk['text'][:300]}"
            )
            for chunk in analysis.chunks[:10]
        )

        try:
            raw = await complete(
                ai_client,
                system=self.EVAL_SYSTEM,
                user=(
                    f'Answer to evaluate:\n{synthesis.brief}\n\n'
                    f'Textbook chunks:\n{source_summary}\n\n'
                    'Extract claims and decide if each is grounded in the chunks.'
                ),
                temperature=0.0,
                max_tokens=1200,
                json_mode=True,
            )
            data = json.loads(raw)
            claims = data.get('claims', [])
            grounded = [c for c in claims if c.get('grounded')]
            ungrounded = [c.get('claim', '') for c in claims if not c.get('grounded')]
            score = float(data.get('grounding_score', len(grounded) / max(len(claims), 1)))
        except Exception as exc:
            claims = []
            grounded = []
            ungrounded = []
            score = 0.0
            data = {'explanation': f'Eval failed: {exc}'}

        citation_errors = await self._verify_citations(synthesis.brief, analysis)

        return EvalResult(
            passed=score >= 0.75 and not citation_errors,
            score=round(score, 3),
            claims_checked=len(claims),
            claims_grounded=len(grounded),
            ungrounded_claims=ungrounded,
            explanation=data.get('explanation', ''),
            citation_errors=citation_errors,
        )
