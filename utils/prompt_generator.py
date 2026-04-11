"""Claude Code prompt generator — converts pipeline output into an actionable dev brief.

After the full pipeline runs (phases 0-6), this module takes the accumulated
context and builds a comprehensive, copy-pasteable prompt that a developer
can send to Claude Code to start building the project.

The prompt follows a structured format:
1. Project overview and business context
2. Selected concept and validation summary
3. Architecture and tech stack
4. Execution plan with milestones
5. Constraints and risk mitigations
6. Explicit first-steps instructions
"""

from __future__ import annotations


def build_claude_code_prompt(ctx: dict) -> str:
    """Build a comprehensive Claude Code development prompt from pipeline context.

    Args:
        ctx: The full pipeline context dict accumulated across all phases.

    Returns:
        A ready-to-paste prompt string for Claude Code.
    """
    sections = []

    # --- Header ---
    sections.append(_build_header(ctx))

    # --- Business Context ---
    sections.append(_build_business_context(ctx))

    # --- Selected Concept ---
    sections.append(_build_concept_section(ctx))

    # --- Architecture ---
    sections.append(_build_architecture_section(ctx))

    # --- Execution Plan ---
    sections.append(_build_execution_section(ctx))

    # --- Constraints & Risks ---
    sections.append(_build_constraints_section(ctx))

    # --- Critical Review Notes ---
    sections.append(_build_review_notes(ctx))

    # --- Actionable First Steps ---
    sections.append(_build_first_steps(ctx))

    # --- Footer ---
    sections.append(_build_footer())

    return "\n\n".join(s for s in sections if s)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_header(ctx: dict) -> str:
    concept = ctx.get("selected_concept", "")
    domain = ctx.get("user_prompt", "")
    return f"""# Project Development Brief — {concept or domain}

You are about to build a complete project based on a validated idea that went
through a 7-phase analysis pipeline (market research, ideation, validation,
architecture, execution planning, and critical review). Everything below is
the output of that analysis. Use it as your single source of truth for what
to build, how to build it, and in what order."""


def _build_business_context(ctx: dict) -> str:
    lines = ["## Business Context"]

    domain = ctx.get("user_prompt", "")
    if domain:
        lines.append(f"\n**Domain/Idea:** {domain}")

    # Best opportunity
    opps = ctx.get("opportunities", [])
    if opps:
        best_opp = opps[0]
        lines.append(f"\n**Target Audience:** {best_opp.get('target_audience', 'N/A')}")
        lines.append(f"**Pain Point:** {best_opp.get('pain_point', 'N/A')}")
        lines.append(f"**Revenue Model:** {best_opp.get('revenue_potential', 'N/A')}")
        lines.append(f"**Timing Rationale:** {best_opp.get('timing_rationale', 'N/A')}")
        lines.append(f"**Competition:** {best_opp.get('competition_landscape', 'N/A')}")

        signals = best_opp.get("market_signals", [])
        if signals:
            lines.append("\n**Key Market Signals:**")
            for s in signals[:5]:
                lines.append(f"- {s}")

    # Trends summary
    trends = ctx.get("trends", [])
    if trends:
        lines.append(f"\n**Market Sentiment:** {ctx.get('market_sentiment', 'N/A')}")
        lines.append(f"**Key Takeaway:** {ctx.get('key_takeaway', 'N/A')}")

    return "\n".join(lines)


def _build_concept_section(ctx: dict) -> str:
    lines = ["## Selected Concept"]

    concept_name = ctx.get("selected_concept", "")
    concepts = ctx.get("concepts", [])

    # Find the selected concept or use the best one
    selected = None
    for c in concepts:
        if c.get("name") == concept_name:
            selected = c
            break
    if not selected and concepts:
        selected = concepts[0]

    if not selected:
        lines.append("\nNo concept data available.")
        return "\n".join(lines)

    lines.append(f"\n**Name:** {selected.get('name', 'N/A')}")
    lines.append(f"**One-liner:** {selected.get('one_liner', 'N/A')}")
    lines.append(f"**How it works:** {selected.get('how_it_works', 'N/A')}")
    lines.append(f"**Key Differentiator:** {selected.get('key_differentiator', 'N/A')}")
    lines.append(f"**Monetization:** {selected.get('monetization_model', 'N/A')}")
    lines.append(f"**MVP Scope:** {selected.get('mvp_scope', 'N/A')}")
    lines.append(f"**Target User:** {selected.get('target_user_persona', 'N/A')}")

    assumptions = selected.get("assumptions", [])
    if assumptions:
        lines.append("\n**Core Assumptions (must hold true):**")
        for a in assumptions:
            lines.append(f"- {a}")

    # Validation scores
    vals = ctx.get("validations", [])
    if vals:
        best_val = max(vals, key=lambda v: v.get("overall_score", 0))
        lines.append(f"\n**Validation Score:** {best_val.get('overall_score', 0):.1f}/10")
        lines.append(f"- Market Fit: {best_val.get('market_fit_score', 0)}/10")
        lines.append(f"- Feasibility: {best_val.get('feasibility_score', 0)}/10")
        lines.append(f"- Revenue Viability: {best_val.get('revenue_viability_score', 0)}/10")

        strengths = best_val.get("strengths", [])
        if strengths:
            lines.append("\n**Strengths:**")
            for s in strengths:
                lines.append(f"- {s}")

        weaknesses = best_val.get("weaknesses", [])
        if weaknesses:
            lines.append("\n**Weaknesses to address:**")
            for w in weaknesses:
                lines.append(f"- {w}")

    return "\n".join(lines)


def _build_architecture_section(ctx: dict) -> str:
    arch = ctx.get("architecture", {})
    if not arch:
        return ""

    lines = ["## Architecture"]

    overview = arch.get("system_overview", "")
    if overview:
        lines.append(f"\n{overview}")

    lines.append(f"\n**Complexity:** {arch.get('estimated_complexity', 'N/A')}")

    # Tech stack
    stack = arch.get("tech_stack", [])
    if stack:
        lines.append("\n### Tech Stack")
        for comp in stack:
            name = comp.get("name", "?")
            tech = comp.get("technology", "?")
            purpose = comp.get("purpose", "")
            rationale = comp.get("rationale", "")
            lines.append(f"\n**{name}:** {tech}")
            if purpose:
                lines.append(f"  - Purpose: {purpose}")
            if rationale:
                lines.append(f"  - Why: {rationale}")
            alts = comp.get("alternatives", [])
            if alts:
                lines.append(f"  - Alternatives considered: {', '.join(alts)}")

    # Roles
    roles = arch.get("roles", [])
    if roles:
        lines.append("\n### Roles & Agents")
        for r in roles:
            title = r.get("title", "?")
            rtype = r.get("type", "?")
            lines.append(f"\n**{title}** ({rtype})")
            for resp in r.get("responsibilities", []):
                lines.append(f"  - {resp}")
            tools = r.get("tools_needed", [])
            if tools:
                lines.append(f"  - Tools: {', '.join(tools)}")

    # Data flow
    df = arch.get("data_flow", "")
    if df:
        lines.append(f"\n### Data Flow\n{df}")

    # Cost
    cost = arch.get("cost_structure", "")
    if cost:
        lines.append(f"\n### Cost Structure\n{cost}")

    return "\n".join(lines)


def _build_execution_section(ctx: dict) -> str:
    plan = ctx.get("execution_plan", {})
    if not plan:
        return ""

    lines = ["## Execution Plan"]

    # Quick wins
    qw = plan.get("quick_wins", [])
    if qw:
        lines.append("\n### Quick Wins (do these first)")
        for q in qw:
            lines.append(f"- {q}")

    # Milestones
    phases = plan.get("phases", [])
    if phases:
        lines.append("\n### Milestones")
        for i, m in enumerate(phases, 1):
            name = m.get("name", "?")
            duration = m.get("estimated_duration", "?")
            lines.append(f"\n**{i}. {name}** — {duration}")
            desc = m.get("description", "")
            if desc:
                lines.append(f"   {desc}")
            deliverables = m.get("deliverables", [])
            if deliverables:
                lines.append("   Deliverables:")
                for d in deliverables:
                    lines.append(f"   - {d}")
            deps = m.get("dependencies", [])
            if deps:
                lines.append(f"   Depends on: {', '.join(deps)}")
            criteria = m.get("success_criteria", [])
            if criteria:
                lines.append("   Done when:")
                for c in criteria:
                    lines.append(f"   - {c}")

    # Critical path
    crit = plan.get("critical_path", [])
    if crit:
        lines.append(f"\n### Critical Path\n{' → '.join(crit)}")

    return "\n".join(lines)


def _build_constraints_section(ctx: dict) -> str:
    plan = ctx.get("execution_plan", {})
    review = ctx.get("critical_review", {})

    lines = ["## Constraints & Risk Mitigations"]

    # Risk mitigations from execution plan
    mits = plan.get("risk_mitigations", {})
    if mits:
        for risk, mitigation in mits.items():
            lines.append(f"\n- **{risk}:** {mitigation}")

    # Killer risks from validation
    vals = ctx.get("validations", [])
    killer_risks = []
    for v in vals:
        killer_risks.extend(v.get("killer_risks", []))
    if killer_risks:
        lines.append("\n### Killer Risks (must be addressed)")
        for r in killer_risks:
            lines.append(f"- {r}")

    # User guidance if any
    guidance = ctx.get("user_guidance", "")
    if guidance:
        lines.append(f"\n### User Constraints\n{guidance}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _build_review_notes(ctx: dict) -> str:
    review = ctx.get("critical_review", {})
    if not review:
        return ""

    lines = ["## Critical Review Notes"]

    verdict = review.get("go_no_go", "?")
    score = review.get("score", 0)
    viability = review.get("overall_viability", "?")
    lines.append(f"\n**Verdict:** {verdict.upper()} — Score: {score}/10 — Viability: {viability}")

    final = review.get("final_verdict", "")
    if final:
        lines.append(f"\n{final}")

    conditions = review.get("conditions", [])
    if conditions:
        lines.append("\n**Conditions to meet:**")
        for c in conditions:
            lines.append(f"- {c}")

    changes = review.get("recommended_changes", [])
    if changes:
        lines.append("\n**Recommended changes:**")
        for c in changes:
            lines.append(f"- {c}")

    blind_spots = review.get("blind_spots", [])
    if blind_spots:
        lines.append("\n**Blind spots to watch:**")
        for b in blind_spots:
            lines.append(f"- {b}")

    return "\n".join(lines)


def _build_first_steps(ctx: dict) -> str:
    arch = ctx.get("architecture", {})
    plan = ctx.get("execution_plan", {})
    concept_name = ctx.get("selected_concept", "the project")

    # Extract tech stack names for setup instructions
    stack = arch.get("tech_stack", [])
    tech_names = [comp.get("technology", "") for comp in stack if comp.get("technology")]

    lines = ["## Instructions for Claude Code"]
    lines.append(f"""
Build **{concept_name}** following the architecture and execution plan above.

### How to approach this:
1. **Start with project scaffolding** — set up the repository structure, install
   dependencies, and create the foundational files based on the tech stack defined above.
2. **Implement milestone by milestone** — follow the execution plan in order.
   Each milestone has clear deliverables and success criteria. Complete one before
   moving to the next.
3. **Quick wins first** — if the execution plan lists quick wins, do those before
   the first formal milestone. They build momentum and validate the setup.
4. **Respect the architecture** — the roles, data flow, and tech choices were
   validated through the pipeline. Deviate only when you hit a concrete technical
   blocker, and explain why.
5. **Test as you go** — each milestone should have passing tests before proceeding.
   Write tests alongside implementation, not after.""")

    if tech_names:
        lines.append(f"\n### Tech Stack to set up\n{', '.join(tech_names)}")

    qw = plan.get("quick_wins", [])
    if qw:
        lines.append("\n### Start here (quick wins)")
        for q in qw:
            lines.append(f"- [ ] {q}")

    phases = plan.get("phases", [])
    if phases:
        first = phases[0]
        lines.append(f"\n### First milestone: {first.get('name', '?')}")
        for d in first.get("deliverables", []):
            lines.append(f"- [ ] {d}")

    return "\n".join(lines)


def _build_footer() -> str:
    return """---
*This prompt was generated by Fábrica de Soluções — a multi-agent pipeline
that researches, ideates, validates, architects, plans, and reviews product ideas
before development begins.*"""
