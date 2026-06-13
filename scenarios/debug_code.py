"""Scenario: Debug a Python TypeError.

Tests error recovery — the first run_code call will fail, agent must adapt.
"""

from agent_evaluator.models import (
    Difficulty,
    ErrorInjection,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("debug_code")
def build_scenario() -> Scenario:
    return Scenario(
        id="debug_code",
        name="Debug Python Code",
        description="Read a Python file with a TypeError, identify the bug, fix it, and verify the fix runs correctly.",
        user_query="There's a bug in utils.py — it's throwing a TypeError when processing user data. Can you find and fix it?",
        available_tools=[
            ToolDefinition(
                name="read_file",
                description="Read the contents of a file.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"},
                    },
                    "required": ["path"],
                },
                mock_responses=[
                    MockResponse(
                        match={"path": "utils.py"},
                        response={
                            "content": 'def process_user_data(users):\n    """Process a list of user dicts."""\n    results = []\n    for user in users:\n        # Bug: calling .upper() on an int\n        name = user["name"].upper()\n        age = user["age"].upper()  # TypeError!\n        results.append({"name": name, "age": age})\n    return results\n',
                        },
                    ),
                    MockResponse(
                        match={},
                        response={"error": "File not found"},
                    ),
                ],
            ),
            ToolDefinition(
                name="edit_file",
                description="Edit a file by replacing old content with new content.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_content": {"type": "string", "description": "Content to replace"},
                        "new_content": {"type": "string", "description": "Replacement content"},
                    },
                    "required": ["path", "old_content", "new_content"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={"status": "ok", "message": "File updated successfully"},
                    ),
                ],
            ),
            ToolDefinition(
                name="run_code",
                description="Execute a Python file and return stdout/stderr.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Python file to run"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "Command-line arguments"},
                    },
                    "required": ["path"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={"stdout": "All tests passed!\n", "stderr": "", "exit_code": 0},
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["read_file", "edit_file", "run_code"],
        expected_final_answer_contains=["fixed", "age", "str"],
        max_reasonable_steps=4,
        difficulty=Difficulty.MEDIUM,
        error_injection=[
            ErrorInjection(
                tool_name="run_code",
                trigger_on_call_number=1,
                error_message="TypeError: 'int' object has no attribute 'upper' (line 6, in process_user_data)",
                description="First run triggers the bug to test if agent reads error and fixes it",
            ),
        ],
    )
