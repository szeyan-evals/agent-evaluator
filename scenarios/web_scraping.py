"""Scenario: Extract product prices from a webpage.

Tests parameter quality — agent must correctly specify CSS selectors and data extraction.
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("web_scraping")
def build_scenario() -> Scenario:
    return Scenario(
        id="web_scraping",
        name="Web Scraping",
        description="Fetch a product listing page, extract product names and prices, and return a structured summary.",
        user_query="Go to https://example.com/products and extract all product names and prices. Give me a table.",
        available_tools=[
            ToolDefinition(
                name="fetch_url",
                description="Fetch the HTML content of a URL.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                    },
                    "required": ["url"],
                },
                mock_responses=[
                    MockResponse(
                        match={"url": "https://example.com/products"},
                        response={
                            "status": 200,
                            "html": '<div class="product"><h3>Widget A</h3><span class="price">$29.99</span></div><div class="product"><h3>Widget B</h3><span class="price">$49.99</span></div><div class="product"><h3>Widget C</h3><span class="price">$19.99</span></div>',
                        },
                    ),
                    MockResponse(match={}, response={"status": 404, "html": ""}),
                ],
            ),
            ToolDefinition(
                name="extract_data",
                description="Extract structured data from HTML using CSS selectors.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "html": {"type": "string"},
                        "selector": {"type": "string", "description": "CSS selector"},
                        "fields": {
                            "type": "object",
                            "description": "Field name to sub-selector mapping",
                        },
                    },
                    "required": ["html", "selector"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={
                            "data": [
                                {"name": "Widget A", "price": "$29.99"},
                                {"name": "Widget B", "price": "$49.99"},
                                {"name": "Widget C", "price": "$19.99"},
                            ],
                        },
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["fetch_url", "extract_data"],
        expected_final_answer_contains=["Widget A", "29.99", "Widget B", "49.99"],
        max_reasonable_steps=3,
        difficulty=Difficulty.MEDIUM,
    )
