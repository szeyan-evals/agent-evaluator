# Phase 4 Plan — Deterministic Detectors First

**Phase:** 04 — Deterministic Detectors First
**Source decisions:** `04-CONTEXT.md` (D1–D4)
**Source artifacts:**
- `.planning/research/JUDGMENT.md` (F-A — reducing LLM calls reduces silent-zero blast)
- `.planning/REQUIREMENTS.md` (DET-01..04)
- `.planning/ROADMAP.md` (Phase 4 success criteria)
- `.planning/codebase/ARCHITECTURE.md`

**Goal restatement:** Replace 3 LLM-judged dims with deterministic detectors; track judge mechanism per score; bump schema v2 → v3. After Phase 4, ~54% fewer LLM calls per comparison run; deterministic dims produce reproducible scores.

---

## Pre-flight notes

### Cross-phase impact (schema bump)

Phase 4 bumps `EvaluationResult.schema_version` default from `2` to `3`. The `_detect_legacy` validator's trigger condition stays `< 2` (per CONTEXT D3), so:
- v1 files (no schema_version, pre-TRUST): trigger `legacy=True` + DeprecationWarning (unchanged)
- v2 files (post-Phase-1, pre-Phase-4): load cleanly under v3, all dims default `judge_method="llm"` (accurate for their content)
- v3 files (post-Phase-4): load cleanly with explicit `judge_method` per dim

### Build-green-after-every-commit ordering

| T# | Lands | Why build stays green |
|----|-------|-----------------------|
| T1 | models.py: judge_method on DimensionScore + schema_version 2→3 + tests | Both new fields have defaults. Existing 47 tests don't reference them. |
| T2 | rubrics.py: judge_method on Rubric + 3 detector functions + DETECTORS dict + tests | Rubric.judge_method default is "llm"; existing test_rubrics tests pass. Detectors are pure functions; new tests pass. **judge.py still routes everything through LLM at this point** — no behavior change yet. |
| T3 | judge.py: deterministic dispatch (both classes) + new test_judge.py case | T2 already has Rubric.judge_method set + DETECTORS populated. Now judge.py actually uses them. Behavior changes for the 3 deterministic dims. |
| T4 | report.py: judge_method annotation in per-scenario detail (cosmetic) | No test changes; visual change only. |
| T5 | E2E verification | Synthetic full-pipeline + ruff + agent-eval list. |

---

## Tasks

### T1 — `models.py`: `judge_method` field + schema_version bump

**Files:** `src/agent_evaluator/models.py`, `tests/test_models.py`

**Changes:**

1. In `DimensionScore`, add `judge_method`:
```python
class DimensionScore(BaseModel):
    """Score on one evaluation dimension."""

    dimension: str
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence: list[str] = Field(default_factory=list)
    status: Literal["ok", "error", "na"] = "ok"
    error_type: str | None = None
    judge_method: Literal["llm", "deterministic"] = "llm"  # NEW (Phase 4 D3)
```

2. In `EvaluationResult`, bump default schema_version:
```python
class EvaluationResult(BaseModel):
    schema_version: int = 3  # was 2 (Phase 4 D3)
    legacy: bool = False
    # ... rest unchanged
```

3. **Legacy detection unchanged.** Note (per plan-checker Concern 2): the legacy logic lives in `EvaluationResult.from_json` classmethod, NOT a Pydantic `model_validator`. CONTEXT/PLAN refer to it as "the `_detect_legacy` validator" for narrative continuity, but the actual code is at `models.py::EvaluationResult.from_json` (lines ~147–172). The trigger condition `if v < 2` stays unchanged — v2 files are NOT legacy under v3.

4. Add tests in `tests/test_models.py`:
```python
def test_default_judge_method_llm(self):
    s = DimensionScore(dimension="x", score=0.5, reasoning="y")
    assert s.judge_method == "llm"

def test_judge_method_deterministic_round_trip(self):
    s = DimensionScore(
        dimension="efficiency", score=0.8, reasoning="2 steps",
        judge_method="deterministic",
    )
    json_str = s.model_dump_json()
    restored = DimensionScore.model_validate_json(json_str)
    assert restored.judge_method == "deterministic"

def test_v2_eval_loads_under_v3_with_default_method(self):
    """v2 files (schema_version=2, no judge_method per dim) load cleanly
    as v3-compatible results with all dims defaulting to judge_method='llm'."""
    v2_eval = json.dumps({
        "schema_version": 2,
        "scenario_id": "x",
        "model_id": "y",
        "dimension_scores": [
            {"dimension": "tool_selection", "score": 0.85, "reasoning": "good"},
        ],
        "overall_score": 0.85,
        "summary": "ok",
    })
    # v2 schema_version doesn't trigger legacy (only < 2 does)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        restored = EvaluationResult.from_json(v2_eval)
    assert restored.legacy is False
    assert restored.schema_version == 2  # preserves the v2 marker
    assert restored.dimension_scores[0].judge_method == "llm"  # default applied

def test_new_eval_has_schema_version_3(self):
    result = EvaluationResult(
        scenario_id="x", model_id="y",
        dimension_scores=[DimensionScore(dimension="x", score=0.5, reasoning="y")],
        overall_score=0.5, summary="ok",
    )
    assert result.schema_version == 3
```

**Acceptance:**
- `DimensionScore` defaults `judge_method` to `"llm"`.
- New `EvaluationResult` instances have `schema_version=3` by default.
- v2 JSON loads cleanly with `judge_method="llm"` on all dims; not legacy.
- v1 JSON (no schema_version) still triggers legacy=True + DeprecationWarning (Phase 1 behavior preserved).

**Anti-regression + 2 existing test updates (per plan-checker Concern 1):**
- Two existing tests in `tests/test_models.py` assert `schema_version == 2` and use `_make_eval()` (which doesn't specify schema_version, so defaults apply). The schema-bump flips both. **Update them in the same T1 commit:**
  - `test_v2_from_json_no_warning` (line ~143): rename to `test_current_schema_from_json_no_warning`. Update assertion from `restored.schema_version == 2` to `restored.schema_version == 3` (the new default reflects the current schema version this test is checking — no warning when loading a freshly-dumped result).
  - `test_construction_does_not_emit_legacy_warning` (line ~152): keep the name (still describes the behavior). Update assertion from `result.schema_version == 2` to `result.schema_version == 3`.
- After these updates, all 47 prior tests continue to pass under the new schema default.
- `test_partial_*` tests still work — judge_method doesn't affect partial semantics.

**Note:** "v2 file loads as legacy=False, schema_version preserved" is verified by the NEW `test_v2_eval_loads_under_v3_with_default_method` test (which constructs raw v2 JSON, NOT via `_make_eval()`, so no helper coupling).

**Atomic commit:** `feat(models): add DimensionScore.judge_method + bump schema_version to 3 (Phase 4 D3)`

---

### T2 — `rubrics.py`: extend Rubric class + add 3 detectors + DETECTORS dict

**Files:** `src/agent_evaluator/rubrics.py`, `tests/test_rubrics.py`

**Changes:**

1. Extend `Rubric` class:
```python
from typing import Literal

class Rubric(BaseModel):
    dimension: str
    weight: float = Field(ge=0.0, le=1.0)
    description: str
    judge_method: Literal["llm", "deterministic"] = "llm"  # NEW (Phase 4 D4)
    # LLM-only fields (used when judge_method == "llm"):
    system_prompt: str = ""
    user_prompt_template: str = ""
    score_anchors: dict[str, str] = Field(default_factory=dict)
    # Note: render_user_prompt() should only be called when judge_method == "llm".
```

2. Update the 3 deterministic-targeted RUBRICS entries to set `judge_method="deterministic"`:
```python
RUBRICS = {
    "tool_selection": Rubric(
        dimension="tool_selection",
        weight=0.25,
        description="Correct tool chosen at each step",
        judge_method="deterministic",  # NEW
        # system_prompt / user_prompt_template / score_anchors retained as
        # historical reference; not invoked.
        system_prompt=JUDGE_SYSTEM_BASE,
        user_prompt_template="...",  # existing content unchanged
        score_anchors={...},
    ),
    "parameter_quality": Rubric(
        dimension="parameter_quality",
        weight=0.20,
        description="...",
        judge_method="llm",  # default; explicit for clarity
        system_prompt=JUDGE_SYSTEM_BASE,
        user_prompt_template="...",
        score_anchors={...},
    ),
    "efficiency": Rubric(
        dimension="efficiency",
        weight=0.20,
        description="Task solved in reasonable steps",
        judge_method="deterministic",  # NEW
        # ...
    ),
    "error_recovery": Rubric(
        dimension="error_recovery",
        weight=0.15,
        description="...",
        judge_method="llm",  # explicit
        # ...
    ),
    "final_correctness": Rubric(
        dimension="final_correctness",
        weight=0.20,
        description="Final answer matches expected output",
        judge_method="deterministic",  # NEW
        # ...
    ),
}
```

3. Add 3 detector functions (placement: after RUBRICS dict). Concrete formulas:

```python
from agent_evaluator.models import AgentTrajectory, DimensionScore, Scenario, TrajectoryStep


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
    """LCS-based score: actual tool sequence vs scenario.expected_tool_sequence."""
    actual = [s.tool_call.tool_name for s in traj.steps]
    expected = list(scen.expected_tool_sequence)

    if not expected and not actual:
        score = 1.0  # vacuous match
    else:
        lcs = _lcs_length(actual, expected)
        score = lcs / max(len(expected), len(actual))

    return DimensionScore(
        dimension="tool_selection",
        score=round(min(score, 1.0), 3),
        reasoning=(
            f"LCS-based match: actual={actual}, expected={expected}"
        ),
        evidence=[f"actual: {actual}", f"expected: {expected}"],
        status="ok",
        judge_method="deterministic",
    )


def _detect_efficiency(
    traj: AgentTrajectory, scen: Scenario
) -> DimensionScore:
    """Steps-vs-budget + action-loop penalty.

    Folds DET-02 (action-loop detection) into efficiency per CONTEXT D2.
    """
    steps = len(traj.steps)
    expected_len = max(1, len(scen.expected_tool_sequence))
    max_steps = max(expected_len, scen.max_reasonable_steps)

    # base score
    if steps <= expected_len:
        base = 1.0
    elif steps <= max_steps:
        # linear 1.0 → 0.7 from expected to max
        ratio = (steps - expected_len) / max(1, max_steps - expected_len)
        base = 1.0 - 0.3 * ratio
    else:
        # linear 0.7 → 0.0 over the next 5 steps past max
        over = steps - max_steps
        base = max(0.0, 0.7 - 0.14 * over)

    loops = _count_consecutive_identical(traj.steps)
    penalty = min(0.5, 0.1 * loops)
    score = max(0.0, base - penalty)

    return DimensionScore(
        dimension="efficiency",
        score=round(score, 3),
        reasoning=(
            f"{steps} steps (expected ~{expected_len}, "
            f"max_reasonable {max_steps}); {loops} action-loops"
        ),
        evidence=[
            f"steps={steps}",
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

    Folds DET-03 (termination correctness) into final_correctness per CONTEXT D2.
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
        substring_score = 1.0  # nothing required, anything goes

    # Termination check: agent stopped within budget (max_reasonable + 5 grace)
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
```

Add `from typing import Callable` (or `Callable` from collections.abc) and import `AgentTrajectory`, `DimensionScore`, `Scenario`, `TrajectoryStep` from models.

4. Add tests in `tests/test_rubrics.py`:

```python
class TestRubricJudgeMethod:
    def test_default_judge_method_is_llm(self):
        # parameter_quality and error_recovery should be LLM
        assert RUBRICS["parameter_quality"].judge_method == "llm"
        assert RUBRICS["error_recovery"].judge_method == "llm"

    def test_deterministic_dims_marked(self):
        # Phase 4 D1 split
        assert RUBRICS["tool_selection"].judge_method == "deterministic"
        assert RUBRICS["efficiency"].judge_method == "deterministic"
        assert RUBRICS["final_correctness"].judge_method == "deterministic"


class TestDetectors:
    def _scenario(self, **overrides):
        defaults = dict(
            id="x", name="X", description="x", user_query="x",
            available_tools=[
                ToolDefinition(name="get_weather", description="x",
                               parameters_schema={"type":"object","properties":{}}),
                ToolDefinition(name="search", description="x",
                               parameters_schema={"type":"object","properties":{}}),
            ],
            expected_tool_sequence=["get_weather"],
            expected_final_answer_contains=["55", "cloudy"],
            max_reasonable_steps=2,
        )
        defaults.update(overrides)
        return Scenario(**defaults)

    def _step(self, idx, name, params=None):
        return TrajectoryStep(
            step_index=idx,
            tool_call=ToolCall(tool_name=name, parameters=params or {}),
            tool_response=ToolResponse(tool_name=name, result={}),
        )

    # tool_selection
    def test_tool_selection_exact_match(self):
        scen = self._scenario(expected_tool_sequence=["a", "b"])
        traj = AgentTrajectory(scenario_id="x", model_id="m", steps=[
            self._step(0, "a"), self._step(1, "b"),
        ])
        ds = _detect_tool_selection(traj, scen)
        assert ds.score == 1.0
        assert ds.judge_method == "deterministic"
        assert ds.status == "ok"

    def test_tool_selection_complete_miss(self):
        scen = self._scenario(expected_tool_sequence=["a"])
        traj = AgentTrajectory(scenario_id="x", model_id="m", steps=[
            self._step(0, "z"),
        ])
        ds = _detect_tool_selection(traj, scen)
        assert ds.score == 0.0

    def test_tool_selection_partial_overlap(self):
        scen = self._scenario(expected_tool_sequence=["a", "b", "c"])
        traj = AgentTrajectory(scenario_id="x", model_id="m", steps=[
            self._step(0, "a"), self._step(1, "c"),
        ])
        ds = _detect_tool_selection(traj, scen)
        # LCS={a,c}=2, max(3,2)=3 → 2/3 ≈ 0.667
        assert 0.5 < ds.score < 0.8

    # efficiency
    def test_efficiency_under_budget(self):
        scen = self._scenario(expected_tool_sequence=["a"], max_reasonable_steps=3)
        traj = AgentTrajectory(scenario_id="x", model_id="m", steps=[
            self._step(0, "a"),
        ])
        ds = _detect_efficiency(traj, scen)
        assert ds.score == 1.0

    def test_efficiency_over_budget_with_loops(self):
        scen = self._scenario(expected_tool_sequence=["a"], max_reasonable_steps=2)
        # 4 identical steps = 3 loop pairs
        traj = AgentTrajectory(scenario_id="x", model_id="m", steps=[
            self._step(i, "a", {"q":"foo"}) for i in range(4)
        ])
        ds = _detect_efficiency(traj, scen)
        # over budget AND 3 loops penalty (0.3) → low score
        assert ds.score < 0.5

    # final_correctness
    def test_final_correctness_full_match_terminated(self):
        scen = self._scenario(expected_final_answer_contains=["55", "cloudy"])
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[self._step(0, "get_weather")],
            final_answer="The weather is 55°F and Cloudy.",
        )
        ds = _detect_final_correctness(traj, scen)
        assert ds.score == 1.0

    def test_final_correctness_partial_match(self):
        scen = self._scenario(expected_final_answer_contains=["55", "cloudy"])
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[self._step(0, "get_weather")],
            final_answer="It's 55 degrees today.",
        )
        ds = _detect_final_correctness(traj, scen)
        # 1/2 substrings match, terminated ok → 0.5
        assert ds.score == 0.5

    def test_final_correctness_no_termination(self):
        scen = self._scenario(expected_final_answer_contains=["55"])
        traj = AgentTrajectory(
            scenario_id="x", model_id="m",
            steps=[self._step(0, "get_weather")],
            final_answer=None,
        )
        ds = _detect_final_correctness(traj, scen)
        assert ds.score == 0.0
        assert "did not terminate" in ds.reasoning.lower()


class TestDETECTORSRegistry:
    def test_detectors_dict_has_three_entries(self):
        assert set(DETECTORS.keys()) == {"tool_selection", "efficiency", "final_correctness"}

    def test_all_deterministic_rubrics_have_detectors(self):
        for dim, rubric in RUBRICS.items():
            if rubric.judge_method == "deterministic":
                assert dim in DETECTORS, f"{dim} marked deterministic but no detector"
            else:
                assert dim not in DETECTORS, f"{dim} is LLM but in DETECTORS"
```

**Acceptance:**
- `Rubric.judge_method` is set correctly on all 5 entries: 3 deterministic, 2 LLM.
- `DETECTORS` dict has exactly 3 entries matching the deterministic dims.
- All 3 detectors return well-formed `DimensionScore` instances with `status="ok"`, `judge_method="deterministic"`, scores in [0.0, 1.0].
- `tool_selection` LCS produces correct ratios (1.0 exact, 0.0 miss, fractional partial).
- `efficiency` penalizes over-budget + action-loops.
- `final_correctness` honors substring match + termination check.
- `compute_overall_score` (unchanged from Phase 1) handles a mix of deterministic-ok + LLM-ok dims correctly.

**Anti-regression:**
- `test_all_dimensions_defined` still passes (5 keys).
- `test_weights_sum_to_one` still passes (weights unchanged).
- `test_rubric_has_score_anchors` still passes (anchors retained on deterministic Rubrics as historical reference).
- `test_error_recovery_template_no_unreachable_branch` still passes (Phase 2 D4 fix preserved).
- All `TestOverallScore` tests still pass (compute_overall_score unchanged).
- All Phase 1+2 partial-status tests still pass (judge_method orthogonal).

**Dependency:** T1 (DimensionScore.judge_method must exist).

**Atomic commit:** `feat(rubrics): add 3 deterministic detectors + judge_method on Rubric (DET-01..04)`

---

### T3 — `judge.py`: deterministic dispatch in `_evaluate_dimension`

**File:** `src/agent_evaluator/judge.py`, `tests/test_judge.py`

**Changes:**

1. **AnthropicJudge `_evaluate_dimension`** — add deterministic dispatch BETWEEN the Phase 2 short-circuit and the LLM call. **Also update the Phase 2 short-circuit's `DimensionScore` to set `judge_method="deterministic"`** (per plan-checker Concern 3 — the short-circuit IS a deterministic decision based on `scenario.error_injection`; persisting `judge_method="llm"` would be misleading since no LLM was called):

```python
async def _evaluate_dimension(
    self,
    dimension: str,
    trajectory: AgentTrajectory,
    scenario: Scenario,
) -> DimensionScore:
    """Ask the judge LLM to score one dimension.

    Phase 2 short-circuit: error_recovery is N/A for no-injection scenarios.
    Phase 4 deterministic dispatch: dims marked judge_method='deterministic'
    are scored by detector functions (no LLM call).
    """
    # Phase 2 short-circuit (UPDATED Phase 4: set judge_method correctly)
    if dimension == "error_recovery" and len(scenario.error_injection) == 0:
        return DimensionScore(
            dimension="error_recovery", score=0.0,
            reasoning="N/A — no errors injected in this scenario.",
            evidence=[], status="na", error_type=None,
            judge_method="deterministic",  # NEW (Phase 4): not LLM
        )

    # Phase 4 deterministic dispatch
    rubric = RUBRICS[dimension]
    if rubric.judge_method == "deterministic":
        from agent_evaluator.rubrics import DETECTORS
        return DETECTORS[dimension](trajectory, scenario)

    # LLM path (existing)
    user_prompt = rubric.render_user_prompt(
        trajectory=trajectory,
        scenario=scenario,
    )
    # ... rest unchanged
```

2. **OpenAIJudge `_evaluate_dimension`** — same insertion at the parallel location, including the `judge_method="deterministic"` on the Phase 2 short-circuit's DimensionScore.

3. Add tests in `tests/test_judge.py` (extend `TestMakeJudge` or add new class):

```python
@pytest.mark.asyncio
async def test_deterministic_dim_does_not_call_sdk():
    """Phase 4: dims with judge_method='deterministic' route to DETECTORS,
    not the SDK. Verifies efficiency dispatch as a representative case."""
    fake = _FakeAnthropicClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    scenario = _scenario_no_injection()
    trajectory = AgentTrajectory(scenario_id=scenario.id, model_id="t", steps=[])

    result = await judge._evaluate_dimension("efficiency", trajectory, scenario)
    assert result.judge_method == "deterministic"
    assert result.dimension == "efficiency"
    assert result.status == "ok"
    assert fake.call_count == 0  # SDK NOT called


@pytest.mark.asyncio
async def test_llm_dim_still_calls_sdk():
    """Phase 4 anti-regression: parameter_quality still goes to LLM path."""
    fake = _FakeAnthropicClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    scenario = _scenario_no_injection()
    trajectory = AgentTrajectory(scenario_id=scenario.id, model_id="t", steps=[])

    with pytest.raises(AssertionError, match="Short-circuit failed"):
        await judge._evaluate_dimension("parameter_quality", trajectory, scenario)
    assert fake.call_count == 1


@pytest.mark.asyncio
async def test_phase2_short_circuit_sets_judge_method_deterministic():
    """Phase 4 plan-checker fix: when the Phase 2 short-circuit fires
    (error_recovery on no-injection), the persisted DimensionScore must
    record judge_method='deterministic' — the decision was code-level, not
    LLM. Persisting judge_method='llm' would be misleading."""
    fake = _FakeAnthropicClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    result = await judge._evaluate_dimension(
        "error_recovery",
        _empty_trajectory("weather_test"),
        _scenario_no_injection(),
    )
    assert result.status == "na"
    assert result.judge_method == "deterministic"  # was "llm" pre-Phase-4 fix
    assert fake.call_count == 0
```

**Acceptance:**
- AnthropicJudge `_evaluate_dimension("efficiency", traj, scen)` returns `DimensionScore(judge_method="deterministic")` without calling the SDK.
- AnthropicJudge `_evaluate_dimension("parameter_quality", traj, scen)` still routes to the LLM (SDK call attempted).
- AnthropicJudge `_evaluate_dimension("error_recovery", traj, scen_no_injection)` continues short-circuit to `status="na"` (Phase 2 behavior preserved).
- OpenAIJudge has identical dispatch behavior.

**Anti-regression:**
- All Phase 1+2+3 tests continue to pass.
- The 3 short-circuit tests in test_judge.py (Phase 2) still pass.
- The 4 make_judge tests in TestMakeJudge (Phase 3) still pass.

**Dependency:** T1 (judge_method field), T2 (RUBRICS marked + DETECTORS populated).

**Atomic commit:** `feat(judge): dispatch deterministic dims to DETECTORS in _evaluate_dimension (DET-01..04, both classes)`

---

### T4 — `report.py`: judge_method annotation in per-scenario detail

**File:** `src/agent_evaluator/report.py`

**Changes:**

In `generate_report`'s per-scenario detail section, surface judge_method:

```python
# generate_report — per-scenario detail loop
for score in result.dimension_scores:
    cell = _render_dim_cell(score)
    method_tag = f" _({score.judge_method})_" if score.status == "ok" else ""
    status_tag = (
        f"  _(status: {score.status}, error_type: {score.error_type or '—'})_"
        if score.status != "ok" else ""
    )
    lines.append(
        f"**{score.dimension.replace('_', ' ').title()}**: {cell}{method_tag}{status_tag}"
    )
    lines.append(f"> {score.reasoning}\n")
    # ... evidence rendering unchanged
```

So the line for an ok dim now reads e.g.:
```
**Tool Selection**: 0.85 _(deterministic)_
> LCS-based match: actual=['get_weather'], expected=['get_weather']
```

For non-ok dims (error/na), the existing `(status: ..., error_type: ...)` annotation continues to apply; method_tag is omitted to avoid redundancy.

**Acceptance:**
- Per-scenario detail in `generate_report` shows `(deterministic)` or `(llm)` annotation on each ok dim's header line.
- Non-ok dims continue to show `(status: ..., error_type: ...)` only (no method tag).
- `generate_comparison_report` unchanged (no per-cell annotation; would be too noisy in a wide table).

**Anti-regression:**
- No existing tests for report rendering; visual smoke verified in T5.

**Dependency:** T1 (`judge_method` field exists), T3 (deterministic dims actually populate the field).

**Atomic commit:** `feat(report): surface judge_method annotation in per-scenario detail (Phase 4 D4)`

---

### T5 — End-to-end verification

**No file changes.** Verification step.

**Verification checklist:**

1. `pytest -v` — all tests pass. Target count: 47 (Phase 3 baseline) + 4 T1 + ~13 T2 + 3 T3 (incl. judge_method-on-short-circuit test) = **~67 total**. Note: the 2 existing tests `test_v2_from_json_no_warning` and `test_construction_does_not_emit_legacy_warning` are UPDATED in T1 (not added), so they don't increase the count — but their assertions change from `schema_version == 2` → `schema_version == 3`.

2. `ruff check src/ scenarios/ tests/` — zero findings (the existing clean state holds).

3. `agent-eval list` — returns 13 scenarios.

4. **Synthetic E2E (no live API):**
   - Construct a scenario + trajectory; instantiate `AnthropicJudge(client=fake)`; iterate through all 5 dims via `_evaluate_dimension`. Verify:
     - 3 dims return immediately with `judge_method="deterministic"` (no SDK call expected for these).
     - `error_recovery` short-circuits to `status="na"` (no SDK call) when scenario has no injection.
     - `parameter_quality` routes to the LLM path (would call SDK; in test, raises FakeClient AssertionError).
   - Build a synthetic `EvaluationResult` from a real scenario via `evaluate_trajectory` (catching the FakeClient error for the LLM dim or providing canned responses). Verify:
     - `result.schema_version == 3`
     - 3 dims have `judge_method == "deterministic"`, 1 has `judge_method == "llm"` (parameter_quality), 1 has `judge_method == "llm"` (error_recovery — except when scenario has no injection, then status="na" with judge_method="llm" by default since it short-circuits before deterministic dispatch).
   - Call `compute_overall_score(valid_scores)` on a mix of ok-deterministic + ok-llm + na dims. Verify renormalized correctly.
   - Render `generate_report` — verify per-scenario detail shows `(deterministic)` and `(llm)` annotations.

5. **Cross-phase compatibility check:**
   - Load a synthetic v2 eval JSON via `EvaluationResult.from_json`. Verify: `schema_version=2`, `legacy=False`, all dims `judge_method="llm"` (default applied), no DeprecationWarning emitted.

6. **(Optional, user-required for live closure)** Live-API smoke if available:
   - `agent-eval evaluate <fresh_trajectory.json>` — verify resulting `eval_*.json` shows mixed `judge_method` values (3 deterministic + 2 llm), `schema_version: 3`, and ~2 SDK calls per scenario instead of ~5.

7. **ROADMAP success-criteria mapping:**

| ROADMAP SC | Verified by |
|-----------|-------------|
| 1 (efficiency reproducible bit-for-bit) | T2 detector tests + T5 step 4 |
| 2 (action-loop detection correct on identical/diverse cases) | T2 `test_efficiency_over_budget_with_loops` + diverse scenario test |
| 3 (termination check returns appropriate scores) | T2 `test_final_correctness_no_termination` (un-terminated → 0) + terminated case |
| 4 (count of LLM-judged dims decreases; rationale documented) | T2 RUBRICS marks; CONTEXT.md D1 documents; T5 step 4 verifies dispatch |

**Atomic commit:** None — verification only.

---

## Risks and watch-items

1. ~~**`error_recovery` short-circuit returns judge_method="llm" by default**~~ **RESOLVED in plan revision (post plan-check Concern 3):** the Phase 2 short-circuit's `DimensionScore` construction in T3 now explicitly sets `judge_method="deterministic"`. This keeps the persisted `eval_*.json` honest: the dim was decided by code (based on `scenario.error_injection`), so `judge_method="deterministic"` accurately describes how the score was produced. New test `test_phase2_short_circuit_sets_judge_method_deterministic` defends this.

2. **Detector formulas are heuristics.** Phase 4 ships baseline formulas that match the test cases; calibration against human ground truth is deferred to v2. Risk: detector scores might not correlate well with human judgment on edge cases. Acceptable for v1 — the alternative (LLM judgment) had silent-zero issues, so deterministic-with-some-noise is still an improvement.

3. **`scenario.expected_final_answer_contains` substring match is case-insensitive but otherwise literal.** Doesn't handle synonyms or semantic equivalence. A Phase 4 detector saying "agent failed final_correctness" might be wrong if the agent gave a semantically correct but worded-differently answer. Mitigation: scenarios should use distinctive substrings (e.g., specific numbers, keywords). Documented in detector docstring.

4. **Backwards compat with v2 eval files in production.** A user who has a `results/eval_*.json` from before Phase 4 would load it with all dims `judge_method="llm"`. That's accurate — those files WERE all-LLM-judged. No action needed; Phase 4 is forward-compatible.

5. **`_count_consecutive_identical` compares `parameters` dicts directly.** Python dict equality is structural; should work for typical scenarios. Edge case: dicts with different key insertion orders would still compare equal in Python 3.7+. Risk: very low.

## Open questions deferred to executor

1. (T2 detector formulas) Exact penalty curves and thresholds. Sketched values are starting points; planner can refine. **Recommendation:** ship as sketched; tune in v2 if needed.
2. (T2 LCS) Whether to prefer Levenshtein distance over LCS. **Recommendation:** LCS — matches the "subsequence" semantic of `expected_tool_sequence` (order matters but interleaved extra calls are tolerable).
3. (T4 annotation format) Whether `_(deterministic)_` italic vs `[det]` bracket vs symbol prefix. **Recommendation:** italic in parens — matches existing status annotation style.
4. (T5 step 4) Whether to provide canned LLM responses for `parameter_quality` in the synthetic E2E to actually compute an overall_score. **Recommendation:** yes for thoroughness; can use a fixed-response fake client.

## Estimated work

- T1: 25 min (schema + 4 new tests + 2 existing test updates per plan-checker Concern 1)
- T2: 60 min (Rubric extension + 3 detectors with formulas + LCS helper + ~13 detector tests)
- T3: 25 min (dispatch in 2 sites + Phase 2 short-circuit `judge_method` fix per Concern 3 + 3 tests)
- T4: 10 min (one rendering tweak)
- T5: 20 min (synthetic E2E exercise)
- **Total: ~140 min** (was 130; +10 min for plan-checker fixes)

## Out of scope (reaffirmed)

- Calibration of deterministic dims against human ground truth — v2 research project.
- Variance / N-trials / repeated-run averaging — v2.
- Detector tuning beyond baseline formulas — v2.
- Schema_version validator changing trigger threshold — D3 explicitly preserves `< 2`.
- Per-scenario weight overrides — uniform weights stay.
- TEST integration tests for full LLM paths — Phase 5.

---
*Plan written: 2026-05-06 from CONTEXT.md decisions D1–D4 + canonical refs. Same SDK-API caveat as Phases 1+2+3; manual planning equivalent quality. Verification by `gsd-plan-checker` next.*
