"""Tests for core data models — serialization round-trips and validation."""

import json
import warnings

import pytest
from pydantic import ValidationError

from agent_evaluator.models import (
    AgentTrajectory,
    DimensionScore,
    EvaluationResult,
    MockResponse,
    Scenario,
    ToolCall,
    ToolDefinition,
    ToolResponse,
    TrajectoryStep,
)


def make_trajectory() -> AgentTrajectory:
    return AgentTrajectory(
        scenario_id="test_scenario",
        model_id="test-model",
        steps=[
            TrajectoryStep(
                step_index=0,
                thought="I should search for weather",
                tool_call=ToolCall(
                    tool_name="get_weather",
                    parameters={"city": "London"},
                ),
                tool_response=ToolResponse(
                    tool_name="get_weather",
                    result={"temp_f": 55, "condition": "Cloudy"},
                    latency_ms=42.0,
                ),
            ),
        ],
        final_answer="The weather in London is 55°F and cloudy.",
        total_duration_ms=1500.0,
    )


class TestTrajectoryRoundTrip:
    def test_serialize_deserialize(self):
        trajectory = make_trajectory()
        json_str = trajectory.model_dump_json()
        restored = AgentTrajectory.model_validate_json(json_str)
        assert restored.scenario_id == trajectory.scenario_id
        assert len(restored.steps) == 1
        assert restored.steps[0].tool_call.tool_name == "get_weather"
        assert restored.final_answer == trajectory.final_answer

    def test_empty_trajectory(self):
        t = AgentTrajectory(
            scenario_id="empty",
            model_id="test",
            steps=[],
        )
        assert t.final_answer is None
        assert t.total_duration_ms is None


class TestDimensionScore:
    def test_valid_score(self):
        s = DimensionScore(dimension="test", score=0.85, reasoning="Good")
        assert s.score == 0.85

    def test_score_out_of_range(self):
        with pytest.raises(ValidationError):
            DimensionScore(dimension="test", score=1.5, reasoning="Too high")

        with pytest.raises(ValidationError):
            DimensionScore(dimension="test", score=-0.1, reasoning="Too low")

    def test_default_status_ok(self):
        s = DimensionScore(dimension="test", score=0.5, reasoning="x")
        assert s.status == "ok"
        assert s.error_type is None

    def test_status_error_with_error_type(self):
        s = DimensionScore(
            dimension="test",
            score=0.0,
            reasoning="Evaluation failed: RateLimitError",
            status="error",
            error_type="RateLimitError",
        )
        json_str = s.model_dump_json()
        restored = DimensionScore.model_validate_json(json_str)
        assert restored.status == "error"
        assert restored.error_type == "RateLimitError"

    def test_default_judge_method_llm(self):
        s = DimensionScore(dimension="x", score=0.5, reasoning="y")
        assert s.judge_method == "llm"

    def test_judge_method_deterministic_round_trip(self):
        s = DimensionScore(
            dimension="efficiency", score=0.8, reasoning="2 steps",
            judge_method="deterministic",
        )
        json_str = s.model_dump_json()
        restored = DimensionScore.model_validate_json(json_str)
        assert restored.judge_method == "deterministic"

    def test_score_none_for_na_round_trips(self):
        """Non-ok dims carry score=None, not a sentinel 0.0. None must survive
        the JSON round-trip so consumers can test `score is not None`."""
        s = DimensionScore(
            dimension="error_recovery", reasoning="N/A", status="na",
        )
        assert s.score is None
        restored = DimensionScore.model_validate_json(s.model_dump_json())
        assert restored.score is None
        assert restored.status == "na"

    def test_score_none_for_error_round_trips(self):
        s = DimensionScore(
            dimension="parameter_quality", score=None, reasoning="failed",
            status="error", error_type="RateLimitError",
        )
        restored = DimensionScore.model_validate_json(s.model_dump_json())
        assert restored.score is None
        assert restored.status == "error"

    def test_legitimate_zero_still_allowed(self):
        """A genuine 0.0 with status=ok (e.g. no final answer) is distinct from
        the None sentinel and must remain valid."""
        s = DimensionScore(dimension="final_correctness", score=0.0, reasoning="x")
        assert s.score == 0.0
        assert s.status == "ok"

    def test_score_bounds_still_enforced(self):
        """Optional[float] must not relax the [0,1] bound for real values."""
        with pytest.raises(ValidationError):
            DimensionScore(dimension="x", score=1.5, reasoning="y")


def _make_eval(*, partial_dim: bool = False) -> EvaluationResult:
    """Helper: build an EvaluationResult with optional one errored dim."""
    ok = DimensionScore(dimension="tool_selection", score=0.9, reasoning="g")
    if partial_dim:
        bad = DimensionScore(
            dimension="efficiency",
            score=0.0,
            reasoning="Evaluation failed: RateLimitError",
            status="error",
            error_type="RateLimitError",
        )
        dims = [ok, bad]
    else:
        dims = [ok, DimensionScore(dimension="efficiency", score=0.7, reasoning="ok")]
    return EvaluationResult(
        scenario_id="test",
        model_id="test-model",
        dimension_scores=dims,
        overall_score=0.8,
        summary="Solid performance",
    )


class TestEvaluationResult:
    def test_round_trip(self):
        result = _make_eval()
        json_str = result.model_dump_json()
        restored = EvaluationResult.model_validate_json(json_str)
        assert restored.overall_score == 0.8
        assert len(restored.dimension_scores) == 2

    def test_legacy_detection(self):
        legacy_json = json.dumps(
            {
                "scenario_id": "x",
                "model_id": "y",
                "dimension_scores": [],
                "overall_score": 0.0,
                "summary": "z",
            }
        )
        with pytest.warns(DeprecationWarning, match="legacy eval"):
            restored = EvaluationResult.from_json(legacy_json)
        assert restored.legacy is True
        assert restored.schema_version == 1  # preserved for visibility

    def test_current_schema_from_json_no_warning(self):
        # Round-trip a freshly-dumped result; current schema_version expected.
        result = _make_eval()
        json_str = result.model_dump_json()
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            restored = EvaluationResult.from_json(json_str)
        assert restored.legacy is False
        assert restored.schema_version == 3

    def test_construction_does_not_emit_legacy_warning(self):
        # In-code construction must never trigger the legacy warning
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            result = _make_eval()
        assert result.legacy is False
        assert result.schema_version == 3

    def test_partial_true_when_any_error(self):
        result = _make_eval(partial_dim=True)
        assert result.partial is True
        dumped = json.loads(result.model_dump_json())
        assert dumped["partial"] is True

    def test_partial_false_when_all_ok(self):
        result = _make_eval()
        assert result.partial is False
        dumped = json.loads(result.model_dump_json())
        assert dumped["partial"] is False

    def test_partial_round_trip(self):
        result = _make_eval(partial_dim=True)
        json_str = result.model_dump_json()
        restored = EvaluationResult.model_validate_json(json_str)
        # partial recomputes from dimension_scores on load (computed_field is read-only)
        assert restored.partial is True

    def test_v2_eval_loads_under_v3_with_default_method(self):
        """Phase 4 D3: v2 files load cleanly under v3 — schema_version=2 in
        input is preserved (not overwritten by v3 default), no legacy flag,
        all dims default judge_method='llm' (accurate for v2 content)."""
        v2_eval = json.dumps({
            "schema_version": 2,
            "scenario_id": "x",
            "model_id": "y",
            "dimension_scores": [
                {"dimension": "tool_selection", "score": 0.85, "reasoning": "good"},
            ],
            "overall_score": 0.85,
            "summary": "ok",
        })
        # v2 schema_version doesn't trigger legacy (only < 2 does)
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            restored = EvaluationResult.from_json(v2_eval)
        assert restored.legacy is False
        assert restored.schema_version == 2  # preserves the v2 marker
        assert restored.dimension_scores[0].judge_method == "llm"  # default applied

    def test_new_eval_has_schema_version_3(self):
        result = EvaluationResult(
            scenario_id="x", model_id="y",
            dimension_scores=[DimensionScore(dimension="x", score=0.5, reasoning="y")],
            overall_score=0.5, summary="ok",
        )
        assert result.schema_version == 3

    def test_partial_false_when_only_na_dims(self):
        """Phase 2 D3: N/A status should NOT make a result partial.

        N/A means 'this dim doesn't apply to this scenario' (e.g., error_recovery
        on a no-injection scenario). It's routine; partial=True is reserved for
        actual evaluation errors.
        """
        result = EvaluationResult(
            scenario_id="test",
            model_id="test-model",
            dimension_scores=[
                DimensionScore(
                    dimension="tool_selection", score=0.9, reasoning="ok"
                ),
                DimensionScore(
                    dimension="error_recovery", score=0.0,
                    reasoning="N/A — no errors injected",
                    status="na", error_type=None,
                ),
            ],
            overall_score=0.9, summary="ok",
        )
        assert result.partial is False
        dumped = json.loads(result.model_dump_json())
        assert dumped["partial"] is False


class TestMockResponse:
    def test_default_match(self):
        r = MockResponse(response={"data": "test"})
        assert r.match == {}
        assert r.error is None

    def test_error_response(self):
        r = MockResponse(response={}, error="Not found")
        assert r.error == "Not found"


class TestScenario:
    def test_minimal_scenario(self):
        s = Scenario(
            id="test",
            name="Test",
            description="A test",
            user_query="Do something",
            available_tools=[
                ToolDefinition(
                    name="tool1",
                    description="A tool",
                    parameters_schema={"type": "object", "properties": {}},
                ),
            ],
            expected_tool_sequence=["tool1"],
            expected_final_answer_contains=["result"],
            max_reasonable_steps=3,
        )
        assert s.difficulty.value == "medium"
        assert len(s.available_tools) == 1
