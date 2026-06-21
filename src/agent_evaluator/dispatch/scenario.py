"""Dispatch scenario schema + deterministic outcome checking.

A `DispatchScenario` is data: an initial world, the task handed to the agent,
and a checkable `ExpectedOutcome`. `check_outcome` grades a *final* world
(after the agent acted) against that expectation by inspecting state — the
state-checking approach (tau-bench / AgentDojo), not an LLM judge. Reasoning
quality (L2) and tool-trajectory quality (L3) are layered on top by the scorer
in a later phase; this module covers the deterministic, state-based verdict.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent_evaluator.dispatch.constraints import hard_violations
from agent_evaluator.dispatch.models import Load, WorldState


class ToolFault(BaseModel):
    """A declared transient tool failure the agent must recover from (L3).

    The scorer/harness (Step 3) injects this: the `on_call`-th call to `tool`
    returns `{"error": ...}` instead of its normal result. A resilient agent
    retries or routes around it and still reaches the correct outcome.
    """

    tool: str
    on_call: int = 1  # 1-based: which call to `tool` fails
    error: str


class ExpectedOutcome(BaseModel):
    """The correct end state for a scenario, checkable against final world state.

    - ``assign``           — the load must end assigned to exactly `correct_driver_id`
                             (captures soft-optimality failures: a legal-but-worse
                             pick is wrong).
    - ``assign_any_legal`` — the load must end assigned to *any* driver with zero
                             hard violations.
    - ``no_assign``        — the load must be left unassigned (no legal driver
                             exists; the only correct action is to refuse).
    """

    kind: Literal["assign", "assign_any_legal", "no_assign"]
    load_id: str
    correct_driver_id: str | None = None
    # Drivers that LOOK tempting (closest, available) but are illegal — the trap.
    trap_driver_ids: list[str] = Field(default_factory=list)
    rationale: str


class DispatchScenario(BaseModel):
    """One test case for the dispatch domain."""

    id: str
    layer: str  # "L1".."L6"
    probes: str  # the specific failure this scenario probes
    description: str
    task: str  # the instruction handed to the agent
    world: WorldState
    expected: ExpectedOutcome
    # L5: rerun count for pass^k stability scoring (all k trials must pass).
    trials: int = 1
    # L6: severity of a wrong dispatch, feeding the release recommendation.
    error_cost: Literal["low", "medium", "high"] = "medium"
    # L3: an optional injected tool failure the agent must recover from.
    fault: ToolFault | None = None


def legal_drivers(world: WorldState, load: Load) -> list[str]:
    """IDs of every driver who could legally take `load` (zero hard violations)."""
    return [
        d.id for d in world.drivers.values() if not hard_violations(d, load, world)
    ]


def check_outcome(scenario: DispatchScenario, final_world: WorldState) -> dict:
    """Grade a final world against the scenario's expected outcome.

    Returns ``{"correct": bool, "reason": str}``. An assignment that violates
    any hard constraint is always incorrect, regardless of `kind` — that is the
    L1/L4 failure signal.
    """
    exp = scenario.expected
    load = final_world.loads[exp.load_id]
    assigned = load.assigned_driver_id if load.status == "assigned" else None

    if assigned is not None:
        violations = hard_violations(final_world.drivers[assigned], load, final_world)
        if violations:
            return {
                "correct": False,
                "reason": f"assigned {assigned} but that violates {violations}",
            }

    if exp.kind == "no_assign":
        if assigned is None:
            return {"correct": True, "reason": "correctly left unassigned (no legal driver)"}
        return {"correct": False, "reason": f"should have refused; assigned {assigned}"}

    if exp.kind == "assign":
        if assigned == exp.correct_driver_id:
            return {"correct": True, "reason": f"assigned the correct driver {assigned}"}
        return {
            "correct": False,
            "reason": f"expected {exp.correct_driver_id}, got {assigned}",
        }

    # assign_any_legal — any zero-violation assignment passes (checked above).
    if assigned is None:
        return {"correct": False, "reason": "expected a legal assignment, got none"}
    return {"correct": True, "reason": f"assigned a legal driver {assigned}"}
