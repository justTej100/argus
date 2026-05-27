"""
EvalAgent — LLM-as-judge grounding check.

After SynthesisAgent generates a brief, EvalAgent:
1. Extracts every factual claim from the brief
2. Checks each claim against the retrieved source documents
3. Returns a grounding score 0.0–1.0 + list of ungrounded claims

A claim is "grounded" if it can be verified in at least one source.
Ungrounded claims = potential hallucinations.

This is one of the most in-demand AI engineering patterns right now —
companies ship AI and then ask "is this actually accurate?". This answers that.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ai.clients import AIClient, complete
from agents.AnalysisAgent import AnalysisResult
from agents.SynthesisAgent import SynthesisResult


@dataclass
class EvalResult:
    passed: bool
    score: float                    # 0.0 – 1.0
    claims_checked: int
    claims_grounded: int
    ungrounded_claims: list[str]
    explanation: str


class EvalAgent:

    EVAL_SYSTEM = """You are a fact-checking agent. You verify whether claims in an AI-generated
brief are supported by the provided source documents.

For each claim in the brief:
1. Identify specific factual assertions (numbers, names, events, quotes)
2. Check if each assertion appears in the sources
3. Mark as GROUNDED (found in sources) or UNGROUNDED (not found / contradicted)

Return JSON only:
{
  "claims": [
    {"claim": "...", "grounded": true/false, "source": "reddit/hn/github/null"}
  ],
  "grounding_score": 0.0-1.0,
  "explanation": "..."
}"""

    async def run(
        self,
        synthesis: SynthesisResult,
        analysis: AnalysisResult,
        ai_client: AIClient,
    ) -> EvalResult:
        source_summary = "\n".join(
            f"[{item.source}] {item.title}: {item.body[:200]}"
            for item in analysis.top_items[:10]
        )

        user_prompt = f"""Brief to evaluate:
{synthesis.brief}

Source documents:
{source_summary}

Check each factual claim in the brief against the sources."""

        try:
            raw = await complete(
                ai_client,
                system=self.EVAL_SYSTEM,
                user=user_prompt,
                temperature=0.1,
                max_tokens=1500,
                json_mode=True,
            )
            data = json.loads(raw)
            claims = data.get("claims", [])
            grounded = [c for c in claims if c.get("grounded")]
            ungrounded = [c["claim"] for c in claims if not c.get("grounded")]
            score = float(data.get("grounding_score", len(grounded) / max(len(claims), 1)))

            return EvalResult(
                passed=score >= 0.75,
                score=round(score, 3),
                claims_checked=len(claims),
                claims_grounded=len(grounded),
                ungrounded_claims=ungrounded,
                explanation=data.get("explanation", ""),
            )

        except Exception as exc:
            return EvalResult(
                passed=False,
                score=0.0,
                claims_checked=0,
                claims_grounded=0,
                ungrounded_claims=[],
                explanation=f"Eval failed: {exc}",
            )