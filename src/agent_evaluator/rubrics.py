"""Scoring rubrics for the 5 evaluation dimensions.

Each rubric defines the system prompt and user prompt templates
that the LLM judge uses to score a trajectory on one dimension.

DELIBERATE: the user_prompt_template renders only observable behavior —
tool_call.tool_name, tool_call.parameters, and tool_response. It does NOT
render TrajectoryStep.thought, and must not. `thought` is vendor-asymmetric:
Anthropic populates it from leading text blocks, while OpenAI's chat-completion
tool-call turns return content=None (and o-series reasoning text is never
exposed by the API at all). Feeding it to an LLM-judged dimension would give
the judge richer context for one vendor than another — a latent bias in a
cross-vendor comparison. Judge observable behavior, not narration. If reasoning
must be scored, elicit it symmetrically from both vendors via a structured
contract; do not interpolate `thought` here. Asymmetry origin:
runner._extract_thought_anthropic vs the OpenAI path's choice.message.content.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from jinja2 import Template

from agent_evaluator.models import (
    AgentTrajectory,
    DimensionScore,
    Scenario,
    TrajectoryStep,
)


class Rubric(BaseModel):
    """Rubric definition for one evaluation dimension.

    `judge_method` (Phase 4 D4) selects between LLM judging and a
    deterministic detector function. When "deterministic", the detector is
    looked up in DETECTORS by dimension name; system_prompt /
    user_prompt_template / score_anchors are retained as historical
    documentation but unused at runtime.
    """

    model_config = ConfigDict(extra="forbid")

    dimension: str
    weight: float = Field(ge=0.0, le=1.0)
    description: str
    judge_method: Literal["llm", "deterministic"] = "llm"
    system_prompt: str = ""
    user_prompt_template: str = ""
    score_anchors: dict[str, str] = Field(default_factory=dict)

    def render_user_prompt(self, **kwargs: object) -> str:
        return Template(self.user_prompt_template).render(**kwargs)


JUDGE_SYSTEM_BASE = """\
You are an expert evaluator of AI agent tool-calling behavior.
You assess agent trajectories — the sequence of tool calls an agent made to solve a task.

You MUST respond with valid JSON in this exact format:
{
  "score": <float 0.0 to 1.0>,
  "reasoning": "<2-3 sentences explaining the score>",
  "evidence": ["<specific step or observation>", ...]
}

Be strict but fair. Score based on the rubric provided."""


RUBRICS: dict[str, Rubric] = {
    "tool_selection": Rubric(
        dimension="tool_selection",
        weight=0.25,
        description="Did the agent pick the right tool at each step?",
        judge_method="deterministic",
        system_prompt=JUDGE_SYSTEM_BASE,
        score_anchors={
            "1.0": "Every tool call matches the expected sequence perfectly",
            "0.7": "Most tools correct, 1-2 minor deviations",
            "0.4": "Several wrong tool choices or hallucinated tools",
            "0.0": "Completely wrong tools used throughout",
        },
        user_prompt_template="""\
## Dimension: Tool Selection Accuracy

Evaluate whether the agent selected the correct tools at each step.

### Scenario
- **Task**: {{ scenario.description }}
- **Available tools**: {{ scenario.available_tools | map(attribute='name') | list }}
- **Expected tool sequence**: {{ scenario.expected_tool_sequence }}

### Agent's Actual Tool Calls
{% for step in trajectory.steps %}
Step {{ step.step_index }}: {{ step.tool_call.tool_name }}({{ step.tool_call.parameters | tojson }})
{% endfor %}

### Scoring Rubric
- 1.0: Every tool call matches the expected sequence perfectly
- 0.7: Most tools correct, 1-2 minor deviations that still make sense
- 0.4: Several wrong tool choices or hallucinated tools not in the available set
- 0.0: Completely wrong tools used throughout

Consider: Did the agent use tools that exist? Did it follow a logical sequence?
Were any tools called unnecessarily or skipped when needed?""",
    ),
    "parameter_quality": Rubric(
        dimension="parameter_quality",
        weight=0.2,
        description="Were tool inputs well-formed and correct?",
        system_prompt=JUDGE_SYSTEM_BASE,
        score_anchors={
            "1.0": "All parameters correct, complete, and well-formatted",
            "0.7": "Minor parameter issues that didn't affect outcomes",
            "0.4": "Multiple malformed or missing required parameters",
            "0.0": "Parameters consistently wrong or hallucinated",
        },
        user_prompt_template="""\
## Dimension: Parameter Quality

Evaluate whether the agent provided correct, complete parameters to each tool.

### Scenario
- **Task**: {{ scenario.description }}

### Tool Schemas
{% for tool in scenario.available_tools %}
**{{ tool.name }}**: {{ tool.parameters_schema | tojson }}
{% endfor %}

### Agent's Tool Calls
{% for step in trajectory.steps %}
Step {{ step.step_index }}: {{ step.tool_call.tool_name }}({{ step.tool_call.parameters | tojson }})
  → {% if step.tool_response.error %}ERROR: {{ step.tool_response.error }}{% else %}{{ step.tool_response.result | tojson }}{% endif %}
{% endfor %}

### Scoring Rubric
- 1.0: All parameters correct, complete, and well-formatted
- 0.7: Minor issues (e.g., slightly wrong format) that didn't affect outcomes
- 0.4: Multiple malformed or missing required parameters
- 0.0: Parameters consistently wrong or hallucinated fields

Check: required params present? Values plausible? Types correct? No extra hallucinated fields?""",
    ),
    "efficiency": Rubric(
        dimension="efficiency",
        weight=0.2,
        description="Did the agent solve the task in a reasonable number of steps?",
        judge_method="deterministic",
        system_prompt=JUDGE_SYSTEM_BASE,
        score_anchors={
            "1.0": "Optimal or near-optimal number of steps",
            "0.7": "Slightly more steps than necessary but still reasonable",
            "0.4": "Significant redundancy or wasted calls",
            "0.0": "Excessive steps, loops, or completely inefficient",
        },
        user_prompt_template="""\
## Dimension: Efficiency

Evaluate whether the agent solved the task efficiently.

### Scenario
- **Task**: {{ scenario.description }}
- **Maximum reasonable steps**: {{ scenario.max_reasonable_steps }}
- **Expected tool sequence length**: {{ scenario.expected_tool_sequence | length }}

### Agent's Trajectory
- **Total steps taken**: {{ trajectory.steps | length }}
{% for step in trajectory.steps %}
Step {{ step.step_index }}: {{ step.tool_call.tool_name }}({{ step.tool_call.parameters | tojson }})
{% endfor %}

### Scoring Rubric
- 1.0: Steps taken ≤ expected sequence length
- 0.7: Steps taken ≤ max_reasonable_steps
- 0.4: Steps taken > max_reasonable_steps, with clear redundancy
- 0.0: Excessive steps, repeated calls, or circular behavior

Look for: redundant calls, unnecessary retries, steps that don't advance the task.""",
    ),
    "error_recovery": Rubric(
        dimension="error_recovery",
        weight=0.15,
        description="When a tool call failed, did the agent adapt?",
        system_prompt=JUDGE_SYSTEM_BASE,
        score_anchors={
            "1.0": "Gracefully handled all errors with smart recovery",
            "0.7": "Recovered from most errors with minor issues",
            "0.4": "Poor recovery — retried blindly or gave up too easily",
            "0.0": "No recovery attempt or made errors worse",
            "N/A": "No errors occurred in this trajectory",
        },
        user_prompt_template="""\
## Dimension: Error Recovery

Evaluate how the agent handled tool call failures.

### Scenario
- **Task**: {{ scenario.description }}
{% if scenario.error_injection %}
- **Injected errors**: {% for e in scenario.error_injection %}{{ e.tool_name }} (call #{{ e.trigger_on_call_number }}): "{{ e.error_message }}"{% endfor %}
{% endif %}

### Agent's Trajectory
{% for step in trajectory.steps %}
Step {{ step.step_index }}: {{ step.tool_call.tool_name }}({{ step.tool_call.parameters | tojson }})
  → {% if step.tool_response.error %}**ERROR**: {{ step.tool_response.error }}{% else %}OK{% endif %}
{% endfor %}

### Scoring Rubric
- 1.0: Immediately adapted strategy, tried alternative approach, succeeded
- 0.7: Recovered but took an extra step or two
- 0.4: Blindly retried the same call, or gave up too quickly
- 0.0: Ignored the error, repeated it, or spiraled

For each error: What did the agent do next? Did it change parameters, try a different tool, or ask for clarification?""",
    ),
    "final_correctness": Rubric(
        dimension="final_correctness",
        weight=0.2,
        description="Did the agent produce the correct final answer?",
        judge_method="deterministic",
        system_prompt=JUDGE_SYSTEM_BASE,
        score_anchors={
            "1.0": "Completely correct and well-formatted answer",
            "0.7": "Mostly correct with minor omissions",
            "0.4": "Partially correct — some key information wrong or missing",
            "0.0": "Completely wrong or no answer provided",
        },
        user_prompt_template="""\
## Dimension: Final Correctness

Evaluate whether the agent's final answer is correct.

### Scenario
- **Task**: {{ scenario.description }}
- **Expected answer should contain**: {{ scenario.expected_final_answer_contains }}

### Agent's Final Answer
{{ trajectory.final_answer or "(No final answer provided)" }}

### Full Trajectory Context
{% for step in trajectory.steps %}
Step {{ step.step_index }}: {{ step.tool_call.tool_name }} → {% if step.tool_response.error %}ERROR{% else %}{{ step.tool_response.result | tojson }}{% endif %}
{% endfor %}

### Scoring Rubric
- 1.0: Answer contains all expected elements, is accurate and well-presented
- 0.7: Mostly correct, minor details missing
- 0.4: Partially correct — important information wrong or absent
- 0.0: Completely wrong, irrelevant, or no answer at all

Does the answer address the original task? Is it supported by the tool results?""",
    ),
}


def compute_overall_score(dimension_scores: list[DimensionScore]) -> float:
    """Weighted overall score, excluding non-ok dimensions.

    Dimensions with `status != "ok"` (i.e., "error" or "na") are excluded
    from BOTH numerator and denominator. The result is the weighted score
    over the ok subset, renormalized as if the rubric were natively defined
    on those dimensions only. See .planning/research/JUDGMENT.md F-A and
    TRUST-03 acceptance for rationale.
    """
    total_weight = 0.0
    weighted_sum = 0.0
    for ds in dimension_scores:
        if ds.status != "ok":
            continue  # excluded from numerator AND denominator
        rubric = RUBRICS.get(ds.dimension)
        if rubric is None:
            continue  # unknown dim — skip silently
        weighted_sum += rubric.weight * ds.score
        total_weight += rubric.weight
    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight, 3)


# ============================================================================
# Phase 4: Deterministic Detectors
# ============================================================================
#
# These functions replace LLM judgment for the 3 dims marked
# judge_method="deterministic" above (tool_selection, efficiency,
# final_correctness). They return fully-formed DimensionScore instances with
# status="ok", judge_method="deterministic", and human-readable reasoning.
#
# See .planning/phases/04-deterministic-detectors-first/04-CONTEXT.md D1+D2.


def _lcs_length(a: list[str], b: list[str]) -> int:
    """Longest common subsequence length (DP, O(len(a)*len(b)) time)."""
    if not a or not b:
        return 0
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[len(a)][len(b)]


def _count_consecutive_identical(steps: list[TrajectoryStep]) -> int:
    """Count adjacent step pairs with identical (tool_name, parameters)."""
    count = 0
    for i in range(1, len(steps)):
        prev, curr = steps[i - 1], steps[i]
        if (
            curr.tool_call.tool_name == prev.tool_call.tool_name
            and curr.tool_call.parameters == prev.tool_call.parameters
        ):
            count += 1
    return count


def _detect_tool_selection(
    traj: AgentTrajectory, scen: Scenario
) -> DimensionScore:
    """LCS-based score: actual tool sequence vs scenario.expected_tool_sequence.

    Score = LCS_length / max(len(expected), len(actual)). Vacuous match
    (both empty) = 1.0. Phase 4 D1.
    """
    actual = [s.tool_call.tool_name for s in traj.steps]
    expected = list(scen.expected_tool_sequence)

    if not expected and not actual:
        score = 1.0
    else:
        lcs = _lcs_length(actual, expected)
        score = lcs / max(len(expected), len(actual))

    return DimensionScore(
        dimension="tool_selection",
        score=round(min(score, 1.0), 3),
        reasoning=f"LCS-based match: actual={actual}, expected={expected}",
        evidence=[f"actual: {actual}", f"expected: {expected}"],
        status="ok",
        judge_method="deterministic",
    )


def _detect_efficiency(
    traj: AgentTrajectory, scen: Scenario
) -> DimensionScore:
    """Effort-vs-budget + action-loop penalty.

    Phase 4 D2: action-loop detection (DET-02) is folded into efficiency.
    base score: 1.0 if effort <= expected_len; 1.0 → 0.7 linear from
    expected_len to max_reasonable_steps; 0.7 → 0.0 over the next 5 steps.
    Loop penalty: 0.1 per consecutive-identical pair, capped at 0.5.

    "Effort" is API round-trips (turns), not tool calls, when the trajectory
    carries a turn_index for every step. Round-trips are the real
    latency/efficiency cost: a model that batches N tool calls into one
    parallel turn is more efficient than one making N sequential turns, even
    though both make N calls — and only the turn-aware path can see that
    difference. Falls back to raw step count for legacy trajectories captured
    before turn tracking (any step missing turn_index). The loop penalty stays
    on steps: redundant calls are wasteful regardless of how they're batched.
    """
    steps = len(traj.steps)
    expected_len = max(1, len(scen.expected_tool_sequence))
    max_steps = max(expected_len, scen.max_reasonable_steps)

    turn_ids = {s.turn_index for s in traj.steps}
    turns_known = bool(traj.steps) and None not in turn_ids
    effort = len(turn_ids) if turns_known else steps

    if effort <= expected_len:
        base = 1.0
    elif effort <= max_steps:
        ratio = (effort - expected_len) / max(1, max_steps - expected_len)
        base = 1.0 - 0.3 * ratio
    else:
        over = effort - max_steps
        base = max(0.0, 0.7 - 0.14 * over)

    loops = _count_consecutive_identical(traj.steps)
    penalty = min(0.5, 0.1 * loops)
    score = max(0.0, base - penalty)

    effort_label = f"{effort} turns" if turns_known else f"{steps} steps"
    return DimensionScore(
        dimension="efficiency",
        score=round(score, 3),
        reasoning=(
            f"{effort_label} over {steps} calls "
            f"(expected ~{expected_len}, max_reasonable {max_steps}); "
            f"{loops} action-loops"
        ),
        evidence=[
            f"steps={steps}",
            f"turns={len(turn_ids)}" if turns_known else "turns=unknown",
            f"effort={effort}",
            f"expected_len={expected_len}",
            f"max_reasonable_steps={max_steps}",
            f"action_loops={loops}",
        ],
        status="ok",
        judge_method="deterministic",
    )


def _detect_final_correctness(
    traj: AgentTrajectory, scen: Scenario
) -> DimensionScore:
    """Substring match on final answer + termination correctness.

    Phase 4 D2: termination correctness (DET-03) folds into final_correctness.
    score = substring_match * (1.0 if terminated_within_budget else 0.7).
    No final answer => 0.0.
    """
    expected = list(scen.expected_final_answer_contains)
    final = traj.final_answer

    if final is None:
        return DimensionScore(
            dimension="final_correctness",
            score=0.0,
            reasoning="No final answer (agent did not terminate).",
            evidence=[f"expected: {expected}"],
            status="ok",
            judge_method="deterministic",
        )

    final_lower = final.lower()
    matched = [s for s in expected if s.lower() in final_lower]
    if expected:
        substring_score = len(matched) / len(expected)
    else:
        substring_score = 1.0

    grace = scen.max_reasonable_steps + 5
    terminated_ok = len(traj.steps) <= grace
    multiplier = 1.0 if terminated_ok else 0.7
    score = substring_score * multiplier

    return DimensionScore(
        dimension="final_correctness",
        score=round(score, 3),
        reasoning=(
            f"matched {len(matched)}/{len(expected)} expected substrings; "
            f"terminated within budget={terminated_ok}"
        ),
        evidence=[
            f"matched: {matched}",
            f"missing: {[s for s in expected if s.lower() not in final_lower]}",
            f"steps={len(traj.steps)}, budget={grace}",
        ],
        status="ok",
        judge_method="deterministic",
    )


DETECTORS: dict[str, Callable[[AgentTrajectory, Scenario], DimensionScore]] = {
    "tool_selection": _detect_tool_selection,
    "efficiency": _detect_efficiency,
    "final_correctness": _detect_final_correctness,
}
