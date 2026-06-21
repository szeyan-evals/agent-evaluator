"""LLM-as-judge evaluator for agent trajectories.

Scores each trajectory on 5 dimensions concurrently using async calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

import anthropic

from agent_evaluator.models import (
    AgentTrajectory,
    DimensionScore,
    EvaluationResult,
    Scenario,
)
from agent_evaluator.pricing import estimate_cost
from agent_evaluator.providers import DEFAULT_MODEL, is_openai_model
from agent_evaluator.rubrics import RUBRICS, compute_overall_score

logger = logging.getLogger(__name__)


class JudgeProtocol(Protocol):
    """Interface for trajectory judges."""

    async def evaluate_trajectory(
        self,
        trajectory: AgentTrajectory,
        scenario: Scenario,
    ) -> EvaluationResult: ...


class AnthropicJudge:
    """Uses Claude as the judge model to score trajectories."""

    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        model: str = DEFAULT_MODEL,
        max_retries: int = 2,
    ):
        self.client = client or anthropic.AsyncAnthropic()
        self.model = model
        self.max_retries = max_retries

    async def evaluate_trajectory(
        self,
        trajectory: AgentTrajectory,
        scenario: Scenario,
    ) -> EvaluationResult:
        """Score a trajectory on all 5 dimensions concurrently."""
        tasks = [
            self._evaluate_dimension(dim, trajectory, scenario)
            for dim in RUBRICS
        ]
        dimension_scores = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any failures: tag with status="error" + error_type and leave
        # score=None so consumers can distinguish from a legitimate 0.0.
        # See JUDGMENT.md F-A.
        valid_scores: list[DimensionScore] = []
        for dim_name, result in zip(RUBRICS, dimension_scores):
            if isinstance(result, Exception):
                logger.error("Failed to evaluate %s: %s", dim_name, result)
                valid_scores.append(
                    DimensionScore(
                        dimension=dim_name,
                        score=None,
                        reasoning=f"Evaluation failed: {result}",
                        evidence=[],
                        status="error",
                        error_type=type(result).__name__,
                    )
                )
            else:
                valid_scores.append(result)

        overall = compute_overall_score(valid_scores)

        return EvaluationResult(
            scenario_id=scenario.id,
            model_id=trajectory.model_id,
            dimension_scores=valid_scores,
            overall_score=overall,
            summary=self._build_summary(valid_scores, overall),
            cost_usd=estimate_cost(
                trajectory.model_id,
                trajectory.total_input_tokens,
                trajectory.total_output_tokens,
            ),
        )

    async def _evaluate_dimension(
        self,
        dimension: str,
        trajectory: AgentTrajectory,
        scenario: Scenario,
    ) -> DimensionScore:
        """Ask the judge LLM to score one dimension.

        Phase 2 short-circuit: error_recovery is N/A for no-injection scenarios.
        Phase 4 deterministic dispatch: dims marked judge_method="deterministic"
        are scored by detector functions (no LLM call). See JUDGMENT.md F-B.
        """
        if dimension == "error_recovery" and len(scenario.error_injection) == 0:
            return DimensionScore(
                dimension="error_recovery",
                score=None,
                reasoning="N/A — no errors injected in this scenario.",
                evidence=[],
                status="na",
                error_type=None,
                judge_method="deterministic",
            )

        # Phase 4 deterministic dispatch
        rubric = RUBRICS[dimension]
        if rubric.judge_method == "deterministic":
            from agent_evaluator.rubrics import DETECTORS
            return DETECTORS[dimension](trajectory, scenario)

        user_prompt = rubric.render_user_prompt(
            trajectory=trajectory,
            scenario=scenario,
        )

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    system=rubric.system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    max_tokens=1024,
                )
                return self._parse_score(response.content[0].text, dimension)
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                if attempt == self.max_retries:
                    raise ValueError(
                        f"Failed to parse judge response for {dimension} "
                        f"after {self.max_retries + 1} attempts: {e}"
                    ) from e
                logger.warning(
                    "Retry %d for %s: %s", attempt + 1, dimension, e
                )

        raise RuntimeError("Unreachable")

    def _parse_score(self, text: str, dimension: str) -> DimensionScore:
        """Parse structured JSON from judge response."""
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])

        data = json.loads(cleaned)
        return DimensionScore(
            dimension=dimension,
            score=float(data["score"]),
            reasoning=str(data["reasoning"]),
            evidence=data.get("evidence", []),
        )

    def _build_summary(
        self, scores: list[DimensionScore], overall: float
    ) -> str:
        parts = [f"Overall: {overall:.2f}"]
        for s in scores:
            val = f"{s.score:.2f}" if s.score is not None else "n/a"
            parts.append(f"  {s.dimension}: {val}")
        return "\n".join(parts)


class OpenAIJudge:
    """Uses GPT-4o as the judge model. Same interface as AnthropicJudge."""

    def __init__(
        self,
        client: object | None = None,
        model: str = "gpt-4o",
        max_retries: int = 2,
    ):
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError(
                "openai package required for OpenAIJudge. "
                "Install with: pip install openai"
            ) from e
        self.client = client or AsyncOpenAI()
        self.model = model
        self.max_retries = max_retries

    async def evaluate_trajectory(
        self,
        trajectory: AgentTrajectory,
        scenario: Scenario,
    ) -> EvaluationResult:
        """Score a trajectory using OpenAI's API."""
        tasks = [
            self._evaluate_dimension(dim, trajectory, scenario)
            for dim in RUBRICS
        ]
        dimension_scores = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any failures: tag with status="error" + error_type and leave
        # score=None so consumers can distinguish from a legitimate 0.0.
        # See JUDGMENT.md F-A.
        valid_scores: list[DimensionScore] = []
        for dim_name, result in zip(RUBRICS, dimension_scores):
            if isinstance(result, Exception):
                logger.error("Failed to evaluate %s: %s", dim_name, result)
                valid_scores.append(
                    DimensionScore(
                        dimension=dim_name,
                        score=None,
                        reasoning=f"Evaluation failed: {result}",
                        evidence=[],
                        status="error",
                        error_type=type(result).__name__,
                    )
                )
            else:
                valid_scores.append(result)

        overall = compute_overall_score(valid_scores)

        return EvaluationResult(
            scenario_id=scenario.id,
            model_id=trajectory.model_id,
            dimension_scores=valid_scores,
            overall_score=overall,
            summary=self._build_summary(valid_scores, overall),
            cost_usd=estimate_cost(
                trajectory.model_id,
                trajectory.total_input_tokens,
                trajectory.total_output_tokens,
            ),
        )

    async def _evaluate_dimension(
        self,
        dimension: str,
        trajectory: AgentTrajectory,
        scenario: Scenario,
    ) -> DimensionScore:
        # Phase 2 short-circuit + Phase 4 deterministic dispatch — see
        # AnthropicJudge._evaluate_dimension for the full rationale.
        if dimension == "error_recovery" and len(scenario.error_injection) == 0:
            return DimensionScore(
                dimension="error_recovery",
                score=None,
                reasoning="N/A — no errors injected in this scenario.",
                evidence=[],
                status="na",
                error_type=None,
                judge_method="deterministic",
            )

        rubric = RUBRICS[dimension]
        if rubric.judge_method == "deterministic":
            from agent_evaluator.rubrics import DETECTORS
            return DETECTORS[dimension](trajectory, scenario)

        user_prompt = rubric.render_user_prompt(
            trajectory=trajectory,
            scenario=scenario,
        )

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": rubric.system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=1024,
                )
                text = response.choices[0].message.content
                return self._parse_score(text, dimension)
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                if attempt == self.max_retries:
                    raise ValueError(
                        f"Failed to parse judge response for {dimension}: {e}"
                    ) from e

        raise RuntimeError("Unreachable")

    def _parse_score(self, text: str, dimension: str) -> DimensionScore:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])
        data = json.loads(cleaned)
        return DimensionScore(
            dimension=dimension,
            score=float(data["score"]),
            reasoning=str(data["reasoning"]),
            evidence=data.get("evidence", []),
        )

    def _build_summary(
        self, scores: list[DimensionScore], overall: float
    ) -> str:
        parts = [f"Overall: {overall:.2f}"]
        for s in scores:
            val = f"{s.score:.2f}" if s.score is not None else "n/a"
            parts.append(f"  {s.dimension}: {val}")
        return "\n".join(parts)


def make_judge(
    model: str,
    *,
    client: Any | None = None,
) -> AnthropicJudge | OpenAIJudge:
    """Auto-route judge construction by model name prefix.

    Uses the same shared vendor routing as AgentRunner:
    OpenAI prefixes ("gpt-", "o1-", "o3-", "o4-") route to OpenAIJudge;
    everything else routes to AnthropicJudge. Closes JUDGMENT.md F-D
    (OpenAIJudge previously unreachable).

    Args:
        model: Model name; routed by prefix.
        client: Optional pre-constructed SDK client. Pass-through to the
            judge class constructor. Required for testing in unkeyed
            environments because OpenAI's SDK constructor is eager and
            raises without OPENAI_API_KEY (Anthropic's defers auth to
            first request, so AnthropicJudge does not need a fake client
            in tests). Production callers (cli.py::_cmd_*) pass None and
            rely on env keys loaded by dotenv.

    Returns:
        AnthropicJudge or OpenAIJudge instance with model set.
    """
    if is_openai_model(model):
        return OpenAIJudge(model=model, client=client)
    return AnthropicJudge(model=model, client=client)
