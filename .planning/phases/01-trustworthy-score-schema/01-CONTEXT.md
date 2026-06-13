# Phase 1 Context — Trustworthy Score Schema

**Phase:** 01 — Trustworthy Score Schema
**Goal:** Add a failure channel to `DimensionScore` and propagate it through aggregation, persistence, and reporting. After this phase, transient API errors and non-text content blocks are structurally distinguishable from legitimate low scores.
**Requirements:** TRUST-01, TRUST-02, TRUST-03, TRUST-04, TRUST-05
**Status:** discussion complete; planning next

---

## Domain

This phase delivers the **failure channel on the score schema** — the dependency root for v1 remediation. Per the System Judge Decision Engine: "without this, every other fix is decorative." Phase 2 (DIM) and Phase 4 (DET) explicitly depend on this schema; Phases 3 and 5 do not but benefit from it.

## Canonical refs

- `.planning/research/JUDGMENT.md` — System Judge full-pipeline analysis (LOCKED — must read before planning)
- `.planning/research/SUMMARY.md` — Compressed findings + pitfall→phase map
- `.planning/codebase/ARCHITECTURE.md` — Critical call paths and data flow (call path #4 "Trajectory evaluation" is the silent-zero amplifier site)
- `.planning/codebase/STACK.md` — Pydantic v2, Anthropic/OpenAI SDKs surface
- `.planning/REQUIREMENTS.md` — TRUST-01..05 acceptance criteria
- `.planning/ROADMAP.md` — Phase 1 success criteria (5 items) + anti-regression surface

## Decisions

### D1 — Schema shape: status field on `DimensionScore`

`DimensionScore` carries `status: Literal["ok", "error", "na"]` as an explicit field. `score` stays `float`. `error_type: str | None` records the exception class name when status == "error". Default `status="ok"` for new-code ergonomics; legacy detection happens at the `EvaluationResult` level (D2) rather than via missing-status.

```python
class DimensionScore(BaseModel):
    score: float
    reasoning: str
    status: Literal["ok", "error", "na"] = "ok"
    error_type: str | None = None
```

**Consumer pattern (locked):**
```python
if dim.status == "ok":
    weighted += dim.score * weight
    total_weight += weight
# else: dim is excluded from both numerator and denominator (TRUST-03)
```

**Why this shape (not Optional[float], not discriminated union):**
- Most idiomatic for Pydantic v2 with backward-compatible JSON shape (still has score and reasoning fields).
- Keeps `compute_overall_score` consumer logic simple — single `if dim.status == "ok"` check.
- Distinguishes error from N/A (the discriminated-union does too, but with API churn). N/A is needed for Phase 2 (DIM-01).
- `error_type` separated from `reasoning` so the human-readable string and the machine-classifiable type don't conflate.

### D2 — Migration strategy: `schema_version` + `legacy` flag on `EvaluationResult`

Add `schema_version: int = 2` and `legacy: bool = False` to `EvaluationResult`. A model-level validator detects pre-v2 files (no `schema_version` field, or `schema_version < 2`), tags them `legacy=True`, and emits a `DeprecationWarning` (or similar). Aggregation paths (`compute_overall_score`, `report.generate_*_report`) exclude legacy results from new aggregations unless an explicit opt-in flag is passed.

```python
class EvaluationResult(BaseModel):
    schema_version: int = 2
    legacy: bool = False
    # ... existing fields unchanged

    @model_validator(mode="before")
    @classmethod
    def _detect_legacy(cls, data: dict) -> dict:
        if isinstance(data, dict):
            v = data.get("schema_version", 1)
            if v < 2:
                warnings.warn(
                    f"Loading legacy eval (schema_version={v}). "
                    "Pre-TRUST scores may include silent zeros from "
                    "judge errors. See JUDGMENT.md F-A.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                data["legacy"] = True
        return data
```

**Why this shape (not fail-loudly, not silent default):**
- Fail-loudly was rejected: breaks workflows where the user keeps old eval files as historical reference.
- Silent default was rejected: pre-TRUST silent zeros would re-launder as legitimate `score=0.0`, perpetuating the very corruption v1 exists to fix.
- Version-field + warn preserves files, surfaces the issue, and gives the user explicit choice (regenerate or accept they're legacy).

### D3 — Partial markers in report: asterisk on cells + footnote section

`report.generate_report` and `generate_comparison_report` mark partial-evaluation cells with a trailing asterisk (`0.85*`). A "Partial evaluations" section below the main table lists each partial row with which dimension(s) errored and the recorded `error_type`. Cells from N/A dimensions render as `--` (dash, no number, no asterisk — distinct from partial).

**Output shape (locked):**

```markdown
| Model            | Task | Tools | Eff  | Reas | ErrR | Overall |
|------------------|------|-------|------|------|------|---------|
| claude-sonnet-4  | 0.92 | 0.85  | 0.78 | 0.85 | 1.00 | 0.87    |
| gpt-4o           | 0.88* | 0.82* | 0.71* | -- | 1.00 | 0.81*   |

**Partial evaluations:**
- gpt-4o on book_flight: reasoning_quality errored (RateLimitError, after 2 retries) — excluded from overall
```

**Why this shape (not status column, not strikethrough):**
- Asterisk is minimal disruption — comparison.md is already 5+ columns wide; adding a Status column makes it 8+.
- Footnote separates at-a-glance signal (asterisk) from detail (which dim, what error). The user sees the table; the detail is there when wanted.
- Strikethrough is poorly supported in Markdown renderers; emoji + italics is more visually noisy and less academic.
- The dash (`--`) for N/A is distinct from `0.00` (legitimate zero) and `0.00*` (partial zero) — three states are visually distinguishable.

### D4 — Legacy `results/comparison.md` disposition

Move `results/comparison.md` (Apr 8 artifact) to `results/legacy/comparison-2026-04-08.md`. Prepend a top-of-file disclaimer noting it pre-dates v1 TRUST schema and the Error Recovery column is a known constant per System Judge F-B. New v1 outputs live in `results/`; historical outputs are sequestered in `results/legacy/`.

**Disclaimer text (locked):**

```markdown
> ⚠ **LEGACY ARTIFACT — pre-v1 TRUST schema.** This comparison was generated
> on 2026-04-08 before the v1 remediation milestone. The Error Recovery
> column is a known structural constant (1.00 in 26/26 cells); see
> `.planning/research/JUDGMENT.md` finding F-B. Overall scores in this file
> include the +0.15 bias from that constant and may also include silent
> zeros from judge errors (finding F-A). Do not use this as a model-quality
> reference. Retained for historical context only.
```

**Why move + disclaimer (not delete, not in-place disclaimer):**
- Delete was rejected: the file is concrete evidence cited by JUDGMENT.md and is useful as an artifact (e.g., to show a future maintainer "this is what an untrustworthy comparison looks like"). The judgment quote preserves the smoking-gun evidence (26/26 = 1.00) but the full table has additional value.
- In-place disclaimer was rejected: when `results/` accumulates new v1 comparisons, the legacy file would mix with them — risk of confusion.
- `results/legacy/` cleanly separates pre-v1 from v1+ artifacts; the disclaimer makes the file self-documenting.

## Implementation surface (for planner)

### Files to modify

- `src/agent_evaluator/models.py`
  - Add `status`, `error_type` to `DimensionScore`.
  - Add `schema_version`, `legacy`, and `_detect_legacy` validator to `EvaluationResult`.
- `src/agent_evaluator/judge.py`
  - Replace `DimensionScore(score=0.0, reasoning="Evaluation failed: ...")` substitution at `judge.py:64-73` (Anthropic) and `judge.py:179-188` (OpenAI) with `DimensionScore(score=0.0, status="error", error_type=type(result).__name__, reasoning=...)`.
  - Same applies to the inner `_evaluate_dimension` final-failure path after retry exhaustion.
- `src/agent_evaluator/rubrics.py`
  - Update `compute_overall_score` to skip dims where `status != "ok"` from BOTH numerator and weight total (TRUST-03). Existing semantics for `score >= 0` inclusion is replaced.
- `src/agent_evaluator/report.py`
  - `generate_report`: render `--` for N/A cells, append `*` to partial cells, render footnote section.
  - `generate_comparison_report`: same plus skip `legacy=True` rows from aggregations (or render them in a separate "Legacy" section, decided in planning).
- `src/agent_evaluator/cli.py::_cmd_evaluate`
  - Persist new fields in `eval_*.json` (Pydantic auto-handles via model_dump_json).
- File system change:
  - Create `results/legacy/` directory.
  - Move `results/comparison.md` → `results/legacy/comparison-2026-04-08.md`.
  - Prepend disclaimer banner.

### Files to test (for Phase 5 — record now so TEST-01..04 see them)

- `tests/test_models.py` — add cases for `status`, `error_type`, `schema_version`, `legacy` round-trip; legacy detection validator.
- `tests/test_rubrics.py` — add cases for `compute_overall_score` with mixed ok/error/na dims; verify renormalization is correct.
- `tests/test_report.py` (new) — partial markers, footnote section, N/A rendering.
- `tests/test_runner.py` — round-trip on `EvaluationResult` with new fields (likely just regenerated fixtures).

### Anti-regression checks

- All 19 existing tests must continue to pass after schema migration. Tests of `compute_overall_score` will need updates (the missing-dim case now uses `status="na"` instead of dim absence).
- `agent-eval list` continues to return 13 scenarios.
- `agent-eval evaluate <existing-trajectory.json>` continues to produce a valid `eval_*.json` (now with `schema_version: 2`).
- CLI flags unchanged.

## Open in planning (not visionary, planner decides)

These are implementation choices the planner can settle without re-asking the user:
- Whether to use `model_validator(mode="before")` or `mode="after"` for legacy detection.
- Exact warning class (`DeprecationWarning` vs custom `LegacyEvalWarning` subclass).
- Whether `compute_overall_score` opt-in for legacy/error/na inclusion is a parameter or a separate `_unsafe` function.
- Migration helper script (e.g., `agent-eval migrate <eval.json>` to write a v2 file with `legacy=True` baked in) — planner decides if this is in Phase 1 scope or deferred to a follow-up.

## Code context (reusable assets)

- `MockToolExecutor` is unchanged by Phase 1 — Phase 1 only touches `DimensionScore`/`EvaluationResult` and downstream readers/writers.
- The 13 scenarios are unchanged by Phase 1.
- `runner.py` only writes `AgentTrajectory`, not `EvaluationResult` — so the agent-loop paths (untested per F-F) are also unchanged by Phase 1. They become the focus of Phase 5 testing.

## Deferred ideas

- **Migration helper script** (`agent-eval migrate <eval.json>`) — useful for users with stockpiled legacy eval files, but adds CLI surface. Defer to Phase 5 or v2 unless user explicitly requests.
- **Telemetry on partial-rate** — would be useful operationally (track what % of evals are partial over time), but operational concerns are deferred per PROJECT.md out-of-scope (v2 SLO milestone).
- **`status="retryable_error"` vs `status="permanent_error"` distinction** — finer-grained taxonomy could help debugging. Deferred — current 3-state status suffices for v1 trustworthiness.
- **Schema version on `AgentTrajectory`** — only `EvaluationResult` gets versioned in Phase 1. Trajectory schema is stable; revisit if Phase 4 (DET) requires it.

## Next steps

1. `/gsd-plan-phase 1` — produce PLAN.md from this CONTEXT and the canonical refs above.
2. Plan should explicitly enumerate atomic commits for the schema change cascade (models.py → judge.py → rubrics.py → report.py → cli.py → file system).
3. After plan approval, execute. Verify against the 5 Phase 1 success criteria in ROADMAP.md.

---
*Discussion complete: 2026-05-05. 4 areas selected, 4 decisions locked. Estimated context for downstream agents: this CONTEXT.md + the linked canonical refs.*
