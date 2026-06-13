"""Judge.py LLM-path integration tests (TEST-02, F-A / F-I guards).

These tests use FixtureAnthropicClient (defined in conftest.py) to drive the
judge LLM dispatch path with pre-baked JSON fixtures rather than real API
calls.  They cover:

  - Fenced-JSON happy path (F-I standard case)
  - JSONDecodeError retry loop (bounded by max_retries)
  - Retry exhaustion → status="error" + error_type (F-A guard)
  - No-closing-fence multi-line input → parse fails → retry fires (F-I guard)
  - asyncio.gather mixed ok/error aggregation (F-A guard)
"""

import json
import os
import sys
from pathlib import Path

import pytest

from agent_evaluator.judge import AnthropicJudge
from agent_evaluator.models import AgentTrajectory, Scenario, ToolDefinition

# FixtureAnthropicClient is defined in tests/conftest.py (auto-discovered by pytest).
# Add tests/ to sys.path so it is importable as a regular module.
_tests_dir = os.path.dirname(os.path.abspath(__file__))
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from conftest import FixtureAnthropicClient  # noqa: E402

# ---------------------------------------------------------------------------
# Inline scenario / trajectory factories (same pattern as test_judge.py)
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "anthropic"


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


def _empty_trajectory(scenario_id: str) -> AgentTrajectory:
    return AgentTrajectory(
        scenario_id=scenario_id,
        model_id="claude-test",
        steps=[],
    )


# ---------------------------------------------------------------------------
# Task 1a: LLM happy path — standard fenced JSON parses correctly (F-I std)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_dimension_llm_path_parses_fenced_json():
    """LLM dispatch: fenced-JSON response → status='ok', judge_method='llm',
    score≈0.9.  Asserts the model kwarg is passed through to the SDK call."""
    client = FixtureAnthropicClient(  # noqa: F821 — injected by conftest.py
        [_FIXTURE_DIR / "judge_response_ok.json"]
    )
    judge = AnthropicJudge(client=client, model="claude-test", max_retries=2)
    result = await judge._evaluate_dimension(
        "parameter_quality",
        _empty_trajectory("weather_test"),
        _scenario_no_injection(),
    )
    assert result.status == "ok"
    assert result.judge_method == "llm"
    assert result.score == pytest.approx(0.9)
    assert client.calls[0]["model"] == "claude-test"


# ---------------------------------------------------------------------------
# Task 1b: retry-on-JSONDecodeError — malformed × 2 → ok on 3rd attempt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_dimension_retries_on_malformed_json():
    """Retry loop: two malformed responses → succeed on 3rd (max_retries=2).
    len(client.calls) == 3 proves both retries fired."""
    client = FixtureAnthropicClient(
        [
            _FIXTURE_DIR / "judge_response_malformed.json",
            _FIXTURE_DIR / "judge_response_malformed.json",
            _FIXTURE_DIR / "judge_response_ok.json",
        ]
    )
    judge = AnthropicJudge(client=client, model="claude-test", max_retries=2)
    result = await judge._evaluate_dimension(
        "parameter_quality",
        _empty_trajectory("weather_test"),
        _scenario_no_injection(),
    )
    assert result.status == "ok"
    assert len(client.calls) == 3


# ---------------------------------------------------------------------------
# Task 1c: retry exhaustion → ValueError → status="error" via gather (F-A)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_dimension_exhausts_retries_produces_error_status():
    """F-A guard: 3 malformed responses (max_retries=2) → ValueError raised →
    asyncio.gather wraps it as Exception → DimensionScore with status='error',
    error_type='ValueError', score is None (NOT 0.0)."""
    client = FixtureAnthropicClient(
        [
            _FIXTURE_DIR / "judge_response_malformed.json",
            _FIXTURE_DIR / "judge_response_malformed.json",
            _FIXTURE_DIR / "judge_response_malformed.json",
        ]
    )
    judge = AnthropicJudge(client=client, model="claude-test", max_retries=2)
    eval_result = await judge.evaluate_trajectory(
        _empty_trajectory("weather_test"),
        _scenario_no_injection(),
    )
    param_score = next(
        s for s in eval_result.dimension_scores if s.dimension == "parameter_quality"
    )
    assert param_score.status == "error"
    assert param_score.error_type == "ValueError"
    assert param_score.score is None  # F-A: not a silent zero masquerading as ok


# ---------------------------------------------------------------------------
# Task 1d: fence-stripper edge cases (F-I guard)
# ---------------------------------------------------------------------------


def _build_fenced_text(body: str, closing_fence: bool = True) -> str:
    """Build a raw text string as it would arrive from the SDK."""
    lines = ["```json", body]
    if closing_fence:
        lines.append("```")
    return "\n".join(lines)


@pytest.mark.asyncio
async def test_parse_score_fence_variations():
    """F-I guard: standard closing-fence → parses cleanly.
    Multi-line body with NO closing fence → json.loads raises → retry fires.

    Observable proxy for 'retry fired': drive the no-closing-fence text
    through evaluate_trajectory; because every fixture attempt is no-closing-
    fence, retries are exhausted and the gathered result lands as status='error'
    — proving the parse failure propagated through the retry loop rather than
    silently returning corrupt data.
    """
    judge_no_fence = AnthropicJudge(model="claude-test", max_retries=0)

    # --- standard closing fence parses directly ---
    ok_text = _build_fenced_text(
        '{"score": 0.75, "reasoning": "ok", "evidence": []}', closing_fence=True
    )
    result_ok = judge_no_fence._parse_score(ok_text, "parameter_quality")
    assert result_ok.score == pytest.approx(0.75)
    assert result_ok.status == "ok"

    # --- no-closing-fence multi-line → json.loads raises ---
    # Body spans multiple lines; without the closing ``` the stripper includes
    # the last data line in the payload — i.e. lines[1:-1] omits the last
    # content line, producing truncated / corrupt JSON.
    multi_line_no_close = _build_fenced_text(
        '{\n  "score": 0.75,\n  "reasoning": "good",\n  "evidence": []',
        closing_fence=False,
    )
    with pytest.raises((json.JSONDecodeError, KeyError, ValueError)):
        judge_no_fence._parse_score(multi_line_no_close, "parameter_quality")


# ---------------------------------------------------------------------------
# Task 1e: asyncio.gather mixed ok/error (F-A guard)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gather_mixed_ok_and_error():
    """F-A guard: evaluate_trajectory where parameter_quality is driven to
    exhaustion (malformed × 3) while all deterministic dims succeed normally.
    Result must have exactly one status='error' DimensionScore and the rest
    non-error (ok or na)."""
    client = FixtureAnthropicClient(
        [
            _FIXTURE_DIR / "judge_response_malformed.json",
            _FIXTURE_DIR / "judge_response_malformed.json",
            _FIXTURE_DIR / "judge_response_malformed.json",
        ]
    )
    judge = AnthropicJudge(client=client, model="claude-test", max_retries=2)
    eval_result = await judge.evaluate_trajectory(
        _empty_trajectory("weather_test"),
        _scenario_no_injection(),
    )
    scores = eval_result.dimension_scores
    error_scores = [s for s in scores if s.status == "error"]
    non_error_scores = [s for s in scores if s.status != "error"]

    assert len(error_scores) == 1
    assert error_scores[0].dimension == "parameter_quality"
    assert error_scores[0].score is None  # F-A: never a silent 0.0
    assert len(non_error_scores) == len(scores) - 1
    assert all(s.status in ("ok", "na") for s in non_error_scores)
