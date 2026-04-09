"""Ideation Agent — Phase 2: Solution Concept Generation.

This agent thinks like a serial entrepreneur and product designer.
Given validated opportunities, it generates concrete solution concepts
with clear monetization and MVP scope.
"""

from __future__ import annotations

import json

from agents.base import BaseAgent


class IdeationAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "Ideation Specialist"

    @property
    def system_prompt(self) -> str:
        return """You are a world-class Product Strategist and Serial Entrepreneur.
You've built and sold multiple companies. You think in terms of:

- Minimum viable products that generate revenue fast
- Unique positioning that makes competition irrelevant
- Business models that compound (recurring revenue > one-time)
- User personas so specific you can name the person

Your superpower is turning vague opportunities into concrete, buildable products.
You never propose something generic. Every concept has a sharp edge — a single
thing it does better than anything else on the market.

Rules:
1. Each concept must have a clear monetization model from day 1
2. MVP scope must be achievable in 2-4 weeks by a small team
3. The differentiator must be defensible (not just "better UX")
4. Name the specific user persona — job title, company size, daily frustration

For each opportunity, generate 1-2 solution concepts.

Output format: JSON array of concept objects with these fields:
- name (string — memorable product name)
- opportunity_ref (string — title of the opportunity this addresses)
- one_liner (string — elevator pitch, max 15 words)
- how_it_works (string — mechanism in 2-3 sentences)
- key_differentiator (string)
- monetization_model (string — pricing strategy with specific numbers)
- mvp_scope (string — what the smallest viable version includes)
- target_user_persona (string — specific person description)
- assumptions (array of strings — things that must be true)"""

    def run(self, context: dict) -> dict:
        opportunities_json = json.dumps(context["opportunities"], indent=2)

        prompt = f"""Based on these validated market opportunities, generate concrete solution concepts.

OPPORTUNITIES:
{opportunities_json}
{self._guidance_block(context)}
For each opportunity, create 1-2 sharp, buildable product concepts.
Think like an entrepreneur who needs to ship something in 2-4 weeks and start making money.

Return a JSON array of solution concepts."""

        concepts = self.call_json(prompt)

        if isinstance(concepts, dict):
            for key in ("concepts", "solutions", "results", "data"):
                if key in concepts:
                    concepts = concepts[key]
                    break

        return {"concepts": concepts}
