"""Scenario: Book a flight from SFO to JFK.

Tests tool selection (multi-step booking flow) and parameter quality.
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("book_flight")
def build_scenario() -> Scenario:
    return Scenario(
        id="book_flight",
        name="Book a Flight",
        description="Search for and book a round-trip flight from SFO to JFK for Dec 15-22, economy class, for 1 adult.",
        user_query="I need to book a round-trip flight from San Francisco (SFO) to New York (JFK). Departing December 15, returning December 22. Economy class, 1 adult. Find the cheapest option and book it.",
        available_tools=[
            ToolDefinition(
                name="search_flights",
                description="Search for available flights between two airports.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "origin": {"type": "string", "description": "Origin airport code (e.g., SFO)"},
                        "destination": {"type": "string", "description": "Destination airport code (e.g., JFK)"},
                        "departure_date": {"type": "string", "description": "Departure date (YYYY-MM-DD)"},
                        "return_date": {"type": "string", "description": "Return date (YYYY-MM-DD), omit for one-way"},
                        "cabin_class": {"type": "string", "enum": ["economy", "business", "first"]},
                        "passengers": {"type": "integer", "minimum": 1},
                    },
                    "required": ["origin", "destination", "departure_date"],
                },
                mock_responses=[
                    MockResponse(
                        match={"origin": "SFO", "destination": "JFK"},
                        response={
                            "flights": [
                                {
                                    "flight_id": "UA-1234",
                                    "airline": "United Airlines",
                                    "price": 389.00,
                                    "departure": "2024-12-15T08:00:00",
                                    "arrival": "2024-12-15T16:30:00",
                                    "return_departure": "2024-12-22T09:00:00",
                                    "return_arrival": "2024-12-22T12:30:00",
                                    "stops": 0,
                                },
                                {
                                    "flight_id": "DL-5678",
                                    "airline": "Delta",
                                    "price": 425.00,
                                    "departure": "2024-12-15T10:00:00",
                                    "arrival": "2024-12-15T18:45:00",
                                    "return_departure": "2024-12-22T14:00:00",
                                    "return_arrival": "2024-12-22T17:30:00",
                                    "stops": 1,
                                },
                                {
                                    "flight_id": "AA-9101",
                                    "airline": "American Airlines",
                                    "price": 359.00,
                                    "departure": "2024-12-15T06:00:00",
                                    "arrival": "2024-12-15T14:20:00",
                                    "return_departure": "2024-12-22T07:00:00",
                                    "return_arrival": "2024-12-22T10:30:00",
                                    "stops": 0,
                                },
                            ]
                        },
                    ),
                    MockResponse(
                        match={},
                        response={"flights": [], "message": "No flights found for the given criteria."},
                    ),
                ],
            ),
            ToolDefinition(
                name="select_flight",
                description="Select a specific flight from search results to proceed with booking.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "flight_id": {"type": "string", "description": "The flight ID to select"},
                    },
                    "required": ["flight_id"],
                },
                mock_responses=[
                    MockResponse(
                        match={"flight_id": "AA-9101"},
                        response={
                            "status": "selected",
                            "flight_id": "AA-9101",
                            "total_price": 359.00,
                            "requires_payment": True,
                        },
                    ),
                    MockResponse(
                        match={},
                        response={"status": "selected", "requires_payment": True},
                    ),
                ],
            ),
            ToolDefinition(
                name="book_flight",
                description="Confirm and book the selected flight. Requires payment info.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "flight_id": {"type": "string"},
                        "passenger_name": {"type": "string"},
                        "payment_method": {"type": "string", "enum": ["credit_card", "debit_card"]},
                    },
                    "required": ["flight_id", "passenger_name", "payment_method"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={
                            "status": "confirmed",
                            "confirmation_code": "ABC123",
                            "message": "Flight booked successfully!",
                        },
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["search_flights", "select_flight", "book_flight"],
        expected_final_answer_contains=["AA-9101", "359", "confirmed"],
        max_reasonable_steps=4,
        difficulty=Difficulty.MEDIUM,
    )
