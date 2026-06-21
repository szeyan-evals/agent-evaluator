"""Step 2 verification: the dispatch scenario set is well-formed and self-consistent.

These tests prove the scenarios are authored correctly — every scenario has a
valid solution, the traps are genuinely traps, and `check_outcome` grades both
right and wrong final worlds correctly. (Running an actual agent against them is
a later phase.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest  # noqa: E402

from agent_evaluator.dispatch import (  # noqa: E402
    DispatchTools,
    all_scenarios,
    check_outcome,
    legal_drivers,
    scenario_by_id,
)

SCENARIOS = all_scenarios()
LAYERS = {"L1", "L2", "L3", "L4", "L5", "L6"}


def _ids():
    return [sc.id for sc in SCENARIOS]


def test_scenarios_have_unique_ids():
    assert len(_ids()) == len(set(_ids()))


def test_all_six_layers_covered():
    assert {sc.layer for sc in SCENARIOS} == LAYERS


def test_target_count_is_small_and_high_quality():
    # The set is intentionally compact (~12-16), not hundreds.
    assert 12 <= len(SCENARIOS) <= 18


@pytest.mark.parametrize("sc", SCENARIOS, ids=_ids())
def test_scenario_is_self_consistent(sc):
    """The declared answer must actually be achievable, and the situation must
    match the kind of answer claimed."""
    load = sc.world.loads[sc.expected.load_id]
    legal = legal_drivers(sc.world, load)

    if sc.expected.kind == "no_assign":
        # The whole point: there is genuinely no legal driver.
        assert legal == [], f"{sc.id}: no_assign but legal drivers exist: {legal}"
    else:
        assert legal, f"{sc.id}: needs at least one legal driver"

    if sc.expected.kind == "assign":
        cid = sc.expected.correct_driver_id
        assert cid is not None, f"{sc.id}: kind=assign requires correct_driver_id"
        assert cid in legal, f"{sc.id}: declared correct driver {cid} is not legal"


@pytest.mark.parametrize("sc", SCENARIOS, ids=_ids())
def test_trap_drivers_are_tempting_but_wrong(sc):
    """Each declared trap must be (a) tempting — on duty and selectable — and
    (b) wrong — booking it is graded incorrect. A trap may be illegal (hard
    violation) or merely suboptimal (legal but not the right call)."""
    for tid in sc.expected.trap_driver_ids:
        d = sc.world.drivers[tid]
        assert d.on_duty and d.active_load_id is None, f"{sc.id}: trap {tid} isn't selectable"
        bad_world = _apply(sc, tid)
        assert check_outcome(sc, bad_world)["correct"] is False, (
            f"{sc.id}: trap {tid} was graded correct"
        )


def _apply(sc, driver_id):
    """Run a fresh copy of the scenario world and book driver_id onto the load."""
    sc = scenario_by_id(sc.id)  # fresh deep copy via rebuild
    tools = DispatchTools(sc.world)
    tools.assign_driver_to_load(driver_id, sc.expected.load_id)
    return sc.world


@pytest.mark.parametrize("sc", [s for s in SCENARIOS if s.expected.kind == "assign"], ids=lambda s: s.id)
def test_check_outcome_passes_correct_and_fails_trap(sc):
    correct_world = _apply(sc, sc.expected.correct_driver_id)
    assert check_outcome(sc, correct_world)["correct"] is True

    for tid in sc.expected.trap_driver_ids:
        bad_world = _apply(sc, tid)
        assert check_outcome(sc, bad_world)["correct"] is False


def test_no_assign_scenario_grading():
    sc = scenario_by_id("l4_no_legal_option_injection")
    # Refusing (leaving it unassigned) is correct.
    assert check_outcome(sc, scenario_by_id(sc.id).world)["correct"] is True
    # Caving to the injection and booking the illegal driver is wrong.
    bad = _apply(sc, "D1")
    assert check_outcome(sc, bad)["correct"] is False


def test_injection_scenarios_carry_the_attack_in_load_notes():
    for sc in SCENARIOS:
        if sc.layer == "L4":
            load = sc.world.loads[sc.expected.load_id]
            assert load.notes.strip(), f"{sc.id}: L4 scenario must carry an injected note"


def test_stability_scenario_requests_multiple_trials():
    assert scenario_by_id("l5_consistency").trials == 8


def test_l3_error_recovery_declares_a_fault():
    sc = scenario_by_id("l3_error_recovery")
    assert sc.fault is not None and sc.fault.tool == "get_distance"


def test_declared_faults_reference_real_tools():
    tool_names = {
        "list_available_drivers", "get_driver", "get_load",
        "get_hours_of_service", "get_distance", "assign_driver_to_load",
    }
    for sc in SCENARIOS:
        if sc.fault is not None:
            assert sc.fault.tool in tool_names, f"{sc.id}: fault on unknown tool {sc.fault.tool}"


def test_business_risk_costs_span_the_spectrum():
    costs = {sc.error_cost for sc in SCENARIOS}
    assert {"low", "high"} <= costs
