"""Data models for the Solution Factory pipeline.

Each model represents the output of one pipeline phase, flowing forward
as structured context to the next phase. This is the "contract" between agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


# -- Phase 1: Opportunity Discovery --


@dataclass
class Opportunity:
    """A market opportunity identified by the Market Intelligence agent."""

    title: str
    domain: str  # e.g. "SaaS", "developer tools", "healthcare"
    pain_point: str  # the problem people are willing to pay to solve
    target_audience: str
    market_signals: list[str]  # trends, data points, indicators
    revenue_potential: str  # qualitative estimate with reasoning
    competition_landscape: str
    timing_rationale: str  # why NOW is the right time
    confidence: Confidence = Confidence.MEDIUM


# -- Phase 2: Ideation --


@dataclass
class SolutionConcept:
    """A concrete solution concept generated from an opportunity."""

    name: str
    opportunity_ref: str  # which opportunity this addresses
    one_liner: str  # elevator pitch
    how_it_works: str  # mechanism in 2-3 sentences
    key_differentiator: str  # why this beats existing alternatives
    monetization_model: str  # how it makes money
    mvp_scope: str  # what the smallest viable version looks like
    target_user_persona: str
    assumptions: list[str]  # things that must be true for this to work


# -- Phase 3: Validation --


@dataclass
class ValidationResult:
    """Stress-test results for a solution concept."""

    concept_ref: str  # which concept was validated
    market_fit_score: int  # 1-10
    feasibility_score: int  # 1-10
    revenue_viability_score: int  # 1-10
    overall_score: float  # weighted composite
    strengths: list[str]
    weaknesses: list[str]
    killer_risks: list[str]  # any of these = do not proceed
    missing_information: list[str]  # things we'd need to verify
    recommendation: str  # "proceed" | "pivot" | "kill"
    reasoning: str


# -- Phase 4: Solution Architecture --


@dataclass
class AgentRole:
    """A role/agent that the solution needs — could be human or AI."""

    title: str
    type: str  # "human", "ai_agent", "hybrid"
    responsibilities: list[str]
    skills_required: list[str]
    tools_needed: list[str]
    interaction_pattern: str  # how this role connects to others


@dataclass
class TechComponent:
    """A technology building block in the solution architecture."""

    name: str
    purpose: str
    technology: str  # specific tech/tool recommendation
    alternatives: list[str]
    rationale: str  # why this choice over alternatives


@dataclass
class SolutionArchitecture:
    """Full architecture for a validated solution."""

    concept_ref: str
    system_overview: str  # high-level description of how everything fits
    roles: list[AgentRole]
    tech_stack: list[TechComponent]
    data_flow: str  # how data moves through the system
    integration_points: list[str]  # external systems/APIs needed
    scalability_notes: str
    estimated_complexity: str  # "low" | "medium" | "high"
    cost_structure: str  # rough cost breakdown


# -- Phase 5: Execution Planning --


@dataclass
class Milestone:
    """A key milestone in the execution plan."""

    name: str
    description: str
    deliverables: list[str]
    dependencies: list[str]  # names of milestones that must complete first
    estimated_duration: str  # e.g. "1-2 weeks"
    assigned_roles: list[str]  # which AgentRole titles handle this
    success_criteria: list[str]


@dataclass
class ExecutionPlan:
    """The full execution roadmap from MVP to launch."""

    concept_ref: str
    phases: list[Milestone]
    critical_path: list[str]  # milestone names on the critical path
    quick_wins: list[str]  # things that can be done immediately
    launch_criteria: list[str]  # what "done" looks like
    risk_mitigations: dict[str, str]  # risk -> mitigation strategy
    resource_requirements: str


# -- Phase 6: Critical Review --


@dataclass
class CriticalReview:
    """Final quality gate — the critic's assessment of the full plan."""

    overall_viability: Confidence
    score: int  # 1-10
    fatal_flaws: list[str]  # any = send back for rework
    blind_spots: list[str]  # things the pipeline may have missed
    strongest_elements: list[str]
    recommended_changes: list[str]
    go_no_go: str  # "go" | "no_go" | "conditional_go"
    conditions: list[str]  # if conditional_go, what must change
    final_verdict: str  # one paragraph synthesis


# -- Pipeline State --


@dataclass
class PipelineState:
    """Tracks the full state of a solution pipeline run."""

    user_prompt: str
    opportunities: list[Opportunity] = field(default_factory=list)
    concepts: list[SolutionConcept] = field(default_factory=list)
    validations: list[ValidationResult] = field(default_factory=list)
    architecture: SolutionArchitecture | None = None
    execution_plan: ExecutionPlan | None = None
    critical_review: CriticalReview | None = None
    current_phase: str = "opportunity_discovery"
    iteration: int = 1  # pipeline can loop if critic sends back for rework
