from __future__ import annotations

"""Citation verification for generated answers (page-level)."""

import re
from dataclasses import dataclass

from agents.AnalysisAgent import AnalysisResult
from agents.SynthesisAgent import SynthesisResult
from ui.citations import extract_page_citations, is_citation_only


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
    """Check page citations and whether the answer contains real prose."""
    PAGE_RE = re.compile(r'\[p(\d+)\]')

    async def _verify_citations(self, answer_text: str, analysis: AnalysisResult) -> list[str]:
        """Verify page tags against retrieved chunks; skip harsh checks if answer is substantive."""
        if is_citation_only(answer_text):
            return ['Answer contained no explanation — only page references.']

        pages_in_chunks = {int(c['page_number']) for c in analysis.chunks}
        cited_pages = extract_page_citations(answer_text)
        if not cited_pages:
            return []  # prose without refs is fine

        errors: list[str] = []
        for page in cited_pages:
            if page not in pages_in_chunks:
                errors.append(f'Page reference [p{page}] was not in the retrieved excerpts.')
        return errors

    async def run(
        self,
        synthesis: SynthesisResult,
        analysis: AnalysisResult,
    ) -> EvalResult:
        """Verify page citations without an extra LLM call."""
        citation_errors = await self._verify_citations(synthesis.brief, analysis)
        return EvalResult(
            passed=not citation_errors,
            score=1.0 if not citation_errors else 0.5,
            claims_checked=0,
            claims_grounded=0,
            ungrounded_claims=[],
            explanation='Page citation check.',
            citation_errors=citation_errors,
        )
