"""Execution Planner Agent — Phase 5: Roadmap & Milestones.

This agent converts architecture into actionable execution steps.
It thinks like a seasoned engineering manager / project lead who has
shipped many products and knows where projects actually get stuck.
"""

from __future__ import annotations

import json

from agents.base import BaseAgent


class ExecutionPlannerAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "Execution Planner"

    @property
    def system_prompt(self) -> str:
        return """You are a veteran Engineering Manager and Product Lead who has shipped
dozens of products from zero to revenue. You know:

- Where projects ACTUALLY get stuck (not where plans say they will)
- How to sequence work so you're never blocked
- The difference between a plan that looks good on paper and one that survives contact with reality
- How to identify the critical path and protect it

Your planning philosophy:
1. SHIP EARLY: The first milestone must produce something usable/testable
2. DEPENDENCIES FIRST: Do the risky, uncertain work early — not last
3. PARALLEL TRACKS: Identify work that can happen simultaneously
4. QUICK WINS: Start with things that build momentum and prove the concept
5. CLEAR EXITS: Every milestone has a "this isn't working" criteria too

You think in terms of:
- What can go wrong at each stage and how to de-risk it
- Which roles/agents are needed when (not everyone from day 1)
- What "done" looks like at each milestone (specific, measurable)
- Resource constraints (solo builder vs team, budget limits)

Output format: JSON object with these fields:
- concept_ref (string)
- phases (array of milestone objects, each with: name, description,
  deliverables [array], dependencies [array of milestone names],
  estimated_duration [string], assigned_roles [array of role titles],
  success_criteria [array])
- critical_path (array of milestone names in order)
- quick_wins (array of strings — things to do in the first 48 hours)
- launch_criteria (array of strings — what "shipped" means)
- risk_mitigations (object — risk: mitigation pairs)
- resource_requirements (string)"""

    def run(self, context: dict) -> dict:
        architecture = context.get("architecture", {})
        concept_ref = context.get("selected_concept", "Unknown")

        prompt = f"""Create a detailed execution plan for building this solution.

SOLUTION ARCHITECTURE:
{json.dumps(architecture, indent=2)}

CONCEPT: {concept_ref}

Create a phased plan that:
1. Starts with quick wins in the first 48 hours
2. Gets to a testable MVP as fast as possible
3. Sequences risky/uncertain work EARLY
4. Identifies what can be parallelized
5. Has clear success criteria for every milestone
6. Includes specific risk mitigations for each known risk

Assume the builder is a skilled solo developer or very small team.
Be realistic about timelines — pad estimates by 1.5x.
{self._guidance_block(context)}
Return a JSON object with the execution plan."""

        plan = self.call_json(prompt)
        return {"execution_plan": plan}
