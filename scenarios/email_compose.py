"""Scenario: Draft and send a meeting invite.

Tests tool selection — correct 3-step flow.
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("email_compose")
def build_scenario() -> Scenario:
    return Scenario(
        id="email_compose",
        name="Email Compose",
        description="Look up a contact, compose a meeting invite email, and send it.",
        user_query="Send a meeting invite email to Sarah Chen for a project kickoff meeting next Tuesday at 2pm in Conference Room B.",
        available_tools=[
            ToolDefinition(
                name="get_contacts",
                description="Search contacts by name.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
                mock_responses=[
                    MockResponse(
                        match={"name": "Sarah Chen"},
                        response={
                            "contacts": [
                                {"name": "Sarah Chen", "email": "sarah.chen@company.com", "department": "Engineering"},
                            ],
                        },
                    ),
                    MockResponse(
                        match={},
                        response={"contacts": [], "message": "No contacts found"},
                    ),
                ],
            ),
            ToolDefinition(
                name="compose_email",
                description="Draft an email.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={"draft_id": "DRAFT-789", "status": "drafted"},
                    ),
                ],
            ),
            ToolDefinition(
                name="send_email",
                description="Send a drafted email.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "draft_id": {"type": "string"},
                    },
                    "required": ["draft_id"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={"status": "sent", "message_id": "MSG-101", "message": "Email sent successfully."},
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["get_contacts", "compose_email", "send_email"],
        expected_final_answer_contains=["sent", "Sarah Chen", "Tuesday"],
        max_reasonable_steps=4,
        difficulty=Difficulty.EASY,
    )
