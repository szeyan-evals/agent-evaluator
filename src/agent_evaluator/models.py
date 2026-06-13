"""Core data models for agent trajectory evaluation."""

from __future__ import annotations

import json as _json
import warnings
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ToolDefinition(BaseModel):
    """Schema for a mock tool available in a scenario."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    mock_responses: list[MockResponse] = Field(default_factory=list)


class MockResponse(BaseModel):
    """A canned response for a mock tool, matched by parameter conditions."""

    match: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameter key-value pairs to match. Empty dict = default/fallback response.",
    )
    response: dict[str, Any]
    error: str | None = None
    latency_ms: float = 50.0


class Scenario(BaseModel):
    """Definition of a test scenario for agent evaluation."""

    id: str
    name: str
    description: str
    user_query: str
    available_tools: list[ToolDefinition]
    expected_tool_sequence: list[str] = Field(
        description="Ideal tool call order. Partial matches are scored proportionally."
    )
    expected_final_answer_contains: list[str] = Field(
        description="Substrings that should appear in the final answer."
    )
    max_reasonable_steps: int = Field(
        description="Beyond this many steps, efficiency score drops."
    )
    difficulty: Difficulty = Difficulty.MEDIUM
    error_injection: list[ErrorInjection] = Field(
        default_factory=list,
        description="Deliberate errors to inject for testing error recovery.",
    )


class ErrorInjection(BaseModel):
    """Defines an error to inject at a specific point in the trajectory."""

    tool_name: str
    trigger_on_call_number: int = 1
    error_message: str
    description: str = ""


class ToolCall(BaseModel):
    """A single tool invocation within a trajectory."""

    tool_name: str
    parameters: dict[str, Any]
    timestamp: datetime | None = None


class ToolResponse(BaseModel):
    """The result returned by a tool."""

    tool_name: str
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: float | None = None


class TrajectoryStep(BaseModel):
    """One think-act-observe cycle in an agent trajectory."""

    step_index: int
    thought: str | None = None
    tool_call: ToolCall
    tool_response: ToolResponse


class AgentTrajectory(BaseModel):
    """Complete record of an agent solving a scenario."""

    scenario_id: str
    model_id: str
    steps: list[TrajectoryStep]
    final_answer: str | None = None
    total_duration_ms: float | None = None
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DimensionScore(BaseModel):
    """Score on one evaluation dimension.

    The `status` field is the failure channel introduced in v1 TRUST schema.
    When status != "ok", `score` is `None` — there is no meaningful score for
    an errored or not-applicable dimension, so the field is left empty rather
    than carrying a sentinel 0.0 that consumers could mistake for a real zero.
    Consumers must check status (or test `score is not None`) before using
    score. A genuine 0.0 (status="ok") is distinct and legitimate — e.g. an
    agent that produced no final answer scores 0.0 on final_correctness.
    See .planning/research/JUDGMENT.md F-A for context.

    The `judge_method` field (Phase 4) records whether the score was produced
    by an LLM judge or by a deterministic detector. Defaults to "llm" so
    legacy v2 files (which were all LLM-judged) load with accurate semantics.
    """

    dimension: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning: str
    evidence: list[str] = Field(default_factory=list)
    status: Literal["ok", "error", "na"] = "ok"
    error_type: str | None = None
    judge_method: Literal["llm", "deterministic"] = "llm"


class EvaluationResult(BaseModel):
    """Full evaluation of one trajectory.

    `schema_version` and `legacy` introduced in v1 TRUST schema. Loading a
    file without `schema_version` (or with `schema_version < 2`) emits a
    DeprecationWarning and tags `legacy=True`. The computed `partial`
    property is True when any dimension's status != "ok".
    """

    schema_version: int = 3
    legacy: bool = False
    scenario_id: str
    model_id: str
    dimension_scores: list[DimensionScore]
    overall_score: float = Field(ge=0.0, le=1.0)
    summary: str
    cost_usd: float | None = None

    @classmethod
    def from_json(cls, json_str: str) -> "EvaluationResult":
        """Load from JSON, detecting pre-v1 TRUST schema and warning.

        Use this instead of `model_validate_json` when loading eval files
        from disk (e.g., in cli._cmd_report / _cmd_compare). Loading via
        `model_validate_json` directly skips legacy detection and silently
        applies the schema_version=2 default — appropriate for round-trips
        of in-memory v2 instances, NOT for files that may pre-date TRUST.

        See .planning/research/JUDGMENT.md F-A for context.
        """
        data = _json.loads(json_str)
        if isinstance(data, dict):
            v = data.get("schema_version", 1)
            if v < 2:
                warnings.warn(
                    f"Loading legacy eval (schema_version={v}). "
                    "Pre-TRUST scores may include silent zeros from judge "
                    "errors. See .planning/research/JUDGMENT.md F-A.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                data["legacy"] = True
                data["schema_version"] = v  # preserve original for visibility
        return cls.model_validate(data)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def partial(self) -> bool:
        # Phase 2 D3: tightened from any(non-ok) to error-only.
        # N/A is a routine status (a dim doesn't apply to a scenario) and
        # should not raise the "be cautious" signal that partial conveys.
        # Errors are the actionable case. See 02-CONTEXT.md D3.
        return any(ds.status == "error" for ds in self.dimension_scores)


class ComparisonResult(BaseModel):
    """Side-by-side comparison of multiple models on the same scenario set."""

    scenarios: list[str]
    results_by_model: dict[str, list[EvaluationResult]]
