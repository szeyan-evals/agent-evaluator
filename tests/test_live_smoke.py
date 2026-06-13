"""Marker-skipped live smoke tests (TEST-02 live opt-in, D3).

These tests require real API keys and are NEVER run in CI.
They are gated behind the `live` marker; CI runs `pytest -m 'not live'`
so this file has zero effect on the default test run.

Run manually with:
    pytest -m live tests/test_live_smoke.py -v

Tests:
  1. test_live_anthropic_judge_short_circuit — Phase 2 short-circuit on
     error_recovery (no-injection scenario): proves no tokens spent.
  2. test_live_anthropic_judge_llm_dim — LLM dispatch on parameter_quality
     against a real trajectory: proves end-to-end judge path works.
  3. test_live_make_judge_routes_openai — make_judge("gpt-4o") returns an
     OpenAIJudge instance: proves Phase 3 F-C dispatch closure.

Security note (T-05-05): real API keys are never required in CI; the live
marker prevents execution. This file imports cleanly without any keys present.
"""

import pytest

from agent_evaluator.judge import AnthropicJudge, OpenAIJudge, make_judge
from agent_evaluator.models import AgentTrajectory
from scenarios.registry import load_scenario


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_anthropic_judge_short_circuit():
    """Live: error_recovery on a no-injection scenario returns status='na'
    and judge_method='deterministic', consuming zero API tokens (Phase 2
    short-circuit).  Requires ANTHROPIC_API_KEY."""
    judge = AnthropicJudge()  # real client, uses ANTHROPIC_API_KEY
    scenario = load_scenario("weather_lookup")  # no error_injection
    trajectory = AgentTrajectory(
        scenario_id=scenario.id,
        model_id="claude-sonnet-4-20250514",
        steps=[],
    )
    result = await judge._evaluate_dimension("error_recovery", trajectory, scenario)
    assert result.status == "na"
    assert result.judge_method == "deterministic"


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_anthropic_judge_llm_dim():
    """Live: parameter_quality on a real (empty) trajectory returns a valid
    LLM-judged score.  Requires ANTHROPIC_API_KEY."""
    judge = AnthropicJudge()  # real client, uses ANTHROPIC_API_KEY
    scenario = load_scenario("weather_lookup")
    trajectory = AgentTrajectory(
        scenario_id=scenario.id,
        model_id="claude-sonnet-4-20250514",
        steps=[],
    )
    result = await judge._evaluate_dimension("parameter_quality", trajectory, scenario)
    assert result.status == "ok"
    assert result.judge_method == "llm"
    assert result.score is not None
    assert 0.0 <= result.score <= 1.0


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_make_judge_routes_openai():
    """Live: make_judge('gpt-4o') returns an OpenAIJudge instance (Phase 3
    F-C dispatch closure).  Requires OPENAI_API_KEY to construct the real
    OpenAI client inside make_judge."""
    judge = make_judge("gpt-4o")
    assert isinstance(judge, OpenAIJudge)
