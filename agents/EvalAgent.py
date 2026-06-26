from __future__ import annotations

"""Citation verification for generated answers."""

import re
from dataclasses import dataclass

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
    """Check whether citation tags in the answer map to stored sentences."""
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
    ) -> EvalResult:
        """Verify citation tags without an extra LLM call."""
        citation_errors = await self._verify_citations(synthesis.brief, analysis)
        return EvalResult(
            passed=not citation_errors,
            score=1.0 if not citation_errors else 0.5,
            claims_checked=0,
            claims_grounded=0,
            ungrounded_claims=[],
            explanation='Citation check only.',
            citation_errors=citation_errors,
        )
