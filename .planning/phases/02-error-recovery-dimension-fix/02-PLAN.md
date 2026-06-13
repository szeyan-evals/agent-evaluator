# Phase 2 Plan — Error Recovery Dimension Fix

**Phase:** 02 — Error Recovery Dimension Fix
**Source decisions:** `02-CONTEXT.md` (D1–D4)
**Source artifacts:**
- `.planning/research/JUDGMENT.md` (F-B is the Phase 2 target)
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/REQUIREMENTS.md` (DIM-01, DIM-02)
- `.planning/ROADMAP.md` (Phase 2 success criteria 1–3)
- `.planning/phases/01-trustworthy-score-schema/01-CONTEXT.md` (Phase 1 D1–D4 — the schema this phase relies on)

**Goal restatement:** Eliminate the `+0.15`-weighted constant on the 11 scenarios with no `error_injection`. After this phase, `error_recovery` returns `status="na"` for those scenarios (excluded from the weighted sum), and stays LLM-judged for `code_generation` and `debug_code`.

---

## Pre-flight notes

### Phase 1 amendment: `partial` semantic tightening

CONTEXT D3 amends the `EvaluationResult.partial` computed_field shipped in Phase 1. Phase 1 defined:

```python
@computed_field
@property
def partial(self) -> bool:
    return any(ds.status != "ok" for ds in self.dimension_scores)  # PHASE 1
```

Phase 2 tightens to:

```python
@computed_field
@property
def partial(self) -> bool:
    return any(ds.status == "error" for ds in self.dimension_scores)  # PHASE 2
```

**Why now, not Phase 1:** Phase 1 didn't yet have N/A in production. Phase 2 introduces N/A as a routine status. Without the tightening, every no-injection scenario would surface in the "Partial evaluations" footnote — alert fatigue. Done now to land alongside the work that introduces the load.

**Phase 1 tests still pass:** `test_partial_true_when_any_error` (uses error dim → still True), `test_partial_false_when_all_ok` (no non-ok → still False), `test_partial_round_trip` (uses error dim). Only the SEMANTIC of `partial` changes; the tests don't exercise the old-vs-new edge case.

### Build-green-after-every-commit ordering

| T# | Lands | Why build stays green |
|----|-------|-----------------------|
| T1 | models.py `partial` amendment + new test | Existing 30 tests use only ok or error cases, not pure-na. New test validates the amendment. |
| T2 | judge.py short-circuit (both classes) + test_judge.py | No existing test exercises the short-circuit path; the new test validates it without mocking SDKs. |
| T3 | report.py footnote tightening | No existing test for footnote logic. T1 already changed `partial` semantics; T3 propagates the tightening to the rendered output. |
| T4 | rubrics.py Jinja branch removal | No existing test validates the rubric's unreachable branch. Optional defensive assertion in T4 protects against accidental re-addition. |
| T5 | Verification | E2E smoke; live-API path noted but not required for closure. |

---

## Tasks

### T1 — `models.py` `partial` amendment + N/A-only test

**File:** `src/agent_evaluator/models.py`, `tests/test_models.py`

**Changes:**

1. In `models.py`, change the `partial` computed_field body:

```python
@computed_field  # type: ignore[prop-decorator]
@property
def partial(self) -> bool:
    return any(ds.status == "error" for ds in self.dimension_scores)
```

2. Add new test in `tests/test_models.py::TestEvaluationResult`:

```python
def test_partial_false_when_only_na_dims(self):
    """Phase 2 D3: N/A status should NOT make a result partial."""
    result = EvaluationResult(
        scenario_id="test",
        model_id="test-model",
        dimension_scores=[
            DimensionScore(
                dimension="tool_selection", score=0.9, reasoning="ok"
            ),
            DimensionScore(
                dimension="error_recovery", score=0.0,
                reasoning="N/A — no errors injected",
                status="na", error_type=None,
            ),
        ],
        overall_score=0.9, summary="ok",
    )
    assert result.partial is False
    dumped = json.loads(result.model_dump_json())
    assert dumped["partial"] is False
```

**Acceptance:**
- `result.partial is False` for a result containing one `na` dim and otherwise-ok dims.
- `result.partial is True` for a result containing any `error` dim (existing tests still pass).
- The dumped JSON's top-level `partial` key reflects the new semantic.

**Anti-regression:**
- All 30 Phase 1 tests pass without changes.
- Specifically: `test_partial_true_when_any_error`, `test_partial_false_when_all_ok`, `test_partial_round_trip` all continue to pass with the new definition.

**Atomic commit:** `refactor(models): tighten EvaluationResult.partial to error-only (Phase 2 D3 amends Phase 1)`

---

### T2 — Judge `_evaluate_dimension` short-circuit (both classes) + test_judge.py

**Files:** `src/agent_evaluator/judge.py`, `tests/test_judge.py` (NEW)

**Changes:**

1. **AnthropicJudge `_evaluate_dimension` (currently `judge.py:88-120` area)** — insert short-circuit at the top of the method, BEFORE the retry loop:

```python
async def _evaluate_dimension(
    self,
    dimension: str,
    trajectory: AgentTrajectory,
    scenario: Scenario,
) -> DimensionScore:
    """Ask the judge LLM to score one dimension.

    Short-circuit: error_recovery is N/A for scenarios with no
    error_injection. See .planning/research/JUDGMENT.md F-B and
    .planning/phases/02-.../02-CONTEXT.md D1+D2.
    """
    if dimension == "error_recovery" and len(scenario.error_injection) == 0:
        return DimensionScore(
            dimension="error_recovery",
            score=0.0,
            reasoning="N/A — no errors injected in this scenario.",
            evidence=[],
            status="na",
            error_type=None,
        )

    rubric = RUBRICS[dimension]
    user_prompt = rubric.render_user_prompt(...)
    # ... existing retry loop unchanged
```

2. **OpenAIJudge `_evaluate_dimension`** — insert the same short-circuit at the top of the parallel method (same pattern, same logic).

3. **Create `tests/test_judge.py`** — single test that validates the short-circuit fires WITHOUT a live SDK call:

```python
"""Tests for judge short-circuit logic (Phase 2 D1)."""

import pytest

from agent_evaluator.judge import AnthropicJudge, OpenAIJudge
from agent_evaluator.models import (
    AgentTrajectory,
    Scenario,
    ToolDefinition,
)


def _scenario_no_injection() -> Scenario:
    return Scenario(
        id="weather_test",
        name="Weather Test",
        description="Look up weather",
        user_query="What's the weather?",
        available_tools=[
            ToolDefinition(
                name="get_weather",
                description="Get weather",
                parameters_schema={"type": "object", "properties": {}},
            ),
        ],
        expected_tool_sequence=["get_weather"],
        expected_final_answer_contains=["weather"],
        max_reasonable_steps=2,
        error_injection=[],  # NO injection — should short-circuit
    )


def _empty_trajectory() -> AgentTrajectory:
    return AgentTrajectory(
        scenario_id="weather_test",
        model_id="claude-test",
        steps=[],
    )


class _FakeClient:
    """Records SDK calls to verify short-circuit means no API call."""

    def __init__(self):
        self.call_count = 0

    @property
    def messages(self):
        return self

    async def create(self, **kwargs):
        self.call_count += 1
        raise AssertionError("Short-circuit failed: SDK was called")


@pytest.mark.asyncio
async def test_anthropic_short_circuits_error_recovery_when_no_injection():
    fake = _FakeClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    result = await judge._evaluate_dimension(
        "error_recovery", _empty_trajectory(), _scenario_no_injection()
    )
    assert result.status == "na"
    assert result.dimension == "error_recovery"
    assert "no errors injected" in result.reasoning.lower()
    assert fake.call_count == 0  # SDK MUST NOT be called


@pytest.mark.asyncio
async def test_anthropic_does_not_short_circuit_other_dimensions():
    """For non-error_recovery dims, short-circuit must not fire even on
    no-injection scenarios. The LLM call would happen — verify by asserting
    the SDK IS called (then fails the assertion, which we catch)."""
    fake = _FakeClient()
    judge = AnthropicJudge(client=fake, model="claude-test")
    with pytest.raises(AssertionError, match="Short-circuit failed"):
        await judge._evaluate_dimension(
            "tool_selection", _empty_trajectory(), _scenario_no_injection()
        )
    assert fake.call_count == 1  # SDK was called as expected
```

**Note on the second test (per plan-checker concern):** `test_anthropic_does_not_short_circuit_other_dimensions` passes both pre-T2 (because the short-circuit doesn't yet exist, so any dim invokes the SDK) and post-T2 (because the short-circuit fires only for `error_recovery`). It does NOT directly validate the T2 change — its role is defense-in-depth against an over-broad short-circuit (e.g., a future typo of `if dimension != "tool_selection"`). The primary regression signal for T2 is the first test (`test_anthropic_short_circuits_error_recovery_when_no_injection`).

(OpenAI variant of the test is skipped initially — same logic, more SDK plumbing. Add if Phase 5 demands it; for Phase 2 the AnthropicJudge test proves the short-circuit pattern.)

**Acceptance:**
- `pytest tests/test_judge.py -v` — both new tests pass.
- AnthropicJudge `_evaluate_dimension("error_recovery", traj, scenario_with_empty_injection)` returns a `DimensionScore` with `status="na"`, `dimension="error_recovery"`, reasoning mentioning "no errors injected".
- The SDK is NOT called when the short-circuit fires.
- For non-`error_recovery` dimensions, the short-circuit does NOT fire (LLM call attempted, in the test caught by the fake client raising).
- For `error_recovery` on a scenario WITH `error_injection`, short-circuit does NOT fire (existing LLM path retained for `code_generation`, `debug_code`).

**Anti-regression:**
- AnthropicJudge `_evaluate_dimension("error_recovery", traj, scenario_with_injection)` continues to invoke the LLM (covered implicitly — we don't add a test that breaks if it does call, just one that requires it doesn't call when no injection).

**Dependency:** T1 (the new short-circuit returns `status="na"`, which depends on the schema; though T1's specific change to `partial` is independent — short-circuit just needs the existing schema fields). Order T1 first for clean cross-phase amendment.

**Atomic commit:** `feat(judge): short-circuit error_recovery to status=na when no injection (DIM-01, F-B remediation)`

---

### T3 — `report.py` partial-footnote inner-loop tightening

**File:** `src/agent_evaluator/report.py`

**Changes:**

In `_partial_footnote_lines`, change the inner loop filter:

```python
# BEFORE (Phase 1 T4):
for ds in r.dimension_scores:
    if ds.status == "ok":
        continue
    err = ds.error_type or "unknown"
    lines.append(...)

# AFTER (Phase 2 D3):
for ds in r.dimension_scores:
    if ds.status != "error":
        continue
    err = ds.error_type or "unknown"
    lines.append(...)
```

**Acceptance:**
- A result with one `status="error"` dim and one `status="na"` dim has only the error dim listed in the "Partial evaluations" footnote (na is silent).
- A result with only `status="na"` dims has `partial == False` (per T1) and is not listed in the footnote at all.
- `_partial_footnote_lines` returns `[]` if no result has `partial == True` (note: post-T1, only error makes a result partial).

**Anti-regression:**
- Per-cell rendering unchanged: `--` for na, `0.85*` for error, `0.85` for ok.
- Per-scenario detail section in `generate_report` continues to surface status info for non-ok dims (including na — useful in the verbose section).
- Average-row partial-marker logic unchanged: still `*` when any contributing row has `errored == True` (which post-T1 is equivalent to `partial == True`).

**Dependency:** T1 (logical — the footnote contents must align with the new `partial` semantic; physically T3 could land before T1 with no observable break, but the build-green table sequences T1 first for narrative consistency).

**Atomic commit:** `refactor(report): tighten partial footnote to error-only entries (Phase 2 D3)`

---

### T4 — `rubrics.py` surgical Jinja branch removal

**Files:** `src/agent_evaluator/rubrics.py`, optional defensive test in `tests/test_rubrics.py`

**Changes:**

1. In `rubrics.py`, the `error_recovery` rubric's `user_prompt_template` currently contains:

```jinja
{% set error_steps = trajectory.steps | selectattr('tool_response.error') | list %}
{% if error_steps | length == 0 %}
No errors occurred. Score this as 1.0 with reasoning "N/A — no errors to recover from."
{% else %}
### Scoring Rubric
- 1.0: Immediately adapted strategy, tried alternative approach, succeeded
- 0.7: Recovered but took an extra step or two
- 0.4: Blindly retried the same call, or gave up too quickly
- 0.0: Ignored the error, repeated it, or spiraled

For each error: What did the agent do next? Did it change parameters, try a different tool, or ask for clarification?
{% endif %}
```

Replace with the unconditional non-empty branch (drop the `{% set %}`, `{% if %}`, no-error message, `{% else %}`, and `{% endif %}`):

```
### Scoring Rubric
- 1.0: Immediately adapted strategy, tried alternative approach, succeeded
- 0.7: Recovered but took an extra step or two
- 0.4: Blindly retried the same call, or gave up too quickly
- 0.0: Ignored the error, repeated it, or spiraled

For each error: What did the agent do next? Did it change parameters, try a different tool, or ask for clarification?
```

2. Add a defensive assertion in `tests/test_rubrics.py::TestRubrics`:

```python
def test_error_recovery_template_no_unreachable_branch(self):
    """Phase 2 D4: the unreachable no-error branch is removed.

    Post-Phase-2 the short-circuit in judge.py prevents the LLM from
    seeing the no-error case, so the rubric template must not contain
    the dead 'No errors occurred. Score this as 1.0' instruction.
    See .planning/research/JUDGMENT.md F-B.
    """
    template = RUBRICS["error_recovery"].user_prompt_template
    assert "Score this as 1.0" not in template
    assert "{% if error_steps" not in template
    assert "No errors occurred." not in template
```

**Acceptance:**
- The defensive test passes (the removed strings are absent from the template).
- The remaining template content is the original "Scoring Rubric" + the per-error question, with NO Jinja conditional wrapping.
- The rubric's `score_anchors` dict (lines 155-161) still includes the `"N/A"` key — it's documentation-only metadata; not removed.

**Anti-regression:**
- `test_all_dimensions_defined` continues to pass (5 keys including `error_recovery`).
- `test_weights_sum_to_one` continues to pass (weights unchanged).
- `test_rubric_has_score_anchors` continues to pass (1.0 and 0.0 anchors preserved).

**Dependency:** T2 (the short-circuit makes this branch unreachable; removing it before T2 lands could theoretically allow a regression if the short-circuit weren't yet in place — though the rubric-without-no-error-branch would just send the LLM a slightly different prompt, not a hard break. T2-then-T4 is the safe order.)

**Atomic commit:** `chore(rubrics): remove unreachable no-error branch from error_recovery template (Phase 2 D4)`

---

### T5 — End-to-end smoke verification

**No file changes.** Verification step that runs after T1–T4 land.

**Verification checklist:**

1. `cd /Users/szeyan/Documents/Dev/agent-evaluator && pytest -v` — all tests pass: 30 from Phase 1 + 1 (T1's new partial-na test) + 2 (T2's two judge short-circuit tests) + 1 (T4's defensive rubric test) = 34 total. Ruff: still 1 finding (book_flight unused import — JUDGMENT F-J, deferred to Phase 3).
2. `agent-eval list` returns 13 scenarios (anti-regression for EVAL-03).
3. **Synthetic E2E smoke (no live API needed):**
   - For each of the 11 no-injection scenarios, construct an `AgentTrajectory` (empty steps OK), run `AnthropicJudge(client=fake)._evaluate_dimension("error_recovery", traj, scenario_loaded_from_registry)`. Verify each returns `status="na"` without invoking the SDK.
   - For `code_generation` and `debug_code`, verify the short-circuit does NOT fire (would invoke SDK in real life; with `_FakeClient` this raises AssertionError as expected).
   - Construct a synthetic post-Phase-2 `EvaluationResult` for a no-injection scenario with all 5 dims, where `error_recovery.status="na"` and the other 4 are ok. Verify `result.partial is False`. Verify `compute_overall_score(dim_scores)` returns the renormalized score over 4 dims (excluding the na dim from numerator AND denominator) — value matches the manually-computed renormalization.
   - Run `generate_comparison_report` over a mix of no-injection (partial=False, error_recovery=`--`) and post-injection results; verify the rendered table shows variance in the Error Recovery column rather than constant 1.00.

4. **(REQUIRED for phase completion — same as Phase 1 T7 step 4)** Live-API smoke if API keys are available: run `agent-eval evaluate <fresh_trajectory_for_weather_lookup.json>`. Verify the resulting `eval_*.json` shows `error_recovery.status == "na"`, `score=0.0`, reasoning containing "no errors injected", and SDK call count is 4 (not 5) for that run. Same handoff caveat as Phase 1: requires `ANTHROPIC_API_KEY` and consumes tokens; user-required if no in-tree trajectory exists.

5. **ROADMAP success-criteria mapping:**

| ROADMAP SC | Verified by |
|-----------|-------------|
| 1 (no-injection scenarios produce `error_recovery.status == "na"`) | T2 acceptance + T5 step 3 (synthetic) + T5 step 4 (live, optional) |
| 2 (`code_generation`, `debug_code` continue to be LLM-judged) | T2 acceptance ("does not short-circuit other dimensions" test) + T5 step 3 |
| 3 (`compute_overall_score` returns renormalized 4-dim score on no-error scenarios; comparison shows variance) | Phase 1 TRUST-03 (already shipped) + T5 step 3 (renormalization assertion + variance in synthetic comparison) |

If any step fails: do NOT mark the phase complete. File a follow-up task or reopen the relevant T#.

**Atomic commit:** None — verification only.

---

## Risks and watch-items

1. **`_evaluate_dimension` short-circuit ordering.** The short-circuit must run BEFORE the rubric/SDK setup. Inserting it as the first statement in the method (above `rubric = RUBRICS[dimension]`) ensures the LLM is never invoked for the N/A case. Verified by T2's `_FakeClient` test asserting `call_count == 0`.

2. **`score=0.0` on N/A.** Same convention as `status="error"` — score is meaningless when status != "ok", but the field-level `Field(ge=0.0, le=1.0)` constraint requires a value. Setting `0.0` is consistent with Phase 1's error path; downstream consumers must check `status` before using `score`.

3. **`evidence=[]` on the short-circuit.** No trajectory inspection happens, so no evidence to cite. Consistent with the error path (also `evidence=[]`).

4. **Phase 1 amendment risk.** D3 changes the `partial` semantic in models.py. If any external consumer is reading `partial` and depending on the "any non-ok" semantic, this is a breaking change. There are no external consumers in this repo (verified by Phase 1's anti-regression analysis — `partial` is only consumed by `report.py`). T3 updates report.py to align. **Risk: low and contained.**

5. **OpenAIJudge short-circuit not test-covered in Phase 2.** The pattern is identical to AnthropicJudge; the same _FakeClient pattern would work for OpenAI's `chat.completions.create` shape. Deferred to Phase 5 TEST-01 / TEST-02 to avoid Phase 2 scope creep on test infrastructure. **Risk: parallelism between two implementations is brittle if one drifts; mitigated by code review of both sites in T2.**

6. **Future scenario authors might forget to set `error_injection` and intend non-N/A behavior.** The implicit contract becomes "leave error_injection empty → error_recovery is N/A." This is documented in CONTEXT.md D2 but not enforced by code. **Risk: low; surface area is tiny (only the error_recovery dim cares).**

7. **Defensive `len(scenario.error_injection)` access (per plan-checker concern).** The short-circuit assumes `scenario` is a real `Scenario` instance with `error_injection` populated by Pydantic's `default_factory=list`. All current call sites pass typed `Scenario` and the field default ensures it's always a list (never `None`, never missing). If a future caller passes a duck-typed object or a partially-deserialized dict, `len(scenario.error_injection)` would raise `AttributeError`. **Risk: very low** — would surface immediately and loudly (not silently corrupt data). Mitigation deferred unless a real call site emerges; keeping the simple `len()` form keeps T2 minimal.

## Open questions deferred to executor

1. (T2) Whether to add the OpenAIJudge variant of the short-circuit test in Phase 2 or defer to Phase 5. **Recommendation:** defer to Phase 5 — keeps Phase 2 lean. Add a note in `02-CONTEXT.md "deferred ideas"`.
2. (T4) Whether to also remove the `"N/A"` key from `score_anchors` (currently at `rubrics.py:160`). **Recommendation:** keep — it's documentation-only metadata and the test doesn't explicitly require its removal.
3. (T5 step 4) Whether to bundle a one-time `agent-eval run --scenario weather_lookup` smoke that produces a real trajectory + eval to verify end-to-end without manual ad-hoc steps. **Recommendation:** out of scope for Phase 2 plan; the user runs it once on demand to close the live-API verification gap.

## Estimated work

- T1: 10 min (one-line change + one new test)
- T2: 25 min (short-circuit at 2 sites + new test_judge.py with 2 tests)
- T3: 5 min (one-line filter change)
- T4: 10 min (Jinja edit + defensive test)
- T5: 15 min (synthetic smoke + verification checklist)
- **Total: ~65 min**

## Out of scope (reaffirmed)

- Real (non-mocked) tool execution — out of scope per PROJECT.md.
- Full rewrite of `error_recovery` rubric prompt — D4 surgical only; Phase 4 (DET-04) revisits.
- Runtime-error-detection signal — D2 rejected this; only `len(scenario.error_injection) == 0` triggers N/A.
- Adding `errored` / `has_na` separate computed fields — D3 collapsed `partial` to error-only; no new field needed.
- F-G / F-H / F-I (regression guards) — Phase 5.
- VEND, DET, TEST requirements — their own phases.

---
*Plan written: 2026-05-06 from CONTEXT.md decisions D1–D4 + canonical refs. Same SDK-API caveat as Phase 1: manual planning equivalent quality. Verification by `gsd-plan-checker` next.*
