"""Configuration for the Solution Factory agent system."""

import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Model assignments — Opus for high-stakes reasoning, Sonnet for throughput work
ORCHESTRATOR_MODEL = "claude-opus-4-6"
SPECIALIST_MODEL = "claude-sonnet-4-6"
CRITIC_MODEL = "claude-opus-4-6"  # critic needs deep reasoning too

# Pipeline phases in execution order
PIPELINE_PHASES = [
    "trend_research",
    "opportunity_discovery",
    "ideation",
    "validation",
    "architecture",
    "execution_planning",
    "critical_review",
]

# Max parallel agents per phase
MAX_PARALLEL = 3

# Token budgets per agent call
MAX_TOKENS_SPECIALIST = 8192
MAX_TOKENS_ORCHESTRATOR = 8192
MAX_TOKENS_CRITIC = 8192

# Country code to English name mapping for search agents
COUNTRY_NAMES_MAP = {
    "worldwide": "worldwide",
    "BR": "Brazil", "US": "United States", "GB": "United Kingdom",
    "DE": "Germany", "FR": "France", "JP": "Japan", "IN": "India",
    "CA": "Canada", "AU": "Australia", "PT": "Portugal", "ES": "Spain",
    "MX": "Mexico", "AR": "Argentina", "CL": "Chile", "CO": "Colombia",
    "CN": "China", "KR": "South Korea", "IL": "Israel", "AE": "United Arab Emirates",
    "NG": "Nigeria", "KE": "Kenya", "SG": "Singapore",
}
