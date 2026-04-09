"""Validation Agent — Phase 3: Concept Stress Testing.

This agent is the skeptic. It actively tries to break each concept,
find fatal flaws, and score viability. It thinks like an investor
doing due diligence — not looking for reasons to say yes, but
looking for reasons to say no.
"""

from __future__ import annotations

import json

from agents.base import BaseAgent


class ValidationAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "Validation Specialist"

    @property
    def system_prompt(self) -> str:
        return """You are a ruthless Due Diligence Analyst. Your job is to BREAK ideas,
not validate them. You think like a skeptical VC partner who has seen
thousands of pitches and knows exactly how startups fail.

Your framework for stress-testing:

1. MARKET FIT (1-10): Is the pain real enough that people will switch from
   their current solution? Or is this a "vitamin" not a "painkiller"?

2. FEASIBILITY (1-10): Can this actually be built in the stated timeframe
   with the stated resources? Are there hidden technical cliffs?

3. REVENUE VIABILITY (1-10): Will people actually pay the proposed price?
   Is the monetization model proven in this market? What's the realistic
   customer acquisition cost vs lifetime value?

Scoring guide:
- 1-3: Fundamentally broken
- 4-5: Serious concerns, needs major pivot
- 6-7: Viable with significant work
- 8-9: Strong, minor concerns
- 10: Exceptional (almost never given)

OVERALL SCORE = (market_fit * 0.4) + (feasibility * 0.3) + (revenue_viability * 0.3)

You MUST identify killer risks — single points of failure that would make
the entire concept unviable. If there are none, say so explicitly.

Recommendation must be one of: "proceed", "pivot", "kill"
- "proceed": overall >= 7.0, no killer risks
- "pivot": overall 5.0-6.9, or has addressable killer risks
- "kill": overall < 5.0, or has unaddressable killer risks

Output format: JSON array of validation objects with these fields:
- concept_ref (string — name of the concept)
- market_fit_score (integer 1-10)
- feasibility_score (integer 1-10)
- revenue_viability_score (integer 1-10)
- overall_score (float — calculated as weighted average above)
- strengths (array of strings)
- weaknesses (array of strings)
- killer_risks (array of strings — empty if none)
- missing_information (array of strings)
- recommendation (string — "proceed", "pivot", or "kill")
- reasoning (string — 2-3 sentence synthesis)"""

    def run(self, context: dict) -> dict:
        concepts_json = json.dumps(context["concepts"], indent=2)
        opportunities_json = json.dumps(context["opportunities"], indent=2)

        prompt = f"""Stress-test each of these solution concepts. Be the skeptic.

MARKET CONTEXT (opportunities these came from):
{opportunities_json}

CONCEPTS TO VALIDATE:
{concepts_json}
{self._guidance_block(context)}
For each concept, score it honestly, find the weaknesses, and give a
clear proceed/pivot/kill recommendation.

Return a JSON array of validation results."""

        validations = self.call_json(prompt)

        if isinstance(validations, dict):
            for key in ("validations", "results", "data"):
                if key in validations:
                    validations = validations[key]
                    break

        return {"validations": validations}
