"""Scenario: Find a free meeting slot for 3 people.

Tests efficiency + correctness — multiple calendar lookups, overlap calculation.
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("calendar_scheduling")
def build_scenario() -> Scenario:
    return Scenario(
        id="calendar_scheduling",
        name="Calendar Scheduling",
        description="Find a 1-hour free slot on Monday for Alice, Bob, and Carol, then create the meeting.",
        user_query="I need to schedule a 1-hour meeting with Alice, Bob, and Carol next Monday. Find a time when all three are free and create the event.",
        available_tools=[
            ToolDefinition(
                name="get_calendar",
                description="Get a person's calendar events for a specific date.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "person": {"type": "string"},
                        "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    },
                    "required": ["person", "date"],
                },
                mock_responses=[
                    MockResponse(
                        match={"person": "Alice"},
                        response={
                            "events": [
                                {"title": "Standup", "start": "09:00", "end": "09:30"},
                                {"title": "Design Review", "start": "11:00", "end": "12:00"},
                                {"title": "Lunch", "start": "12:00", "end": "13:00"},
                            ],
                        },
                    ),
                    MockResponse(
                        match={"person": "Bob"},
                        response={
                            "events": [
                                {"title": "Standup", "start": "09:00", "end": "09:30"},
                                {"title": "1:1 with Manager", "start": "10:00", "end": "10:30"},
                                {"title": "Lunch", "start": "12:00", "end": "13:00"},
                                {"title": "Sprint Planning", "start": "14:00", "end": "15:00"},
                            ],
                        },
                    ),
                    MockResponse(
                        match={"person": "Carol"},
                        response={
                            "events": [
                                {"title": "Standup", "start": "09:00", "end": "09:30"},
                                {"title": "Lunch", "start": "12:00", "end": "13:00"},
                                {"title": "Client Call", "start": "15:00", "end": "16:00"},
                            ],
                        },
                    ),
                    MockResponse(
                        match={},
                        response={"events": []},
                    ),
                ],
            ),
            ToolDefinition(
                name="create_event",
                description="Create a calendar event for specified attendees.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "date": {"type": "string"},
                        "start_time": {"type": "string", "description": "Start time in HH:MM format"},
                        "end_time": {"type": "string", "description": "End time in HH:MM format"},
                        "attendees": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "date", "start_time", "end_time", "attendees"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={
                            "status": "created",
                            "event_id": "EVT-456",
                            "message": "Event created and invitations sent.",
                        },
                    ),
                ],
            ),
        ],
        expected_tool_sequence=[
            "get_calendar", "get_calendar", "get_calendar", "create_event",
        ],
        expected_final_answer_contains=["13:00", "14:00", "created"],
        max_reasonable_steps=5,
        difficulty=Difficulty.HARD,
    )
