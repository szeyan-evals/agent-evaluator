# Phase 4 Context — Deterministic Detectors First

**Phase:** 04 — Deterministic Detectors First
**Goal:** Replace LLM-judged dimensions that are actually arithmetic with code-level checks. Reduces failure surface (fewer LLM calls = fewer silent-zero opportunities), reduces cost, makes scores reproducible. Target per DET-04: 3 deterministic + 2 LLM-judged dims.
**Requirements:** DET-01, DET-02, DET-03, DET-04
**Status:** discussion complete; planning next

---

## Domain

Phase 4 is the largest remaining behavioral change. Per the post-judgment discussion (see "What AI Eval Needs" exchange in chat history): "many things being judged by LLMs (token efficiency, action loops, redundant context) genuinely could be code." This phase implements that principle.

Composes with prior phases:
- Phase 1 TRUST schema makes deterministic dim status carry the same `status` field semantics as LLM dims
- Phase 2 short-circuit established the precedent for code-level dim resolution before LLM call
- Phase 3 vendor coupling unaffected (judges are still selected by `make_judge` for the LLM dims)

## Canonical refs

- `.planning/research/JUDGMENT.md` — F-A (silent-zero amplifier; reducing LLM call surface reduces F-A blast)
- `.planning/REQUIREMENTS.md` — DET-01..04
- `.planning/ROADMAP.md` — Phase 4 success criteria
- `.planning/codebase/ARCHITECTURE.md` — current rubric structure
- `src/agent_evaluator/rubrics.py` — `Rubric` class + 5 RUBRICS dict
- `src/agent_evaluator/judge.py::_evaluate_dimension` — Phase 2 short-circuit insertion point (parallel to where Phase 4 deterministic dispatch lives)
- `src/agent_evaluator/models.py::DimensionScore` — schema target for Phase 4 `judge_method` field

## Carried-forward (locked from prior phases)

- `DimensionScore.status: Literal["ok","error","na"]` (Phase 1)
- `EvaluationResult.partial = any(status == "error")` (Phase 2 D3 amendment)
- `EvaluationResult.schema_version: int = 2` (Phase 1) — Phase 4 bumps to **3**
- `compute_overall_score` skips non-`ok` dims (TRUST-03)
- `make_judge(model, *, client=None)` factory (Phase 3)

## Decisions

### D1 — Per-dim audit: 3 deterministic + 2 LLM-judged

Final dim split:

| Dimension | Weight | Method | Signal |
|---|---|---|---|
| `tool_selection` | 0.25 | **deterministic** | Compare actual tool sequence against `scenario.expected_tool_sequence`. Score via longest-common-subsequence ratio (or similar — chosen during planning). |
| `parameter_quality` | 0.20 | **LLM** | Subjective: are tool args well-formed for the task? |
| `efficiency` | 0.20 | **deterministic** | Steps count vs `max_reasonable_steps` + action-loop penalty (see D2). |
| `error_recovery` | 0.15 | **LLM** (with Phase 2 short-circuit to N/A on no-injection scenarios) | Subjective: did the agent adapt? |
| `final_correctness` | 0.20 | **deterministic** | Substring match against `scenario.expected_final_answer_contains` + termination check (see D2). |

**Effective LLM-call reduction:** 60% (3 of 5 dims now deterministic). Combined with Phase 2's `error_recovery` short-circuit on 11/13 scenarios, the typical comparison run drops from ~5 LLM judge calls × 13 scenarios = 65 calls to ~2 LLM calls × 13 scenarios + ~2 LLM calls × 2 scenarios with injection ≈ 30 calls. **~54% total reduction.**

**Why this split (not 2-det/3-LLM, not 4-det/1-LLM):**
- 2-det/3-LLM is too conservative — leaves obvious arithmetic (tool_selection sequence match, final_correctness substring match) under LLM judgment.
- 4-det/1-LLM is too aggressive — `error_recovery` deterministic scoring would be brittle on nuanced cases (e.g., "agent retried but with worse parameters" — needs judgment).
- 3-det/2-LLM keeps LLM judgment for the genuinely subjective dims and matches DET-04 target exactly.

### D2 — DET-02 (action-loops) + DET-03 (termination) folded into existing dims

**No new dimensions added.** The 5-dim structure stays; weights stay; schema_version bump is only for D3 (judge_method).

- **Action-loop detection (DET-02)** folds into `efficiency`:
  ```python
  def _detect_efficiency(traj, scen) -> DimensionScore:
      base_score = _score_step_count(traj, scen)        # steps vs max_reasonable
      loop_penalty = _detect_action_loops(traj)          # consecutive identical calls
      return DimensionScore(
          dimension="efficiency",
          score=max(0.0, base_score - loop_penalty),
          reasoning=f"steps={...}, loops_detected={...}",
          status="ok",
          judge_method="deterministic",
      )
  ```

- **Termination correctness (DET-03)** folds into `final_correctness`:
  ```python
  def _detect_final_correctness(traj, scen) -> DimensionScore:
      substring_match = _check_expected_substrings(traj, scen)  # 0.0–1.0
      termination_ok = _check_termination(traj)                  # bool
      score = substring_match * (1.0 if termination_ok else 0.7)
      return DimensionScore(...)
  ```

**Why folded (not new dims, not standalone):**
- New dims would force schema migration of legacy eval files (more work) AND require weight redistribution across the rubric — bigger structural change with no clean upgrade path.
- Standalone signals (separate report rows not weighted into overall) lose the "this affected the score" signal — users would have to mentally combine.
- Folding keeps the 5-dim contract that PROJECT.md describes and matches typical-user expectations.

### D3 — `DimensionScore.judge_method` field; `EvaluationResult.schema_version` bump v2 → v3

Add to `DimensionScore`:
```python
judge_method: Literal["llm", "deterministic"] = "llm"
```
Default `"llm"` so legacy v2 files load with `judge_method="llm"` for every dim — which matches their actual pre-Phase-4 behavior (everything was LLM-judged, including the dims that should have been deterministic).

Bump `EvaluationResult.schema_version` default from `2` to `3`. The model_validator's `_detect_legacy` logic remains: legacy iff `schema_version < 2`. Files with `schema_version == 2` (post-Phase-1 and pre-Phase-4) are still considered "non-legacy" — they have `judge_method="llm"` filled by the field default, which accurately describes their content.

**Why v2 files are NOT considered legacy in v3:** The contract for `legacy=True` is "file may contain silent-zero corruption" (per Phase 1 D2). v2 files don't have silent-zero corruption (Phase 1 fixed F-A). So they remain trustworthy under v3, just with `judge_method="llm"` everywhere.

**Schema-version trigger update:** the `_detect_legacy` validator checks `if v < 2`. Phase 4 leaves this unchanged — only files that pre-date the TRUST schema (no schema_version, or schema_version=1) trigger the warning. Phase-2/3 files (schema_version=2) load cleanly under v3 with default judge_method="llm".

### D4 — Rubric structure: `judge_method` on Rubric + parallel `DETECTORS` dict

```python
# rubrics.py — extended Rubric class
class Rubric(BaseModel):
    dimension: str
    weight: float = Field(ge=0.0, le=1.0)
    description: str
    judge_method: Literal["llm", "deterministic"] = "llm"
    # LLM fields (used only when judge_method == "llm"):
    system_prompt: str = ""
    user_prompt_template: str = ""
    score_anchors: dict[str, str] = {}

# Detectors live alongside Rubric definitions — separate dict because
# Pydantic models can't cleanly hold Callable fields.
DETECTORS: dict[str, Callable[[AgentTrajectory, Scenario], DimensionScore]] = {
    "tool_selection": _detect_tool_selection,
    "efficiency": _detect_efficiency,
    "final_correctness": _detect_final_correctness,
}

# judge.py::_evaluate_dimension dispatches:
async def _evaluate_dimension(self, dim, traj, scen):
    # Phase 2 short-circuit (na for error_recovery on no-injection)
    if dim == "error_recovery" and len(scen.error_injection) == 0:
        return DimensionScore(...na...)

    # Phase 4 deterministic dispatch
    if RUBRICS[dim].judge_method == "deterministic":
        return DETECTORS[dim](traj, scen)

    # LLM path (existing)
    rubric = RUBRICS[dim]
    user_prompt = rubric.render_user_prompt(...)
    # ... rest unchanged
```

**Why this shape:**
- Single source of truth for dim metadata (Rubric class).
- Detector functions are colocated with Rubric definitions in `rubrics.py` — readers see the whole story per dim.
- judge.py dispatch is one branch — minimal code change.
- Two LLM dims (`parameter_quality`, `error_recovery`) keep their existing Rubric shape (system_prompt + user_prompt_template + score_anchors); deterministic dims have empty strings for those fields (or omitted, since defaults are empty).

**Why not split registries / new module:**
- Two registries: doubles the lookup logic in judge.py (`if dim in DETECTORS: ... else if dim in LLM_RUBRICS: ...`). No real benefit.
- New `detectors.py` module: more files, more imports. Right shape if Phase 4 became 50+ detectors; for 3 detectors it's over-engineering.

## Implementation surface (for planner)

### Files to modify

- `src/agent_evaluator/models.py`
  - `DimensionScore`: add `judge_method: Literal["llm","deterministic"] = "llm"` field.
  - `EvaluationResult`: change `schema_version: int = 2` → `schema_version: int = 3`. Update the warning text in `_detect_legacy` validator if needed (probably unchanged — still fires for v < 2).
- `src/agent_evaluator/rubrics.py`
  - Extend `Rubric` class with `judge_method` field (default `"llm"`).
  - Add 3 detector functions: `_detect_tool_selection`, `_detect_efficiency`, `_detect_final_correctness`. Each returns a fully-formed `DimensionScore` with `status="ok"`, `judge_method="deterministic"`, sensible `reasoning` text, and `evidence` list.
  - Add `DETECTORS` dict at module top-level.
  - Update the 3 existing det-targeted Rubric definitions (tool_selection, efficiency, final_correctness) to set `judge_method="deterministic"`. Their existing system_prompt/user_prompt_template/score_anchors stay (harmless dead docs — useful as reference for what the LLM prompt USED to be).
- `src/agent_evaluator/judge.py`
  - Add deterministic dispatch in `_evaluate_dimension` (both AnthropicJudge and OpenAIJudge — parallel structure). Place AFTER Phase 2's error_recovery short-circuit, BEFORE the LLM call setup.
- `src/agent_evaluator/report.py`
  - Optional: surface judge_method in per-scenario detail section (e.g., "Tool Selection: 0.85 _(deterministic)_"). Optional because the dim-name ↔ method mapping is now stable; explicit annotation is helpful but not required.

### Detector formula sketches (for planner — final formulas decided in execution)

- **`_detect_tool_selection`**: compute longest common subsequence (LCS) ratio between actual sequence (`[step.tool_call.tool_name for step in traj.steps]`) and `scenario.expected_tool_sequence`. Score = LCS_length / max(len(expected), len(actual)). Reasoning includes both sequences.

- **`_detect_efficiency`**:
  - `base_score`: steps_taken / max_reasonable_steps. If actual ≤ expected length: 1.0. If ≤ max_reasonable_steps: linear interp 1.0 → 0.7. Beyond max: 0.7 → 0.0.
  - `loop_penalty`: count of consecutive identical (tool_name + parameters) calls. Each adds 0.1 penalty (cap at 0.5).
  - Final: `max(0.0, base_score - loop_penalty)`.
  - Reasoning: "{steps}/{max_reasonable_steps} steps, {loop_count} loops detected".

- **`_detect_final_correctness`**:
  - `substring_match`: fraction of `expected_final_answer_contains` strings present in `trajectory.final_answer` (case-insensitive). 0.0 if `final_answer is None` (agent didn't terminate).
  - `termination_ok`: True if `final_answer is not None` AND last step had no errors.
  - Final: `substring_match * (1.0 if termination_ok else 0.7)`.
  - Reasoning: "{matched}/{total} expected substrings; terminated={ok}".

### Tests to add (Phase 4 atomic; deeper tests in Phase 5)

- `tests/test_models.py`: round-trip on judge_method field; legacy v2 files load with judge_method="llm" everywhere.
- `tests/test_rubrics.py`: 3 detector functions tested with synthetic trajectories.
  - `tool_selection`: exact match → 1.0; partial overlap → fractional; complete miss → 0.0.
  - `efficiency`: under-budget → 1.0; over-budget → < 0.7; with action-loops → penalized.
  - `final_correctness`: all expected substrings present + terminated → 1.0; missing substrings → fractional; un-terminated → reduced.
- `tests/test_judge.py`: short-circuit dispatch fires for deterministic dims (no SDK call) — extends Phase 2 pattern.

### Anti-regression checks

- All 47 Phase 1+2+3 tests continue to pass.
- `compute_overall_score` works correctly on a mix of deterministic-ok + LLM-ok + LLM-error + na dims.
- Legacy v2 eval files: schema_version=2 in JSON → loaded with all dims judge_method="llm" → reports show all-LLM. No silent change of historical interpretation.
- Cross-vendor `compare` (Phase 3) unaffected — judges still get constructed via `make_judge`, just call fewer dims.

## Open in planning (executor decides, not user)

- (D2 detectors) Exact penalty curves and thresholds. Formula sketches above are starting points; planner can refine. **Recommendation:** simple linear interpolations as a baseline; tune in v2 once we have data.
- (D2 action-loop) Definition of "consecutive identical": exact match on `(tool_name, parameters)` or fuzzy (e.g., same tool but different params)? **Recommendation:** exact match for v1 (simplest, lowest false-positive rate).
- (D2 termination) What counts as "terminated correctly"? Just `final_answer is not None`, or also "didn't hit max_steps"? **Recommendation:** both — final_answer present AND step count ≤ max_reasonable_steps + 5.
- (D3 schema bump) Whether `_detect_legacy` validator should ALSO emit a warning for v2 files post-Phase-4 ("Pre-judge_method tracking — all dims default to LLM"). **Recommendation:** no — v2 files are not legacy in the F-A corruption sense. Default-LLM is accurate for them.
- (D4 evidence field) Should detectors populate `DimensionScore.evidence` with detector-specific data (e.g., the LCS sequence, the loop indices)? **Recommendation:** yes for debuggability, plain strings.
- (Report) Should `report.py` add a note about which dims are deterministic? **Recommendation:** show `(det)` or `(LLM)` annotation in the per-scenario detail section's dim header. Subtle, useful for trust.

## Code context (reusable assets)

- Phase 2's `_evaluate_dimension` short-circuit pattern (early-return DimensionScore before LLM) — Phase 4's deterministic dispatch is structurally identical.
- Phase 1's TRUST schema (`status`, `partial`, `compute_overall_score` skip-non-ok) — Phase 4 detectors return `status="ok"` so they participate normally in aggregation.
- `tests/test_judge.py::_FakeAnthropicClient` — extend to test that detector dispatch doesn't call SDK.

## Deferred ideas

- **Calibrate deterministic dims against human ground truth** — needs the calibrated judge benchmark from "What AI Eval Needs" thread; v2 research project.
- **Variance/N-trials reporting** — non-trivial; v2 reliability milestone.
- **Per-scenario weight overrides** — some scenarios might warrant different dim weights; current uniform weights are simpler.
- **Granular failure-mode taxonomy detectors** (e.g., "agent gave up too early" vs "agent retried with worse params") — Phase 4 keeps it simple; future detector elaboration in v2.
- **Configurable judge_method per dim** (toggle between LLM and deterministic for the same dim) — useful for ablation studies; v2.

## Next steps

1. `/gsd-plan-phase 4` — produce 04-PLAN.md from this CONTEXT.
2. Plan should be small-medium (5-7 atomic tasks): models.py schema bump, rubrics.py extension + 3 detector functions, judge.py dispatch (both classes), tests, report.py annotation, verification.
3. Plan-checker pass.
4. Execute. Verify DET-01..04 acceptance.

---
*Discussion complete: 2026-05-06. 4 areas selected, 4 decisions locked. Cross-phase impact: schema_version bump v2 → v3 (D3); legacy semantics unchanged.*
