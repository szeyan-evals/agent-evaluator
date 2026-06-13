"""Scenario: Generate and test a function.

Tests error recovery — first test run fails, agent must debug.
"""

from agent_evaluator.models import (
    Difficulty,
    ErrorInjection,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("code_generation")
def build_scenario() -> Scenario:
    return Scenario(
        id="code_generation",
        name="Code Generation",
        description="Write a Python function to validate email addresses, then run the test suite to verify it works.",
        user_query="Write a Python function called `is_valid_email` that validates email addresses. It should check for @ symbol, valid domain, and non-empty local part. Then run the tests.",
        available_tools=[
            ToolDefinition(
                name="write_code",
                description="Write code to a file.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={"status": "written", "path": "email_validator.py"},
                    ),
                ],
            ),
            ToolDefinition(
                name="run_tests",
                description="Run the test suite for a module.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to the test file or module"},
                    },
                    "required": ["path"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={
                            "passed": 5,
                            "failed": 0,
                            "output": "5 passed in 0.02s",
                        },
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["write_code", "run_tests"],
        expected_final_answer_contains=["is_valid_email", "passed"],
        max_reasonable_steps=5,
        difficulty=Difficulty.MEDIUM,
        error_injection=[
            ErrorInjection(
                tool_name="run_tests",
                trigger_on_call_number=1,
                error_message="FAILED test_empty_local_part - AssertionError: is_valid_email('@domain.com') should return False but got True",
                description="First test run fails to test error recovery",
            ),
        ],
    )
