# Phase 2 Context — Error Recovery Dimension Fix

**Phase:** 02 — Error Recovery Dimension Fix
**Goal:** Eliminate the +0.15-weighted constant on the 11 scenarios with no `error_injection`. After this phase, `error_recovery` returns `status="na"` for those scenarios (excluded from the weighted sum), and stays LLM-judged honestly for `code_generation` and `debug_code`.
**Requirements:** DIM-01, DIM-02
**Status:** discussion complete; planning next

---

## Domain

The constant-as-signal defect (System Judge F-B). `results/legacy/comparison-2026-04-08.md` empirically shows Error Recovery = 1.00 in 26/26 cells, contributing a fixed 0.15 bias to overall scores on most scenarios. Phase 2 makes the dimension N/A by configuration (per scenario) and exercises the existing TRUST schema's `status="na"` path.

## Canonical refs

- `.planning/research/JUDGMENT.md` — F-B is the Phase 2 target (Tier 1 INEVITABLE)
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/REQUIREMENTS.md` — DIM-01, DIM-02 acceptance
- `.planning/ROADMAP.md` — Phase 2 success criteria
- `.planning/phases/01-trustworthy-score-schema/01-CONTEXT.md` — Phase 1 D1–D4 (TRUST schema this phase relies on)
- `src/agent_evaluator/rubrics.py:178-179` — the `{% if error_steps|length == 0 %}` branch to remove
- `src/agent_evaluator/judge.py::_evaluate_dimension` — short-circuit insertion point

## Carried-forward decisions (locked, NOT re-asked)

From Phase 1 (Phase 2 builds on these):
- `DimensionScore.status: Literal["ok","error","na"]` field exists with `error_type: str | None`.
- `compute_overall_score` already excludes non-`ok` from numerator AND denominator (TRUST-03).
- Report renders `--` for `na` cells, `0.85*` for `error` cells.
- `EvaluationResult.from_json` handles legacy detection.

## Decisions

### D1 — N/A trigger mechanism: hybrid (short-circuit + rubric cleanup)

The N/A decision is made **in code** (judge.py), not via prompt. Two coordinated changes:

**1a. Short-circuit in `judge.py::_evaluate_dimension`** — before the LLM call, check if the dimension is `error_recovery` AND the scenario has empty `error_injection`. If yes, return immediately with `status="na"`. No SDK call.

```python
async def _evaluate_dimension(self, dimension, trajectory, scenario):
    # Short-circuit: error_recovery is N/A for scenarios without injection.
    # See .planning/research/JUDGMENT.md F-B and Phase 2 D1.
    if dimension == "error_recovery" and len(scenario.error_injection) == 0:
        return DimensionScore(
            dimension="error_recovery",
            score=0.0,
            reasoning="N/A — no errors injected in this scenario.",
            evidence=[],
            status="na",
            error_type=None,
        )
    # ... existing LLM-call path
```

**1b. Remove the unreachable rubric branch in `rubrics.py`** (D4 below — surgical removal of `{% if error_steps|length == 0 %}` block).

**Why hybrid (not prompt-only, not short-circuit-only):**
- **Short-circuit**: deterministic (no judge variance), saves ~17% of judge tokens (1 dim × 11 of 13 scenarios), aligned with the Law-1 principle from JUDGMENT.md ("don't trust the LLM with deterministic decisions").
- **Rubric cleanup**: the `score this as 1.0` branch is dead code post-short-circuit. Leaving it in is bit-rot; removing it is bookkeeping. Belt-and-suspenders also protects against a future regression that bypasses the short-circuit (the rubric would then NOT silently regress to 1.0).

### D2 — N/A detection signal: scenario config only

**Single signal:** `len(scenario.error_injection) == 0`. No runtime trajectory inspection.

**Why config-only (not config + runtime, not runtime-only):**
- Simplest. Scenario's `error_injection` IS the configuration of "this scenario tests error recovery." If the list is empty, the scenario isn't testing error recovery, regardless of whether runtime errors happened to occur.
- A scenario configured with errors but where the agent legitimately avoided triggering them is still meaningful eval surface — the LLM judge can score it honestly ("agent did/didn't navigate the error space well"). Don't conflate scenario design with runtime behavior.
- Future scenario authors get a clean rule: "leave error_injection empty if your scenario doesn't test error recovery."

### D3 — N/A vs partial semantics: `partial = error-only`; N/A silent (Phase 1 amendment)

**Phase 2 amends Phase 1's `EvaluationResult.partial` definition:**

```python
# BEFORE (Phase 1 D2 / TRUST-02):
@computed_field
@property
def partial(self) -> bool:
    return any(ds.status != "ok" for ds in self.dimension_scores)

# AFTER (Phase 2 D3):
@computed_field
@property
def partial(self) -> bool:
    return any(ds.status == "error" for ds in self.dimension_scores)
```

**Report footnote semantics correspondingly tightened:**
- `report.py::_partial_footnote_lines` — inner loop already skips `status == "ok"`; change to skip `status != "error"` (skip both `ok` and `na`). Only real errors appear in the "Partial evaluations" footnote.
- N/A cells render as `--` per existing rule. No additional footnote for N/A.

**Why this amendment:**
- `partial=True` should be an **actionable warning** ("be cautious about this score") — not a routine N/A note.
- Original Phase 1 D2 conflated error and na under `partial`. Once N/A becomes common (most scenarios in Phase 2+), the footnote would fill with non-actionable entries, training users to ignore real errors. Alert fatigue.
- N/A is legitimately routine (a scenario simply doesn't test that dim); error is genuinely bad (something went wrong). Different semantics → different signal level.

**Phase 1 acceptance criteria still hold:** TRUST-02 ("EvaluationResult.partial is correctly set when any dimension errored") is satisfied — `error` is the strict subset, but the spec text used "errored" to mean "actual failure," not "any non-ok." This amendment tightens to the more useful semantic.

**Test impact:**
- Phase 1 `test_partial_true_when_any_error`: passes unchanged (error dim → partial True).
- Phase 1 `test_partial_false_when_all_ok`: passes unchanged.
- Phase 1 `test_partial_round_trip`: passes unchanged.
- New test in Phase 2: `test_partial_false_when_only_na_dims` — a result with one `na` dim (and rest ok) has `partial == False`.

### D4 — Rubric prompt: surgical removal of unreachable branch

**Edit `rubrics.py:178-179`** — delete the `{% if error_steps|length == 0 %}` ... `{% endif %}` block in the `error_recovery` rubric template. Keep the rest of the rubric intact (the score anchors, the system prompt, the body for non-empty error_steps).

**No rewrite of the rest of the prompt.** Phase 4 (DET-04) will revisit which dimensions stay LLM-judged vs become deterministic detectors. If `error_recovery` survives that audit, Phase 4 can do the substantive prompt improvement. If it gets collapsed to deterministic detection, full rewrite would have been wasted.

**Why not full rewrite or full defer:**
- Full rewrite: risk of wasted effort if Phase 4 changes the dim's nature. Also expands Phase 2 scope.
- Full defer: the unreachable branch becomes dead code in the prompt template — visual noise + bit-rot risk. Surgical removal is one edit, one verification.

## Implementation surface (for planner)

### Files to modify

- `src/agent_evaluator/judge.py` — add short-circuit at the top of `_evaluate_dimension` in BOTH `AnthropicJudge` and `OpenAIJudge` (parallel structure, same change).
- `src/agent_evaluator/rubrics.py:178-179` — delete the unreachable Jinja branch.
- `src/agent_evaluator/models.py` — change `EvaluationResult.partial` computed_field body from `!= "ok"` to `== "error"`.
- `src/agent_evaluator/report.py::_partial_footnote_lines` — inner loop filter changes from `if ds.status == "ok": continue` to `if ds.status != "error": continue`.

### Tests to add

- `tests/test_models.py::TestEvaluationResult::test_partial_false_when_only_na_dims` — single result with one na + four ok → `partial == False`. Asserts the Phase 2 D3 amendment.
- `tests/test_judge.py` (NEW FILE) — minimal test for the short-circuit path. Mock the judge client at the boundary (no LLM call expected). Construct a scenario with empty error_injection. Call `judge._evaluate_dimension("error_recovery", traj, scenario)`. Assert returned `DimensionScore(status="na")`. Assert SDK was NOT called.
- `tests/test_rubrics.py` — no new tests strictly needed (the rubric branch removal is unreachable). Optional: assert the rubric template doesn't contain the removed text.

### Anti-regression checks

- All 30 Phase-1 tests continue to pass.
- Specifically: Phase 1's `test_partial_true_when_any_error` continues to pass (error dim → partial True). The semantic tightening (D3) doesn't break this case.
- A scenario with `len(error_injection) > 0` (i.e., `code_generation`, `debug_code`) continues to invoke the LLM judge for `error_recovery` — short-circuit path NOT taken.
- `compute_overall_score` honors `status="na"` per Phase 1 TRUST-03 — unchanged behavior, just exercised more.

## Open in planning (executor decides, not user)

- Whether to add a small assertion in test for the prompt template that the removed `{% if error_steps|length == 0 %}` block is gone (defensive against accidental re-addition). Lightweight; recommended yes.
- Whether the new `test_judge.py` should mock at the SDK level (`anthropic.AsyncAnthropic`) or at the judge instance level (pass a mock client into the judge constructor). Recommendation: judge constructor mock — simpler, doesn't require monkeypatching SDK internals.

## Code context (reusable assets from Phase 1)

- `_render_dim_cell` in report.py already correctly renders `--` for `status == "na"`.
- `compute_overall_score` already excludes `status != "ok"` (so na works for free).
- `DimensionScore.status="na"` is a no-op constructor change (default is `"ok"`, just specify when needed).
- `EvaluationResult.partial` only needs the predicate body change, the field shape stays.

## Deferred ideas

- **Full rewrite of error_recovery rubric** — defer to Phase 4 (DET-04) audit.
- **Runtime detection signal** (na iff no injection AND no runtime errors) — rejected per D2; revisit if a scenario ships where this matters.
- **Per-scenario dimension applicability matrix** — generalizing N/A beyond `error_recovery` (e.g., `efficiency` for trivial scenarios) — Phase 4 territory.
- **Telemetry on N/A rate per dimension** — operational, deferred to v2.

## Next steps

1. `/gsd-plan-phase 2` — produce 02-PLAN.md from this CONTEXT and the canonical refs.
2. Plan should be small (3-4 tasks): models.py partial amendment, judge.py short-circuit (both classes), rubrics.py branch removal, tests.
3. After plan approval, execute. Verify `error_recovery` is `status="na"` on all 11 no-injection scenarios via a synthetic eval (no live API needed).

---
*Discussion complete: 2026-05-06. 4 areas selected, 4 decisions locked. Phase 2 amends Phase 1's `partial` semantic per D3 — flag this in PLAN.md so the executor doesn't miss the cross-phase impact.*
