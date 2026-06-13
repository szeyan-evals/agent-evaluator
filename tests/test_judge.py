"""Tests for judge short-circuit logic (Phase 2 D1+D2).

These tests use a fake client that records SDK calls — the short-circuit
must complete WITHOUT invoking the LLM API. See 02-CONTEXT.md D1.
"""

import pytest

from agent_evaluator.judge import AnthropicJudge
from agent_evaluator.models import (
    AgentTrajectory,
    ErrorInjection,
    Scenario,
    ToolDefinition,
)


def _scenario_no_injection() -> Scenario:
    return Scenario(
        id="weather_test",
        name="Weather Test",
        description="Look up weather",
        user_query="What's the weather?",
        available_tools=[
            ToolDefinition(
                name="get_weather",
                description="Get weather",
                parameters_schema={"type": "object", "properties": {}},
            ),
        ],
        expected_tool_sequence=["get_weather"],
        expected_final_answer_contains=["weather"],
        max_reasonable_steps=2,
        error_injection=[],
    )


def _scenario_with_injection() -> Scenario:
    return Scenario(
        id="debug_test",
        name="Debug Test",
        description="Debug code with injected errors",
        user_query="Find the bug",
        available_tools=[
            ToolDefinition(
                name="run_tests",
                description="Run tests",
                parameters_schema={"type": "object", "properties": {}},
            ),
        ],
        expected_tool_sequence=["run_tests"],
        expected_final_answer_contains=["fixed"],
        max_reasonable_steps=3,
        error_injection=[
            ErrorInjection(
                tool_name="run_tests",
                trigger_on_call_number=1,
                error_message="Module not found",
            ),
        ],
    )


def _empty_trajectory(scenario_id: str) -> AgentTrajectory:
    return AgentTrajectory(
        scenario_id=scenario_id,
        model_id="claude-test",
        steps=[],
    )


class _FakeAnthropicClient:
    """Records SDK calls to verify short-circuit means no API call."""

    def __init__(self):
        self.call_count = 0

    @property
    def messages(self):
        return self

    async def create(self, **kwargs):
        self.call_count += 1
        raise AssertionError("Short-circuit failed: SDK was called")


@pytest.mark.asyncio
async def test_anthropic_short_circuits_error_recovery_when_no_injection():
    """The primary regression signal for Phase 2 D1: error_recovery on a
    no-injection scenario must NOT call the SDK and must return status='na'."""
    fake = _FakeAnthropicClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    result = await judge._evaluate_dimension(
        "error_recovery",
        _empty_trajectory("weather_test"),
        _scenario_no_injection(),
    )
    assert result.status == "na"
    assert result.score is None  # na carries no usable score (not a sentinel 0.0)
    assert result.dimension == "error_recovery"
    assert "no errors injected" in result.reasoning.lower()
    assert result.error_type is None
    assert fake.call_count == 0


@pytest.mark.asyncio
async def test_anthropic_does_not_short_circuit_llm_dims():
    """Defense-in-depth: short-circuit must NOT fire for non-error_recovery
    dims that remain LLM-judged. Updated for Phase 4: uses parameter_quality
    (still LLM) since tool_selection became deterministic."""
    fake = _FakeAnthropicClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    with pytest.raises(AssertionError, match="Short-circuit failed"):
        await judge._evaluate_dimension(
            "parameter_quality",
            _empty_trajectory("weather_test"),
            _scenario_no_injection(),
        )
    assert fake.call_count == 1


@pytest.mark.asyncio
async def test_anthropic_does_not_short_circuit_when_injection_present():
    """For scenarios WITH error_injection (e.g., code_generation, debug_code),
    error_recovery must continue to invoke the LLM. ROADMAP SC #2."""
    fake = _FakeAnthropicClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    with pytest.raises(AssertionError, match="Short-circuit failed"):
        await judge._evaluate_dimension(
            "error_recovery",
            _empty_trajectory("debug_test"),
            _scenario_with_injection(),
        )
    assert fake.call_count == 1


# --- Phase 3 T1: make_judge factory tests ---

class _FakeOpenAIClient:
    """Minimal stub for OpenAI SDK client. The factory just stores it;
    tests don't invoke anything on it. Required because OpenAI's real
    SDK constructor is eager and raises without OPENAI_API_KEY."""
    pass


class TestMakeJudge:
    def test_make_judge_routes_openai(self):
        """OpenAI's SDK constructor is eager and raises without OPENAI_API_KEY,
        so we inject a fake client to keep this test hermetic. Production
        callers (cli.py) pass client=None and rely on env keys."""
        from agent_evaluator.judge import OpenAIJudge, make_judge
        fake = _FakeOpenAIClient()
        judge = make_judge("gpt-4o", client=fake)
        assert isinstance(judge, OpenAIJudge)
        assert judge.model == "gpt-4o"
        assert judge.client is fake

    def test_make_judge_routes_anthropic(self):
        from agent_evaluator.judge import AnthropicJudge, make_judge
        judge = make_judge("claude-sonnet-4-20250514")
        assert isinstance(judge, AnthropicJudge)
        assert judge.model == "claude-sonnet-4-20250514"

    def test_make_judge_unknown_routes_anthropic(self):
        """Unknown prefixes (mistral, llama, etc.) route to Anthropic per
        the existing _is_openai_model semantics. Phase 3 doesn't change
        that — JUDGMENT F-E remediation is deferred."""
        from agent_evaluator.judge import AnthropicJudge, make_judge
        judge = make_judge("mistral-large")
        assert isinstance(judge, AnthropicJudge)
        assert judge.model == "mistral-large"

    def test_make_judge_passes_client_to_anthropic(self):
        """Same client-injection contract for AnthropicJudge."""
        from agent_evaluator.judge import AnthropicJudge, make_judge
        fake = _FakeAnthropicClient()
        judge = make_judge("claude-sonnet-4-20250514", client=fake)
        assert isinstance(judge, AnthropicJudge)
        assert judge.client is fake


# --- Phase 4: deterministic dispatch + short-circuit judge_method fix ---


@pytest.mark.asyncio
async def test_deterministic_dim_does_not_call_sdk():
    """Phase 4 D4: dims with judge_method='deterministic' route to DETECTORS,
    not the SDK. Verifies efficiency dispatch as a representative case."""
    fake = _FakeAnthropicClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    scenario = _scenario_no_injection()
    trajectory = AgentTrajectory(
        scenario_id=scenario.id, model_id="t", steps=[]
    )

    result = await judge._evaluate_dimension("efficiency", trajectory, scenario)
    assert result.judge_method == "deterministic"
    assert result.dimension == "efficiency"
    assert result.status == "ok"
    assert fake.call_count == 0  # SDK NOT called


@pytest.mark.asyncio
async def test_llm_dim_still_calls_sdk():
    """Phase 4 anti-regression: parameter_quality still goes to LLM path."""
    fake = _FakeAnthropicClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    scenario = _scenario_no_injection()
    trajectory = AgentTrajectory(
        scenario_id=scenario.id, model_id="t", steps=[]
    )

    with pytest.raises(AssertionError, match="Short-circuit failed"):
        await judge._evaluate_dimension(
            "parameter_quality", trajectory, scenario
        )
    assert fake.call_count == 1


@pytest.mark.asyncio
async def test_phase2_short_circuit_sets_judge_method_deterministic():
    """Phase 4 plan-checker fix: when the Phase 2 short-circuit fires
    (error_recovery on no-injection), the persisted DimensionScore must
    record judge_method='deterministic' — the decision was code-level, not
    LLM. Persisting judge_method='llm' would be misleading."""
    fake = _FakeAnthropicClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    result = await judge._evaluate_dimension(
        "error_recovery",
        _empty_trajectory("weather_test"),
        _scenario_no_injection(),
    )
    assert result.status == "na"
    assert result.score is None  # na carries no usable score (not a sentinel 0.0)
    assert result.judge_method == "deterministic"  # was "llm" pre-Phase-4 fix
    assert fake.call_count == 0
