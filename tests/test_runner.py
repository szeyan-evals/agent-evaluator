"""Tests for the mock tool executor."""

from agent_evaluator.models import (
    ErrorInjection,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from agent_evaluator.runner import MockToolExecutor


def make_scenario() -> Scenario:
    return Scenario(
        id="test",
        name="Test",
        description="Test scenario",
        user_query="Test query",
        available_tools=[
            ToolDefinition(
                name="get_weather",
                description="Get weather",
                parameters_schema={"type": "object", "properties": {"city": {"type": "string"}}},
                mock_responses=[
                    MockResponse(
                        match={"city": "London"},
                        response={"temp": 55},
                    ),
                    MockResponse(
                        match={},
                        response={"temp": 0, "message": "Unknown city"},
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["get_weather"],
        expected_final_answer_contains=["55"],
        max_reasonable_steps=2,
    )


class TestMockToolExecutor:
    def test_matched_response(self):
        executor = MockToolExecutor(make_scenario())
        resp = executor.execute("get_weather", {"city": "London"})
        assert resp.result["temp"] == 55
        assert resp.error is None

    def test_default_response(self):
        executor = MockToolExecutor(make_scenario())
        resp = executor.execute("get_weather", {"city": "Tokyo"})
        assert resp.result["message"] == "Unknown city"

    def test_unknown_tool(self):
        executor = MockToolExecutor(make_scenario())
        resp = executor.execute("nonexistent_tool", {})
        assert resp.error is not None
        assert "not found" in resp.error

    def test_error_injection(self):
        scenario = make_scenario()
        scenario.error_injection = [
            ErrorInjection(
                tool_name="get_weather",
                trigger_on_call_number=1,
                error_message="Service unavailable",
            ),
        ]
        executor = MockToolExecutor(scenario)

        # First call should get injected error
        resp1 = executor.execute("get_weather", {"city": "London"})
        assert resp1.error == "Service unavailable"

        # Second call should work normally
        resp2 = executor.execute("get_weather", {"city": "London"})
        assert resp2.error is None
        assert resp2.result["temp"] == 55
