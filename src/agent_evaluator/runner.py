"""Agent runner — executes scenarios against LLMs and records trajectories.

Supports live execution (calling an LLM with mock tools) and
replay mode (loading pre-recorded trajectories from JSON).
Works with both Anthropic and OpenAI models.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from agent_evaluator.models import (
    AgentTrajectory,
    ErrorInjection,
    MockResponse,
    Scenario,
    ToolCall,
    ToolDefinition,
    ToolResponse,
    TrajectoryStep,
)

logger = logging.getLogger(__name__)

# Models that should be routed to OpenAI
OPENAI_PREFIXES = ("gpt-", "o1-", "o3-", "o4-")


def _is_openai_model(model: str) -> bool:
    return any(model.startswith(p) for p in OPENAI_PREFIXES)


# o-series reasoning models (o1/o3/o4...) reject the legacy `max_tokens`
# param and require `max_completion_tokens`. gpt-* chat models still use
# `max_tokens`. Detect so the OpenAI path picks the right kwarg instead of
# erroring the moment self.model points at a reasoning model.
def _is_openai_reasoning_model(model: str) -> bool:
    return model.startswith(("o1", "o3", "o4"))


class MockToolExecutor:
    """Simulates tool execution using canned responses from scenario definitions."""

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self._tool_map: dict[str, ToolDefinition] = {
            t.name: t for t in scenario.available_tools
        }
        self._call_counts: dict[str, int] = {}
        self._error_map = self._build_error_map(scenario.error_injection)

    def _build_error_map(
        self, injections: list[ErrorInjection]
    ) -> dict[tuple[str, int], str]:
        return {
            (e.tool_name, e.trigger_on_call_number): e.error_message
            for e in injections
        }

    def execute(self, tool_name: str, parameters: dict[str, Any]) -> ToolResponse:
        """Execute a mock tool call and return a response."""
        self._call_counts[tool_name] = self._call_counts.get(tool_name, 0) + 1
        call_num = self._call_counts[tool_name]

        # Check for injected errors
        error_key = (tool_name, call_num)
        if error_key in self._error_map:
            return ToolResponse(
                tool_name=tool_name,
                error=self._error_map[error_key],
                latency_ms=10.0,
            )

        # Find matching mock response
        tool_def = self._tool_map.get(tool_name)
        if tool_def is None:
            return ToolResponse(
                tool_name=tool_name,
                error=f"Tool '{tool_name}' not found in available tools",
                latency_ms=5.0,
            )

        response = self._find_matching_response(tool_def.mock_responses, parameters)
        if response is None:
            return ToolResponse(
                tool_name=tool_name,
                result={"status": "ok", "message": f"{tool_name} executed successfully"},
                latency_ms=50.0,
            )

        if response.error:
            return ToolResponse(
                tool_name=tool_name,
                error=response.error,
                latency_ms=response.latency_ms,
            )

        return ToolResponse(
            tool_name=tool_name,
            result=response.response,
            latency_ms=response.latency_ms,
        )

    def _find_matching_response(
        self, responses: list[MockResponse], parameters: dict[str, Any]
    ) -> MockResponse | None:
        """Find the best matching mock response for given parameters."""
        default: MockResponse | None = None
        for resp in responses:
            if not resp.match:
                default = resp
                continue
            if all(
                parameters.get(k) == v for k, v in resp.match.items()
            ):
                return resp
        return default


class AgentRunner:
    """Runs scenarios against an LLM and records tool-calling trajectories.

    Automatically routes to the correct SDK based on the model name:
    - gpt-*, o1-*, o3-*, o4-* → OpenAI
    - Everything else → Anthropic
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        self._use_openai = _is_openai_model(model)

        if self._use_openai:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI()
        else:
            import anthropic
            self._anthropic_client = anthropic.AsyncAnthropic()

    async def run_scenario(self, scenario: Scenario) -> AgentTrajectory:
        """Execute a scenario and record the full trajectory."""
        if self._use_openai:
            return await self._run_openai(scenario)
        return await self._run_anthropic(scenario)

    # ── Anthropic path ──────────────────────────────────────────────

    async def _run_anthropic(self, scenario: Scenario) -> AgentTrajectory:
        executor = MockToolExecutor(scenario)
        tools = self._build_anthropic_tools(scenario.available_tools)

        messages: list[dict] = [
            {"role": "user", "content": scenario.user_query}
        ]
        steps: list[TrajectoryStep] = []
        step_index = 0
        max_steps = scenario.max_reasonable_steps + 5
        total_input_tokens = 0
        total_output_tokens = 0

        start_time = time.monotonic()

        for turn_index in range(max_steps):
            response = await self._anthropic_client.messages.create(
                model=self.model,
                max_tokens=2048,
                tools=tools,
                messages=messages,
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            tool_use_blocks = [
                b for b in response.content if b.type == "tool_use"
            ]

            if not tool_use_blocks:
                text_blocks = [
                    b for b in response.content if b.type == "text"
                ]
                final_answer = text_blocks[0].text if text_blocks else None
                break

            tool_results = []
            for block in tool_use_blocks:
                tool_call = ToolCall(
                    tool_name=block.name,
                    parameters=block.input,
                )
                tool_response = executor.execute(block.name, block.input)

                steps.append(
                    TrajectoryStep(
                        step_index=step_index,
                        turn_index=turn_index,
                        thought=self._extract_thought_anthropic(response.content),
                        tool_call=tool_call,
                        tool_response=tool_response,
                    )
                )
                step_index += 1

                if tool_response.error:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"error": tool_response.error}),
                        "is_error": True,
                    })
                else:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_response.result),
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            final_answer = None

        duration = (time.monotonic() - start_time) * 1000

        return AgentTrajectory(
            scenario_id=scenario.id,
            model_id=self.model,
            steps=steps,
            final_answer=final_answer,
            total_duration_ms=duration,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )

    # ── OpenAI path ─────────────────────────────────────────────────

    async def _run_openai(self, scenario: Scenario) -> AgentTrajectory:
        executor = MockToolExecutor(scenario)
        tools = self._build_openai_tools(scenario.available_tools)

        messages: list[dict] = [
            {"role": "user", "content": scenario.user_query}
        ]
        steps: list[TrajectoryStep] = []
        step_index = 0
        max_steps = scenario.max_reasonable_steps + 5
        total_input_tokens = 0
        total_output_tokens = 0

        start_time = time.monotonic()

        # Reasoning models require max_completion_tokens; chat models use
        # max_tokens. Pick once outside the loop.
        token_param = (
            "max_completion_tokens"
            if _is_openai_reasoning_model(self.model)
            else "max_tokens"
        )

        for turn_index in range(max_steps):
            response = await self._openai_client.chat.completions.create(
                model=self.model,
                tools=tools,
                messages=messages,
                **{token_param: 2048},
            )

            choice = response.choices[0]
            usage = response.usage
            if usage:
                total_input_tokens += usage.prompt_tokens
                total_output_tokens += usage.completion_tokens

            tool_calls = choice.message.tool_calls or []

            if not tool_calls:
                final_answer = choice.message.content
                break

            # Append the assistant message (with tool_calls) to conversation
            messages.append(choice.message)

            for tc in tool_calls:
                args = json.loads(tc.function.arguments)
                tool_call = ToolCall(
                    tool_name=tc.function.name,
                    parameters=args,
                )
                tool_response = executor.execute(tc.function.name, args)

                steps.append(
                    TrajectoryStep(
                        step_index=step_index,
                        turn_index=turn_index,
                        thought=choice.message.content,
                        tool_call=tool_call,
                        tool_response=tool_response,
                    )
                )
                step_index += 1

                # Append tool result to conversation
                if tool_response.error:
                    result_content = json.dumps({"error": tool_response.error})
                else:
                    result_content = json.dumps(tool_response.result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_content,
                })
        else:
            final_answer = None

        duration = (time.monotonic() - start_time) * 1000

        return AgentTrajectory(
            scenario_id=scenario.id,
            model_id=self.model,
            steps=steps,
            final_answer=final_answer,
            total_duration_ms=duration,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )

    # ── Tool format builders ────────────────────────────────────────

    def _build_anthropic_tools(self, tool_defs: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters_schema,
            }
            for t in tool_defs
        ]

    def _build_openai_tools(self, tool_defs: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters_schema,
                },
            }
            for t in tool_defs
        ]

    def _extract_thought_anthropic(self, content: list) -> str | None:
        thoughts = []
        for block in content:
            if block.type == "text":
                thoughts.append(block.text)
            elif block.type == "tool_use":
                break
        return "\n".join(thoughts) if thoughts else None

    @staticmethod
    def load_trajectory(path: Path) -> AgentTrajectory:
        return AgentTrajectory.model_validate_json(path.read_text())

    @staticmethod
    def save_trajectory(trajectory: AgentTrajectory, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(trajectory.model_dump_json(indent=2))
