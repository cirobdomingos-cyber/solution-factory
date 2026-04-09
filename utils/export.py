"""Export utilities - save pipeline results to structured files."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime


SESSIONS_SUBDIR = "sessions"
SESSIONS_INDEX_FILENAME = "_index.json"


def _phase_to_stage(current_phase: int, context: dict) -> str:
    """Map pipeline progress to a production lifecycle stage."""
    if current_phase < 0:
        return "Backlog"

    phase_stage = {
        0: "Discovery",
        1: "Discovery",
        2: "Validation",
        3: "Validation",
        4: "Architecture",
        5: "Build Plan",
    }

    if current_phase == 6:
        verdict = context.get("critical_review", {}).get("go_no_go", "")
        return {
            "go": "Ready for Build",
            "conditional_go": "Needs Revision",
            "no_go": "Parked",
        }.get(verdict, "Review")

    return phase_stage.get(current_phase, "In Progress")


def _sessions_dir(output_dir: str) -> str:
    return os.path.join(output_dir, SESSIONS_SUBDIR)


def _sessions_index_path(output_dir: str) -> str:
    return os.path.join(_sessions_dir(output_dir), SESSIONS_INDEX_FILENAME)


def _load_sessions_index(output_dir: str) -> list[dict]:
    path = _sessions_index_path(output_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _save_sessions_index(output_dir: str, rows: list[dict]) -> None:
    path = _sessions_index_path(output_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


def _build_meta_from_file(fpath: str, fname: str) -> dict | None:
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    meta = data.get("_session_meta", {})
    context = data.get("context", {})
    idea_id = meta.get("idea_id") or context.get("idea_id") or f"legacy-{fname}"
    production_stage = (
        meta.get("production_stage")
        or context.get("production_stage")
        or _phase_to_stage(meta.get("current_phase", -1), context)
    )

    return {
        "path": fpath,
        "filename": fname,
        "idea_id": idea_id,
        "production_stage": production_stage,
        **meta,
    }


def save_session(
    context: dict,
    current_phase: int,
    output_dir: str = "output",
    user_email: str = "",
) -> str:
    """Persist the full pipeline context so it can be reloaded later.

    Saved to ``output/sessions/<timestamp>_<slug>.json`` and indexed in
    ``output/sessions/_index.json``.
    Returns the path to the created file.
    """
    sessions_dir = _sessions_dir(output_dir)
    os.makedirs(sessions_dir, exist_ok=True)

    idea_id = context.get("idea_id") or f"idea-{uuid.uuid4().hex[:10]}"
    context["idea_id"] = idea_id
    context["production_stage"] = context.get("production_stage") or _phase_to_stage(current_phase, context)

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
            "idea_id": idea_id,
            "production_stage": context.get("production_stage", _phase_to_stage(current_phase, context)),
            "owner_email": user_email or context.get("owner_email", ""),
        },
        "context": context,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    index = _load_sessions_index(output_dir)
    index = [row for row in index if row.get("filename") != filename]
    index.append({
        "path": filepath,
        "filename": filename,
        **payload["_session_meta"],
    })
    index.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    _save_sessions_index(output_dir, index)

    return filepath


def list_sessions(output_dir: str = "output", user_email: str = "") -> list[dict]:
    """Return session metadata for all saved sessions, newest first.

    Each item has: ``path``, ``timestamp``, ``user_prompt``, ``verdict``,
    ``score``, ``selected_concept``, ``current_phase``, ``idea_id``,
    ``production_stage``.
    """
    sessions_dir = _sessions_dir(output_dir)
    if not os.path.isdir(sessions_dir):
        return []

    index = _load_sessions_index(output_dir)
    if index:
        rows = sorted(index, key=lambda x: x.get("timestamp", ""), reverse=True)
        if user_email:
            rows = [r for r in rows if r.get("owner_email", "") == user_email]
        return rows

    results: list[dict] = []
    for fname in os.listdir(sessions_dir):
        if not fname.endswith(".json") or fname == SESSIONS_INDEX_FILENAME:
            continue
        fpath = os.path.join(sessions_dir, fname)
        row = _build_meta_from_file(fpath, fname)
        if row is not None:
            results.append(row)

    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    _save_sessions_index(output_dir, results)
    if user_email:
        return [r for r in results if r.get("owner_email", "") == user_email]
    return results


def load_session(path: str) -> tuple[dict, int]:
    """Load a previously saved session.

    Returns ``(context_dict, current_phase)``.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ctx = data.get("context", {})
    meta = data.get("_session_meta", {})
    phase = meta.get("current_phase", -1)

    if "idea_id" not in ctx:
        ctx["idea_id"] = meta.get("idea_id") or f"legacy-{os.path.basename(path)}"
    if "production_stage" not in ctx:
        ctx["production_stage"] = meta.get("production_stage") or _phase_to_stage(phase, ctx)
    if "owner_email" not in ctx:
        ctx["owner_email"] = meta.get("owner_email", "")

    return ctx, phase


def update_idea_stage(
    idea_id: str,
    new_stage: str,
    output_dir: str = "output",
    user_email: str = "",
) -> int:
    """Update production stage for all sessions of an idea.

    Returns number of sessions updated.
    """
    if not idea_id:
        return 0

    sessions = list_sessions(output_dir=output_dir)
    updated = 0

    for session in sessions:
        if session.get("idea_id") != idea_id:
            continue
        if user_email and session.get("owner_email", "") != user_email:
            continue

        path = session.get("path", "")
        if not path or not os.path.isfile(path):
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("_session_meta", {})["production_stage"] = new_stage
            data.setdefault("context", {})["production_stage"] = new_stage
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            updated += 1
        except (json.JSONDecodeError, OSError):
            continue

    if updated:
        index = _load_sessions_index(output_dir)
        for row in index:
            if row.get("idea_id") == idea_id and (not user_email or row.get("owner_email", "") == user_email):
                row["production_stage"] = new_stage
        _save_sessions_index(output_dir, index)

    return updated


def export_results(context: dict, output_dir: str = "output") -> str:
    """Export full pipeline results to a timestamped JSON file.

    Returns the path to the created file.
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(context.get("user_prompt", "unknown")[:50])
    filename = f"{timestamp}_{slug}.json"
    filepath = os.path.join(output_dir, filename)

    export = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "user_prompt": context.get("user_prompt"),
            "iterations": context.get("iteration", 1),
            "selected_concept": context.get("selected_concept"),
            "idea_id": context.get("idea_id"),
            "production_stage": context.get("production_stage"),
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
