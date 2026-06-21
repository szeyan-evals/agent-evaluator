"""Step 3 verification: the scoring harness runs and discriminates.

The reference solver (answer key) must pass every scenario; the naive solver
(first-available, no checks, no recovery) must be caught on the trap scenarios.
Also pins fresh-world isolation, fault recovery, pass^k, the L2/L3 layer rules,
and report rendering — all hermetic (no API).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_evaluator.dispatch import (  # noqa: E402
    evaluate_all,
    keyword_reasoning_judge,
    naive_solver,
    reference_solver,
    render_dispatch_report,
    run_once,
    scenario_by_id,
    score_scenario,
)


def test_run_once_uses_a_fresh_world():
    sc = scenario_by_id("l1_equipment")
    run_once(sc, naive_solver)
    # The shared scenario world is untouched — the run acts on a deep copy.
    assert sc.world.loads["L1"].status == "unassigned"
    assert sc.world.drivers["D1"].active_load_id is None


def test_fault_is_injected_then_recovered():
    sc = scenario_by_id("l3_error_recovery")
    rec = run_once(sc, reference_solver)
    # get_distance was called (and faulted on the first call), yet the agent
    # still reached the correct assignment by retrying.
    assert any(c["tool"] == "get_distance" for c in rec.calls)
    assert rec.final_world.loads["L1"].assigned_driver_id == "D2"


def test_reference_solver_passes_every_scenario():
    report = evaluate_all(reference_solver)
    failed = [r.id for r in report.results if not r.passed]
    assert failed == [], f"reference solver should pass all scenarios; failed: {failed}"
    assert report.release_signal()[0] == "GO-candidate"


def test_naive_solver_is_caught_on_traps():
    report = evaluate_all(naive_solver)
    by_id = {r.id: r for r in report.results}
    must_fail = [
        "l1_equipment", "l1_hours_of_service", "l1_customer_ban",
        "l4_equipment_override_injection", "l4_ban_override_injection",
        "l4_no_legal_option_injection", "l3_check_hos_first", "l3_error_recovery",
        "l5_consistency", "l2_tier_tiebreak",
    ]
    still_passing = [sid for sid in must_fail if by_id[sid].passed]
    assert not still_passing, f"naive solver wrongly passed: {still_passing}"

    passed, total = report.overall()
    assert passed < total
    # High-cost injection failures must force the mechanical signal to NO-GO.
    assert report.release_signal()[0] == "NO-GO"


def test_pass_caret_k_for_stability_scenario():
    ref = score_scenario(scenario_by_id("l5_consistency"), reference_solver)
    assert ref.trials == 8 and ref.trial_passes == 8 and ref.passed is True
    nai = score_scenario(scenario_by_id("l5_consistency"), naive_solver)
    assert nai.trial_passes == 0 and nai.passed is False


def test_l3_requires_information_gathering():
    # naive assigns straight off the stub list — never looks anything up.
    assert score_scenario(scenario_by_id("l3_check_hos_first"), naive_solver).passed is False
    assert score_scenario(scenario_by_id("l3_check_hos_first"), reference_solver).passed is True


def test_l2_requires_sound_reasoning_not_just_outcome():
    # On l2_missing_endorsement naive happens to pick the right driver (D1), but
    # its rationale cites no decision factor, so the L2 verdict still fails.
    nai = score_scenario(scenario_by_id("l2_missing_endorsement"), naive_solver)
    assert nai.passed is False
    ref = score_scenario(scenario_by_id("l2_missing_endorsement"), reference_solver)
    assert ref.passed is True


def test_keyword_reasoning_judge():
    sc = scenario_by_id("l1_equipment")
    assert keyword_reasoning_judge(sc, "D2 has the reefer equipment required")[0] is True
    assert keyword_reasoning_judge(sc, "because I said so")[0] is False


def test_report_renders_the_evidence():
    md = render_dispatch_report(evaluate_all(reference_solver))
    assert "# Dispatch Agent Evaluation" in md
    assert "Pass rate by layer" in md
    assert "Release signal (mechanical)" in md
    assert "Per-scenario results" in md
