"""Run an agent against a dispatch scenario and capture what happened.

`run_once` is agent-agnostic: an ``agent`` is any callable
``agent(scenario, tools) -> AgentResult``. It receives a fresh deep copy of the
scenario world (so trials and reruns never bleed into each other) wrapped in
`DispatchTools` (with any declared fault wired in), drives tool calls, and
returns its rationale. The runner returns the final world, the tool-call
trajectory, and that rationale for the scorer to grade.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_evaluator.dispatch.scenario import DispatchScenario
from agent_evaluator.dispatch.tools import DispatchTools
from agent_evaluator.dispatch.models import WorldState


@dataclass
class AgentResult:
    """What an agent returns after acting on a scenario."""

    rationale: str = ""


@dataclass
class RunRecord:
    """One run's observable outcome: final state + trajectory + rationale."""

    scenario_id: str
    final_world: WorldState
    calls: list[dict] = field(default_factory=list)
    rationale: str = ""


def run_once(scenario: DispatchScenario, agent) -> RunRecord:
    """Run `agent` against a fresh copy of `scenario`'s world; capture the result."""
    world = scenario.world.model_copy(deep=True)
    tools = DispatchTools(world, fault=scenario.fault)
    result = agent(scenario, tools)
    rationale = result.rationale if isinstance(result, AgentResult) else str(result or "")
    calls = [{"tool": name, "args": args} for name, args in tools.calls]
    return RunRecord(
        scenario_id=scenario.id,
        final_world=world,
        calls=calls,
        rationale=rationale,
    )
