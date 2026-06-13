"""Scenario: Research quantum computing.

Tests efficiency — agent should search, read key pages, and summarize
without excessive browsing.
"""

from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
from scenarios.registry import register


@register("research_topic")
def build_scenario() -> Scenario:
    return Scenario(
        id="research_topic",
        name="Research Topic",
        description="Research recent advances in quantum computing and provide a concise summary with key developments.",
        user_query="Give me a brief overview of the latest advances in quantum computing. Focus on the most important developments from the past year.",
        available_tools=[
            ToolDefinition(
                name="web_search",
                description="Search the web for information.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "num_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={
                            "results": [
                                {
                                    "title": "Google's Willow Quantum Chip Achieves Error Correction Milestone",
                                    "url": "https://example.com/willow-chip",
                                    "snippet": "Google's Willow chip demonstrates below-threshold quantum error correction...",
                                },
                                {
                                    "title": "IBM Unveils 1000+ Qubit Condor Processor",
                                    "url": "https://example.com/ibm-condor",
                                    "snippet": "IBM's Condor processor pushes qubit count past 1000...",
                                },
                                {
                                    "title": "Microsoft Announces Topological Qubit Breakthrough",
                                    "url": "https://example.com/ms-topological",
                                    "snippet": "Microsoft's Majorana-based topological qubits show improved stability...",
                                },
                            ],
                        },
                    ),
                ],
            ),
            ToolDefinition(
                name="read_page",
                description="Read the content of a web page.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                    },
                    "required": ["url"],
                },
                mock_responses=[
                    MockResponse(
                        match={"url": "https://example.com/willow-chip"},
                        response={
                            "title": "Google's Willow Quantum Chip",
                            "content": "Google's Willow chip achieved a landmark in quantum error correction. The 105-qubit processor demonstrated that increasing qubit count actually reduces error rates — a key requirement for practical quantum computing. This 'below threshold' performance was achieved using surface codes.",
                        },
                    ),
                    MockResponse(
                        match={"url": "https://example.com/ibm-condor"},
                        response={
                            "title": "IBM Condor Processor",
                            "content": "IBM's 1,121-qubit Condor processor represents the largest gate-based quantum computer. However, IBM is shifting focus to modular architectures with their Heron processor, which has fewer qubits but better error rates.",
                        },
                    ),
                    MockResponse(
                        match={"url": "https://example.com/ms-topological"},
                        response={
                            "title": "Microsoft Topological Qubits",
                            "content": "Microsoft announced progress on topological qubits using Majorana zero modes. These qubits are inherently more stable, potentially requiring less error correction overhead. Still in early research phase.",
                        },
                    ),
                    MockResponse(
                        match={},
                        response={"content": "Page content unavailable."},
                    ),
                ],
            ),
            ToolDefinition(
                name="summarize",
                description="Summarize a collection of text passages.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "texts": {"type": "array", "items": {"type": "string"}},
                        "max_length": {"type": "integer", "default": 200},
                    },
                    "required": ["texts"],
                },
                mock_responses=[
                    MockResponse(
                        match={},
                        response={
                            "summary": "Key quantum computing advances: (1) Google's Willow chip achieved below-threshold error correction with 105 qubits, (2) IBM built the 1,121-qubit Condor but is pivoting to modular designs, (3) Microsoft made progress on inherently stable topological qubits.",
                        },
                    ),
                ],
            ),
        ],
        expected_tool_sequence=["web_search", "read_page", "read_page", "read_page"],
        expected_final_answer_contains=["Google", "Willow", "error correction", "IBM"],
        max_reasonable_steps=5,
        difficulty=Difficulty.EASY,
    )
