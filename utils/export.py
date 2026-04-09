"""Export utilities — save pipeline results to structured files."""

from __future__ import annotations

import json
import os
from datetime import datetime


def save_session(context: dict, current_phase: int, output_dir: str = "output") -> str:
    """Persist the full pipeline context so it can be reloaded later.

    Saved to ``output/sessions/<timestamp>_<slug>.json``.
    Returns the path to the created file.
    """
    sessions_dir = os.path.join(output_dir, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(context.get("user_prompt", "unknown")[:50])
    filename = f"{timestamp}_{slug}.json"
    filepath = os.path.join(sessions_dir, filename)

    payload = {
        "_session_meta": {
            "timestamp": datetime.now().isoformat(),
            "current_phase": current_phase,
            "user_prompt": context.get("user_prompt", ""),
            "verdict": context.get("critical_review", {}).get("go_no_go", ""),
            "score": context.get("critical_review", {}).get("score", 0),
            "selected_concept": context.get("selected_concept", ""),
        },
        "context": context,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    return filepath


def list_sessions(output_dir: str = "output") -> list[dict]:
    """Return session metadata for all saved sessions, newest first.

    Each item has: ``path``, ``timestamp``, ``user_prompt``, ``verdict``,
    ``score``, ``selected_concept``, ``current_phase``.
    """
    sessions_dir = os.path.join(output_dir, "sessions")
    if not os.path.isdir(sessions_dir):
        return []

    results = []
    for fname in os.listdir(sessions_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(sessions_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("_session_meta", {})
            results.append({
                "path": fpath,
                "filename": fname,
                **meta,
            })
        except Exception:
            continue

    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return results


def load_session(path: str) -> tuple[dict, int]:
    """Load a previously saved session.

    Returns ``(context_dict, current_phase)``.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    ctx = data.get("context", {})
    phase = data.get("_session_meta", {}).get("current_phase", -1)
    return ctx, phase


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
