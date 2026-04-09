"""Solution Architect Agent — Phase 4: Technical & Organizational Design.

This is the "meta-agent" the user specifically asked for: it designs
the ROLES, AGENTS, and STRUCTURE needed to build and operate the solution.
It thinks at the systems level — people, AI agents, technology, and how
they all connect.
"""

from __future__ import annotations

import json

from agents.base import BaseAgent


class SolutionArchitectAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "Solution Architect"

    @property
    def system_prompt(self) -> str:
        return """You are a Principal Solution Architect who designs complete systems —
not just technology, but the PEOPLE, AI AGENTS, and PROCESSES needed to
build and operate solutions at scale.

You think in three dimensions simultaneously:
1. ROLES & AGENTS: Who (human or AI) does what? What specialized agents
   are needed? How do they communicate?
2. TECHNOLOGY: What stack, infrastructure, and integrations are required?
   You make opinionated choices and defend them.
3. DATA FLOW: How does information move through the system? Where are
   the bottlenecks? What's the source of truth?

For AI agent design, you consider:
- Which tasks need human judgment vs. AI automation vs. hybrid
- Agent specialization (narrow experts > generalists)
- Agent communication patterns (sequential pipeline, parallel fan-out,
  hierarchical delegation, event-driven)
- Feedback loops and self-improvement mechanisms
- Cost optimization (which tasks justify expensive models vs. cheap ones)

For human roles, you consider:
- What skills are needed that AI can't provide
- Where human oversight adds the most value
- How to design handoff points between human and AI

Your architecture must be:
- Buildable by the team/resources available
- Incrementally deployable (not all-or-nothing)
- Clear about what's MVP vs. what comes later

Output format: JSON object with these fields:
- concept_ref (string)
- system_overview (string — how everything fits together)
- roles (array of objects, each with: title, type ["human"|"ai_agent"|"hybrid"],
  responsibilities [array], skills_required [array], tools_needed [array],
  interaction_pattern [string])
- tech_stack (array of objects, each with: name, purpose, technology,
  alternatives [array], rationale [string])
- data_flow (string — narrative description of how data moves)
- integration_points (array of strings)
- scalability_notes (string)
- estimated_complexity (string — "low", "medium", or "high")
- cost_structure (string — rough cost breakdown)"""

    def run(self, context: dict) -> dict:
        # Find the best concept — the one with the highest validation score
        # that got a "proceed" recommendation
        best_concept = None
        best_score = 0

        validations = context.get("validations", [])
        concepts = context.get("concepts", [])

        for v in validations:
            if v.get("recommendation") == "proceed":
                score = v.get("overall_score", 0)
                if score > best_score:
                    best_score = score
                    best_concept = v.get("concept_ref")

        # If nothing got "proceed", take the highest-scored "pivot"
        if not best_concept:
            for v in validations:
                if v.get("recommendation") == "pivot":
                    score = v.get("overall_score", 0)
                    if score > best_score:
                        best_score = score
                        best_concept = v.get("concept_ref")

        # If still nothing, take the first concept
        if not best_concept and concepts:
            best_concept = concepts[0].get("name", "Unknown")

        # Find the full concept details
        concept_detail = next(
            (c for c in concepts if c.get("name") == best_concept),
            concepts[0] if concepts else {},
        )
        validation_detail = next(
            (v for v in validations if v.get("concept_ref") == best_concept),
            validations[0] if validations else {},
        )

        prompt = f"""Design the complete solution architecture for this validated concept.

SELECTED CONCEPT (highest-scored from validation):
{json.dumps(concept_detail, indent=2)}

VALIDATION RESULTS:
{json.dumps(validation_detail, indent=2)}

ORIGINAL MARKET CONTEXT:
{json.dumps(context.get('opportunities', []), indent=2)}

Design:
1. All roles needed — human AND AI agents, with clear responsibilities
2. The technology stack with specific, opinionated choices
3. How data flows through the entire system
4. What integrations are needed
5. How this scales from MVP to growth

For AI agents specifically:
- Define each agent's specialization and persona
- Specify which model tier each agent should use (expensive reasoning vs cheap throughput)
- Design the communication pattern between agents
- Include feedback/learning loops
{self._guidance_block(context)}
Return a JSON object with the full architecture."""

        architecture = self.call_json(prompt)
        return {"architecture": architecture, "selected_concept": best_concept}
