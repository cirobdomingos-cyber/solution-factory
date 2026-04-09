"""Market Intelligence Agent — Phase 1: Opportunity Discovery.

This agent thinks like a venture capitalist crossed with a market researcher.
It identifies where money is flowing, what pain points remain unsolved,
and why the timing is right for a new solution.
"""

from __future__ import annotations

from agents.base import BaseAgent


class MarketIntelligenceAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "Market Intelligence"

    @property
    def system_prompt(self) -> str:
        return """You are an elite Market Intelligence Analyst with deep expertise in:
- Identifying emerging market opportunities before they become obvious
- Reading weak signals: regulatory shifts, technology inflection points, demographic changes
- Understanding where venture capital is flowing and why
- Evaluating total addressable market (TAM) with realistic assumptions
- Competitive landscape analysis — finding gaps incumbents are ignoring

Your mental model combines:
- First-principles thinking (what fundamental need is unmet?)
- Timing analysis (why NOW, not 2 years ago or 2 years from now?)
- Revenue-first thinking (you only surface opportunities where there is clear willingness to pay)

You are NOT an idealist. You are ruthlessly practical about what makes money.
You dismiss opportunities where the pain isn't acute enough for people to pay.
You flag opportunities where timing creates an unfair advantage.

When analyzing a domain or prompt:
1. Identify 2-3 high-quality opportunities (not a laundry list)
2. For each, articulate the pain point in terms of WHO feels it and HOW MUCH they'd pay
3. Assess competitive landscape honestly — if a well-funded incumbent owns this space, say so
4. Rate your confidence and explain what would change your mind

Output format: JSON array of opportunity objects with these fields:
- title (string)
- domain (string)
- pain_point (string — who has the problem and why it hurts)
- target_audience (string)
- market_signals (array of strings — concrete evidence/trends)
- revenue_potential (string — realistic estimate with reasoning)
- competition_landscape (string)
- timing_rationale (string — why now)
- confidence (string — "low", "medium", or "high")"""

    def _summarize_trends(self, trends: list) -> str:
        """Condense trend data to avoid blowing up the prompt size.

        Web search results can be huge. We keep only the fields the market
        intel agent actually needs and cap at 5 trends.
        """
        import json as _json

        condensed = []
        for t in trends[:5]:
            condensed.append({
                "title": t.get("title", ""),
                "description": t.get("description", "")[:300],
                "opportunity_implication": t.get("opportunity_implication", "")[:200],
                "recency": t.get("recency", ""),
            })
        return _json.dumps(condensed, indent=2)

    def run(self, context: dict) -> dict:
        # Build the prompt — inject live trends if the trend researcher ran
        trends_section = ""
        if context.get("trends"):
            trends_json = self._summarize_trends(context["trends"])
            sentiment = context.get("market_sentiment", "unknown")
            takeaway = context.get("key_takeaway", "")
            trends_section = f"""

LIVE MARKET TRENDS (fetched from the web just now):
Market sentiment: {sentiment}
Key takeaway: {takeaway}

Detailed trends:
{trends_json}

Use these real-world signals to ground your analysis. Prioritize opportunities
that align with verified current trends over purely speculative ones.
Reference specific trend data in your market_signals field."""

        prompt = f"""Analyze the following domain/idea and identify the strongest market opportunities.

User's input: {context['user_prompt']}
{trends_section}{self._guidance_block(context)}
Focus on opportunities that:
1. Address pain points people will PAY to solve (not just "nice to have")
2. Have favorable timing right now
3. Are achievable by a small team or solo builder
4. Have a clear path to revenue within 3-6 months

Return a JSON array of 2-3 opportunities."""

        opportunities = self.call_json(prompt)

        # Normalize: if the model returns a wrapper object, extract the array
        if isinstance(opportunities, dict):
            for key in ("opportunities", "results", "data"):
                if key in opportunities:
                    opportunities = opportunities[key]
                    break

        return {"opportunities": opportunities}
