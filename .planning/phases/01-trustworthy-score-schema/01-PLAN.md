# Phase 1 Plan — Trustworthy Score Schema

**Phase:** 01 — Trustworthy Score Schema
**Source decisions:** `01-CONTEXT.md` (D1–D4)
**Source artifacts:**
- `.planning/research/JUDGMENT.md` (LOCKED — read first)
- `.planning/codebase/ARCHITECTURE.md` (call path #4 is the silent-zero amplifier site)
- `.planning/REQUIREMENTS.md` (TRUST-01..05)
- `.planning/ROADMAP.md` (Phase 1 success criteria)

**Goal restatement:** Add a failure channel to `DimensionScore` and propagate it through aggregation, persistence, and reporting. After this phase, transient API errors and non-text content blocks are structurally distinguishable from legitimate low scores in `eval_*.json`.

---

## Pre-flight notes (read before executing)

### Rubric dimension names — actual vs aspirational

The earlier planning docs (PROJECT.md, REQUIREMENTS.md, ROADMAP.md) use illustrative dim names like "task_completion" and "reasoning_quality." The **actual rubric keys in code** are:

```python
{"tool_selection", "parameter_quality", "efficiency", "error_recovery", "final_correctness"}
```

(per `tests/test_rubrics.py::test_all_dimensions_defined` and `src/agent_evaluator/rubrics.py::RUBRICS`).

The TRUST schema work in this plan operates at the `DimensionScore` level and is **dimension-name-agnostic** — it doesn't depend on which names exist, only that each instance carries the new `status` field. So no rename is needed; the plan's task acceptance criteria reference dimension names exactly as they appear in code.

### `compute_overall_score` signature change

The existing signature is `compute_overall_score(dimension_scores: dict[str, float]) -> float`. To honor `status` (TRUST-03), we change it to:

```python
def compute_overall_score(dimension_scores: list[DimensionScore]) -> float
```

The dict-of-scores form was lossy — it threw away the `DimensionScore.status` field at the call site. The list form preserves it. Test updates in `test_rubrics.py` are mechanical (build a list of `DimensionScore`).

**Two call sites in `judge.py` must update together** (not one — plan-checker pass surfaced this):
- `judge.py:77-78` (AnthropicJudge): `score_map = {s.dimension: s.score for s in valid_scores}; overall = compute_overall_score(score_map)` → `overall = compute_overall_score(valid_scores)`
- `judge.py:194-195` (OpenAIJudge): same pattern, same change

`include_legacy` opt-in is **not** included in the v1 signature — deferred. If future tooling needs it, it can be added without breaking existing callers (kw-only with default `False`).

### Build-green-after-every-commit ordering

Tasks are ordered so each commit can land independently with all tests passing:

| T# | Lands | Why build stays green |
|----|-------|-----------------------|
| T1 | New fields on models with defaults | New fields are optional; existing code paths never read them; test_models extended to cover them. |
| T2 | `compute_overall_score` accepts `list[DimensionScore]` | test_rubrics updated in same commit; old dict signature removed. judge.py updated in same commit (it's the only other caller). |
| T3 | `judge.py` error path produces `status="error"` | No existing test exercises the silent-zero path, so nothing to break. judge.py compiles against the T2 signature. |
| T4 | `report.py` renders partial markers + skips legacy | No existing test for report.py. Visual regression check by manual smoke (T7). |
| T5 | `cli.py` smoke check for new field persistence | Pydantic auto-handles serialization; verification only. |
| T6 | Filesystem move of legacy comparison.md | No test depends on this. |
| T7 | End-to-end smoke verification | Anti-regression checklist run. |

---

## Tasks

### T1 — Schema fields on `models.py`

**File:** `src/agent_evaluator/models.py`

**Changes:**
1. On `DimensionScore`: add
   ```python
   status: Literal["ok", "error", "na"] = "ok"
   error_type: str | None = None
   ```
   Keep existing fields unchanged. The `score: float = Field(ge=0.0, le=1.0)` constraint stays — `score=0.0` is allowed when `status` is "error" (legacy convention; `score` is meaningless when `status != "ok"` but the value is still in-range).
2. On `EvaluationResult`: add
   ```python
   schema_version: int = 2
   legacy: bool = False

   @computed_field
   @property
   def partial(self) -> bool:
       return any(ds.status != "ok" for ds in self.dimension_scores)
   ```
   Plus a `model_validator(mode="before")` named `_detect_legacy` that:
   - Accepts a raw dict.
   - Reads `data.get("schema_version", 1)`.
   - If `< 2`: sets `data["legacy"] = True` and emits `warnings.warn("Loading legacy eval (schema_version=...). Pre-TRUST scores may include silent zeros from judge errors. See JUDGMENT.md F-A.", DeprecationWarning, stacklevel=3)`.
   - Returns `data`.
   - Skip validation if input isn't a dict (Pydantic round-tripping from a model instance shouldn't trigger the warning).
3. Top of file: add `import warnings`, `from typing import Literal`, and `from pydantic import computed_field` (in addition to the existing `BaseModel`, `Field` imports).

**`partial` design notes (locked):**
- `@computed_field` (Pydantic v2.0+, declared `pydantic>=2.7` so available) auto-serializes in `model_dump_json()` — JSON top-level shows `"partial": true/false`. No write path; single source of truth (derived from `dimension_scores`).
- On load: Pydantic's default behavior with computed fields is to **ignore** the `"partial"` key in input JSON (it's read-only). Round-tripping `dump → load` works because `partial` is recomputed from `dimension_scores` on the loaded instance. Verify in T1 acceptance.

**Acceptance:**
- `python -c "from agent_evaluator.models import DimensionScore; d = DimensionScore(dimension='x', score=0.5, reasoning='y'); assert d.status == 'ok' and d.error_type is None"` passes.
- Loading a legacy JSON (`{"scenario_id":"x","model_id":"y","dimension_scores":[],"overall_score":0.0,"summary":"z"}` — no `schema_version`) produces an `EvaluationResult` with `legacy=True` and emits a `DeprecationWarning`.
- Round-tripping a v2 `EvaluationResult` (constructed in code) preserves `schema_version=2`, `legacy=False`, and does NOT emit the warning.
- Constructing an `EvaluationResult` with one `DimensionScore` having `status="error"` and serializing via `model_dump_json()` produces JSON containing `"partial": true` at top level. Constructing one with all `status="ok"` produces `"partial": false`.

**Tests:** Extend `tests/test_models.py`:
- `TestDimensionScore::test_default_status_ok` — default `status` is `"ok"`.
- `TestDimensionScore::test_status_error_with_error_type` — error case round-trips.
- `TestEvaluationResult::test_legacy_detection` — load JSON without `schema_version`, assert `legacy=True` and capture warning via `pytest.warns(DeprecationWarning)`.
- `TestEvaluationResult::test_v2_no_warning` — round-trip a v2 result, assert no warning emitted (use `warnings.catch_warnings()` or `pytest.warns(None)`).
- `TestEvaluationResult::test_partial_true_when_any_error` — construct with one `status="error"` dim, assert `result.partial is True` and `model_dump_json()` contains `"partial": true`.
- `TestEvaluationResult::test_partial_false_when_all_ok` — all dims `status="ok"`, assert `result.partial is False`.
- `TestEvaluationResult::test_partial_round_trip` — dump a partial result, load it back from JSON, assert `restored.partial == True` (recomputed from dimension_scores, not from input "partial" key).

**Anti-regression:** All existing `test_models.py` cases (TrajectoryRoundTrip, DimensionScore valid/out-of-range, EvaluationResult round_trip, MockResponse, Scenario) continue to pass.

**Atomic commit:** `feat(models): add status to DimensionScore + schema_version/legacy/partial to EvaluationResult (TRUST-01, TRUST-02)`

---

### T2 — `compute_overall_score` honors status

**File:** `src/agent_evaluator/rubrics.py`

**Changes:**
1. Replace existing `compute_overall_score(dimension_scores: dict[str, float])` with:
   ```python
   def compute_overall_score(dimension_scores: list[DimensionScore]) -> float:
       """Weighted overall score, excluding non-ok dimensions."""
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
   ```
2. Add `from agent_evaluator.models import DimensionScore` at top.
3. Update **both** `compute_overall_score` call sites in `judge.py` (in the same commit — leaving either one on the old dict form breaks the build silently because no integration test catches it):
   - `judge.py:77-78` (AnthropicJudge): replace `score_map = {s.dimension: s.score for s in valid_scores}; overall = compute_overall_score(score_map)` with `overall = compute_overall_score(valid_scores)`. Remove the dict comprehension.
   - `judge.py:194-195` (OpenAIJudge): same pattern, same change.
   - After this commit, `grep -n "score_map" src/agent_evaluator/judge.py` should return no results.

**Acceptance:**
- A list of 5 `DimensionScore` all with `status="ok"` and `score=1.0` returns `1.0`.
- A list with one `status="error"` (any score) returns the same overall as if that dimension didn't exist (renormalized over 4 dims).
- A list with one `status="na"` behaves identically to `status="error"` for aggregation purposes — both are excluded from numerator AND denominator.
- A list with all dims `status != "ok"` returns `0.0` (defensive — `total_weight == 0` branch).

**Tests:** Update `tests/test_rubrics.py::TestOverallScore`:
- Convert all 4 existing tests from `dict[str, float]` input to `list[DimensionScore]` input. Add `from agent_evaluator.models import DimensionScore`.
- Mechanical translation: `{dim: 1.0 for dim in RUBRICS}` becomes `[DimensionScore(dimension=dim, score=1.0, reasoning="x") for dim in RUBRICS]`.
- Add new test `test_excludes_errored_dim`: 4 ok + 1 status="error", assert overall renormalized.
- Add new test `test_excludes_na_dim`: 4 ok + 1 status="na", assert same renormalized.
- Add new test `test_all_errored_returns_zero`: all dims status="error", assert overall == 0.0.

**Anti-regression:** Both `TestRubrics` cases (`test_all_dimensions_defined`, `test_weights_sum_to_one`, `test_rubric_has_score_anchors`) continue to pass — they don't touch `compute_overall_score`.

**Dependency:** T1 (needs `DimensionScore.status`).

**Atomic commit:** `refactor(rubrics): compute_overall_score honors DimensionScore.status (TRUST-03)`

---

### T3 — Judge error path sets `status="error"`

**File:** `src/agent_evaluator/judge.py`

**Changes (4 sites — 2 in AnthropicJudge, 2 in OpenAIJudge):**

1. **AnthropicJudge `evaluate_trajectory` exception handler** (`judge.py:64-73`):
   Replace the silent-zero substitution
   ```python
   if isinstance(result, Exception):
       logger.error("Failed to evaluate %s: %s", dim_name, result)
       valid_scores.append(
           DimensionScore(
               dimension=dim_name,
               score=0.0,
               reasoning=f"Evaluation failed: {result}",
               evidence=[],
           )
       )
   ```
   with
   ```python
   if isinstance(result, Exception):
       logger.error("Failed to evaluate %s: %s", dim_name, result)
       valid_scores.append(
           DimensionScore(
               dimension=dim_name,
               score=0.0,
               reasoning=f"Evaluation failed: {result}",
               evidence=[],
               status="error",
               error_type=type(result).__name__,
           )
       )
   ```
2. **AnthropicJudge `_evaluate_dimension` final-failure path** — after retries exhaust, the current code raises `ValueError`. That `ValueError` is then caught by the outer `gather(return_exceptions=True)` and routed through the substitution above. So this site needs no separate change — the change at site (1) handles it.

3. **AnthropicJudge `evaluate_trajectory`'s call to `compute_overall_score`** (`judge.py:77-78`):
   Updated in T2 (passes `valid_scores` list directly instead of building `score_map`).

4. **OpenAIJudge** — apply the same change at the corresponding location (parallel structure to AnthropicJudge in `judge.py` second half). Match the pattern.

**Acceptance:**
- A judge run where `_evaluate_dimension` raises `RateLimitError` (or any non-parse exception) produces a `DimensionScore` with `status="error"`, `error_type="RateLimitError"`, `score=0.0`. The `EvaluationResult` containing it has `partial=False` (we haven't set partial yet — that's T4 or computed-on-demand; see open question below).
- The persisted `eval_*.json` shows `"status": "error"` and `"error_type": "RateLimitError"` on the failed dimension.
- `compute_overall_score` (post-T2) excludes that dimension from aggregation, returning a renormalized overall.

**Tests:** No new tests in this phase. Phase 5 (TEST-02) covers integration testing of judge.py with mocked SDK responses.

**Anti-regression:**
- Existing tests pass — none touch the judge error path.
- A successful judge run (all dims status="ok") produces an `EvaluationResult` indistinguishable from the pre-T3 shape except for the new `status` field on each dim and `schema_version: 2` on the result.

**Dependency:** T1 (needs `status` and `error_type` fields), T2 (signature change to `compute_overall_score`).

**Atomic commit:** `fix(judge): set status="error" on dimension failures instead of silent zero (TRUST-01, TRUST-02, F-A remediation)`

**Note:** `EvaluationResult.partial` is added as a `@computed_field` in T1 (locked decision). T3 doesn't explicitly set it — it's derived from `dimension_scores` by the property. T3's only responsibility is ensuring failed dims carry `status="error"`; the property propagates that into `result.partial` automatically.

---

### T4 — Report rendering: partial markers, N/A markers, footnote, legacy skip

**File:** `src/agent_evaluator/report.py`

**Changes:**
1. **In `generate_report`** (single-model report):
   - For each `DimensionScore` cell:
     - If `status == "na"`: render `"--"`
     - If `status == "error"`: render `f"{score:.2f}*"` (partial marker)
     - Else (`status == "ok"`): render `f"{score:.2f}"` (unchanged)
   - For the overall column:
     - If `EvaluationResult.partial` (or computed equivalent): render `f"{overall:.2f}*"`
     - Else: render `f"{overall:.2f}"`
   - After the table: append a "Partial evaluations" section iff at least one row is partial. Each line: `- {model_id} on {scenario_id}: {dim_name} {status} ({error_type}, after {max_retries} retries) — excluded from overall`. Skip the section entirely if no partials.
2. **In `generate_comparison_report`** (multi-model report): same cell/overall rules. Plus: skip rows where `EvaluationResult.legacy is True` from the main table aggregations. If any legacy results were filtered, append a "Legacy evaluations excluded" note listing them by `(model_id, scenario_id, schema_version)`.
3. **Average-row partial propagation** (TRUST-04 strict reading per plan-checker concern #3):
   - When computing the average row over the per-row `overall_score` values, also track whether any contributing row was partial (i.e., `result.partial is True`).
   - If any contributing row was partial: the average row's overall cell renders as `f"{avg:.2f}*"` (asterisk marker), AND a footnote line is appended: `*Average computed across N rows; M were partial.*`
   - Per-dim cells in the average row apply the same per-cell rule: if any contributing per-dim cell was partial (or excluded as N/A), the average for that dim renders with a `*` and the count is included in the footnote line.
   - Existing arithmetic stays — `overall_score` is renormalized post-T2 so the average is no longer biased by silent zeros, but the marker propagates the partial state visually. (F-L's deeper avg-row math defects beyond this propagation remain out of scope; flagged for verification only.)

**Acceptance:**
- A `comparison.md` generated post-T4 shows `--` for any N/A cells (e.g., `error_recovery` after Phase 2 lands; for now Phase 1 only sees error cells).
- A `comparison.md` generated post-T4 shows `0.85*` for any errored cells with the footnote section listing them.
- A `comparison.md` generated post-T4 with a mix of v1 and v2 eval files shows only the v2 ones in the main table, with the legacy note appended.
- A `comparison.md` generated post-T4 with no errors and no legacy renders identically to a pre-Phase-1 report (modulo the new schema_version field which is invisible at the table level).
- When at least one contributing row is partial, the average row's overall cell carries `*` and a footnote line states the partial count. When all contributing rows are non-partial, the average row carries no marker.

**Tests:** No new test files in this phase (report.py tests are TEST-03, Phase 5). Manual smoke verification in T7.

**Anti-regression:** No existing tests touch `report.py`. EVAL-06 is preserved by T4's anti-regression bullet (no-error/no-legacy renders identically).

**Dependency:** T1 (fields exist), T3 (errored cells exist to render — without T3 there's nothing to demo, but T4 could land before T3 with no observable effect).

**Atomic commit:** `feat(report): render partial markers, N/A cells, footnote section, skip legacy (TRUST-04)`

---

### T5 — Verify `cli.py` persistence (likely no-op)

**File:** `src/agent_evaluator/cli.py`

**Changes:** Likely none. `_cmd_evaluate` calls `result.model_dump_json(indent=2)` to write — Pydantic v2 auto-includes the new fields. **Verification step**, not a code change.

**Acceptance:**
- After T1+T3 land, run a manual smoke: `agent-eval evaluate <fresh_trajectory.json>` produces an `eval_*.json` containing `"schema_version": 2`, `"legacy": false`, and per-dimension `"status": "ok"` (or `"error"` if a real judge call failed).
- If T5 reveals that some `_cmd_*` path serializes by hand (rather than `model_dump_json`), patch it to use the model's serializer. Otherwise commit nothing.

**Tests:** None.

**Anti-regression:** EVAL-07 (CLI subcommands) preserved. `agent-eval list` still returns 13 scenarios.

**Dependency:** T1, T3.

**Atomic commit (only if changes are made):** `chore(cli): ensure new schema fields persist on _cmd_evaluate (TRUST-04)`

---

### T6 — Move legacy `comparison.md` to `results/legacy/`

**Filesystem changes:**
1. `mkdir -p /Users/szeyan/Documents/Dev/agent-evaluator/results/legacy`
2. Move `results/comparison.md` → `results/legacy/comparison-2026-04-08.md`
3. Prepend the disclaimer banner from `01-CONTEXT.md` D4 to the moved file.

**Disclaimer text (locked, copy verbatim):**
```markdown
> ⚠ **LEGACY ARTIFACT — pre-v1 TRUST schema.** This comparison was generated
> on 2026-04-08 before the v1 remediation milestone. The Error Recovery
> column is a known structural constant (1.00 in 26/26 cells); see
> `.planning/research/JUDGMENT.md` finding F-B. Overall scores in this file
> include the +0.15 bias from that constant and may also include silent
> zeros from judge errors (finding F-A). Do not use this as a model-quality
> reference. Retained for historical context only.

---
```

**Acceptance:**
- `results/comparison.md` no longer exists.
- `results/legacy/comparison-2026-04-08.md` exists.
- The first line of the moved file matches the disclaimer's first line.
- The original table content is preserved verbatim after the disclaimer + horizontal rule.

**Tests:** None.

**Anti-regression:** No code path reads from `results/comparison.md` directly (it's a user-facing artifact, not consumed). `results/` glob patterns in `_cmd_report` and `_cmd_compare` look for `eval_*.json`, not `comparison.md`.

**Dependency:** None (independent of code tasks; can land anytime).

**Atomic commit:** `chore(results): move pre-v1 comparison.md to results/legacy/ with disclaimer (TRUST-05)`

---

### T7 — End-to-end smoke verification

**No file changes.** Verification step that runs after T1–T6 land.

**Verification checklist:**

1. `cd /Users/szeyan/Documents/Dev/agent-evaluator && pytest -v` — all tests pass (existing 19 + new ones from T1, T2). Ruff: `ruff check src/ tests/ scenarios/` shows no new findings beyond the 3 known auto-fixable ones (or fewer if T6's filesystem move didn't accidentally introduce any).
2. `agent-eval list` returns 13 scenarios. Output unchanged from pre-Phase-1.
3. `agent-eval evaluate <existing or fresh trajectory.json>` produces an `eval_*.json` with `schema_version: 2`, `legacy: false`, all dim `status: "ok"` (assuming the live judge call succeeded). Inspect file manually.
4. Manual error simulation (**REQUIRED for phase completion** — F-A is the dependency-root finding for the entire v1 milestone, so we must observe the error path at least once before declaring Phase 1 done): temporarily wrap one of the Anthropic SDK calls (e.g., monkeypatch `_evaluate_dimension` for one dim, or seed a fake `client` that raises) so it raises a synthetic exception for one dimension. Run `agent-eval evaluate`. Verify the resulting `eval_*.json` has `status: "error"`, `error_type` matching the exception class on that dim. `overall_score` is computed across the remaining 4 dims with renormalized weights. `partial: true` at top level. Revert the test injection. If this step is skipped, the phase is incomplete — F-A remediation is structurally untested.
5. Manual report check: drop the resulting `eval_*.json` files into `results/`, run `agent-eval report` (or `compare`). Verify the rendered Markdown shows the asterisk on partial cells and the footnote section with `error_type`. Visual confirmation only — no automated test.
6. Final inspection of `results/legacy/comparison-2026-04-08.md`: file exists, disclaimer at top, original table preserved.
7. **No file in the working tree** named `results/comparison.md`.

**ROADMAP success-criteria mapping:**

| ROADMAP SC | Verified by |
|-----------|-------------|
| 1 (status discriminator persisted; structurally distinguishable) | T1 acceptance + T7 step 3+4 |
| 2 (`partial` correctly set) | T1 + T3 (computed property if (a), explicit if (b)) + T7 step 4 |
| 3 (`compute_overall_score` excludes non-ok from numerator AND denominator) | T2 acceptance + T7 step 4 |
| 4 (report visible PARTIAL marker; never silently averages) | T4 acceptance + T7 step 5 |
| 5 (existing artifacts regenerated or labeled) | T6 acceptance + T7 step 6 + step 7 |

If any step fails: do NOT mark the phase complete. File a follow-up task or reopen the relevant T#. Do not silently degrade.

**Atomic commit:** None — verification only. If ad-hoc fixups are needed during verification, scope them to the originating task and amend with care (or open a follow-up task — the GSD preference is new commit over amend).

---

## Risks and watch-items

1. **Pydantic v2 `model_validator(mode="before")` semantics.** When loading a model instance (e.g., via `model_copy` or round-tripping in-memory) vs from JSON, the `data` parameter shape may differ. The `if isinstance(data, dict)` guard above prevents the warning from firing on non-dict inputs. Test in T1 covers both cases.
2. **`@computed_field` round-trip semantics for `EvaluationResult.partial`.** Pydantic v2 serializes `@computed_field` properties by default in `model_dump_json()` (top-level JSON contains `"partial": true/false`). On `model_validate_json()`, the computed field is **read-only** — it ignores any `"partial"` key in input JSON and recomputes from `dimension_scores`. This is the correct semantics for a derived field, but it means: (a) if a user hand-edits an `eval_*.json` to flip `partial`, the edit is silently ignored; (b) Pydantic strict-mode configs may need to allow extra keys on input. Verified by `test_partial_round_trip` in T1's test list.
3. **Backwards compat for in-memory `EvaluationResult` round-trip.** When code does `EvaluationResult.model_dump_json` → `model_validate_json`, the validator runs on the dumped dict. Since `schema_version=2` is in the dump, the validator sees `v=2 >= 2` and does NOT mark legacy. Verify with the `test_v2_no_warning` test in T1.
4. **Test_models.py validation tests using `pytest.raises(ValidationError)`** for out-of-range scores still pass — adding `status` field with default doesn't change `score` constraint.
5. **`logger.error` call in judge.py error path** stays — Phase 1 doesn't change logging. Phase 5 (TEST-02) may decide to upgrade to structured logging or add metrics, but not now.
6. **`_parse_score` fence-stripper bug (F-I)** is NOT fixed in Phase 1. It composes with F-A: parse failures retry, retries exhaust, resulting `ValueError` flows into the gather catch and produces — pre-Phase-1 — a silent zero, post-Phase-1 — a `status="error"`, `error_type="ValueError"` entry. So Phase 1 makes F-I observable instead of silent. Phase 5 (TEST-02) covers regression-testing this; an actual fix is deferred.

## Open questions deferred to executor

1. ~~(T3) `partial` as computed property vs explicit field.~~ **LOCKED post plan-check:** computed property, added in T1. T3 no longer carries this open question.
2. ~~(T2) `include_legacy` / `include_non_ok` opt-in parameter on `compute_overall_score`.~~ **LOCKED post plan-check:** not in v1 signature; deferred. Future tooling can add a kw-only param without breaking existing callers.
3. (T6) Should the disclaimer also link to a Phase 1 commit hash? Recommended: no — `.planning/research/JUDGMENT.md` is the canonical reference and survives commit history changes.

## Estimated work

- T1: 30 min (schema + tests)
- T2: 20 min (signature change + test conversions)
- T3: 15 min (4 substitution sites)
- T4: 45 min (rendering logic, footnote assembly, legacy filtering)
- T5: 5 min (verification, likely no-op)
- T6: 5 min (filesystem move + disclaimer prepend)
- T7: 15 min (smoke checklist)
- **Total: ~2.5 hours**

## Out of scope (reaffirmed)

- Real (non-mocked) tool execution — out of scope per PROJECT.md.
- F-I fence-stripper actual fix — deferred per Risks #6.
- F-G OpenAI list[dict] divergence — Phase 5 regression guard.
- F-H Anthropic unguarded `usage` — Phase 5 regression guard.
- New test files for report.py / judge.py / runner.py integration — Phase 5 (TEST-01..03).
- CI configuration — Phase 5 (TEST-04).
- DIM, VEND, DET requirements — their own phases.

---
*Plan written: 2026-05-05 from CONTEXT.md decisions D1–D4 + canonical refs. No `gsd-planner` subagent spawn (workflow's SDK-query API unavailable; manual planning equivalent quality). Verification by `gsd-plan-checker` next.*
