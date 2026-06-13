"""Scenario: Get weather for multiple cities.

Tests efficiency — can the agent batch or parallelize lookups?
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("weather_lookup")
def build_scenario() -> Scenario:
    return Scenario(
        id="weather_lookup",
        name="Weather Lookup",
        description="Get the current weather for San Francisco, New York, and London, then summarize which city is warmest.",
        user_query="What's the current weather in San Francisco, New York, and London? Which city is the warmest right now?",
        available_tools=[
            ToolDefinition(
                name="get_weather",
                description="Get current weather for a city.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"},
                    },
                    "required": ["city"],
                },
                mock_responses=[
                    MockResponse(
                        match={"city": "San Francisco"},
                        response={"city": "San Francisco", "temp_f": 62, "condition": "Foggy", "humidity": 78},
                    ),
                    MockResponse(
                        match={"city": "New York"},
                        response={"city": "New York", "temp_f": 45, "condition": "Cloudy", "humidity": 55},
                    ),
                    MockResponse(
                        match={"city": "London"},
                        response={"city": "London", "temp_f": 50, "condition": "Rainy", "humidity": 82},
                    ),
                    MockResponse(
                        match={},
                        response={"error": "City not found"},
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["get_weather", "get_weather", "get_weather"],
        expected_final_answer_contains=["San Francisco", "warmest", "62"],
        max_reasonable_steps=3,
        difficulty=Difficulty.EASY,
    )
