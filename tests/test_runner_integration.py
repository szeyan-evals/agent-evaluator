"""Runner integration tests (Phase 5 TEST-01).

Exercises AgentRunner._run_anthropic and _run_openai against FixtureClient
replay clients. Includes:
  - Happy-path Anthropic + OpenAI loops (trajectory shape + token totals)
  - F-G regression guard: OpenAI choice.message round-trip into next turn
  - Missing usage telemetry remains explicit as None instead of crashing or zeroing
  - Max-steps termination guard: loop exits with final_answer=None

Client injection pattern: AgentRunner.__init__ builds the real SDK client
eagerly (runner.py lines 124-133), so tests bypass __init__ via __new__ and
set the required attributes directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_evaluator.models import (
    AgentTrajectory,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from agent_evaluator.runner import AgentRunner

# FixtureAnthropicClient and FixtureOpenAIClient are defined in tests/conftest.py
# (auto-discovered by pytest). Import them by accessing the conftest module via
# sys.path since conftest is not a regular package but is on sys.path at test time.
import sys
import os

# Ensure the tests/ directory is on the path so conftest is importable
_tests_dir = os.path.dirname(os.path.abspath(__file__))
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from conftest import FixtureAnthropicClient, FixtureOpenAIClient  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_ANTHRO_DIR = Path("tests/fixtures/anthropic")
_OPENAI_DIR = Path("tests/fixtures/openai")

_ANTHRO_TOOL_USE = _ANTHRO_DIR / "agent_response_tool_use.json"
_ANTHRO_FINAL = _ANTHRO_DIR / "agent_response_final.json"
_ANTHRO_NO_USAGE = _ANTHRO_DIR / "agent_response_no_usage.json"

_OPENAI_TOOL_USE = _OPENAI_DIR / "agent_response_tool_use.json"
_OPENAI_FINAL = _OPENAI_DIR / "agent_response_final.json"
_OPENAI_NO_USAGE = _OPENAI_DIR / "agent_response_no_usage.json"


# ---------------------------------------------------------------------------
# Shared scenario factory
# ---------------------------------------------------------------------------


def _weather_scenario(max_reasonable_steps: int = 3) -> Scenario:
    """Small weather lookup scenario with a single tool and mock responses."""
    return Scenario(
        id="weather_lookup",
        name="Weather Lookup",
        description="Look up the weather for a city",
        user_query="What's the weather like in San Francisco?",
        available_tools=[
            ToolDefinition(
                name="get_weather",
                description="Get current weather for a city",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"}
                    },
                    "required": ["city"],
                },
                mock_responses=[
                    MockResponse(
                        match={"city": "San Francisco"},
                        response={"temperature": 62, "condition": "sunny"},
                        latency_ms=50.0,
                    )
                ],
            )
        ],
        expected_tool_sequence=["get_weather"],
        expected_final_answer_contains=["62", "San Francisco"],
        max_reasonable_steps=max_reasonable_steps,
        error_injection=[],
    )


def _make_anthropic_runner(fixture_paths: list[Path]) -> AgentRunner:
    """Bypass AgentRunner.__init__; inject a FixtureAnthropicClient."""
    runner = AgentRunner.__new__(AgentRunner)
    runner.model = "claude-test"
    runner._use_openai = False
    runner._anthropic_client = FixtureAnthropicClient(fixture_paths)
    return runner


def _make_openai_runner(fixture_paths: list[Path]) -> AgentRunner:
    """Bypass AgentRunner.__init__; inject a FixtureOpenAIClient."""
    runner = AgentRunner.__new__(AgentRunner)
    runner.model = "gpt-test"
    runner._use_openai = True
    runner._openai_client = FixtureOpenAIClient(fixture_paths)
    return runner


# ---------------------------------------------------------------------------
# Anthropic happy-path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_anthropic_happy_path():
    """tool_use turn followed by final turn → one step, non-None answer, correct tokens."""
    runner = _make_anthropic_runner([_ANTHRO_TOOL_USE, _ANTHRO_FINAL])
    scenario = _weather_scenario()

    trajectory = await runner._run_anthropic(scenario)

    assert isinstance(trajectory, AgentTrajectory)
    # One tool-use turn produces one TrajectoryStep
    assert len(trajectory.steps) == 1
    assert trajectory.final_answer is not None
    # Token totals: tool_use fixture (150) + final fixture (200)
    assert trajectory.total_input_tokens == 350  # 150 + 200
    assert trajectory.total_output_tokens == 67  # 42 + 25
    assert trajectory.scenario_id == "weather_lookup"


# ---------------------------------------------------------------------------
# Missing usage telemetry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_anthropic_usage_none_is_preserved():
    runner = _make_anthropic_runner([_ANTHRO_NO_USAGE])
    scenario = _weather_scenario()
    trajectory = await runner._run_anthropic(scenario)

    assert trajectory.final_answer == "Done."
    assert trajectory.total_input_tokens is None
    assert trajectory.total_output_tokens is None


# ---------------------------------------------------------------------------
# Max-steps termination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_anthropic_max_steps_terminates():
    """Loop fed more tool_use turns than max_reasonable_steps+5 terminates with final_answer=None.

    max_reasonable_steps=3 → max_steps=8. Feed 9 tool_use fixtures; the loop
    exhausts the for-range (else branch) and sets final_answer = None.
    """
    # 9 tool_use turns — exceeds max_steps (3+5=8)
    fixture_paths = [_ANTHRO_TOOL_USE] * 9
    runner = _make_anthropic_runner(fixture_paths)
    scenario = _weather_scenario(max_reasonable_steps=3)

    trajectory = await runner._run_anthropic(scenario)

    assert trajectory.final_answer is None, (
        "Expected final_answer to be None when max_steps exceeded, "
        f"but got: {trajectory.final_answer!r}"
    )


# ---------------------------------------------------------------------------
# OpenAI happy-path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_openai_happy_path():
    """OpenAI tool_use turn then final turn → one step, non-None answer, correct tokens."""
    runner = _make_openai_runner([_OPENAI_TOOL_USE, _OPENAI_FINAL])
    scenario = _weather_scenario()

    trajectory = await runner._run_openai(scenario)

    assert isinstance(trajectory, AgentTrajectory)
    assert len(trajectory.steps) == 1
    assert trajectory.final_answer is not None
    # prompt_tokens: 150 (tool_use) + 200 (final)
    assert trajectory.total_input_tokens == 350
    assert trajectory.total_output_tokens == 67  # 42 + 25
    assert trajectory.scenario_id == "weather_lookup"


@pytest.mark.asyncio
async def test_run_openai_usage_none_is_preserved():
    runner = _make_openai_runner([_OPENAI_NO_USAGE])
    scenario = _weather_scenario()
    trajectory = await runner._run_openai(scenario)

    assert trajectory.final_answer == "Done."
    assert trajectory.total_input_tokens is None
    assert trajectory.total_output_tokens is None


# ---------------------------------------------------------------------------
# F-G: OpenAI choice.message round-trip guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_openai_choice_message_round_trip():
    """F-G guard: choice.message (SimpleNamespace) appended to messages= survives the next call.

    runner.py line 267 does: messages.append(choice.message)
    The FixtureOpenAIClient returns SimpleNamespace objects, not raw dicts.
    After the tool_use turn the runner appends choice.message to messages and
    passes the list to the next create() call. This test asserts that:
      1. The loop completes without error (no Pydantic/type rejection).
      2. The second create() call's 'messages' kwarg contains the SimpleNamespace
         from the first turn (the F-G round-trip is proven).
    """
    runner = _make_openai_runner([_OPENAI_TOOL_USE, _OPENAI_FINAL])
    scenario = _weather_scenario()

    # Run the loop — must not raise
    trajectory = await runner._run_openai(scenario)
    assert trajectory is not None, "Loop should complete without error (F-G round-trip)"

    # Retrieve the injected client to inspect recorded calls
    client: FixtureOpenAIClient = runner._openai_client  # type: ignore[attr-defined]
    assert len(client.calls) == 2, (
        f"Expected 2 API calls (tool_use + final), got {len(client.calls)}"
    )

    second_call_messages = client.calls[1]["messages"]
    # The choice.message SimpleNamespace from the first turn must appear in the
    # second call's messages list (runner.py line 267 appended it directly).
    from types import SimpleNamespace
    assert any(
        isinstance(m, SimpleNamespace) for m in second_call_messages
    ), (
        "F-G regression: second create() call's messages= does not contain the "
        "SimpleNamespace choice.message from the prior turn. "
        f"messages types: {[type(m).__name__ for m in second_call_messages]}"
    )
