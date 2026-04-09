"""Critical Review Agent — Phase 6: Final Quality Gate.

This agent is the most important one. It reviews the ENTIRE pipeline output
and decides whether the solution is ready to execute or needs rework.
It uses Opus (the most capable model) because this is the highest-stakes
decision in the pipeline.

This is the "red team" — its job is to find what everyone else missed.
"""

from __future__ import annotations

import json

from agents.base import BaseAgent
import config


class CriticalReviewAgent(BaseAgent):

    def __init__(self):
        super().__init__(model=config.CRITIC_MODEL)
        self.max_tokens = config.MAX_TOKENS_CRITIC

    @property
    def name(self) -> str:
        return "Critical Review"

    @property
    def system_prompt(self) -> str:
        return """You are the Chief Decision Officer — the final quality gate before
execution begins. You have the combined perspective of:

- A skeptical investor (is this worth the resources?)
- A seasoned CTO (is this technically sound?)
- A product strategist (will users actually adopt this?)
- A risk analyst (what could go catastrophically wrong?)

Your job is to review the ENTIRE pipeline output — from opportunity
discovery through execution planning — and render a verdict.

You look for:
1. FATAL FLAWS: Contradictions, impossible assumptions, missing pieces
   that would cause the project to fail. Any fatal flaw = "no_go".
2. BLIND SPOTS: Things the other agents didn't consider — legal issues,
   ethical concerns, market timing shifts, hidden dependencies.
3. COHERENCE: Does the execution plan actually deliver what the architecture
   describes? Does the architecture actually solve the validated opportunity?
4. REALITY CHECK: Is this achievable given realistic constraints?

Scoring (1-10):
- 1-3: Fundamentally flawed, needs complete rethink
- 4-5: Major gaps, send back for rework
- 6-7: Viable but needs specific improvements
- 8-9: Strong, minor adjustments only
- 10: Exceptional, execute immediately

Your go/no_go decision:
- "go": score >= 8, no fatal flaws
- "conditional_go": score 6-7, no fatal flaws, specific conditions listed
- "no_go": score < 6 OR any fatal flaws exist

Output format: JSON object with these fields:
- overall_viability (string — "low", "medium", or "high")
- score (integer 1-10)
- fatal_flaws (array of strings — empty if none)
- blind_spots (array of strings)
- strongest_elements (array of strings)
- recommended_changes (array of strings)
- go_no_go (string — "go", "no_go", or "conditional_go")
- conditions (array of strings — required changes for conditional_go)
- final_verdict (string — one paragraph synthesis of everything)"""

    def run(self, context: dict) -> dict:
        prompt = f"""Review the complete solution pipeline and render your verdict.

ORIGINAL USER REQUEST:
{context.get('user_prompt', 'N/A')}

PHASE 1 — OPPORTUNITIES DISCOVERED:
{json.dumps(context.get('opportunities', []), indent=2)}

PHASE 2 — SOLUTION CONCEPTS:
{json.dumps(context.get('concepts', []), indent=2)}

PHASE 3 — VALIDATION RESULTS:
{json.dumps(context.get('validations', []), indent=2)}

PHASE 4 — SELECTED CONCEPT: {context.get('selected_concept', 'N/A')}
SOLUTION ARCHITECTURE:
{json.dumps(context.get('architecture', {}), indent=2)}

PHASE 5 — EXECUTION PLAN:
{json.dumps(context.get('execution_plan', {}), indent=2)}

Review EVERYTHING. Check for:
1. Contradictions between phases
2. Assumptions that were never validated
3. Missing pieces that would block execution
4. Legal, ethical, or regulatory blind spots
5. Whether the execution plan actually delivers the architecture
6. Whether the whole thing is achievable given realistic constraints

Be thorough. Be honest. This is the last check before someone invests
real time and money.
{self._guidance_block(context)}
Return a JSON object with your review."""

        review = self.call_json(prompt)
        return {"critical_review": review}
