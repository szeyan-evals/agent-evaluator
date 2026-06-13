"""Scenario: Solve a multi-step math word problem.

Tests final correctness with a clear expected answer.
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("math_calculation")
def build_scenario() -> Scenario:
    return Scenario(
        id="math_calculation",
        name="Math Calculation",
        description="Solve: A store has 15% off sale. Item costs $84. Tax is 8.5%. Calculate final price after discount and tax.",
        user_query="A store is having a 15% off sale. I want to buy an item that originally costs $84.00. The sales tax is 8.5%. What will the final price be after the discount and tax? Show your work.",
        available_tools=[
            ToolDefinition(
                name="calculator",
                description="Perform arithmetic calculations.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "Math expression to evaluate (e.g., '84 * 0.85')"},
                    },
                    "required": ["expression"],
                },
                mock_responses=[
                    MockResponse(
                        match={"expression": "84 * 0.85"},
                        response={"result": 71.4},
                    ),
                    MockResponse(
                        match={"expression": "71.4 * 1.085"},
                        response={"result": 77.469},
                    ),
                    MockResponse(
                        match={"expression": "84 * 0.15"},
                        response={"result": 12.6},
                    ),
                    MockResponse(
                        match={"expression": "84 - 12.6"},
                        response={"result": 71.4},
                    ),
                    MockResponse(
                        match={"expression": "71.4 * 0.085"},
                        response={"result": 6.069},
                    ),
                    MockResponse(
                        match={"expression": "71.4 + 6.069"},
                        response={"result": 77.469},
                    ),
                    MockResponse(
                        match={},
                        response={"result": 0, "error": "Could not evaluate expression"},
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["calculator", "calculator"],
        expected_final_answer_contains=["77.47", "71.4"],
        max_reasonable_steps=4,
        difficulty=Difficulty.EASY,
    )
