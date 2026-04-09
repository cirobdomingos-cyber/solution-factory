"""PDF export — render a completed pipeline context as a structured PDF report.

Uses fpdf2 (pure Python, no system font dependencies) so it works on Railway.
"""

from __future__ import annotations

import io
import textwrap
from datetime import datetime
from typing import Any

from fpdf import FPDF, XPos, YPos


# ---------------------------------------------------------------------------
# Colour palette (R, G, B)
# ---------------------------------------------------------------------------
C_PRIMARY  = (17,  94, 178)   # deep blue
C_ACCENT   = (34, 197,  94)   # green
C_WARN     = (251, 146,  60)  # orange
C_DANGER   = (239,  68,  68)  # red
C_LIGHT    = (241, 245, 249)  # light slate bg
C_TEXT     = (15,  23,  42)   # near-black
C_MUTED    = (100, 116, 139)  # slate-500
C_WHITE    = (255, 255, 255)
C_DIVIDER  = (203, 213, 225)  # slate-300


def _safe(text: Any) -> str:
    """Coerce any value to a UTF-8-safe string fpdf2 can render."""
    return str(text or "").encode("latin-1", errors="replace").decode("latin-1")


class ReportPDF(FPDF):
    """Custom PDF with header/footer and helper draw methods."""

    def __init__(self, title: str = "Solution Factory Report") -> None:
        super().__init__()
        self._report_title = title
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(18, 18, 18)
        self.set_font("Helvetica", size=10)

    # ------------------------------------------------------------------
    # Header / footer
    # ------------------------------------------------------------------
    def header(self) -> None:
        self.set_fill_color(*C_PRIMARY)
        self.rect(0, 0, self.w, 12, "F")
        self.set_y(2)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*C_WHITE)
        self.cell(0, 8, _safe(self._report_title), align="C")
        self.set_text_color(*C_TEXT)
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*C_MUTED)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")
        self.set_text_color(*C_TEXT)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    def divider(self) -> None:
        self.set_draw_color(*C_DIVIDER)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def section_header(self, text: str, color: tuple = C_PRIMARY) -> None:
        self.ln(3)
        self.set_fill_color(*color)
        self.set_text_color(*C_WHITE)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, f"  {_safe(text)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*C_TEXT)
        self.ln(2)

    def phase_header(self, num: int, label: str) -> None:
        self.add_page()
        self.set_fill_color(*C_PRIMARY)
        self.set_text_color(*C_WHITE)
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 12, f"  Phase {num}: {_safe(label)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*C_TEXT)
        self.ln(4)

    def kv_row(self, label: str, value: str) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*C_MUTED)
        self.cell(40, 6, _safe(label.upper()), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", size=9)
        self.set_text_color(*C_TEXT)
        available = self.w - self.r_margin - self.l_margin - 40
        self.multi_cell(available, 6, _safe(value))
        self.set_x(self.l_margin)

    def bullet(self, text: str, color: tuple = C_TEXT, indent: float = 4) -> None:
        self.set_x(self.l_margin + indent)
        self.set_font("Helvetica", size=9)
        self.set_text_color(*color)
        available = self.w - self.r_margin - self.l_margin - indent - 4
        lines = textwrap.wrap(_safe(text), width=110)
        for i, line in enumerate(lines):
            prefix = "- " if i == 0 else "  "
            self.cell(5, 5, prefix, new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.multi_cell(available - 5, 5, line)
            self.set_x(self.l_margin + indent)
        self.set_text_color(*C_TEXT)

    def score_bar(self, label: str, score: int, max_score: int = 10) -> None:
        ratio = max(0, min(score / max_score, 1))
        bar_w = 60
        filled = bar_w * ratio
        y = self.get_y()
        self.set_font("Helvetica", size=8)
        self.cell(38, 5, _safe(label), new_x=XPos.RIGHT, new_y=YPos.TOP)
        # background
        self.set_fill_color(*C_LIGHT)
        self.rect(self.get_x(), y, bar_w, 4, "F")
        # fill
        if score >= 7:
            fill_c = C_ACCENT
        elif score >= 4:
            fill_c = C_WARN
        else:
            fill_c = C_DANGER
        self.set_fill_color(*fill_c)
        if filled > 0:
            self.rect(self.get_x(), y, filled, 4, "F")
        self.set_x(self.get_x() + bar_w + 3)
        self.cell(20, 5, f"{score}/{max_score}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def body_text(self, text: str) -> None:
        self.set_font("Helvetica", size=9)
        self.set_text_color(*C_TEXT)
        self.multi_cell(0, 5, _safe(text))
        self.ln(1)

    def badge(self, text: str, color: tuple) -> None:
        self.set_fill_color(*color)
        self.set_text_color(*C_WHITE)
        self.set_font("Helvetica", "B", 8)
        self.cell(0, 6, f"  {_safe(text)}  ", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*C_TEXT)
        self.ln(1)


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_cover(pdf: ReportPDF, ctx: dict) -> None:
    pdf.add_page()
    pdf.set_fill_color(*C_PRIMARY)
    pdf.rect(0, 0, pdf.w, 70, "F")
    pdf.set_y(20)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*C_WHITE)
    pdf.cell(0, 12, "Solution Factory", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", 11)
    pdf.cell(0, 8, "AI-Powered Solution Blueprint", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(30)

    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(*C_TEXT)

    prompt = ctx.get("user_prompt", "")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(30, 7, "Domain:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 7, _safe(prompt))

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(30, 7, "Generated:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 7, datetime.now().strftime("%B %d, %Y %H:%M"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    review = ctx.get("critical_review", {})
    verdict = review.get("go_no_go", "")
    score = review.get("score", 0)
    if verdict:
        pdf.ln(8)
        pdf.divider()
        pdf.set_font("Helvetica", "B", 13)
        vc = {"go": C_ACCENT, "conditional_go": C_WARN, "no_go": C_DANGER}
        pdf.set_text_color(*vc.get(verdict, C_MUTED))
        label = {"go": "GO", "conditional_go": "CONDITIONAL GO", "no_go": "NO GO"}.get(verdict, verdict.upper())
        pdf.cell(0, 10, f"Verdict: {label}  |  Score: {score}/10", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*C_TEXT)

    pdf.divider()
    selected = ctx.get("selected_concept", "")
    if selected:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 7, "Selected concept:", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 7, _safe(selected))


def _render_trends(pdf: ReportPDF, ctx: dict) -> None:
    pdf.phase_header(0, "Live Trend Research")
    trends = ctx.get("trends", [])
    if not trends:
        pdf.body_text("No live trends collected.")
        return
    pdf.kv_row("Sentiment", ctx.get("market_sentiment", "unknown").upper())
    pdf.kv_row("Key Takeaway", ctx.get("key_takeaway", ""))
    pdf.ln(3)
    for t in trends:
        pdf.section_header(t.get("title", "Untitled"), C_PRIMARY)
        pdf.kv_row("Recency", t.get("recency", "?"))
        desc = t.get("description", "")
        if desc:
            pdf.body_text(desc)
        for s in t.get("source_signals", []):
            pdf.bullet(s)
        impl = t.get("opportunity_implication", "")
        if impl:
            pdf.set_fill_color(*C_LIGHT)
            pdf.set_font("Helvetica", "I", 9)
            pdf.multi_cell(0, 5, f"  Builder implication: {_safe(impl)}", fill=True)
            pdf.ln(2)


def _render_opportunities(pdf: ReportPDF, ctx: dict) -> None:
    pdf.phase_header(1, "Opportunity Discovery")
    for opp in ctx.get("opportunities", []):
        conf = opp.get("confidence", "?")
        cc = {"high": C_ACCENT, "medium": C_WARN, "low": C_DANGER}.get(conf, C_MUTED)
        pdf.section_header(f"{opp.get('title', '?')} [{conf.upper()} confidence]", cc)
        pdf.kv_row("Domain", opp.get("domain", "?"))
        pdf.kv_row("Target Audience", opp.get("target_audience", "?"))
        pdf.kv_row("Revenue Potential", opp.get("revenue_potential", "?"))
        pdf.kv_row("Pain Point", opp.get("pain_point", "?"))
        pdf.kv_row("Timing", opp.get("timing_rationale", "?"))
        pdf.kv_row("Competition", opp.get("competition_landscape", "?"))
        for s in opp.get("market_signals", []):
            pdf.bullet(s)
        pdf.ln(2)


def _render_concepts(pdf: ReportPDF, ctx: dict) -> None:
    pdf.phase_header(2, "Solution Ideation")
    for c in ctx.get("concepts", []):
        pdf.section_header(c.get("name", "?"))
        pdf.kv_row("One-liner", c.get("one_liner", ""))
        pdf.kv_row("Addresses", c.get("opportunity_ref", "?"))
        pdf.kv_row("How it works", c.get("how_it_works", "?"))
        pdf.kv_row("Differentiator", c.get("key_differentiator", "?"))
        pdf.kv_row("Monetization", c.get("monetization_model", "?"))
        pdf.kv_row("MVP scope", c.get("mvp_scope", "?"))
        pdf.kv_row("Target user", c.get("target_user_persona", "?"))
        for a in c.get("assumptions", []):
            pdf.bullet(a, C_MUTED)
        pdf.ln(2)


def _render_validation(pdf: ReportPDF, ctx: dict) -> None:
    pdf.phase_header(3, "Concept Validation")
    rec_colors = {"proceed": C_ACCENT, "pivot": C_WARN, "kill": C_DANGER}
    for v in ctx.get("validations", []):
        rec = v.get("recommendation", "?")
        pdf.section_header(
            f"{v.get('concept_ref', '?')} — {v.get('overall_score', 0):.1f}/10 [{rec.upper()}]",
            rec_colors.get(rec, C_MUTED),
        )
        pdf.score_bar("Market Fit",      v.get("market_fit_score", 0))
        pdf.score_bar("Feasibility",     v.get("feasibility_score", 0))
        pdf.score_bar("Revenue Viability", v.get("revenue_viability_score", 0))
        pdf.ln(2)
        pdf.kv_row("Reasoning", v.get("reasoning", ""))
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Strengths", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for s in v.get("strengths", []):
            pdf.bullet(s, C_ACCENT)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Weaknesses", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for w in v.get("weaknesses", []):
            pdf.bullet(w, C_WARN)
        for r in v.get("killer_risks", []):
            pdf.bullet(f"KILLER RISK: {r}", C_DANGER)
        pdf.ln(2)


def _render_architecture(pdf: ReportPDF, ctx: dict) -> None:
    pdf.phase_header(4, "Solution Architecture")
    arch = ctx.get("architecture", {})
    pdf.kv_row("Selected Concept", ctx.get("selected_concept", "?"))
    pdf.kv_row("Complexity", arch.get("estimated_complexity", "?"))
    overview = arch.get("system_overview", "")
    if overview:
        pdf.body_text(overview)

    roles = arch.get("roles", [])
    if roles:
        pdf.section_header("Roles & Agents")
        icons = {"ai_agent": "[AI]", "human": "[HU]", "hybrid": "[HY]"}
        for r in roles:
            rt = r.get("type", "?")
            icon = icons.get(rt, "[??]")
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 5, f"{icon} {_safe(r.get('title', '?'))}  ({rt})", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            for resp in r.get("responsibilities", []):
                pdf.bullet(resp, indent=6)
            tools = r.get("tools_needed", [])
            if tools:
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(*C_MUTED)
                pdf.cell(0, 5, f"  Tools: {', '.join(tools)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(*C_TEXT)
            pdf.ln(1)

    stack = arch.get("tech_stack", [])
    if stack:
        pdf.section_header("Tech Stack")
        for comp in stack:
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 5, f"{_safe(comp.get('name', '?'))} — {_safe(comp.get('technology', '?'))}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.body_text(f"Purpose: {comp.get('purpose', '')}  |  {comp.get('rationale', '')}")

    df = arch.get("data_flow", "")
    if df:
        pdf.section_header("Data Flow")
        pdf.body_text(df)

    cost = arch.get("cost_structure", "")
    if cost:
        pdf.section_header("Cost Structure")
        pdf.body_text(cost)


def _render_execution_plan(pdf: ReportPDF, ctx: dict) -> None:
    pdf.phase_header(5, "Execution Planning")
    plan = ctx.get("execution_plan", {})
    qw = plan.get("quick_wins", [])
    if qw:
        pdf.section_header("Quick Wins (First 48h)", C_ACCENT)
        for q in qw:
            pdf.bullet(q, C_ACCENT)
    for i, m in enumerate(plan.get("phases", [])):
        pdf.section_header(f"Milestone {i+1}: {m.get('name', '?')}  [{m.get('estimated_duration', '?')}]")
        pdf.body_text(m.get("description", ""))
        for d in m.get("deliverables", []):
            pdf.bullet(d)
        deps = m.get("dependencies", [])
        if deps:
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*C_MUTED)
            pdf.cell(0, 5, f"  Depends on: {', '.join(deps)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(*C_TEXT)
        for c in m.get("success_criteria", []):
            pdf.bullet(c, C_MUTED)
        pdf.ln(1)

    crit = plan.get("critical_path", [])
    if crit:
        pdf.section_header("Critical Path")
        pdf.body_text(" → ".join(crit))

    mits = plan.get("risk_mitigations", {})
    if mits:
        pdf.section_header("Risk Mitigations")
        for risk, mit in mits.items():
            pdf.kv_row(risk, mit)


def _render_critical_review(pdf: ReportPDF, ctx: dict) -> None:
    pdf.phase_header(6, "Critical Review")
    review = ctx.get("critical_review", {})
    verdict = review.get("go_no_go", "?")
    vc = {"go": C_ACCENT, "conditional_go": C_WARN, "no_go": C_DANGER}
    vl = {"go": "GO", "conditional_go": "CONDITIONAL GO", "no_go": "NO GO"}
    pdf.badge(f"{vl.get(verdict, verdict.upper())} — Score: {review.get('score', 0)}/10 | Viability: {review.get('overall_viability', '?')}", vc.get(verdict, C_MUTED))
    final = review.get("final_verdict", "")
    if final:
        pdf.body_text(final)
    pdf.section_header("Strongest Elements", C_ACCENT)
    for s in review.get("strongest_elements", []):
        pdf.bullet(s, C_ACCENT)
    pdf.section_header("Blind Spots", C_WARN)
    for b in review.get("blind_spots", []):
        pdf.bullet(b, C_WARN)
    for f in review.get("fatal_flaws", []):
        pdf.bullet(f"FATAL: {f}", C_DANGER)
    conditions = review.get("conditions", [])
    if conditions:
        pdf.section_header("Conditions for GO", C_WARN)
        for c in conditions:
            pdf.bullet(c, C_WARN)
    changes = review.get("recommended_changes", [])
    if changes:
        pdf.section_header("Recommended Changes")
        for c in changes:
            pdf.bullet(c)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SECTION_RENDERERS = [
    ("trends", _render_trends),
    ("opportunities", _render_opportunities),
    ("concepts", _render_concepts),
    ("validations", _render_validation),
    ("architecture", _render_architecture),
    ("execution_plan", _render_execution_plan),
    ("critical_review", _render_critical_review),
]


def build_pdf_bytes(ctx: dict) -> bytes:
    """Build the full report PDF and return it as bytes (for st.download_button).

    Sections are only included when the corresponding pipeline data exists in ctx.
    """
    prompt = ctx.get("user_prompt", "solution")[:60]
    pdf = ReportPDF(title=f"Solution Factory — {prompt}")

    _render_cover(pdf, ctx)

    for key, renderer in SECTION_RENDERERS:
        has_data = bool(ctx.get(key))
        # execution_plan is a dict that may be empty
        if key == "execution_plan":
            has_data = bool(ctx.get(key, {}).get("phases"))
        if has_data:
            renderer(pdf, ctx)

    return bytes(pdf.output())
