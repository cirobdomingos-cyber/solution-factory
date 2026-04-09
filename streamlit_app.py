"""Solution Factory — Interactive Streamlit UI.

A step-by-step, guided interface for the multi-agent solution pipeline.
Before Phase 0, a Topic Explorer helps narrow broad domains into specific
angles. After each phase, the app summarizes results, suggests next steps,
and lets you steer the pipeline before continuing.

Run with:
    py -3.12 -m streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
import os
import time
import traceback

import streamlit as st

from agents.topic_explorer import TopicExplorerAgent
from agents.trend_explorer import OnlineTrendExplorerAgent
from agents.trend_researcher import TrendResearchAgent
from agents.market_intel import MarketIntelligenceAgent
from agents.ideator import IdeationAgent
from agents.validator import ValidationAgent
from agents.architect import SolutionArchitectAgent
from agents.execution_planner import ExecutionPlannerAgent
from agents.critic import CriticalReviewAgent
from utils.export import export_results, save_session, list_sessions, load_session, update_idea_stage
from utils.pdf_export import build_pdf_bytes
from utils.trend_metrics import render_exploration_metrics, render_trend_metrics

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _auth_is_configured() -> bool:
    """True if Google OAuth credentials exist in secrets."""
    try:
        return bool(st.secrets.get("auth", {}).get("client_id", ""))
    except Exception:
        return False


def _current_user_email() -> str:
    """Return the logged-in user's email, or empty string if not logged in / no auth."""
    try:
        if st.user.is_logged_in:
            return st.user.email or ""
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Solution Factory",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not os.getenv("ANTHROPIC_API_KEY"):
    st.warning(
        "ANTHROPIC_API_KEY is not set. Add it in Railway Variables so agents can run. "
        "The UI will load, but pipeline calls will fail without this key.",
        icon="⚠️",
    )

# ---------------------------------------------------------------------------
# Login gate — only shown when OAuth is configured
# ---------------------------------------------------------------------------
_AUTH_CONFIGURED = _auth_is_configured()

if _AUTH_CONFIGURED:
    if not st.user.is_logged_in:
        st.markdown("## Solution Factory")
        st.markdown("Sign in to save and access your session history.")
        st.button("Sign in with Google", on_click=st.login, type="primary")
        st.stop()

_USER_EMAIL = _current_user_email()
LIFECYCLE_STAGES = [
    "Backlog",
    "Discovery",
    "Validation",
    "Architecture",
    "Build Plan",
    "Ready for Build",
    "Needs Revision",
    "Parked",
]


def _phase_to_stage(current_phase: int, context: dict) -> str:
    """Map phase index to a user-facing production stage."""
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


def _checkpoint_session(context: dict, current_phase: int) -> None:
    """Persist an incremental checkpoint for long-running sessions."""
    context["production_stage"] = _phase_to_stage(current_phase, context)
    save_session(context, current_phase, user_email=_USER_EMAIL)

# ---------------------------------------------------------------------------
# Phase registry (Phase 0-6, exploration is pre-phase)
# ---------------------------------------------------------------------------
PHASES = [
    {"key": "trend_research",       "label": "Live Trend Research",  "num": 0, "agent_cls": TrendResearchAgent,     "critical": False},
    {"key": "opportunity_discovery", "label": "Opportunity Discovery", "num": 1, "agent_cls": MarketIntelligenceAgent, "critical": True},
    {"key": "ideation",             "label": "Solution Ideation",    "num": 2, "agent_cls": IdeationAgent,           "critical": True},
    {"key": "validation",           "label": "Concept Validation",   "num": 3, "agent_cls": ValidationAgent,         "critical": True},
    {"key": "architecture",         "label": "Solution Architecture","num": 4, "agent_cls": SolutionArchitectAgent,  "critical": True},
    {"key": "execution_planning",   "label": "Execution Planning",   "num": 5, "agent_cls": ExecutionPlannerAgent,   "critical": True},
    {"key": "critical_review",      "label": "Critical Review",      "num": 6, "agent_cls": CriticalReviewAgent,     "critical": True},
]
TOTAL_PHASES = len(PHASES)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
DEFAULTS = {
    "context": {},
    "current_phase": -1,           # -1 = waiting for input
    "history": [],
    # Exploration state
    "step": "prompt",              # "prompt" | "exploring" | "explored" | "pipeline"
    "exploration_angles": [],
    "exploration_paths": [],
    "exploration_domain": "",
    "exploration_mode": "brainstorm",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("Solution Factory")
    st.caption("Step-by-step idea-to-execution pipeline")

    if _AUTH_CONFIGURED and _USER_EMAIL:
        st.divider()
        st.caption(f"Signed in as **{st.user.name}**")
        st.caption(_USER_EMAIL)
        st.button("Sign out", on_click=st.logout, use_container_width=True)

    st.divider()
    st.subheader("Pipeline Progress")
    current = st.session_state.current_phase
    step = st.session_state.step

    # Exploration indicator
    if step in ("exploring", "explored"):
        st.markdown("  **:blue[>> Topic Exploration]**")
    elif step == "pipeline" and current < 0:
        st.markdown("  :green[Topic Exploration]")
    else:
        st.markdown("  :gray[Topic Exploration]")

    for phase in PHASES:
        num = phase["num"]
        label = phase["label"]
        if current >= 0 and num < current + 1:
            st.markdown(f"  :green[Phase {num}: {label}]")
        elif step == "pipeline" and num == current + 1:
            st.markdown(f"  **:blue[>> Phase {num}: {label}]**")
        else:
            st.markdown(f"  :gray[Phase {num}: {label}]")

    st.divider()
    st.subheader("Session History")
    saved_sessions = list_sessions(user_email=_USER_EMAIL)
    if saved_sessions:
        stage_counts: dict[str, int] = {}
        for s in saved_sessions:
            stage = s.get("production_stage", "Unknown")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        st.caption("Ideas by stage")
        for stage, count in sorted(stage_counts.items(), key=lambda x: x[0]):
            st.markdown(f"- {stage}: {count}")

        latest_by_idea: dict[str, dict] = {}
        for session in saved_sessions:
            idea_key = session.get("idea_id") or session.get("filename", "")
            if idea_key and idea_key not in latest_by_idea:
                latest_by_idea[idea_key] = session

        st.divider()
        st.subheader("Production Board")
        stage_filter = st.selectbox(
            "Filter stage",
            ["All"] + LIFECYCLE_STAGES,
            key="production_board_stage_filter",
        )

        board_items = list(latest_by_idea.values())
        if stage_filter != "All":
            board_items = [
                item for item in board_items
                if item.get("production_stage", "Unknown") == stage_filter
            ]

        if board_items:
            for item in board_items[:8]:
                idea_id = item.get("idea_id") or item.get("filename", "")
                current_stage = item.get("production_stage") or "Backlog"
                title = (item.get("user_prompt") or "Untitled idea")[:48]
                st.markdown(f"**{title}**")
                st.caption(f"{idea_id} | {current_stage}")

                move_col, action_col = st.columns([2, 1])
                with move_col:
                    default_idx = LIFECYCLE_STAGES.index(current_stage) if current_stage in LIFECYCLE_STAGES else 0
                    target_stage = st.selectbox(
                        "Move to",
                        LIFECYCLE_STAGES,
                        index=default_idx,
                        key=f"stage_target_{idea_id}",
                        label_visibility="collapsed",
                    )
                with action_col:
                    if st.button("Update", key=f"stage_apply_{idea_id}", use_container_width=True):
                        updated_count = update_idea_stage(
                            idea_id=idea_id,
                            new_stage=target_stage,
                            user_email=_USER_EMAIL,
                        )
                        if updated_count:
                            st.success(f"Updated {updated_count} session(s).")
                        else:
                            st.warning("No matching sessions to update.")
                        st.rerun()
        else:
            st.caption("No ideas in this stage yet.")

    if saved_sessions:
        for s in saved_sessions[:10]:  # cap at 10
            v = s.get("verdict", "")
            color = {"go": "green", "conditional_go": "orange", "no_go": "red"}.get(v, "gray")
            verdict_label = {"go": "GO", "conditional_go": "COND", "no_go": "NO GO"}.get(v, "WIP")
            prompt_preview = (s.get("user_prompt") or "")[:40]
            ts = (s.get("timestamp") or "")[:10]
            stage = s.get("production_stage") or "Unknown"
            with st.expander(f":{color}[{verdict_label}] {prompt_preview}", expanded=False):
                st.caption(ts)
                st.caption(f"Stage: {stage}")
                idea_id = s.get("idea_id") or ""
                if idea_id:
                    st.caption(f"Idea ID: {idea_id}")
                concept = s.get("selected_concept") or ""
                if concept:
                    st.caption(f"Concept: {concept[:60]}")
                score = s.get("score") or 0
                if score:
                    st.caption(f"Score: {score}/10")
                if st.button("Open session", key=f"open_{s['filename']}", use_container_width=True):
                    ctx_loaded, phase_loaded = load_session(s["path"])
                    for k, dv in DEFAULTS.items():
                        st.session_state[k] = dv
                    st.session_state.context = ctx_loaded
                    st.session_state.current_phase = phase_loaded
                    st.session_state.step = "pipeline"
                    st.rerun()
    else:
        st.caption("No saved sessions yet.")

    if step != "prompt":
        st.divider()
        if st.button("Start Over", use_container_width=True):
            for k, v in DEFAULTS.items():
                st.session_state[k] = v
            st.rerun()


# ====================================================================
# Render helpers
# ====================================================================

def render_trends(ctx: dict) -> None:
    """Render Phase 0 trends with metrics dashboard."""
    trends = ctx.get("trends", [])
    if not trends:
        st.warning("No trends found. Continuing with built-in knowledge.")
        return
    
    # Use the new metrics-focused render function
    trends_output = {
        "trends": trends,
        "market_sentiment": ctx.get("market_sentiment", "cautious"),
        "key_takeaway": ctx.get("key_takeaway", ""),
        "domain": ctx.get("user_prompt", "Unknown Domain"),
        "search_queries_used": ctx.get("search_queries_used", []),
    }
    render_trend_metrics(trends_output)


def render_opportunities(ctx: dict) -> None:
    for opp in ctx.get("opportunities", []):
        conf = opp.get("confidence", "?")
        cc = {"high": "green", "medium": "orange", "low": "red"}.get(conf, "gray")
        with st.expander(f"**{opp.get('title', '?')}** — :{cc}[{conf} confidence]"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Domain:** {opp.get('domain', '?')}")
                st.markdown(f"**Target:** {opp.get('target_audience', '?')}")
                st.markdown(f"**Revenue:** {opp.get('revenue_potential', '?')}")
            with c2:
                st.markdown(f"**Timing:** {opp.get('timing_rationale', '?')}")
                st.markdown(f"**Competition:** {opp.get('competition_landscape', '?')}")
            st.markdown(f"**Pain point:** {opp.get('pain_point', '?')}")
            for s in opp.get("market_signals", []):
                st.markdown(f"- {s}")


def render_concepts(ctx: dict) -> None:
    for c in ctx.get("concepts", []):
        with st.expander(f"**{c.get('name', '?')}** — {c.get('one_liner', '')}"):
            st.markdown(f"**Addresses:** {c.get('opportunity_ref', '?')}")
            st.markdown(f"**How it works:** {c.get('how_it_works', '?')}")
            st.markdown(f"**Differentiator:** {c.get('key_differentiator', '?')}")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Monetization:** {c.get('monetization_model', '?')}")
                st.markdown(f"**MVP scope:** {c.get('mvp_scope', '?')}")
            with c2:
                st.markdown(f"**Target user:** {c.get('target_user_persona', '?')}")
                for a in c.get("assumptions", []):
                    st.markdown(f"- {a}")


def render_validation(ctx: dict) -> None:
    for v in ctx.get("validations", []):
        ref = v.get("concept_ref", "?")
        overall = v.get("overall_score", 0)
        rec = v.get("recommendation", "?")
        rc = {"proceed": "green", "pivot": "orange", "kill": "red"}
        with st.expander(f"**{ref}** — {overall:.1f}/10 :{rc.get(rec, 'gray')}[{rec.upper()}]"):
            c1, c2, c3 = st.columns(3)
            with c1:
                mf = v.get("market_fit_score", 0)
                st.metric("Market Fit", f"{mf}/10")
                st.progress(mf / 10)
            with c2:
                fs = v.get("feasibility_score", 0)
                st.metric("Feasibility", f"{fs}/10")
                st.progress(fs / 10)
            with c3:
                rv = v.get("revenue_viability_score", 0)
                st.metric("Revenue Viability", f"{rv}/10")
                st.progress(rv / 10)
            st.markdown(f"**Reasoning:** {v.get('reasoning', '')}")
            c_s, c_w = st.columns(2)
            with c_s:
                for s in v.get("strengths", []):
                    st.markdown(f"- :green[{s}]")
            with c_w:
                for w in v.get("weaknesses", []):
                    st.markdown(f"- :orange[{w}]")
            for r in v.get("killer_risks", []):
                st.error(r)


def render_architecture(ctx: dict) -> None:
    arch = ctx.get("architecture", {})
    st.markdown(f"**Selected concept:** {ctx.get('selected_concept', '?')}")
    st.markdown(f"**Complexity:** {arch.get('estimated_complexity', '?')}")
    st.markdown(arch.get("system_overview", ""))
    roles = arch.get("roles", [])
    if roles:
        st.markdown("### Roles & Agents")
        ai = [r for r in roles if r.get("type") == "ai_agent"]
        hu = [r for r in roles if r.get("type") == "human"]
        hy = [r for r in roles if r.get("type") == "hybrid"]
        c1, c2, c3 = st.columns(3)
        c1.metric("AI Agents", len(ai))
        c2.metric("Human Roles", len(hu))
        c3.metric("Hybrid", len(hy))
        for r in roles:
            rt = r.get("type", "?")
            icon = {"ai_agent": "🤖", "human": "👤", "hybrid": "🔄"}.get(rt, "?")
            with st.expander(f"{icon} **{r.get('title', '?')}** ({rt})"):
                for resp in r.get("responsibilities", []):
                    st.markdown(f"- {resp}")
                st.markdown(f"**Tools:** {', '.join(r.get('tools_needed', []))}")
    stack = arch.get("tech_stack", [])
    if stack:
        st.markdown("### Tech Stack")
        for comp in stack:
            with st.expander(f"**{comp.get('name', '?')}** — {comp.get('technology', '?')}"):
                st.markdown(f"**Purpose:** {comp.get('purpose', '?')}")
                st.markdown(f"**Rationale:** {comp.get('rationale', '?')}")
    df = arch.get("data_flow", "")
    if df:
        st.markdown(f"### Data Flow\n{df}")
    cost = arch.get("cost_structure", "")
    if cost:
        st.markdown(f"### Cost Structure\n{cost}")


def render_execution_plan(ctx: dict) -> None:
    plan = ctx.get("execution_plan", {})
    qw = plan.get("quick_wins", [])
    if qw:
        st.markdown("### Quick Wins (First 48h)")
        for q in qw:
            st.markdown(f"- {q}")
    for i, m in enumerate(plan.get("phases", [])):
        with st.expander(f"**{i+1}. {m.get('name','?')}** — {m.get('estimated_duration','?')}"):
            st.markdown(m.get("description", ""))
            for d in m.get("deliverables", []):
                st.markdown(f"- {d}")
            deps = m.get("dependencies", [])
            if deps:
                st.markdown(f"**Depends on:** {', '.join(deps)}")
            for c in m.get("success_criteria", []):
                st.markdown(f"- {c}")
    crit = plan.get("critical_path", [])
    if crit:
        st.markdown(f"### Critical Path\n{' → '.join(crit)}")
    mits = plan.get("risk_mitigations", {})
    if mits:
        st.markdown("### Risk Mitigations")
        for risk, mit in mits.items():
            st.markdown(f"- **{risk}:** {mit}")


def render_critical_review(ctx: dict) -> None:
    review = ctx.get("critical_review", {})
    score = review.get("score", 0)
    verdict = review.get("go_no_go", "?")
    viability = review.get("overall_viability", "?")
    vc = {"go": ("success", "GO"), "conditional_go": ("warning", "CONDITIONAL GO"), "no_go": ("error", "NO GO")}
    mt, vt = vc.get(verdict, ("info", verdict.upper()))
    getattr(st, mt)(f"**{vt}** — Score: {score}/10 | Viability: {viability}")
    final = review.get("final_verdict", "")
    if final:
        st.markdown(final)
    c1, c2 = st.columns(2)
    with c1:
        for s in review.get("strongest_elements", []):
            st.markdown(f"- :green[{s}]")
    with c2:
        for b in review.get("blind_spots", []):
            st.markdown(f"- :orange[{b}]")
    for f in review.get("fatal_flaws", []):
        st.error(f)
    for c in review.get("conditions", []):
        st.warning(c)


RENDERERS = {
    "trend_research": render_trends,
    "opportunity_discovery": render_opportunities,
    "ideation": render_concepts,
    "validation": render_validation,
    "architecture": render_architecture,
    "execution_planning": render_execution_plan,
    "critical_review": render_critical_review,
}


# ====================================================================
# Phase summaries
# ====================================================================

def summarize_trend_research(ctx: dict) -> str:
    trends = ctx.get("trends", [])
    sentiment = ctx.get("market_sentiment", "unknown")
    takeaway = ctx.get("key_takeaway", "")
    if not trends:
        return "No live trends found. Continuing with built-in knowledge."
    titles = ", ".join(t.get("title", "?") for t in trends[:3])
    return (
        f"Found **{len(trends)} trends** — sentiment: **{sentiment}**.\n\n"
        f"Top trends: {titles}\n\n"
        f"Key takeaway: *{takeaway}*"
    )

def summarize_opportunities(ctx: dict) -> str:
    opps = ctx.get("opportunities", [])
    if not opps:
        return "No opportunities identified."
    lines = [f"- **{o.get('title','?')}** ({o.get('confidence','?')}) — {o.get('pain_point','')[:100]}" for o in opps]
    return f"Identified **{len(opps)} opportunities:**\n\n" + "\n".join(lines)

def summarize_ideation(ctx: dict) -> str:
    concepts = ctx.get("concepts", [])
    if not concepts:
        return "No concepts generated."
    lines = [f"- **{c.get('name','?')}** — {c.get('one_liner','')}" for c in concepts]
    return f"Generated **{len(concepts)} concepts:**\n\n" + "\n".join(lines)

def summarize_validation(ctx: dict) -> str:
    vals = ctx.get("validations", [])
    if not vals:
        return "No validation results."
    best = max(vals, key=lambda v: v.get("overall_score", 0))
    lines = [f"- **{v.get('concept_ref','?')}** — {v.get('overall_score',0):.1f}/10 ({v.get('recommendation','?')})" for v in vals]
    return "\n".join(lines) + f"\n\nBest: **{best.get('concept_ref','?')}** at {best.get('overall_score',0):.1f}/10"

def summarize_architecture(ctx: dict) -> str:
    arch = ctx.get("architecture", {})
    roles = arch.get("roles", [])
    ai_n = sum(1 for r in roles if r.get("type") == "ai_agent")
    hu_n = sum(1 for r in roles if r.get("type") == "human")
    return (
        f"Architecture for **{ctx.get('selected_concept','?')}** — "
        f"{len(roles)} roles ({ai_n} AI, {hu_n} human), "
        f"complexity: {arch.get('estimated_complexity','?')}"
    )

def summarize_execution_plan(ctx: dict) -> str:
    plan = ctx.get("execution_plan", {})
    phases = plan.get("phases", [])
    crit = plan.get("critical_path", [])
    return f"**{len(phases)} milestones** — Critical path: {' → '.join(crit[:4])}"

def summarize_critical_review(ctx: dict) -> str:
    review = ctx.get("critical_review", {})
    return f"**{review.get('go_no_go','?').upper()}** — Score: {review.get('score',0)}/10"

SUMMARIZERS = {
    "trend_research": summarize_trend_research,
    "opportunity_discovery": summarize_opportunities,
    "ideation": summarize_ideation,
    "validation": summarize_validation,
    "architecture": summarize_architecture,
    "execution_planning": summarize_execution_plan,
    "critical_review": summarize_critical_review,
}


# ====================================================================
# Next-step options per phase
# ====================================================================

def get_next_options(phase_key: str, ctx: dict) -> list[dict]:
    next_idx = next((i for i, p in enumerate(PHASES) if p["key"] == phase_key), -1) + 1
    next_label = PHASES[next_idx]["label"] if next_idx < TOTAL_PHASES else None
    options = []

    if phase_key == "trend_research":
        options.append({"label": f"Continue to {next_label}", "action": "next", "type": "primary",
                        "help": "Feed trends into Market Intelligence for grounded analysis."})
        options.append({"label": "Skip trends & continue", "action": "skip_trends", "type": "secondary",
                        "help": "Clear trends, use only built-in knowledge."})
        options.append({"label": "Re-run trend research", "action": "rerun", "type": "secondary",
                        "help": "Search again with different focus."})

    elif phase_key == "opportunity_discovery":
        n = len(ctx.get("opportunities", []))
        options.append({"label": f"Continue to {next_label}", "action": "next", "type": "primary",
                        "help": f"Generate concepts for {n} opportunities."})
        options.append({"label": "Re-run with guidance", "action": "rerun", "type": "secondary",
                        "help": "Steer the analysis differently."})

    elif phase_key == "ideation":
        n = len(ctx.get("concepts", []))
        options.append({"label": f"Continue to {next_label}", "action": "next", "type": "primary",
                        "help": f"Stress-test {n} concepts."})
        options.append({"label": "Generate more concepts", "action": "rerun", "type": "secondary",
                        "help": "Explore different angles."})

    elif phase_key == "validation":
        vals = ctx.get("validations", [])
        best = max(vals, key=lambda v: v.get("overall_score", 0)) if vals else {}
        options.append({"label": f"Continue to {next_label}", "action": "next", "type": "primary",
                        "help": f"Architect the best concept ({best.get('recommendation','?')})."})
        if any(v.get("recommendation") == "kill" for v in vals):
            options.append({"label": "Back to Ideation", "action": "back_to_ideation", "type": "secondary",
                            "help": "Generate new concepts using validator feedback."})
        options.append({"label": "Re-validate", "action": "rerun", "type": "secondary",
                        "help": "Add context the validator missed."})

    elif phase_key == "architecture":
        options.append({"label": f"Continue to {next_label}", "action": "next", "type": "primary",
                        "help": "Create milestones and timeline."})
        options.append({"label": "Re-architect", "action": "rerun", "type": "secondary",
                        "help": "Add budget/team/tech constraints."})

    elif phase_key == "execution_planning":
        options.append({"label": f"Continue to {next_label}", "action": "next", "type": "primary",
                        "help": "Final review and verdict."})
        options.append({"label": "Adjust plan", "action": "rerun", "type": "secondary",
                        "help": "Add constraints."})

    elif phase_key == "critical_review":
        review = ctx.get("critical_review", {})
        verdict = review.get("go_no_go", "?")
        if verdict == "no_go":
            options.append({"label": "Re-run with feedback", "action": "restart_with_feedback", "type": "primary",
                            "help": "Feed critic issues back for a second iteration."})
        options.append({"label": "Export results", "action": "export",
                        "type": "primary" if verdict != "no_go" else "secondary",
                        "help": "Save full output as JSON."})
        options.append({"label": "New idea", "action": "reset", "type": "secondary",
                        "help": "Start fresh."})

    return options


# ====================================================================
# Run a single phase
# ====================================================================

def run_single_phase(phase_idx: int, ctx: dict, user_notes: str = "") -> dict:
    phase = PHASES[phase_idx]
    agent = phase["agent_cls"]()

    if user_notes.strip():
        ctx["user_guidance"] = user_notes.strip()

    with st.status(f"Phase {phase['num']}: {phase['label']} — running...", expanded=True) as status:
        st.caption(f"Agent: **{agent.name}** | Model: `{agent.model}`")
        start = time.time()
        try:
            result = agent.run(ctx)
            ctx.update(result)
            elapsed = time.time() - start
            status.update(label=f"Phase {phase['num']}: {phase['label']} — {elapsed:.1f}s",
                          state="complete", expanded=False)
        except Exception as e:
            elapsed = time.time() - start
            status.update(label=f"Phase {phase['num']}: {phase['label']} — FAILED ({elapsed:.1f}s)",
                          state="error")
            st.error(f"**{agent.name}** failed: {e}")
            st.code(traceback.format_exc(), language="text")
            if not phase["critical"]:
                if phase["key"] == "trend_research":
                    ctx.update({"trends": [], "market_sentiment": "unknown", "key_takeaway": ""})
            else:
                ctx["_phase_failed"] = True
    return ctx


def score_exploration_path(path: dict) -> dict:
    """Compute a compact why-this-path score for fast selection decisions."""
    momentum = str(path.get("momentum", "warm")).lower()
    momentum_score = {"hot": 3, "warm": 2, "cool": 1}.get(momentum, 1)

    combined_text = " ".join([
        str(path.get("opportunity_hypothesis", "")),
        str(path.get("why_now", "")),
        " ".join(path.get("source_signals", []) or []),
    ]).lower()

    pain_keywords = {
        "pain", "problem", "complaint", "cost", "wait", "shortage", "burnout",
        "dropout", "churn", "risk", "compliance", "inefficiency", "friction",
    }
    pain_hits = sum(1 for kw in pain_keywords if kw in combined_text)
    buyer_pain_score = 3 if pain_hits >= 3 else 2 if pain_hits >= 1 else 1

    feasibility_text = (
        f"{path.get('mid_area', '')} {path.get('narrow_area', '')} "
        f"{path.get('opportunity_hypothesis', '')}"
    ).lower()
    low_feasibility_terms = {
        "drug", "biotech", "clinical trial", "implant", "hardware", "medical device"
    }
    high_feasibility_terms = {
        "saas", "workflow", "platform", "automation", "assistant", "analytics", "copilot"
    }
    if any(term in feasibility_text for term in low_feasibility_terms):
        feasibility_score = 1
    elif any(term in feasibility_text for term in high_feasibility_terms):
        feasibility_score = 3
    else:
        feasibility_score = 2

    total = momentum_score + buyer_pain_score + feasibility_score
    return {
        "momentum": momentum_score,
        "buyer_pain": buyer_pain_score,
        "feasibility": feasibility_score,
        "total": total,
    }


# ====================================================================
# Trending helper
# ====================================================================

@st.cache_data(ttl=3600)
def get_trending_topics() -> list[dict]:
    """Fetch what's trending across domains (cached for 1 hour).
    
    Returns list of dicts with keys: title, why_trending, signal.
    """
    trending = [
        {
            "title": "AI-Powered Supply Chain Optimization",
            "why_trending": "Post-pandemic logistics consolidation + efficiency pressure.",
            "signal": "📦 Tech + Operations",
        },
        {
            "title": "Mental Health in Enterprise",
            "why_trending": "Burnout + regulatory pressure + insurance mandates.",
            "signal": "💼 Health + Work",
        },
        {
            "title": "Biotech Data Infrastructure",
            "why_trending": "AI-driven drug discovery requires massive biomarker pipelines.",
            "signal": "🧬 AI + Biology",
        },
        {
            "title": "Fintech for Emerging Markets",
            "why_trending": "Mobile-first payments + stablecoins for unbanked populations.",
            "signal": "💰 Mobile + Finance",
        },
        {
            "title": "Autonomous Delivery Networks",
            "why_trending": "Last-mile robotics solves labor shortage + cost crisis.",
            "signal": "🤖 Robotics + Logistics",
        },
    ]
    return trending


# ====================================================================
# Main UI
# ====================================================================

st.markdown("# Solution Factory")

step = st.session_state.step

# ------------------------------------------------------------------
# STEP 1: Prompt input
# ------------------------------------------------------------------
if step == "prompt":
    st.markdown("## Discover & Explore")
    st.markdown("Enter a domain, idea, or problem. Or pick what's trending now.")

    # Trending Now section
    st.markdown("### 🔥 Trending Now")
    st.caption("Click any topic to auto-populate the form")

    trending_topics = get_trending_topics()
    trending_cols = st.columns(len(trending_topics))

    for col, trend in zip(trending_cols, trending_topics):
        with col:
            if st.button(
                f"{trend['title']}",
                key=f"trending_{trend['title']}",
                use_container_width=True,
                help=trend["why_trending"],
            ):
                st.session_state.context = {
                    "user_prompt": trend["title"].strip(),
                    "production_stage": "Backlog",
                    "exploration_mode": "online_trends",
                    "owner_email": _USER_EMAIL,
                }
                st.session_state.exploration_mode = "online_trends"
                st.session_state.step = "exploring"
                st.rerun()
            st.caption(f"{trend['signal']}")

    st.divider()
    st.markdown("### Or Explore Your Own")

    with st.form("prompt_form"):
        exploration_mode = st.radio(
            "Exploration mode",
            options=["brainstorm", "online_trends"],
            format_func=lambda v: (
                "Fast brainstorming (LLM ideation)"
                if v == "brainstorm"
                else "Live online trend scan (broad to narrow)"
            ),
            help="Online trend scan uses live web search to propose exploration paths from broad areas to narrow niches.",
            horizontal=True,
            key="exploration_mode_input",
        )
        user_prompt = st.text_area(
            "What domain do you want to explore?",
            placeholder="e.g. health and wellbeing, AI in logistics, fintech for freelancers...",
            height=100,
            max_chars=5000,
        )
        submitted = st.form_submit_button("Explore Topics", type="primary", use_container_width=True)

    if submitted and user_prompt.strip():
        st.session_state.context = {
            "user_prompt": user_prompt.strip(),
            "production_stage": "Backlog",
            "exploration_mode": exploration_mode,
            "owner_email": _USER_EMAIL,
        }
        st.session_state.exploration_mode = exploration_mode
        st.session_state.step = "exploring"
        st.rerun()
    elif submitted:
        st.warning("Enter a domain or idea first.")
    st.stop()

# ------------------------------------------------------------------
# STEP 2: Topic Exploration (runs agent, then shows results)
# ------------------------------------------------------------------
if step == "exploring":
    ctx = st.session_state.context
    exploration_mode = ctx.get("exploration_mode", st.session_state.exploration_mode)
    st.markdown(f"> **Domain:** {ctx['user_prompt']}")
    st.divider()

    status_text = (
        "Scanning live trends and generating broad-to-narrow paths..."
        if exploration_mode == "online_trends"
        else "Exploring topic angles..."
    )

    with st.status(status_text, expanded=True) as status:
        if exploration_mode == "online_trends":
            agent = OnlineTrendExplorerAgent()
            st.caption(f"Agent: **{agent.name}** | Model: `{agent.model}` (live web trend scan)")
        else:
            agent = TopicExplorerAgent()
            st.caption(f"Agent: **{agent.name}** | Model: `{agent.model}` (fast brainstorming)")
        start = time.time()
        try:
            result = agent.run(ctx)
            ctx.update(result)
            st.session_state.context = ctx
            st.session_state.exploration_angles = result.get("exploration_angles", [])
            st.session_state.exploration_paths = result.get("exploration_paths", [])
            st.session_state.exploration_domain = result.get("exploration_domain", ctx["user_prompt"])
            # Store full exploration output for metrics rendering
            st.session_state.exploration_output = {
                "exploration_domain": result.get("exploration_domain", ""),
                "broad_areas": result.get("broad_areas", []),
                "exploration_paths": result.get("exploration_paths", []),
            }
            elapsed = time.time() - start
            status.update(label=f"Topic exploration — {elapsed:.1f}s", state="complete", expanded=False)
            st.session_state.step = "explored"
            st.rerun()
        except Exception as e:
            elapsed = time.time() - start
            status.update(label=f"Topic exploration — FAILED ({elapsed:.1f}s)", state="error")
            st.error(f"**Topic Explorer** failed: {e}")
            st.code(traceback.format_exc(), language="text")
            # Allow skipping exploration on failure
            if st.button("Skip exploration, go straight to trend research"):
                st.session_state.step = "pipeline"
                st.session_state.current_phase = -1
                st.rerun()
    st.stop()

# ------------------------------------------------------------------
# STEP 3: Show exploration results, let user pick angles
# ------------------------------------------------------------------
if step == "explored":
    ctx = st.session_state.context
    exploration_mode = ctx.get("exploration_mode", st.session_state.exploration_mode)
    angles = st.session_state.exploration_angles
    paths = st.session_state.exploration_paths
    domain = st.session_state.exploration_domain

    st.markdown(f"> **Domain:** {ctx['user_prompt']}")
    st.divider()

    st.subheader("Topic Exploration")

    if exploration_mode == "online_trends":
        st.markdown(
            f"I found **{len(paths)} broad-to-narrow paths** based on live online signals in **{domain}**. "
            "Pick the paths you want to investigate first."
        )
        # Render metrics dashboard for exploration paths
        exploration_output = st.session_state.get("exploration_output", {})
        if exploration_output:
            render_exploration_metrics(exploration_output)
    else:
        st.markdown(
            f"I found **{len(angles)} angles** to explore in **{domain}**. "
            f"Select the ones that interest you — these will focus the trend research."
        )

    selected_labels = []

    if exploration_mode == "online_trends":
        grouped_paths: dict[str, list[tuple[int, dict]]] = {}
        for idx, path in enumerate(paths):
            broad = path.get("broad_area", "Other")
            grouped_paths.setdefault(broad, []).append((idx, path))

        MOMENTUM_COLORS = {"hot": "red", "warm": "orange", "cool": "blue"}

        for broad, broad_paths in grouped_paths.items():
            st.markdown(f"### 🌐 {broad}")
            for idx, path in broad_paths:
                mid = path.get("mid_area", "?")
                narrow = path.get("narrow_area", "?")
                momentum = path.get("momentum", "warm")
                momentum_color = MOMENTUM_COLORS.get(momentum, "gray")

                label = f"{broad} -> {mid} -> {narrow}"
                score = score_exploration_path(path)
                col_check, col_content, col_score = st.columns([0.05, 0.75, 0.20])
                with col_check:
                    checked = st.checkbox(
                        label,
                        key=f"path_{idx}",
                        label_visibility="collapsed",
                    )
                with col_content:
                    st.markdown(f"**{mid} -> {narrow}** :{momentum_color}[{momentum}]")
                    hypothesis = path.get("opportunity_hypothesis", "")
                    why_now = path.get("why_now", "")
                    if hypothesis:
                        st.markdown(f"**Opportunity hypothesis:** {hypothesis}")
                    if why_now:
                        st.markdown(f"**Why now:** {why_now}")

                    signals = path.get("source_signals", [])
                    queries = path.get("starter_queries", [])
                    if signals or queries:
                        with st.expander("Signals and starter queries"):
                            for s in signals:
                                st.markdown(f"- {s}")
                            if queries:
                                st.markdown("**Starter queries**")
                                for q in queries:
                                    st.markdown(f"- {q}")
                with col_score:
                    st.markdown("**Why this path**")
                    st.caption(
                        " | ".join(
                            [
                                f"M {score['momentum']}/3",
                                f"Pain {score['buyer_pain']}/3",
                                f"Build {score['feasibility']}/3",
                            ]
                        )
                    )
                    st.metric("Total", f"{score['total']}/9")

                if checked:
                    selected_labels.append(label)
    else:
        # Group angles by category
        categories: dict[str, list] = {}
        for angle in angles:
            cat = angle.get("category", "other")
            categories.setdefault(cat, []).append(angle)

        CATEGORY_ICONS = {
            "technology": "💡", "audience": "👥", "pain_point": "🎯",
            "business_model": "💰", "regulation": "📋", "emerging_niche": "🌱",
        }
        HEAT_COLORS = {"hot": "red", "warm": "orange", "cool": "blue"}

        for cat, cat_angles in categories.items():
            icon = CATEGORY_ICONS.get(cat, "📌")
            st.markdown(f"### {icon} {cat.replace('_', ' ').title()}")

            for angle in cat_angles:
                title = angle.get("title", "?")
                desc = angle.get("description", "")
                heat = angle.get("heat_level", "warm")
                heat_color = HEAT_COLORS.get(heat, "gray")
                questions = angle.get("example_questions", [])

                col_check, col_content = st.columns([0.05, 0.95])
                with col_check:
                    checked = st.checkbox(
                        title,
                        key=f"angle_{title}",
                        label_visibility="collapsed",
                    )
                with col_content:
                    st.markdown(f"**{title}** :{heat_color}[{heat}]")
                    st.markdown(desc)
                    if questions:
                        with st.expander("Research questions"):
                            for q in questions:
                                st.markdown(f"- {q}")

                if checked:
                    selected_labels.append(title)

    st.divider()

    # Custom angle input
    custom_angle = st.text_input(
        "Add your own angle (optional)",
        placeholder="e.g. wearable devices for elderly fall detection",
        key="custom_angle",
    )

    # Summary of selection
    if selected_labels or custom_angle.strip():
        n_selected = len(selected_labels) + (1 if custom_angle.strip() else 0)
        st.info(f"**{n_selected} angle(s) selected.** These will focus the trend research.")

    st.divider()
    st.subheader("Ready to proceed?")
    st.markdown("Choose how to continue:")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Research selected areas", type="primary", use_container_width=True,
                      help="Run live trend research focused on your selected angles."):
            # Build focused prompt from selections
            focus_parts = list(selected_labels)
            if custom_angle.strip():
                focus_parts.append(custom_angle.strip())

            if focus_parts:
                focused_prompt = (
                    f"{ctx['user_prompt']} — specifically focusing on: {'; '.join(focus_parts)}"
                )
            else:
                focused_prompt = ctx["user_prompt"]

            ctx["user_prompt"] = focused_prompt
            ctx["selected_exploration_angles"] = list(selected_labels)
            if custom_angle.strip():
                ctx["selected_exploration_angles"].append(custom_angle.strip())
            st.session_state.context = ctx
            st.session_state.step = "pipeline"
            st.session_state.current_phase = -1
            st.rerun()

    with col2:
        if st.button("Explore more", use_container_width=True,
                      help="Re-run the topic explorer for different suggestions."):
            st.session_state.step = "exploring"
            st.rerun()

    with col3:
        if st.button("Skip to pipeline", use_container_width=True,
                      help="Skip trend research entirely, go straight to opportunity discovery."):
            ctx.update({"trends": [], "market_sentiment": "unknown", "key_takeaway": ""})
            st.session_state.context = ctx
            st.session_state.step = "pipeline"
            st.session_state.current_phase = 0  # skip phase 0, start at phase 1
            st.rerun()

    st.stop()


# ------------------------------------------------------------------
# STEP 4: Pipeline execution (phase-by-phase)
# ------------------------------------------------------------------
assert step == "pipeline"
ctx = st.session_state.context

st.markdown(f"> **Prompt:** {ctx.get('user_prompt', '')}")

# Show selected exploration angles if any
sel_angles = ctx.get("selected_exploration_angles", [])
if sel_angles:
    st.caption(f"Focus areas: {', '.join(sel_angles)}")
st.divider()

next_phase_idx = st.session_state.current_phase + 1

# Auto-run phase 0 when entering pipeline mode
if next_phase_idx == 0:
    ctx = run_single_phase(0, ctx)
    st.session_state.context = ctx
    if not ctx.pop("_phase_failed", False):
        st.session_state.current_phase = 0
        try:
            _checkpoint_session(ctx, 0)
        except Exception:
            pass
    st.rerun()

# -- Show completed phases as collapsed sections --
for i in range(next_phase_idx):
    phase = PHASES[i]
    renderer = RENDERERS.get(phase["key"])
    summarizer = SUMMARIZERS.get(phase["key"])
    summary = summarizer(ctx) if summarizer else ""

    with st.expander(f"Phase {phase['num']}: {phase['label']} — {summary[:80]}", expanded=False):
        if renderer:
            renderer(ctx)

# -- Current phase results + next steps --
if 0 <= st.session_state.current_phase < TOTAL_PHASES:
    current_phase = PHASES[st.session_state.current_phase]
    summarizer = SUMMARIZERS.get(current_phase["key"])

    st.divider()
    st.subheader(f"Phase {current_phase['num']} Complete: {current_phase['label']}")

    if summarizer:
        st.markdown(summarizer(ctx))

    renderer = RENDERERS.get(current_phase["key"])
    if renderer:
        with st.expander("View full details", expanded=True):
            renderer(ctx)

    # Next steps
    st.divider()
    st.subheader("What's next?")

    options = get_next_options(current_phase["key"], ctx)

    if next_phase_idx < TOTAL_PHASES:
        next_p = PHASES[next_phase_idx]
        st.markdown(
            f"Next phase: **Phase {next_p['num']}: {next_p['label']}**. "
            f"Proceed, re-run, or add guidance."
        )

    user_notes = st.text_area(
        "Add guidance for the next phase (optional)",
        placeholder="e.g. Focus on B2B, budget is $5k, prefer Python stack...",
        height=80,
        key=f"notes_{current_phase['key']}",
    )

    cols = st.columns(len(options))
    for col, opt in zip(cols, options):
        with col:
            clicked = st.button(
                opt["label"], help=opt.get("help", ""),
                type=opt.get("type", "secondary"),
                use_container_width=True,
                key=f"btn_{current_phase['key']}_{opt['action']}",
            )
            if clicked:
                action = opt["action"]

                if action == "next" and next_phase_idx < TOTAL_PHASES:
                    ctx = run_single_phase(next_phase_idx, ctx, user_notes)
                    st.session_state.context = ctx
                    if not ctx.pop("_phase_failed", False):
                        st.session_state.current_phase = next_phase_idx
                        try:
                            _checkpoint_session(ctx, next_phase_idx)
                        except Exception:
                            pass
                    st.rerun()

                elif action == "rerun":
                    ctx = run_single_phase(st.session_state.current_phase, ctx, user_notes)
                    st.session_state.context = ctx
                    failed = ctx.pop("_phase_failed", None)
                    if not failed and st.session_state.current_phase >= 0:
                        try:
                            _checkpoint_session(ctx, st.session_state.current_phase)
                        except Exception:
                            pass
                    st.rerun()

                elif action == "skip_trends":
                    ctx.update({"trends": [], "market_sentiment": "unknown", "key_takeaway": ""})
                    st.session_state.context = ctx
                    ctx = run_single_phase(next_phase_idx, ctx, user_notes)
                    st.session_state.context = ctx
                    if not ctx.pop("_phase_failed", False):
                        st.session_state.current_phase = next_phase_idx
                        try:
                            _checkpoint_session(ctx, next_phase_idx)
                        except Exception:
                            pass
                    st.rerun()

                elif action == "back_to_ideation":
                    vals = ctx.get("validations", [])
                    feedback = []
                    for v in vals:
                        rec = v.get("recommendation", "")
                        if rec in ("kill", "pivot"):
                            feedback.append(f"{rec.upper()}: {v.get('concept_ref','?')}: {v.get('reasoning','')}")
                    ctx["validation_feedback"] = feedback
                    ctx = run_single_phase(2, ctx, user_notes)
                    st.session_state.context = ctx
                    if not ctx.pop("_phase_failed", False):
                        st.session_state.current_phase = 2
                        try:
                            _checkpoint_session(ctx, 2)
                        except Exception:
                            pass
                    st.rerun()

                elif action == "restart_with_feedback":
                    review = ctx.get("critical_review", {})
                    ctx["critic_feedback"] = review.get("recommended_changes", [])
                    ctx["fatal_flaws"] = review.get("fatal_flaws", [])
                    ctx = run_single_phase(1, ctx, user_notes)
                    st.session_state.context = ctx
                    if not ctx.pop("_phase_failed", False):
                        st.session_state.current_phase = 1
                        try:
                            _checkpoint_session(ctx, 1)
                        except Exception:
                            pass
                    st.rerun()

                elif action == "export":
                    filepath = export_results(ctx)
                    session_path = save_session(ctx, st.session_state.current_phase, user_email=_USER_EMAIL)
                    st.success(f"Exported to `{filepath}` — session saved for history.")
                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        st.download_button(
                            "Download JSON",
                            data=json.dumps(ctx, indent=2, ensure_ascii=False, default=str),
                            file_name="solution_factory_result.json",
                            mime="application/json",
                            key="download_final_json",
                        )
                    with dl_col2:
                        try:
                            pdf_bytes = build_pdf_bytes(ctx)
                            st.download_button(
                                "Download PDF",
                                data=pdf_bytes,
                                file_name="solution_factory_report.pdf",
                                mime="application/pdf",
                                key="download_final_pdf",
                            )
                        except Exception as pdf_err:
                            st.warning(f"PDF generation failed: {pdf_err}")

                elif action == "reset":
                    for k, v in DEFAULTS.items():
                        st.session_state[k] = v
                    st.rerun()
