"""Export utilities — save pipeline results to structured files."""

from __future__ import annotations

import json
import os
from datetime import datetime


def export_results(context: dict, output_dir: str = "output") -> str:
    """Export full pipeline results to a timestamped JSON file.

    Returns the path to the created file.
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(context.get("user_prompt", "unknown")[:50])
    filename = f"{timestamp}_{slug}.json"
    filepath = os.path.join(output_dir, filename)

    # Build clean export
    export = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "user_prompt": context.get("user_prompt"),
            "iterations": context.get("iteration", 1),
            "selected_concept": context.get("selected_concept"),
        },
        "trends": {
            "data": context.get("trends", []),
            "market_sentiment": context.get("market_sentiment", "unknown"),
            "key_takeaway": context.get("key_takeaway", ""),
        },
        "opportunities": context.get("opportunities", []),
        "concepts": context.get("concepts", []),
        "validations": context.get("validations", []),
        "architecture": context.get("architecture", {}),
        "execution_plan": context.get("execution_plan", {}),
        "critical_review": context.get("critical_review", {}),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    return filepath


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")[:40]
