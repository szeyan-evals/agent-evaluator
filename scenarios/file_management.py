"""Scenario: Organize files into folders.

Tests tool selection — agent must list, create dirs, then move files.
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("file_management")
def build_scenario() -> Scenario:
    return Scenario(
        id="file_management",
        name="File Management",
        description="List files in a directory, then organize them into subfolders by file type (images, documents, code).",
        user_query="Organize the files in ~/Downloads into subfolders by type: images (.png, .jpg), documents (.pdf, .docx), and code (.py, .js). Create the folders if needed.",
        available_tools=[
            ToolDefinition(
                name="list_dir",
                description="List files in a directory.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                },
                mock_responses=[
                    MockResponse(
                        match={"path": "~/Downloads"},
                        response={
                            "files": [
                                "report.pdf", "photo.png", "script.py",
                                "notes.docx", "logo.jpg", "app.js",
                                "diagram.png", "summary.pdf",
                            ],
                        },
                    ),
                    MockResponse(match={}, response={"files": []}),
                ],
            ),
            ToolDefinition(
                name="create_dir",
                description="Create a directory.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                },
                mock_responses=[
                    MockResponse(match={}, response={"status": "created"}),
                ],
            ),
            ToolDefinition(
                name="move_file",
                description="Move a file to a new location.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                },
                mock_responses=[
                    MockResponse(match={}, response={"status": "moved"}),
                ],
            ),
        ],
        expected_tool_sequence=[
            "list_dir", "create_dir", "create_dir", "create_dir",
            "move_file", "move_file", "move_file", "move_file",
            "move_file", "move_file", "move_file", "move_file",
        ],
        expected_final_answer_contains=["images", "documents", "code", "organized"],
        max_reasonable_steps=13,
        difficulty=Difficulty.MEDIUM,
    )
