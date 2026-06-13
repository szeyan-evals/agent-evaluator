"""Scenario: Analyze CSV data and produce summary statistics.

Tests multi-step correctness with data processing.
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("data_analysis")
def build_scenario() -> Scenario:
    return Scenario(
        id="data_analysis",
        name="Data Analysis",
        description="Read a CSV file of sales data, compute summary statistics, and identify the top-performing product.",
        user_query="Analyze the sales data in sales_2024.csv. Give me the total revenue, average order value, and which product generated the most revenue.",
        available_tools=[
            ToolDefinition(
                name="read_csv",
                description="Read a CSV file and return its contents.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "limit": {"type": "integer", "description": "Max rows to return"},
                    },
                    "required": ["path"],
                },
                mock_responses=[
                    MockResponse(
                        match={"path": "sales_2024.csv"},
                        response={
                            "columns": ["date", "product", "quantity", "unit_price", "total"],
                            "rows": [
                                {"date": "2024-01-15", "product": "Widget Pro", "quantity": 10, "unit_price": 49.99, "total": 499.90},
                                {"date": "2024-01-22", "product": "Gadget X", "quantity": 5, "unit_price": 99.99, "total": 499.95},
                                {"date": "2024-02-01", "product": "Widget Pro", "quantity": 20, "unit_price": 49.99, "total": 999.80},
                                {"date": "2024-02-14", "product": "Gadget X", "quantity": 8, "unit_price": 99.99, "total": 799.92},
                                {"date": "2024-03-01", "product": "Widget Pro", "quantity": 15, "unit_price": 49.99, "total": 749.85},
                            ],
                            "total_rows": 5,
                        },
                    ),
                    MockResponse(match={}, response={"error": "File not found"}),
                ],
            ),
            ToolDefinition(
                name="compute_stats",
                description="Compute summary statistics on numerical data.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "data": {"type": "array", "items": {"type": "number"}},
                        "operations": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["sum", "mean", "median", "min", "max"]},
                        },
                    },
                    "required": ["data", "operations"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={
                            "sum": 3549.42,
                            "mean": 709.88,
                            "min": 499.90,
                            "max": 999.80,
                        },
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["read_csv", "compute_stats"],
        expected_final_answer_contains=["3549", "Widget Pro", "709"],
        max_reasonable_steps=4,
        difficulty=Difficulty.HARD,
    )
