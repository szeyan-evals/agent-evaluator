"""Scenario: Find top customers by revenue.

Tests parameter quality — agent must write correct SQL.
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("database_query")
def build_scenario() -> Scenario:
    return Scenario(
        id="database_query",
        name="Database Query",
        description="Explore a database schema, then find the top 5 customers by total revenue.",
        user_query="I need to find our top 5 customers by total revenue. Can you query the database and give me the results?",
        available_tools=[
            ToolDefinition(
                name="list_tables",
                description="List all tables in the database.",
                parameters_schema={
                    "type": "object",
                    "properties": {},
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={
                            "tables": ["customers", "orders", "order_items", "products"],
                        },
                    ),
                ],
            ),
            ToolDefinition(
                name="describe_table",
                description="Get the schema of a database table.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "table_name": {"type": "string"},
                    },
                    "required": ["table_name"],
                },
                mock_responses=[
                    MockResponse(
                        match={"table_name": "customers"},
                        response={
                            "columns": [
                                {"name": "id", "type": "INTEGER", "primary_key": True},
                                {"name": "name", "type": "VARCHAR(255)"},
                                {"name": "email", "type": "VARCHAR(255)"},
                                {"name": "created_at", "type": "TIMESTAMP"},
                            ],
                        },
                    ),
                    MockResponse(
                        match={"table_name": "orders"},
                        response={
                            "columns": [
                                {"name": "id", "type": "INTEGER", "primary_key": True},
                                {"name": "customer_id", "type": "INTEGER", "foreign_key": "customers.id"},
                                {"name": "total_amount", "type": "DECIMAL(10,2)"},
                                {"name": "status", "type": "VARCHAR(50)"},
                                {"name": "created_at", "type": "TIMESTAMP"},
                            ],
                        },
                    ),
                    MockResponse(
                        match={},
                        response={"error": "Table not found"},
                    ),
                ],
            ),
            ToolDefinition(
                name="run_sql",
                description="Execute a SQL query and return results.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL query to execute"},
                    },
                    "required": ["query"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={
                            "rows": [
                                {"name": "Acme Corp", "total_revenue": 52340.00},
                                {"name": "TechStart Inc", "total_revenue": 41200.00},
                                {"name": "Global Solutions", "total_revenue": 38750.00},
                                {"name": "DataFlow LLC", "total_revenue": 29100.00},
                                {"name": "CloudNine Labs", "total_revenue": 24680.00},
                            ],
                            "row_count": 5,
                        },
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["list_tables", "describe_table", "describe_table", "run_sql"],
        expected_final_answer_contains=["Acme Corp", "52340", "top 5"],
        max_reasonable_steps=5,
        difficulty=Difficulty.MEDIUM,
    )
