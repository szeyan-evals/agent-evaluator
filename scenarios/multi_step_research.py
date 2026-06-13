"""Scenario: Compare two products with citations.

Tests all dimensions — search, read, compare, cite across multiple steps.
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("multi_step_research")
def build_scenario() -> Scenario:
    return Scenario(
        id="multi_step_research",
        name="Multi-Step Research",
        description="Compare iPhone 16 Pro vs Samsung Galaxy S25 Ultra on camera, battery, and price, with cited sources.",
        user_query="Compare the iPhone 16 Pro and Samsung Galaxy S25 Ultra. Focus on camera quality, battery life, and price. Cite your sources.",
        available_tools=[
            ToolDefinition(
                name="web_search",
                description="Search the web for information.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={
                            "results": [
                                {"title": "iPhone 16 Pro Review", "url": "https://example.com/iphone16pro", "snippet": "48MP main, 12MP ultrawide..."},
                                {"title": "Galaxy S25 Ultra Review", "url": "https://example.com/s25ultra", "snippet": "200MP main, 50MP ultrawide..."},
                                {"title": "iPhone vs Galaxy Comparison 2025", "url": "https://example.com/comparison", "snippet": "Side by side specs..."},
                            ],
                        },
                    ),
                ],
            ),
            ToolDefinition(
                name="read_page",
                description="Read the content of a web page.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                    },
                    "required": ["url"],
                },
                mock_responses=[
                    MockResponse(
                        match={"url": "https://example.com/iphone16pro"},
                        response={
                            "content": "iPhone 16 Pro: 48MP main camera with sensor-shift OIS, 12MP ultrawide, 12MP 5x telephoto. Battery: 4,685 mAh, lasts ~12 hours screen-on time. Price: starts at $999.",
                        },
                    ),
                    MockResponse(
                        match={"url": "https://example.com/s25ultra"},
                        response={
                            "content": "Galaxy S25 Ultra: 200MP main camera, 50MP ultrawide, 10MP 3x telephoto, 50MP 5x telephoto. Battery: 5,000 mAh, lasts ~14 hours screen-on time. Price: starts at $1,299.",
                        },
                    ),
                    MockResponse(
                        match={"url": "https://example.com/comparison"},
                        response={
                            "content": "Head-to-head: Galaxy S25 Ultra wins on camera resolution and battery. iPhone 16 Pro wins on video quality and price. Both excellent flagship phones.",
                        },
                    ),
                    MockResponse(match={}, response={"content": "Page not available."}),
                ],
            ),
        ],
        expected_tool_sequence=["web_search", "read_page", "read_page", "read_page"],
        expected_final_answer_contains=["iPhone 16 Pro", "Galaxy S25 Ultra", "camera", "battery", "$999", "$1,299"],
        max_reasonable_steps=6,
        difficulty=Difficulty.HARD,
    )
