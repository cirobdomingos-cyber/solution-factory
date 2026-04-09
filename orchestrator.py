"""Master Orchestrator — coordinates the full solution pipeline.

This is the conductor. It runs each phase sequentially (because each phase
depends on the previous one's output), manages the accumulated context,
handles the critic's feedback loop, and produces the final output.

Architecture pattern: Pipeline with feedback loop.
- Phases 1-5 run sequentially, each enriching the shared context.
- Phase 6 (critic) can send the pipeline back for rework (max 2 iterations)
  by returning "no_go" with specific issues to address.

Interview angle: This is an orchestration pattern common in both
microservices (saga pattern) and AI agent systems. The key design
decision is sequential vs. parallel — here we're sequential because
each phase needs the previous phase's output as input. The feedback
loop from the critic is what makes this more sophisticated than a
simple pipeline.
"""

from __future__ import annotations

import json
import logging
import time

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from agents.trend_researcher import TrendResearchAgent
from agents.market_intel import MarketIntelligenceAgent
from agents.ideator import IdeationAgent
from agents.validator import ValidationAgent
from agents.architect import SolutionArchitectAgent
from agents.execution_planner import ExecutionPlannerAgent
from agents.critic import CriticalReviewAgent

logger = logging.getLogger(__name__)
console = Console()

MAX_ITERATIONS = 2


class SolutionOrchestrator:
    """Runs the full ideation-to-execution pipeline."""

    def __init__(self):
        self.agents = {
            "trend_research": TrendResearchAgent(),
            "opportunity_discovery": MarketIntelligenceAgent(),
            "ideation": IdeationAgent(),
            "validation": ValidationAgent(),
            "architecture": SolutionArchitectAgent(),
            "execution_planning": ExecutionPlannerAgent(),
            "critical_review": CriticalReviewAgent(),
        }
        self.phase_labels = {
            "trend_research": "Phase 0: Live Trend Research",
            "opportunity_discovery": "Phase 1: Opportunity Discovery",
            "ideation": "Phase 2: Solution Ideation",
            "validation": "Phase 3: Concept Validation",
            "architecture": "Phase 4: Solution Architecture",
            "execution_planning": "Phase 5: Execution Planning",
            "critical_review": "Phase 6: Critical Review",
        }

    def run(self, user_prompt: str) -> dict:
        """Execute the full pipeline from user prompt to final plan."""
        console.print(
            Panel(
                f"[bold cyan]Solution Factory[/bold cyan]\n\n"
                f'Processing: "{user_prompt}"',
                title="Pipeline Started",
                border_style="cyan",
            )
        )

        context = {"user_prompt": user_prompt}
        iteration = 1

        while iteration <= MAX_ITERATIONS:
            if iteration > 1:
                console.print(
                    f"\n[yellow]Iteration {iteration}: Reworking based on critic feedback...[/yellow]\n"
                )

            context = self._run_pipeline(context, iteration)

            # Check critic's verdict
            review = context.get("critical_review", {})
            verdict = review.get("go_no_go", "no_go")

            if verdict in ("go", "conditional_go"):
                break

            if iteration < MAX_ITERATIONS:
                console.print(
                    "[yellow]Critic returned 'no_go' — running another iteration...[/yellow]"
                )
                # Feed critic's feedback back into context for rework
                context["critic_feedback"] = review.get("recommended_changes", [])
                context["fatal_flaws"] = review.get("fatal_flaws", [])
                iteration += 1
            else:
                console.print(
                    "[red]Max iterations reached. Presenting best result.[/red]"
                )
                break

        self._display_results(context)
        return context

    def _run_pipeline(self, context: dict, iteration: int) -> dict:
        """Run all 6 phases sequentially."""
        phases = [
            "trend_research",
            "opportunity_discovery",
            "ideation",
            "validation",
            "architecture",
            "execution_planning",
            "critical_review",
        ]

        for phase in phases:
            label = self.phase_labels[phase]
            agent = self.agents[phase]

            console.print(f"\n[bold blue]{label}[/bold blue]")
            console.print(f"  Agent: [green]{agent.name}[/green] | Model: {agent.model}")

            start = time.time()

            try:
                result = agent.run(context)
                context.update(result)
                elapsed = time.time() - start

                console.print(f"  [dim]Completed in {elapsed:.1f}s[/dim]")
                self._show_phase_summary(phase, result)

            except Exception as e:
                console.print(f"  [red]ERROR: {e}[/red]")
                logger.exception(f"Phase {phase} failed")
                raise

        context["iteration"] = iteration
        return context

    def _show_phase_summary(self, phase: str, result: dict) -> None:
        """Display a brief summary of each phase's output."""
        if phase == "trend_research":
            trends = result.get("trends", [])
            sentiment = result.get("market_sentiment", "?")
            console.print(f"  [cyan]-> {len(trends)} trends found[/cyan] | Sentiment: {sentiment}")
            for t in trends[:3]:  # Show top 3
                title = t.get("title", "?")
                recency = t.get("recency", "?")
                console.print(f"     {title} ({recency})")
            takeaway = result.get("key_takeaway", "")
            if takeaway:
                console.print(f"  [yellow]Key takeaway:[/yellow] {takeaway}")

        elif phase == "opportunity_discovery":
            opps = result.get("opportunities", [])
            for opp in opps:
                title = opp.get("title", "?")
                confidence = opp.get("confidence", "?")
                console.print(f"  [cyan]-> {title}[/cyan] (confidence: {confidence})")

        elif phase == "ideation":
            concepts = result.get("concepts", [])
            for c in concepts:
                name = c.get("name", "?")
                liner = c.get("one_liner", "")
                console.print(f"  [cyan]-> {name}[/cyan]: {liner}")

        elif phase == "validation":
            vals = result.get("validations", [])
            for v in vals:
                ref = v.get("concept_ref", "?")
                score = v.get("overall_score", 0)
                rec = v.get("recommendation", "?")
                color = {"proceed": "green", "pivot": "yellow", "kill": "red"}.get(rec, "white")
                console.print(f"  [cyan]-> {ref}[/cyan]: {score:.1f}/10 [{color}]{rec}[/{color}]")

        elif phase == "architecture":
            arch = result.get("architecture", {})
            roles = arch.get("roles", [])
            console.print(f"  [cyan]-> {len(roles)} roles/agents defined[/cyan]")
            for r in roles:
                rtype = r.get("type", "?")
                title = r.get("title", "?")
                console.print(f"     [{rtype}] {title}")

        elif phase == "execution_planning":
            plan = result.get("execution_plan", {})
            milestones = plan.get("phases", [])
            console.print(f"  [cyan]-> {len(milestones)} milestones defined[/cyan]")
            for m in milestones:
                console.print(f"     {m.get('name', '?')} ({m.get('estimated_duration', '?')})")

        elif phase == "critical_review":
            review = result.get("critical_review", {})
            score = review.get("score", 0)
            verdict = review.get("go_no_go", "?")
            color = {"go": "green", "conditional_go": "yellow", "no_go": "red"}.get(verdict, "white")
            console.print(f"  [cyan]-> Score: {score}/10[/cyan] | Verdict: [{color}]{verdict}[/{color}]")

    def _display_results(self, context: dict) -> None:
        """Display the final formatted results."""
        console.print("\n")
        console.print(
            Panel(
                "[bold green]Pipeline Complete[/bold green]",
                border_style="green",
            )
        )

        # Summary table
        table = Table(title="Solution Factory Results", border_style="cyan")
        table.add_column("Phase", style="bold")
        table.add_column("Output", style="cyan")

        # Trends
        trends = context.get("trends", [])
        sentiment = context.get("market_sentiment", "N/A")
        table.add_row(
            "Live Trends",
            f"{len(trends)} found (sentiment: {sentiment})",
        )

        # Opportunities
        opps = context.get("opportunities", [])
        table.add_row(
            "Opportunities",
            f"{len(opps)} identified",
        )

        # Concepts
        concepts = context.get("concepts", [])
        table.add_row(
            "Concepts",
            f"{len(concepts)} generated",
        )

        # Best concept
        selected = context.get("selected_concept", "N/A")
        table.add_row("Selected", selected)

        # Validation
        validations = context.get("validations", [])
        best_val = max(validations, key=lambda v: v.get("overall_score", 0)) if validations else {}
        table.add_row(
            "Best Score",
            f"{best_val.get('overall_score', 0):.1f}/10 ({best_val.get('recommendation', '?')})",
        )

        # Architecture roles
        arch = context.get("architecture", {})
        roles = arch.get("roles", [])
        ai_roles = [r for r in roles if r.get("type") == "ai_agent"]
        human_roles = [r for r in roles if r.get("type") == "human"]
        hybrid_roles = [r for r in roles if r.get("type") == "hybrid"]
        table.add_row(
            "Roles Designed",
            f"{len(ai_roles)} AI agents, {len(human_roles)} human, {len(hybrid_roles)} hybrid",
        )

        # Execution
        plan = context.get("execution_plan", {})
        milestones = plan.get("phases", [])
        table.add_row("Milestones", f"{len(milestones)} phases")

        # Critic verdict
        review = context.get("critical_review", {})
        verdict = review.get("go_no_go", "?")
        score = review.get("score", 0)
        table.add_row("Final Verdict", f"{verdict.upper()} (score: {score}/10)")

        console.print(table)

        # Final verdict panel
        final_text = review.get("final_verdict", "No verdict available.")
        verdict_color = {"go": "green", "conditional_go": "yellow", "no_go": "red"}.get(
            verdict, "white"
        )
        console.print(
            Panel(
                final_text,
                title=f"[{verdict_color}]Verdict: {verdict.upper()}[/{verdict_color}]",
                border_style=verdict_color,
            )
        )

        # Show conditions if conditional
        if verdict == "conditional_go":
            conditions = review.get("conditions", [])
            if conditions:
                console.print("\n[yellow]Conditions for go:[/yellow]")
                for c in conditions:
                    console.print(f"  - {c}")

        # Show fatal flaws if no_go
        if verdict == "no_go":
            flaws = review.get("fatal_flaws", [])
            if flaws:
                console.print("\n[red]Fatal flaws:[/red]")
                for f in flaws:
                    console.print(f"  - {f}")
