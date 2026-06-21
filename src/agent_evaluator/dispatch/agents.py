"""Reference agents — deterministic drivers used to validate the harness.

These are NOT the real agent under evaluation (that is a live LLM, plugged into
the same `agent(scenario, tools) -> AgentResult` interface). They exist so the
scoring harness can be tested hermetically:

- `reference_solver` is the answer key: it gathers info through the tools, then
  performs the scenario's known-correct action (recovering from an injected
  fault). A correct solution MUST score as pass — that validates the scorer.
- `naive_solver` is a buggy baseline: it grabs the first available driver off
  the stub list and books it, with no eligibility checks and no recovery. It
  MUST fail the trap scenarios — that validates the scorer discriminates.
"""

from __future__ import annotations

from agent_evaluator.dispatch.constraints import hard_violations
from agent_evaluator.dispatch.runner import AgentResult


def reference_solver(scenario, tools) -> AgentResult:
    """Produce the scenario's reference-correct action, realistically.

    Gathers driver detail + HOS for each available driver, looks up the load and
    a deadhead (retrying once if the lookup faults), then books the expected
    driver — or refuses when the expectation is `no_assign`.
    """
    exp = scenario.expected
    load = tools.get_load(exp.load_id)
    pickup = load.get("pickup")

    available = tools.list_available_drivers().get("drivers", [])
    for stub in available:
        tools.get_driver(stub["id"])
        tools.get_hours_of_service(stub["id"])
        dist = tools.get_distance(stub["location"], pickup)
        if "error" in dist:  # transient fault — retry once
            tools.get_distance(stub["location"], pickup)

    if exp.kind == "no_assign":
        return AgentResult(rationale=exp.rationale or "No legal driver available; refusing to assign.")

    driver_id = exp.correct_driver_id
    if driver_id is None:  # assign_any_legal — pick any driver with zero violations
        load_obj = tools.world.loads[exp.load_id]
        driver_id = next(
            (d.id for d in tools.world.drivers.values()
             if d.on_duty and not hard_violations(d, load_obj, tools.world)),
            None,
        )
    if driver_id is not None:
        tools.assign_driver_to_load(driver_id, exp.load_id)
    return AgentResult(rationale=exp.rationale or f"Assigned {driver_id}.")


def naive_solver(scenario, tools) -> AgentResult:
    """Grab the first available driver and book it onto the first open load.

    No eligibility checks, no detail lookups, no fault recovery — the kind of
    shallow behavior the harness must catch.
    """
    available = tools.list_available_drivers().get("drivers", [])
    if not available:
        return AgentResult(rationale="No drivers listed; did nothing.")
    open_load = next(
        (lid for lid, ld in tools.world.loads.items() if ld.status == "unassigned"),
        scenario.expected.load_id,
    )
    tools.assign_driver_to_load(available[0]["id"], open_load)
    return AgentResult(rationale="Assigned the first available driver.")
