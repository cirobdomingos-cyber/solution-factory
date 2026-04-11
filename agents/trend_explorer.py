"""Online Trend Explorer Agent — Pre-phase: broad-to-narrow discovery.

This agent uses Anthropic server-side web search to scan the current market
and propose exploration paths from broad themes to narrow, buildable niches.
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


class OnlineTrendExplorerAgent:
    """Finds broad-to-narrow opportunity paths using live web signals."""

    def __init__(self, model: str | None = None):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = model or config.SPECIALIST_MODEL
        self.name = "Online Trend Explorer"
        self.max_tokens = config.MAX_TOKENS_SPECIALIST

    @property
    def system_prompt(self) -> str:
        return """You are a market scout that identifies where to explore next.

You have access to web search and must use it to find recent, concrete signals.
Your output must help a builder move from broad exploration to narrow focus.

Output format: JSON object with these fields:
- exploration_domain (string)
- broad_areas (array of objects):
    - title (string)
    - signal_summary (string)
- exploration_paths (array of objects):
    - broad_area (string)
    - mid_area (string)
    - narrow_area (string)
    - opportunity_hypothesis (string)
    - why_now (string)
    - momentum (string: "hot", "warm", "cool")
    - source_signals (array of strings, concrete and specific)
    - starter_queries (array of 2-3 strings)

Rules:
- Generate 8-12 exploration_paths across at least 4 distinct broad_areas
- Favor recency (roughly last 3-6 months when possible)
- Include at least 2 non-obvious or contrarian paths
- Prioritize paths with clear buyer pain and willingness to pay
- Respond with valid JSON only"""

    def run(self, context: dict) -> dict:
        user_prompt = context["user_prompt"]
        search_country = context.get("search_country", "worldwide")

        geo_instruction = ""
        if search_country and search_country != "worldwide":
            from config import COUNTRY_NAMES_MAP
            country_name = COUNTRY_NAMES_MAP.get(search_country, search_country)
            geo_instruction = f"""
GEOGRAPHIC FOCUS: {country_name}
Prioritize signals, launches, regulations, and opportunities specific to {country_name}.
Include the country/region name in your search queries for locally relevant results.
"""

        prompt = f"""The user wants to explore this domain broadly, then narrow down:

DOMAIN: {user_prompt}
{geo_instruction}
Research current online signals and propose broad-to-narrow exploration paths.
Use multiple searches to cover:
1) market movement and launches
2) funding and strategic bets
3) policy/regulation shifts
4) user complaints and unmet needs
5) enabling technology changes

Return only the JSON structure defined in your instructions.
"""

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
                            "max_uses": 7,
                        }
                    ],
                    messages=[{"role": "user", "content": prompt}],
                )
                break
            except anthropic.RateLimitError:
                if attempt == MAX_RETRIES:
                    logger.error(f"[{self.name}] Rate limited after {MAX_RETRIES} attempts")
                    return {
                        "exploration_domain": user_prompt,
                        "broad_areas": [],
                        "exploration_paths": [],
                    }
                delay = RETRY_BASE_DELAY * attempt
                logger.warning(f"[{self.name}] Rate limited, waiting {delay}s...")
                time.sleep(delay)

        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text

        if not text:
            logger.warning(f"[{self.name}] No text in web search response — falling back to built-in knowledge")
            return self._run_builtin_fallback(user_prompt, geo_instruction)

        parsed = self._parse_text(text, user_prompt)
        if not parsed.get("exploration_paths"):
            logger.warning(f"[{self.name}] Web search returned no usable paths — falling back to built-in knowledge")
            return self._run_builtin_fallback(user_prompt, geo_instruction)
        return parsed

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_text(self, text: str, user_prompt: str) -> dict:
        """Parse JSON exploration payload from raw LLM text."""
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
            return {
                "exploration_domain": user_prompt,
                "broad_areas": [],
                "exploration_paths": [],
            }

        if not isinstance(result, dict):
            return {
                "exploration_domain": user_prompt,
                "broad_areas": [],
                "exploration_paths": [],
            }

        return {
            "exploration_domain": result.get("exploration_domain", user_prompt),
            "broad_areas": result.get("broad_areas", []),
            "exploration_paths": result.get("exploration_paths", []),
        }

    def _run_builtin_fallback(self, user_prompt: str, geo_instruction: str = "") -> dict:
        """Call Claude without web search to get built-in knowledge exploration paths.

        Used when the web-search tool returns no text or no usable paths.
        """
        logger.info(f"[{self.name}] Running built-in knowledge fallback for: {user_prompt}")
        fallback_prompt = f"""The user wants to explore this domain broadly, then narrow down:

DOMAIN: {user_prompt}
{geo_instruction}
Using your training knowledge, propose broad-to-narrow exploration paths.
Cover diverse angles: market movement, funding, regulation, user pain points,
and enabling technology.

Return only the JSON structure defined in your instructions.
"""
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
                return {
                    "exploration_domain": user_prompt,
                    "broad_areas": [],
                    "exploration_paths": [],
                    "_source": "builtin",
                }
            result = self._parse_text(text, user_prompt)
            result["_source"] = "builtin"
            return result
        except Exception as e:
            logger.error(f"[{self.name}] Built-in fallback also failed: {e}")
            return {
                "exploration_domain": user_prompt,
                "broad_areas": [],
                "exploration_paths": [],
            }
