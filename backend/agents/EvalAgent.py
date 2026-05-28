"""
EvalAgent — LLM-as-judge grounding check.

The problem this solves: LLMs sometimes "hallucinate" — they state things
confidently that aren't in the source documents. Even with a strict "only
use the sources" prompt, the model can slip in facts from its training data.

The solution: after SynthesisAgent generates the brief, we run a second LLM
call that acts as a fact-checker. This second call:
  1. Reads the brief and extracts every specific factual claim.
  2. Checks each claim against the original source documents.
  3. Labels each claim as GROUNDED (can be verified) or UNGROUNDED (can't).
  4. Returns a score 0.0–1.0 and the list of ungrounded claims.

This pattern is called "LLM-as-judge" — using one LLM call to evaluate the
output of another. It's widely used in production AI systems because humans
can't manually fact-check every response at scale.

The score and ungrounded claims are surfaced directly in the UI so users
can see exactly how reliable the answer is.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ai.clients import AIClient, complete
from agents.AnalysisAgent import AnalysisResult
from agents.SynthesisAgent import SynthesisResult


@dataclass
class EvalResult:
    passed: bool                   # True if score >= 0.75
    score: float                   # 0.0 (nothing verified) to 1.0 (fully grounded)
    claims_checked: int
    claims_grounded: int
    ungrounded_claims: list[str]   # specific claims the LLM couldn't verify
    explanation: str


class EvalAgent:

    # The eval system prompt is very different from the synthesis one.
    # Instead of "be a research assistant", it says "be a fact-checker".
    # We also force JSON output so we can parse the structured results reliably.
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
        # We only give the evaluator the first 10 source items (not all 15)
        # to keep the eval prompt shorter and cheaper.
        # The eval doesn't need every source — just enough to verify the claims.
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
            # json_mode=True tells the LLM to output only valid JSON.
            # This prevents the model from wrapping the JSON in prose like
            # "Here is the evaluation: {...}" which would break json.loads().
            raw = await complete(
                ai_client,
                system=self.EVAL_SYSTEM,
                user=user_prompt,
                temperature=0.1,   # very low temperature — we want consistent, deterministic grading
                max_tokens=1500,
                json_mode=True,
            )
            data = json.loads(raw)
            claims = data.get("claims", [])
            grounded = [c for c in claims if c.get("grounded")]
            ungrounded = [c["claim"] for c in claims if not c.get("grounded")]

            # The LLM returns its own grounding_score, but we compute one from
            # the claims list as a fallback in case it's missing or miscalculated.
            score = float(data.get("grounding_score", len(grounded) / max(len(claims), 1)))

            return EvalResult(
                passed=score >= 0.75,   # 75% is the threshold for "acceptable" grounding
                score=round(score, 3),
                claims_checked=len(claims),
                claims_grounded=len(grounded),
                ungrounded_claims=ungrounded,
                explanation=data.get("explanation", ""),
            )

        except Exception as exc:
            # If eval fails (parse error, API error, etc.), return a neutral result
            # rather than crashing the whole pipeline. The user still gets the
            # brief — they just won't have grounding metrics.
            return EvalResult(
                passed=False,
                score=0.0,
                claims_checked=0,
                claims_grounded=0,
                ungrounded_claims=[],
                explanation=f"Eval failed: {exc}",
            )
