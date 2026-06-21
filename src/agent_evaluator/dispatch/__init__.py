"""Synthetic over-the-road freight dispatch domain.

A publishable, NDA-free dispatch world for exercising tool-calling agents:
entity schemas (drivers, loads), a seedable mutable world state, a tool
interface (read-only lookups + the assignment write), and a hard-vs-soft
constraint model.

Design principle (AgentDojo / tau-bench style): the assignment write is
PERMISSIVE — it books whatever the agent asks, enforcing only the
double-assignment race guard. Hard-constraint violations are detected by
inspecting final world state (see `constraints.hard_violations`), NOT by the
tool refusing the call. That lets an agent make a real mistake the scorer can
catch, instead of the harness silently preventing it.

This domain is deliberately generic. It encodes no business-specific policy —
no tuned magic constants, no proprietary priority comparator, no allocation or
earnings rules. The constraints here are the ones any freight dispatcher would
recognize. See GLOSSARY.md for the scrubbing audit trail.
"""

from agent_evaluator.dispatch.constraints import (
    HARD_CONSTRAINTS,
    SOFT_PREFERENCES,
    hard_violations,
    soft_signals,
)
from agent_evaluator.dispatch.models import (
    Assignment,
    Driver,
    DriverTier,
    EquipmentType,
    Endorsement,
    Load,
    WorldState,
)
from agent_evaluator.dispatch.scenario import (
    DispatchScenario,
    ExpectedOutcome,
    ToolFault,
    check_outcome,
    legal_drivers,
)
from agent_evaluator.dispatch.scenarios import all_scenarios, scenario_by_id
from agent_evaluator.dispatch.agents import naive_solver, reference_solver
from agent_evaluator.dispatch.llm_agent import LLMDispatchAgent, LLMReasoningJudge
from agent_evaluator.dispatch.report import render_dispatch_report
from agent_evaluator.dispatch.runner import AgentResult, RunRecord, run_once
from agent_evaluator.dispatch.scoring import (
    EvaluationReport,
    ScenarioResult,
    evaluate_all,
    keyword_reasoning_judge,
    score_scenario,
)
from agent_evaluator.dispatch.tools import DispatchTools
from agent_evaluator.dispatch.world import build_world

__all__ = [
    "AgentResult",
    "Assignment",
    "DispatchScenario",
    "DispatchTools",
    "Driver",
    "DriverTier",
    "Endorsement",
    "EquipmentType",
    "EvaluationReport",
    "ExpectedOutcome",
    "HARD_CONSTRAINTS",
    "LLMDispatchAgent",
    "LLMReasoningJudge",
    "Load",
    "RunRecord",
    "SOFT_PREFERENCES",
    "ScenarioResult",
    "ToolFault",
    "WorldState",
    "all_scenarios",
    "build_world",
    "check_outcome",
    "evaluate_all",
    "hard_violations",
    "keyword_reasoning_judge",
    "legal_drivers",
    "naive_solver",
    "reference_solver",
    "render_dispatch_report",
    "run_once",
    "scenario_by_id",
    "score_scenario",
    "soft_signals",
]
