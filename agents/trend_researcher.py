"""Trend Research Agent — Phase 0: Live Trend Discovery.

This agent fetches real-time market signals from the web before the rest of
the pipeline runs. It uses Anthropic's server-side web search tool, so no
extra API keys are needed — just the existing Anthropic key.

Interview angle: This is the "tool use" pattern. Instead of relying solely
on the LLM's training-data knowledge, we give it access to live information.
The server-side web_search tool means the API handles the actual fetching —
Claude decides *what* to search, the API executes it, and Claude synthesizes
the results. No client-side tool execution loop required.

The alternative would be a client-side tool loop (you send tool_use blocks
back and forth), which gives more control but adds complexity. Server-side
is the right choice here because we trust Claude to pick good queries and
we don't need to intercept or modify search results.
"""

from __future__ import annotations

import json
import logging
import time

import anthropic

import config

MAX_RETRIES = 3
RETRY_BASE_DELAY = 30

logger = logging.getLogger(__name__)


class TrendResearchAgent:
    """Fetches live market trends using Anthropic's web search tool.

    This agent doesn't inherit from BaseAgent because it needs a different
    call pattern — tool use with web search instead of plain text completion.
    It still follows the same run(context) -> dict interface so the
    orchestrator treats it identically.
    """

    def __init__(self, model: str | None = None):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = model or config.SPECIALIST_MODEL
        self.name = "Trend Researcher"
        self.max_tokens = config.MAX_TOKENS_SPECIALIST

    @property
    def system_prompt(self) -> str:
        return """You are a real-time Market Trend Researcher. Your job is to
search the web for the latest signals relevant to a given domain or idea.

You have access to web search. Use it aggressively — make multiple searches
to cover different angles:
- Recent funding rounds and acquisitions in the space
- New regulations or policy changes affecting the domain
- Emerging technologies or tools gaining traction
- Customer complaints and unmet needs (Reddit, forums, review sites)
- Competitor launches or pivots in the last 6 months

Synthesize what you find into actionable intelligence. Don't just summarize
headlines — connect dots between trends and explain what they mean for
someone building a new product in this space.

Output format: JSON object with these fields:
- domain (string — the domain you researched)
- search_queries_used (array of strings — what you searched for)
- trends (array of objects, each with):
    - title (string)
    - description (string — what's happening and why it matters)
    - source_signals (array of strings — concrete evidence from your searches)
    - opportunity_implication (string — what this means for builders)
    - recency (string — "last_week", "last_month", "last_quarter", "last_year")
- market_sentiment (string — overall mood: "bullish", "cautious", "bearish")
- key_takeaway (string — the single most important insight for a builder)"""

    def run(self, context: dict) -> dict:
        """Fetch live trends relevant to the user's domain/idea."""
        user_prompt = context["user_prompt"]
        search_country = context.get("search_country", "worldwide")

        geo_instruction = ""
        if search_country and search_country != "worldwide":
            from config import COUNTRY_NAMES_MAP
            country_name = COUNTRY_NAMES_MAP.get(search_country, search_country)
            geo_instruction = f"""
GEOGRAPHIC FOCUS: {country_name}
Prioritize trends, news, regulations, and market signals specific to {country_name}.
Include the country/region name in your search queries to get locally relevant results.
"""

        prompt = f"""Research the following domain/idea and find the latest real-world
market trends, news, funding activity, and competitive signals.

DOMAIN/IDEA: {user_prompt}
{geo_instruction}
Search for:
1. Recent news and developments in this space (last 3-6 months)
2. Funding rounds, acquisitions, or new entrants
3. Regulatory changes or upcoming policy shifts
4. Technology trends enabling new solutions
5. Customer pain points being discussed online

Make multiple web searches to get comprehensive coverage. Then synthesize
your findings into the JSON format specified in your instructions.

IMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation,
no text outside the JSON object."""

        response = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"[{self.name}] Calling {self.model} with web search (attempt {attempt})...")

                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=self.system_prompt,
                    tools=[
                        {
                            "type": "web_search_20250305",
                            "name": "web_search",
                            "max_uses": 5,
                        }
                    ],
                    messages=[{"role": "user", "content": prompt}],
                )
                break

            except anthropic.RateLimitError:
                if attempt == MAX_RETRIES:
                    logger.error(f"[{self.name}] Rate limited after {MAX_RETRIES} attempts")
                    return {"trends": [], "market_sentiment": "unknown", "key_takeaway": ""}
                delay = RETRY_BASE_DELAY * attempt
                logger.warning(f"[{self.name}] Rate limited, waiting {delay}s...")
                time.sleep(delay)

            except (anthropic.BadRequestError, anthropic.APIStatusError) as e:
                err_text = str(e).lower()
                if "credit balance" in err_text or "insufficient" in err_text or "plans & billing" in err_text:
                    # Re-raise so the caller can show a credit-specific warning
                    raise
                logger.error(f"[{self.name}] API error on attempt {attempt}: {e}")
                if attempt == MAX_RETRIES:
                    return {"trends": [], "market_sentiment": "unknown", "key_takeaway": "", "_error": str(e)}
                time.sleep(RETRY_BASE_DELAY)

        # Extract the final text block from the response.
        # With server-side web search, the response contains interleaved
        # web_search_tool_result and text blocks. We want the last text block
        # which contains the synthesized JSON output.
        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text

        if not text:
            logger.warning(f"[{self.name}] Web search returned no text — falling back to built-in knowledge call")
            return self._run_builtin_fallback(user_prompt)

        logger.info(f"[{self.name}] Received {len(text)} chars")

        # Parse JSON — same cleanup as BaseAgent.call_json
        return self._parse_text(text)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_text(self, text: str) -> dict:
        """Parse a JSON trend payload from raw LLM text."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.name}] Failed to parse JSON: {e}")
            logger.error(f"[{self.name}] Raw response:\n{text[:500]}")
            return {"trends": [], "market_sentiment": "unknown", "key_takeaway": ""}

        if isinstance(result, dict) and "trends" in result:
            return {
                "trends": result.get("trends", []),
                "market_sentiment": result.get("market_sentiment", "unknown"),
                "key_takeaway": result.get("key_takeaway", ""),
            }
        if isinstance(result, list):
            return {"trends": result, "market_sentiment": "unknown", "key_takeaway": ""}
        return {"trends": [], "market_sentiment": "unknown", "key_takeaway": ""}

    def _run_builtin_fallback(self, user_prompt: str) -> dict:
        """Call Claude without web search to get built-in knowledge trends.

        Used when the web-search tool returns no text — e.g. the tool is not
        available on this API tier, or the domain returned zero results.
        The result is marked with _source='builtin' so the UI can label it.
        """
        logger.info(f"[{self.name}] Running built-in knowledge fallback for: {user_prompt}")
        fallback_prompt = f"""You are a market trend researcher. Using your training knowledge,
identify the most relevant trends, signals, and competitive dynamics for the
following domain/idea. Do NOT apologise for lacking live data — just provide
your best current knowledge.

DOMAIN/IDEA: {user_prompt}

Cover:
1. Key trends shaping this space right now
2. Main customer pain points and unmet needs
3. Technology or regulatory forces enabling or threatening new entrants
4. Competitive landscape and recent moves by incumbents

IMPORTANT: Respond ONLY with valid JSON matching this schema:
{{
  "domain": "<domain string>",
  "trends": [
    {{
      "title": "...",
      "description": "...",
      "source_signals": ["..."],
      "opportunity_implication": "...",
      "recency": "last_year"
    }}
  ],
  "market_sentiment": "bullish|cautious|bearish",
  "key_takeaway": "..."
}}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=[{"role": "user", "content": fallback_prompt}],
            )
            text = ""
            for block in response.content:
                if block.type == "text":
                    text = block.text
            if not text:
                return {"trends": [], "market_sentiment": "unknown", "key_takeaway": ""}
            result = self._parse_text(text)
            result["_source"] = "builtin"
            return result
        except Exception as e:
            logger.error(f"[{self.name}] Built-in fallback also failed: {e}")
            return {"trends": [], "market_sentiment": "unknown", "key_takeaway": ""}
