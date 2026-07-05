from __future__ import annotations

"""Post-generation citation verification (no extra LLM call).

Checks that answers contain real prose (not just [pN] tags) and that cited
pages appeared in the retrieved chunk set.
"""

from dataclasses import dataclass

from citations import extract_page_citations, is_citation_only


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

    def _verify_citations(self, answer_text: str, chunks: list[dict]) -> list[str]:
        if is_citation_only(answer_text):
            return ['Answer contained no explanation — only page references.']

        pages_in_chunks = {int(c['page_number']) for c in chunks}
        cited_pages = extract_page_citations(answer_text)
        if not cited_pages:
            return []

        errors: list[str] = []
        for page in cited_pages:
            if page not in pages_in_chunks:
                errors.append(f'Page reference [p{page}] was not in the retrieved excerpts.')
        return errors

    async def run_on_chunks(self, *, brief: str, chunks: list[dict]) -> EvalResult:
        citation_errors = self._verify_citations(brief, chunks)
        return EvalResult(
            passed=not citation_errors,
            score=1.0 if not citation_errors else 0.5,
            claims_checked=0,
            claims_grounded=0,
            ungrounded_claims=[],
            explanation='Page citation check.',
            citation_errors=citation_errors,
        )
