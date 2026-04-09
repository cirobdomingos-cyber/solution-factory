"""Base agent class — all specialist agents inherit from this.

The pattern here is a "prompted specialist": each agent is the same LLM
but with a different system prompt that gives it a specific expertise persona.
The base class handles the API call mechanics so specialists only define
their persona and output parsing.

Interview angle: This is the Strategy pattern — same interface, different
behavior injected via the system prompt. Interviewers ask about this when
discussing how to make AI systems modular and testable.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod

import anthropic

import config

MAX_RETRIES = 3
RETRY_BASE_DELAY = 30  # seconds — generous for a 30k tokens/min limit

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all pipeline agents."""

    def __init__(self, model: str | None = None):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = model or config.SPECIALIST_MODEL
        self.max_tokens = config.MAX_TOKENS_SPECIALIST

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable agent name."""

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The system prompt that defines this agent's expertise and persona."""

    @staticmethod
    def _guidance_block(context: dict) -> str:
        """Build an optional guidance block from user notes injected via the UI."""
        guidance = context.get("user_guidance", "")
        if not guidance:
            return ""
        return f"\n\nUSER GUIDANCE (from the person running this pipeline):\n{guidance}\n"

    def call(self, user_message: str) -> str:
        """Send a message to the LLM and return the raw text response.

        Retries on rate-limit (429) errors with exponential backoff.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"[{self.name}] Calling {self.model} (attempt {attempt})...")

                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=self.system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )

                text = response.content[0].text
                logger.info(f"[{self.name}] Received {len(text)} chars")
                return text

            except anthropic.RateLimitError as e:
                if attempt == MAX_RETRIES:
                    raise
                delay = RETRY_BASE_DELAY * attempt
                logger.warning(
                    f"[{self.name}] Rate limited, waiting {delay}s before retry..."
                )
                time.sleep(delay)

    def call_json(self, user_message: str) -> dict:
        """Call the LLM and parse the response as JSON.

        Appends an instruction to return valid JSON. Handles markdown
        code fences that models sometimes wrap around JSON.
        """
        prompt = (
            user_message
            + "\n\nIMPORTANT: Respond ONLY with valid JSON. "
            "No markdown, no explanation, no text outside the JSON object."
        )

        raw = self.call(prompt)

        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (with optional language tag)
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"[{self.name}] JSON parse failed: {e}")
            logger.warning(f"[{self.name}] Attempting repair retry...")

            # Ask the model to fix the broken JSON
            repair_prompt = (
                "The following JSON is malformed (likely truncated). "
                "Return ONLY the corrected, complete JSON — no markdown, "
                "no explanation:\n\n" + raw[:6000]
            )
            try:
                raw_retry = self.call(repair_prompt)
                retry_cleaned = raw_retry.strip()
                if retry_cleaned.startswith("```"):
                    first_nl = retry_cleaned.index("\n")
                    retry_cleaned = retry_cleaned[first_nl + 1 :]
                if retry_cleaned.endswith("```"):
                    retry_cleaned = retry_cleaned[:-3]
                retry_cleaned = retry_cleaned.strip()
                return json.loads(retry_cleaned)
            except (json.JSONDecodeError, Exception) as retry_err:
                logger.error(f"[{self.name}] Repair retry also failed: {retry_err}")
                raise ValueError(
                    f"Agent '{self.name}' returned invalid JSON. "
                    f"First 200 chars: {raw[:200]}"
                ) from e

    @abstractmethod
    def run(self, context: dict) -> dict:
        """Execute this agent's phase of the pipeline.

        Args:
            context: Accumulated pipeline state as a dict.

        Returns:
            Dict with this agent's structured output to merge into pipeline state.
        """
