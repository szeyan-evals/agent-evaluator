"""Tests for the None-sentinel rendering and cost estimation added alongside
the Optional[float] score change. Kept separate from the Phase 5 test_report.py
so the two don't collide."""

from agent_evaluator.models import DimensionScore, EvaluationResult
from agent_evaluator.pricing import estimate_cost
from agent_evaluator.report import (
    _render_dim_cell,
    generate_comparison_report,
    generate_report,
)


def _result(*, dims, cost=None, scenario="s1", model="claude-sonnet-4-x"):
    return EvaluationResult(
        scenario_id=scenario,
        model_id=model,
        dimension_scores=dims,
        overall_score=0.80,
        summary="x",
        cost_usd=cost,
    )


class TestRenderDimCell:
    def test_ok_renders_number(self):
        ds = DimensionScore(dimension="x", score=0.85, reasoning="r")
        assert _render_dim_cell(ds) == "0.85"

    def test_na_renders_dashes(self):
        ds = DimensionScore(dimension="x", reasoning="r", status="na")
        assert _render_dim_cell(ds) == "--"

    def test_error_renders_err_marker_without_number(self):
        """Error score is None — the cell must not try to format it as a float
        and must carry the partial '*' marker."""
        ds = DimensionScore(
            dimension="x", score=None, reasoning="boom",
            status="error", error_type="ValueError",
        )
        assert _render_dim_cell(ds) == "err*"

    def test_missing_renders_dashes(self):
        assert _render_dim_cell(None) == "--"


class TestReportSurfacesCostAndStatuses:
    def test_error_and_na_render_without_crash(self):
        dims = [
            DimensionScore(dimension="tool_selection", score=0.9, reasoning="g"),
            DimensionScore(dimension="error_recovery", reasoning="N/A", status="na"),
            DimensionScore(
                dimension="parameter_quality", score=None, reasoning="boom",
                status="error", error_type="ValueError",
            ),
        ]
        report = generate_report([_result(dims=dims)])
        assert "err*" in report          # errored cell marker
        assert "--" in report            # na cell
        assert "Partial evaluations" in report
        assert "ValueError" in report

    def test_cost_line_present_when_known(self):
        dims = [DimensionScore(dimension="tool_selection", score=0.9, reasoning="g")]
        report = generate_report([_result(dims=dims, cost=0.0123)])
        assert "Run cost (est.)" in report
        assert "$0.0123" in report

    def test_cost_line_absent_when_none(self):
        dims = [DimensionScore(dimension="tool_selection", score=0.9, reasoning="g")]
        report = generate_report([_result(dims=dims, cost=None)])
        assert "Run cost" not in report

    def test_comparison_report_handles_errored_cells(self):
        dims = [
            DimensionScore(
                dimension="parameter_quality", score=None, reasoning="boom",
                status="error", error_type="ValueError",
            ),
        ]
        out = generate_comparison_report({"m1": [_result(dims=dims)]})
        assert "err*" in out


class TestEstimateCost:
    def test_known_model_exact(self):
        # gpt-4o: $2.50 in / $10 out per 1M
        cost = estimate_cost("gpt-4o", 1_000_000, 1_000_000)
        assert cost == 12.5

    def test_prefix_match_with_date_suffix(self):
        # claude-sonnet-4-20250514 should match the "claude-sonnet-4" prefix
        cost = estimate_cost("claude-sonnet-4-20250514", 1130, 259)
        # (1130*3 + 259*15) / 1e6 = 0.007275
        assert cost == round((1130 * 3.0 + 259 * 15.0) / 1_000_000, 6)

    def test_longest_prefix_wins(self):
        # gpt-4o-mini must not be priced as gpt-4o
        mini = estimate_cost("gpt-4o-mini", 1_000_000, 0)
        full = estimate_cost("gpt-4o", 1_000_000, 0)
        assert mini == 0.15
        assert full == 2.50

    def test_unknown_model_returns_none(self):
        assert estimate_cost("some-unknown-model", 100, 100) is None

    def test_missing_tokens_returns_none(self):
        assert estimate_cost("gpt-4o", None, 100) is None
        assert estimate_cost("gpt-4o", 100, None) is None
