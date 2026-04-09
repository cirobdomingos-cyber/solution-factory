"""Topic Explorer Agent — Pre-phase: Interactive Topic Narrowing.

When a user enters a broad domain like "health and wellbeing", this agent
quickly generates structured sub-topic suggestions organized by angle
(technology, audience, business model, pain point). The user picks what
interests them, and the selection gets fed into the trend researcher
as a focused query.

Uses Haiku for speed — this is a brainstorming step, not deep analysis.
"""

from __future__ import annotations

from agents.base import BaseAgent


class TopicExplorerAgent(BaseAgent):

    def __init__(self):
        # Haiku for speed — this is interactive brainstorming, not deep reasoning
        super().__init__(model="claude-haiku-4-5-20251001")
        self.max_tokens = 4096

    @property
    def name(self) -> str:
        return "Topic Explorer"

    @property
    def system_prompt(self) -> str:
        return """You are a creative strategist who helps people narrow broad domains
into specific, actionable angles worth researching.

Given a broad topic, generate exploration angles organized into categories.
Each angle should be specific enough to research but broad enough to contain
multiple opportunities.

Output format: JSON object with these fields:
- domain (string — the broad domain as stated)
- angles (array of objects, each with):
    - category (string — one of: "technology", "audience", "pain_point",
      "business_model", "regulation", "emerging_niche")
    - title (string — short, specific angle name)
    - description (string — 1-2 sentences explaining what makes this
      angle interesting and why it might contain opportunities)
    - example_questions (array of 2-3 strings — specific research
      questions this angle raises)
    - heat_level (string — "hot", "warm", "cool" — how much current
      activity/buzz exists around this angle)

Rules:
- Generate 8-12 angles across at least 4 different categories
- Be SPECIFIC, not generic. "AI for mental health screening in workplaces"
  is good. "Technology in health" is useless.
- Include at least 2 contrarian or non-obvious angles
- Think about WHO would pay, not just what's technically cool
- Include at least one regulation/policy angle if relevant"""

    def run(self, context: dict) -> dict:
        user_prompt = context["user_prompt"]

        prompt = f"""The user wants to explore opportunities in this domain:

DOMAIN: {user_prompt}

Generate 8-12 specific angles they could research, organized by category.
Include a mix of obvious high-activity areas AND non-obvious/contrarian angles.
For each angle, suggest 2-3 specific research questions.

IMPORTANT: Respond ONLY with valid JSON."""

        result = self.call_json(prompt)

        # Normalize
        if isinstance(result, dict):
            angles = result.get("angles", [])
        elif isinstance(result, list):
            angles = result
        else:
            angles = []

        return {
            "exploration_domain": result.get("domain", user_prompt) if isinstance(result, dict) else user_prompt,
            "exploration_angles": angles,
        }
