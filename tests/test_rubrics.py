"""Tests for rubric definitions and scoring."""

from agent_evaluator.models import (
    AgentTrajectory,
    DimensionScore,
    Scenario,
    ToolCall,
    ToolDefinition,
    ToolResponse,
    TrajectoryStep,
)
from agent_evaluator.rubrics import (
    DETECTORS,
    RUBRICS,
    _detect_efficiency,
    _detect_final_correctness,
    _detect_tool_selection,
    compute_overall_score,
)


def _ds(dim: str, score: float, *, status: str = "ok", error_type: str | None = None) -> DimensionScore:
    return DimensionScore(
        dimension=dim,
        score=score,
        reasoning="x",
        status=status,
        error_type=error_type,
    )


class TestRubrics:
    def test_all_dimensions_defined(self):
        expected = {
            "tool_selection",
            "parameter_quality",
            "efficiency",
            "error_recovery",
            "final_correctness",
        }
        assert set(RUBRICS.keys()) == expected

    def test_weights_sum_to_one(self):
        total = sum(r.weight for r in RUBRICS.values())
        assert abs(total - 1.0) < 0.01

    def test_rubric_has_score_anchors(self):
        for name, rubric in RUBRICS.items():
            assert rubric.score_anchors, f"{name} missing score anchors"
            assert "1.0" in rubric.score_anchors, f"{name} missing 1.0 anchor"
            assert "0.0" in rubric.score_anchors, f"{name} missing 0.0 anchor"

    def test_error_recovery_template_no_unreachable_branch(self):
        """Phase 2 D4: the unreachable no-error branch is removed.

        Post-Phase-2 the short-circuit in judge.py prevents the LLM from
        seeing the no-error case, so the rubric template must not contain
        the dead 'No errors occurred. Score this as 1.0' instruction or its
        guarding Jinja conditional. Defends against accidental re-addition.
        See .planning/research/JUDGMENT.md F-B.
        """
        template = RUBRICS["error_recovery"].user_prompt_template
        assert "Score this as 1.0" not in template
        assert "{% if error_steps" not in template
        assert "No errors occurred." not in template


class TestOverallScore:
    def test_perfect_scores(self):
        scores = [_ds(dim, 1.0) for dim in RUBRICS]
        assert compute_overall_score(scores) == 1.0

    def test_zero_scores(self):
        scores = [_ds(dim, 0.0) for dim in RUBRICS]
        assert compute_overall_score(scores) == 0.0

    def test_partial_scores(self):
        scores = [
            _ds("tool_selection", 0.8),
            _ds("parameter_quality", 0.6),
            _ds("efficiency", 0.9),
            _ds("error_recovery", 1.0),
            _ds("final_correctness", 0.7),
        ]
        result = compute_overall_score(scores)
        assert 0.0 < result < 1.0

    def test_missing_dimension(self):
        scores = [_ds("tool_selection", 1.0)]
        result = compute_overall_score(scores)
        assert result == 1.0  # only counts available dimension

    def test_excludes_errored_dim(self):
        # 4 ok dims + 1 errored — result should match 4-dim renormalized score
        scores = [
            _ds("tool_selection", 1.0),
            _ds("parameter_quality", 1.0),
            _ds("efficiency", 1.0),
            _ds("final_correctness", 1.0),
            _ds("error_recovery", 0.0, status="error", error_type="RateLimitError"),
        ]
        result = compute_overall_score(scores)
        # all 4 ok dims at 1.0 → renormalized 1.0
        assert result == 1.0

    def test_excludes_na_dim(self):
        # status="na" should behave identically to status="error" for aggregation
        scores = [
            _ds("tool_selection", 0.8),
            _ds("parameter_quality", 0.8),
            _ds("efficiency", 0.8),
            _ds("final_correctness", 0.8),
            _ds("error_recovery", 1.0, status="na"),  # would normally inflate
        ]
        result = compute_overall_score(scores)
        # with error_recovery excluded, all remaining at 0.8 → 0.8 renormalized
        assert result == 0.8

    def test_all_errored_returns_zero(self):
        scores = [_ds(dim, 0.5, status="error", error_type="X") for dim in RUBRICS]
        assert compute_overall_score(scores) == 0.0  # total_weight==0 branch


# ---------- Phase 4: judge_method on Rubric + DETECTORS dict ----------


class TestRubricJudgeMethod:
    def test_default_judge_method_is_llm(self):
        assert RUBRICS["parameter_quality"].judge_method == "llm"
        assert RUBRICS["error_recovery"].judge_method == "llm"

    def test_deterministic_dims_marked(self):
        assert RUBRICS["tool_selection"].judge_method == "deterministic"
        assert RUBRICS["efficiency"].judge_method == "deterministic"
        assert RUBRICS["final_correctness"].judge_method == "deterministic"


class TestDETECTORSRegistry:
    def test_detectors_dict_has_three_entries(self):
        assert set(DETECTORS.keys()) == {"tool_selection", "efficiency", "final_correctness"}

    def test_all_deterministic_rubrics_have_detectors(self):
        for dim, rubric in RUBRICS.items():
            if rubric.judge_method == "deterministic":
                assert dim in DETECTORS, f"{dim} marked deterministic but no detector"
            else:
                assert dim not in DETECTORS, f"{dim} is LLM but in DETECTORS"


def _scenario(**overrides):
    defaults = dict(
        id="x",
        name="X",
        description="x",
        user_query="x",
        available_tools=[
            ToolDefinition(
                name="get_weather",
                description="x",
                parameters_schema={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="search",
                description="x",
                parameters_schema={"type": "object", "properties": {}},
            ),
        ],
        expected_tool_sequence=["get_weather"],
        expected_final_answer_contains=["55", "cloudy"],
        max_reasonable_steps=2,
    )
    defaults.update(overrides)
    return Scenario(**defaults)


def _step(idx, name, params=None):
    return TrajectoryStep(
        step_index=idx,
        tool_call=ToolCall(tool_name=name, parameters=params or {}),
        tool_response=ToolResponse(tool_name=name, result={}),
    )


class TestToolSelectionDetector:
    def test_exact_match(self):
        scen = _scenario(expected_tool_sequence=["a", "b"])
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[_step(0, "a"), _step(1, "b")],
        )
        ds = _detect_tool_selection(traj, scen)
        assert ds.score == 1.0
        assert ds.judge_method == "deterministic"
        assert ds.status == "ok"

    def test_complete_miss(self):
        scen = _scenario(expected_tool_sequence=["a"])
        traj = AgentTrajectory(
            scenario_id="x", model_id="m", steps=[_step(0, "z")],
        )
        ds = _detect_tool_selection(traj, scen)
        assert ds.score == 0.0

    def test_partial_overlap(self):
        scen = _scenario(expected_tool_sequence=["a", "b", "c"])
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[_step(0, "a"), _step(1, "c")],
        )
        ds = _detect_tool_selection(traj, scen)
        # LCS={a,c}=2, max(3,2)=3 → 2/3 ≈ 0.667
        assert 0.5 < ds.score < 0.8

    def test_empty_traj_and_expected(self):
        scen = _scenario(expected_tool_sequence=[])
        traj = AgentTrajectory(scenario_id="x", model_id="m", steps=[])
        ds = _detect_tool_selection(traj, scen)
        assert ds.score == 1.0  # vacuous match


class TestEfficiencyDetector:
    def test_under_budget(self):
        scen = _scenario(expected_tool_sequence=["a"], max_reasonable_steps=3)
        traj = AgentTrajectory(
            scenario_id="x", model_id="m", steps=[_step(0, "a")],
        )
        ds = _detect_efficiency(traj, scen)
        assert ds.score == 1.0
        assert ds.judge_method == "deterministic"

    def test_over_budget_with_loops(self):
        scen = _scenario(expected_tool_sequence=["a"], max_reasonable_steps=2)
        # 4 identical steps = 3 consecutive-identical pairs
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[_step(i, "a", {"q": "foo"}) for i in range(4)],
        )
        ds = _detect_efficiency(traj, scen)
        # over budget AND penalized for loops → low score
        assert ds.score < 0.5

    def test_within_budget_no_loops(self):
        scen = _scenario(
            expected_tool_sequence=["a", "b"], max_reasonable_steps=4
        )
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[_step(0, "a"), _step(1, "b"), _step(2, "c")],
        )
        ds = _detect_efficiency(traj, scen)
        # 3 steps, expected=2, max=4: linear interp 1.0 → 0.7
        # ratio = 1/2 → base = 1.0 - 0.15 = 0.85
        assert 0.7 < ds.score < 1.0


class TestFinalCorrectnessDetector:
    def test_full_match_terminated(self):
        scen = _scenario(expected_final_answer_contains=["55", "cloudy"])
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[_step(0, "get_weather")],
            final_answer="The weather is 55°F and Cloudy.",
        )
        ds = _detect_final_correctness(traj, scen)
        assert ds.score == 1.0
        assert ds.judge_method == "deterministic"

    def test_partial_match(self):
        scen = _scenario(expected_final_answer_contains=["55", "cloudy"])
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[_step(0, "get_weather")],
            final_answer="It's 55 degrees today.",
        )
        ds = _detect_final_correctness(traj, scen)
        # 1/2 substrings match, terminated ok → 0.5
        assert ds.score == 0.5

    def test_no_termination(self):
        scen = _scenario(expected_final_answer_contains=["55"])
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[_step(0, "get_weather")],
            final_answer=None,
        )
        ds = _detect_final_correctness(traj, scen)
        assert ds.score == 0.0
        assert "did not terminate" in ds.reasoning.lower()

    def test_terminated_over_budget(self):
        scen = _scenario(
            expected_final_answer_contains=["x"], max_reasonable_steps=1
        )
        # max_reasonable_steps=1, grace=6, 8 steps → over budget
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[_step(i, "get_weather") for i in range(8)],
            final_answer="x is here",
        )
        ds = _detect_final_correctness(traj, scen)
        # full match (1/1) but over-budget multiplier 0.7 → 0.7
        assert ds.score == 0.7
