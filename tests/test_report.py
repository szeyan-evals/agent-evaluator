"""Report rendering edge-case tests (Phase 5 TEST-03).

Covers generate_report and generate_comparison_report for:
  - Empty results list
  - All-ok results (no partial markers)
  - Partial row (one errored dimension — score=None, renders as err*)
  - All-legacy results (no active rows)
  - Comparison report with a partial row

Dimension names are the five real RUBRICS keys from src/agent_evaluator/rubrics.py:
  tool_selection, parameter_quality, efficiency, error_recovery, final_correctness
There is NO final_answer_quality — that name is fictional and scores under it
would be silently dropped by generate_report (which iterates RUBRICS.keys()).

Non-ok DimensionScores carry score=None (not 0.0); errored cells render as
"err*" (not a number with an asterisk). See models.py DimensionScore docstring.

NOTE on bold vs partial asterisk:
  generate_report always emits Markdown bold markers (e.g. **0.80**).
  The string "**0.80**" contains "0.80*" as a substring (digits + first
  closing bold asterisk), so `assert "0.80*" not in report` always fails when
  the positive `assert "**0.80**" in report` passes. The correct gate strips
  bold markers first: `assert "0.80*" not in report.replace("**", "")`.
"""

from __future__ import annotations


from agent_evaluator.models import DimensionScore, EvaluationResult
from agent_evaluator.report import generate_comparison_report, generate_report

# ---------------------------------------------------------------------------
# Five real RUBRICS dimension names — ORDER doesn't matter for the factory,
# but these exact strings must be used everywhere in this file.
# ---------------------------------------------------------------------------
_DIMS = [
    "tool_selection",
    "parameter_quality",
    "efficiency",
    "error_recovery",
    "final_correctness",
]


# ---------------------------------------------------------------------------
# Shared factory
# ---------------------------------------------------------------------------


def _make_result(
    scenario_id: str = "s1",
    model_id: str = "m1",
    scores: list[DimensionScore] | None = None,
    overall_score: float = 0.8,
    schema_version: int = 3,
    legacy: bool = False,
) -> EvaluationResult:
    """Build an EvaluationResult with sensible defaults for all five dimensions."""
    if scores is None:
        scores = [
            DimensionScore(dimension=d, score=0.8, reasoning="ok", status="ok")
            for d in _DIMS
        ]
    return EvaluationResult(
        schema_version=schema_version,
        legacy=legacy,
        scenario_id=scenario_id,
        model_id=model_id,
        dimension_scores=scores,
        overall_score=overall_score,
        summary="test",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_generate_report_empty():
    """Empty list → single-line message from report.py line 77."""
    report = generate_report([])
    assert "No results to report." in report


def test_generate_report_all_ok():
    """One all-ok result: scenario appears, no partial footnote, clean overall cell."""
    result = _make_result()
    report = generate_report([result])

    # Scenario id must appear in the table
    assert "s1" in report

    # No partial footnote section (all dims are status="ok")
    assert "Partial evaluations" not in report

    # Overall cell for a non-partial row: **0.80** (bold, no trailing asterisk)
    assert "**0.80**" in report

    # Negative partial-suffix check: strip bold markers first so "**0.80**"
    # doesn't masquerade as "0.80*" (the partial-score-suffix form).
    assert "0.80*" not in report.replace("**", "")


def test_generate_report_partial_row():
    """One errored dimension → err* cell, partial footnote, error_type surfaced."""
    error_score = DimensionScore(
        dimension="parameter_quality",
        score=None,
        reasoning="failed",
        status="error",
        error_type="ValueError",
    )
    # Four ok dims + one errored dim
    ok_dims = [d for d in _DIMS if d != "parameter_quality"]
    scores = [
        DimensionScore(dimension=d, score=0.8, reasoning="ok", status="ok")
        for d in ok_dims
    ]
    scores.append(error_score)

    result = _make_result(scores=scores)
    report = generate_report([result])

    # Partial footnote heading must appear (from report.py line 45)
    assert "Partial evaluations" in report

    # Errored dim cell renders as "err*" (score=None → _render_dim_cell → "err*")
    assert "err*" in report

    # error_type surfaces in the footnote
    assert "ValueError" in report


def test_generate_report_all_legacy():
    """All-legacy results: main table skipped, both legacy messages appear."""
    result = _make_result(schema_version=1, legacy=True)
    report = generate_report([result])

    # Main table replacement message (report.py line 85)
    assert "No non-legacy results to report." in report

    # Legacy footnote heading (report.py line 62)
    assert "Legacy evaluations excluded" in report


def test_generate_comparison_report_partial():
    """Comparison report with one partial model row: err* cell + footnote."""
    ok_result = _make_result(scenario_id="s1", model_id="m1")

    # Build partial result for m2: one errored dimension
    error_score = DimensionScore(
        dimension="error_recovery",
        score=None,
        reasoning="failed",
        status="error",
        error_type="RuntimeError",
    )
    ok_dims = [d for d in _DIMS if d != "error_recovery"]
    partial_scores = [
        DimensionScore(dimension=d, score=0.7, reasoning="ok", status="ok")
        for d in ok_dims
    ]
    partial_scores.append(error_score)
    partial_result = _make_result(
        scenario_id="s1", model_id="m2", scores=partial_scores, overall_score=0.7
    )

    report = generate_comparison_report({"m1": [ok_result], "m2": [partial_result]})

    # Errored dim cell renders as "err*" in the comparison table
    assert "err*" in report

    # Partial footnote present because m2's row is partial
    assert "Partial evaluations" in report
