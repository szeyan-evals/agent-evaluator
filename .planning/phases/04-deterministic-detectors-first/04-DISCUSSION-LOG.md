# Phase 4 Discussion Log — Deterministic Detectors First

**Date:** 2026-05-06
**Phase:** 04 — Deterministic Detectors First
**Mode:** default (4 single-question turns; manual fallback)

User selected all 4 presented gray areas.

---

## Area 1 — Per-dim audit

**Selection:** 3 det / 2 LLM (Recommended, matches DET-04 target)

**Decision:** D1 — `tool_selection`, `efficiency`, `final_correctness` become deterministic; `parameter_quality`, `error_recovery` stay LLM-judged. ~54% reduction in total judge calls per comparison run when combined with Phase 2's `error_recovery` short-circuit.

---

## Area 2 — DET-02/DET-03 placement

**Selection:** Folded into existing dims (Recommended)

**Decision:** D2 — Action-loop detection becomes a sub-rule of `efficiency`; termination correctness becomes a sub-rule of `final_correctness`. 5-dim structure preserved; weights unchanged.

---

## Area 3 — DimensionScore.judge_method tracking

**Selection:** Add judge_method field (Recommended)

**Decision:** D3 — `judge_method: Literal["llm","deterministic"] = "llm"` added to DimensionScore. Default `"llm"` ensures legacy v2 files load with the right semantics. Schema bump v2 → v3 (legacy detection unchanged — only files with `schema_version < 2` trigger the deprecation warning, since v2 files don't have F-A silent-zero corruption).

---

## Area 4 — Rubric structure refactoring

**Selection:** judge_method on Rubric + DETECTORS dict (Recommended)

**Decision:** D4 — `Rubric` class gets `judge_method` field. Parallel `DETECTORS` dict in `rubrics.py` holds detector callables (Pydantic Callable storage is awkward). `judge.py::_evaluate_dimension` dispatches: short-circuit (Phase 2) → deterministic check (Phase 4) → LLM path (existing).

---

## Decisions summary

| ID | Decision | Captured |
|----|----------|----------|
| D1 | 3 det (tool_selection, efficiency, final_correctness) + 2 LLM (parameter_quality, error_recovery) | CONTEXT §D1 |
| D2 | Action-loops fold into efficiency; termination correctness folds into final_correctness; 5-dim structure preserved | CONTEXT §D2 |
| D3 | Add judge_method field to DimensionScore (default "llm"); schema_version bump 2 → 3 (legacy detection unchanged) | CONTEXT §D3 |
| D4 | judge_method on Rubric + parallel DETECTORS callable dict in rubrics.py | CONTEXT §D4 |

## Cross-phase impact

**Schema bump 2 → 3 (D3).** Additive change — legacy v2 files load with default judge_method="llm" everywhere, which accurately describes their content. The `_detect_legacy` validator in `models.py` continues to flag only `schema_version < 2` (pre-TRUST files); v2 → v3 transition is silent and forward-compatible.

## Scope creep redirected

None during this discussion. Discussed alternatives (4-det/1-LLM, new dims, 7-dim restructuring) but all rejected as too aggressive or scope-expanding. Phase 4 stays focused on the 5-dim audit + 3 deterministic detectors.
