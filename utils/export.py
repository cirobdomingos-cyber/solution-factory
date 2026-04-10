"""Export utilities - save pipeline results to structured files."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime


SESSIONS_SUBDIR = "sessions"
SESSIONS_INDEX_FILENAME = "_index.json"
SESSIONS_DB_TABLE = "solution_sessions"

_DB_SCHEMA_READY = False


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


def _database_url() -> str:
    """Return the configured sessions database URL, if present."""
    return os.getenv("SESSION_DATABASE_URL", "") or os.getenv("DATABASE_URL", "")


def _db_enabled() -> bool:
    """True when a Postgres URL is configured for session persistence."""
    url = _database_url().strip()
    return url.startswith("postgres://") or url.startswith("postgresql://")


def _coerce_payload(payload: object) -> dict:
    """Normalize payload values returned by DB drivers."""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _ensure_db_schema() -> bool:
    """Create DB table/indexes on first use.

    Returns True when schema is ready; False when DB is unavailable.
    """
    global _DB_SCHEMA_READY
    if _DB_SCHEMA_READY:
        return True
    if not _db_enabled():
        return False

    try:
        import psycopg  # type: ignore

        with psycopg.connect(_database_url(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SESSIONS_DB_TABLE} (
                        session_key TEXT PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL,
                        current_phase INTEGER NOT NULL,
                        user_email TEXT,
                        idea_id TEXT,
                        production_stage TEXT,
                        stage_updated_at TIMESTAMPTZ,
                        payload JSONB NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{SESSIONS_DB_TABLE}_user_created
                    ON {SESSIONS_DB_TABLE} (user_email, created_at DESC)
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{SESSIONS_DB_TABLE}_idea
                    ON {SESSIONS_DB_TABLE} (idea_id)
                    """
                )
        _DB_SCHEMA_READY = True
        return True
    except Exception:
        return False


def _save_session_db(
    payload: dict,
    current_phase: int,
    existing_session_key: str = "",
) -> str | None:
    """Persist a session payload in Postgres and return synthetic path.

    When ``existing_session_key`` is provided, updates that row instead of
    inserting a new one. This keeps checkpoints for the same investigation in
    a single session record.
    """
    if not _ensure_db_schema():
        return None

    meta = payload.get("_session_meta", {})
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    slug = _slugify(meta.get("user_prompt", "unknown")[:50])
    session_key = existing_session_key or f"{timestamp}_{slug}_{uuid.uuid4().hex[:8]}"

    try:
        import psycopg  # type: ignore

        with psycopg.connect(_database_url(), autocommit=True) as conn:
            with conn.cursor() as cur:
                if existing_session_key:
                    cur.execute(
                        f"""
                        UPDATE {SESSIONS_DB_TABLE}
                        SET current_phase = %s,
                            user_email = %s,
                            idea_id = %s,
                            production_stage = %s,
                            stage_updated_at = %s,
                            payload = %s::jsonb
                        WHERE session_key = %s
                        """,
                        (
                            current_phase,
                            meta.get("owner_email", ""),
                            meta.get("idea_id", ""),
                            meta.get("production_stage", ""),
                            meta.get("stage_updated_at", "") or now,
                            json.dumps(payload, ensure_ascii=False, default=str),
                            session_key,
                        ),
                    )
                    if cur.rowcount == 0:
                        cur.execute(
                            f"""
                            INSERT INTO {SESSIONS_DB_TABLE} (
                                session_key, created_at, current_phase, user_email,
                                idea_id, production_stage, stage_updated_at, payload
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                            """,
                            (
                                session_key,
                                now,
                                current_phase,
                                meta.get("owner_email", ""),
                                meta.get("idea_id", ""),
                                meta.get("production_stage", ""),
                                meta.get("stage_updated_at", "") or now,
                                json.dumps(payload, ensure_ascii=False, default=str),
                            ),
                        )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {SESSIONS_DB_TABLE} (
                            session_key, created_at, current_phase, user_email,
                            idea_id, production_stage, stage_updated_at, payload
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            session_key,
                            now,
                            current_phase,
                            meta.get("owner_email", ""),
                            meta.get("idea_id", ""),
                            meta.get("production_stage", ""),
                            meta.get("stage_updated_at", "") or now,
                            json.dumps(payload, ensure_ascii=False, default=str),
                        ),
                    )
        return f"db:{session_key}"
    except Exception:
        return None


def _list_sessions_db(user_email: str = "") -> list[dict] | None:
    """List sessions from Postgres; return None if DB unavailable."""
    if not _ensure_db_schema():
        return None

    try:
        import psycopg  # type: ignore

        if user_email:
            query = (
                f"SELECT session_key, current_phase, payload "
                f"FROM {SESSIONS_DB_TABLE} WHERE user_email = %s "
                f"ORDER BY created_at DESC"
            )
            params = (user_email,)
        else:
            query = f"SELECT session_key, current_phase, payload FROM {SESSIONS_DB_TABLE} ORDER BY created_at DESC"
            params = tuple()

        rows: list[dict] = []
        with psycopg.connect(_database_url(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                for session_key, current_phase, raw_payload in cur.fetchall():
                    payload = _coerce_payload(raw_payload)
                    meta = payload.get("_session_meta", {})
                    ctx = payload.get("context", {})
                    rows.append({
                        "path": f"db:{session_key}",
                        "filename": str(session_key),
                        "timestamp": meta.get("timestamp", ""),
                        "current_phase": meta.get("current_phase", current_phase),
                        "user_prompt": meta.get("user_prompt", ""),
                        "verdict": meta.get("verdict", ""),
                        "score": meta.get("score", 0),
                        "selected_concept": meta.get("selected_concept", ""),
                        "idea_id": meta.get("idea_id") or ctx.get("idea_id", ""),
                        "production_stage": meta.get("production_stage") or ctx.get("production_stage", "In Progress"),
                        "stage_updated_at": meta.get("stage_updated_at") or meta.get("timestamp", ""),
                        "owner_email": meta.get("owner_email", ""),
                    })
        return rows
    except Exception:
        return None


def _load_session_db(path: str) -> tuple[dict, int] | None:
    """Load a session from Postgres using synthetic path db:<session_key>."""
    if not path.startswith("db:"):
        return None
    if not _ensure_db_schema():
        return None

    session_key = path[3:]
    if not session_key:
        return None

    try:
        import psycopg  # type: ignore

        with psycopg.connect(_database_url(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT current_phase, payload FROM {SESSIONS_DB_TABLE} WHERE session_key = %s",
                    (session_key,),
                )
                row = cur.fetchone()

        if not row:
            return None

        current_phase, raw_payload = row
        payload = _coerce_payload(raw_payload)
        ctx = payload.get("context", {})
        meta = payload.get("_session_meta", {})

        if "idea_id" not in ctx:
            ctx["idea_id"] = meta.get("idea_id") or f"legacy-{session_key}"
        if "production_stage" not in ctx:
            ctx["production_stage"] = meta.get("production_stage") or _phase_to_stage(current_phase, ctx)
        if "stage_updated_at" not in ctx:
            ctx["stage_updated_at"] = meta.get("stage_updated_at") or meta.get("timestamp", "")
        if "owner_email" not in ctx:
            ctx["owner_email"] = meta.get("owner_email", "")
        ctx["session_path"] = path

        return ctx, int(current_phase)
    except Exception:
        return None


def _update_idea_stage_db(idea_id: str, new_stage: str, user_email: str = "") -> int | None:
    """Update production stage in Postgres for all sessions of an idea."""
    if not _ensure_db_schema() or not idea_id:
        return None

    now_iso = datetime.now().isoformat()
    try:
        import psycopg  # type: ignore

        if user_email:
            query = f"SELECT session_key, payload FROM {SESSIONS_DB_TABLE} WHERE idea_id = %s AND user_email = %s"
            params = (idea_id, user_email)
        else:
            query = f"SELECT session_key, payload FROM {SESSIONS_DB_TABLE} WHERE idea_id = %s"
            params = (idea_id,)

        updated = 0
        with psycopg.connect(_database_url(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()

                for session_key, raw_payload in rows:
                    payload = _coerce_payload(raw_payload)
                    payload.setdefault("_session_meta", {})["production_stage"] = new_stage
                    payload.setdefault("_session_meta", {})["stage_updated_at"] = now_iso
                    payload.setdefault("context", {})["production_stage"] = new_stage
                    payload.setdefault("context", {})["stage_updated_at"] = now_iso

                    cur.execute(
                        f"""
                        UPDATE {SESSIONS_DB_TABLE}
                        SET production_stage = %s,
                            stage_updated_at = %s,
                            payload = %s::jsonb
                        WHERE session_key = %s
                        """,
                        (
                            new_stage,
                            now_iso,
                            json.dumps(payload, ensure_ascii=False, default=str),
                            session_key,
                        ),
                    )
                    updated += 1

        return updated
    except Exception:
        return None


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
        "stage_updated_at": meta.get("stage_updated_at") or meta.get("timestamp", ""),
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

    now_iso = datetime.now().isoformat()
    idea_id = context.get("idea_id") or f"idea-{uuid.uuid4().hex[:10]}"
    context["idea_id"] = idea_id
    context["production_stage"] = context.get("production_stage") or _phase_to_stage(current_phase, context)
    context["stage_updated_at"] = context.get("stage_updated_at") or now_iso
    context["owner_email"] = user_email or context.get("owner_email", "")

    existing_path = str(context.get("session_path", "") or "")
    if existing_path and existing_path.startswith("db:"):
        db_existing_key = existing_path[3:]
    else:
        db_existing_key = ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(context.get("user_prompt", "unknown")[:50])
    filename = f"{timestamp}_{slug}.json"
    filepath = os.path.join(sessions_dir, filename)
    if existing_path and (not existing_path.startswith("db:")):
        filepath = existing_path
        filename = os.path.basename(existing_path)

    payload = {
        "_session_meta": {
            "timestamp": now_iso,
            "current_phase": current_phase,
            "user_prompt": context.get("user_prompt", ""),
            "verdict": context.get("critical_review", {}).get("go_no_go", ""),
            "score": context.get("critical_review", {}).get("score", 0),
            "selected_concept": context.get("selected_concept", ""),
            "idea_id": idea_id,
            "production_stage": context.get("production_stage", _phase_to_stage(current_phase, context)),
            "stage_updated_at": context.get("stage_updated_at", now_iso),
            "owner_email": user_email or context.get("owner_email", ""),
        },
        "context": context,
    }

    db_path = _save_session_db(payload, current_phase, existing_session_key=db_existing_key)
    if db_path:
        context["session_path"] = db_path
        return db_path

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

    context["session_path"] = filepath

    return filepath


def list_sessions(output_dir: str = "output", user_email: str = "") -> list[dict]:
    """Return session metadata for all saved sessions, newest first.

    Each item has: ``path``, ``timestamp``, ``user_prompt``, ``verdict``,
    ``score``, ``selected_concept``, ``current_phase``, ``idea_id``,
    ``production_stage``.
    """
    db_rows = _list_sessions_db(user_email=user_email)
    if db_rows is not None:
        return db_rows

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
    db_loaded = _load_session_db(path)
    if db_loaded is not None:
        return db_loaded

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ctx = data.get("context", {})
    meta = data.get("_session_meta", {})
    phase = meta.get("current_phase", -1)

    if "idea_id" not in ctx:
        ctx["idea_id"] = meta.get("idea_id") or f"legacy-{os.path.basename(path)}"
    if "production_stage" not in ctx:
        ctx["production_stage"] = meta.get("production_stage") or _phase_to_stage(phase, ctx)
    if "stage_updated_at" not in ctx:
        ctx["stage_updated_at"] = meta.get("stage_updated_at") or meta.get("timestamp", "")
    if "owner_email" not in ctx:
        ctx["owner_email"] = meta.get("owner_email", "")
    ctx["session_path"] = path

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
    db_updated = _update_idea_stage_db(idea_id=idea_id, new_stage=new_stage, user_email=user_email)
    if db_updated is not None:
        return db_updated

    if not idea_id:
        return 0

    now_iso = datetime.now().isoformat()
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
            data.setdefault("_session_meta", {})["stage_updated_at"] = now_iso
            data.setdefault("context", {})["production_stage"] = new_stage
            data.setdefault("context", {})["stage_updated_at"] = now_iso
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
                row["stage_updated_at"] = now_iso
        _save_sessions_index(output_dir, index)

    return updated


def _delete_session_db(path: str, user_email: str = "") -> bool | None:
    """Delete a single Postgres-backed session by synthetic path.

    Returns:
        True/False when DB mode is active, None when DB is unavailable.
    """
    if not path.startswith("db:"):
        return None
    if not _ensure_db_schema():
        return None

    session_key = path[3:]
    if not session_key:
        return False

    try:
        import psycopg  # type: ignore

        with psycopg.connect(_database_url(), autocommit=True) as conn:
            with conn.cursor() as cur:
                if user_email:
                    cur.execute(
                        f"DELETE FROM {SESSIONS_DB_TABLE} WHERE session_key = %s AND user_email = %s",
                        (session_key, user_email),
                    )
                else:
                    cur.execute(
                        f"DELETE FROM {SESSIONS_DB_TABLE} WHERE session_key = %s",
                        (session_key,),
                    )
                return cur.rowcount > 0
    except Exception:
        return False


def delete_session(path: str, output_dir: str = "output", user_email: str = "") -> bool:
    """Delete one saved session (DB or filesystem-backed)."""
    db_deleted = _delete_session_db(path=path, user_email=user_email)
    if db_deleted is not None:
        return db_deleted

    if not path or not os.path.isfile(path):
        return False

    try:
        os.remove(path)
    except OSError:
        return False

    index = _load_sessions_index(output_dir)
    filename = os.path.basename(path)
    index = [
        row for row in index
        if row.get("path") != path and row.get("filename") != filename
    ]
    _save_sessions_index(output_dir, index)
    return True


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
