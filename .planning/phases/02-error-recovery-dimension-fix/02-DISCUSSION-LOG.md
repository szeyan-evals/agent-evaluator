# Phase 2 Discussion Log — Error Recovery Dimension Fix

**Date:** 2026-05-06
**Phase:** 02 — Error Recovery Dimension Fix
**Mode:** default (4 single-question turns, manual fallback per the same SDK-API mismatch flagged in Phase 1)

---

## Areas presented

User was offered 4 phase-specific gray areas. User selected: **all four**.

1. N/A trigger mechanism — code-level short-circuit vs LLM-prompt-only vs hybrid
2. N/A detection signal — scenario config only, config + runtime, or runtime-only
3. N/A vs partial semantics — does N/A make a result partial, or is it semantically distinct
4. Rubric prompt rewrite — surgical / full / defer

---

## Area 1 — N/A trigger mechanism

**Selection:** Hybrid: short-circuit + rubric cleanup (Recommended)

**Locked decision:** D1 in CONTEXT.md.

---

## Area 2 — N/A detection signal

**Selection:** Scenario config only (Recommended)

**Locked decision:** D2 in CONTEXT.md.

---

## Area 3 — N/A vs partial semantics

**Selection:** partial = error-only; N/A silent (Recommended)

**Notes:** This is a Phase 1 amendment. The original `partial` definition (`any(ds.status != "ok")`) is tightened to `any(ds.status == "error")`. CONTEXT.md D3 documents the rationale (alert fatigue / signal dilution).

**Locked decision:** D3 in CONTEXT.md (cross-phase impact: Phase 1 `partial` semantics tightened).

---

## Area 4 — Rubric prompt rewrite

**Selection:** Surgical: remove unreachable branch only (Recommended)

**Notes:** Full prompt rewrite deferred to Phase 4 (DET-04 will revisit which dims stay LLM-judged anyway).

**Locked decision:** D4 in CONTEXT.md.

---

## Decisions summary

| ID | Decision | Captured in |
|----|----------|-------------|
| D1 | Hybrid: short-circuit in judge.py::_evaluate_dimension when dimension=='error_recovery' AND len(scenario.error_injection)==0 + remove unreachable rubric branch | CONTEXT.md §D1 |
| D2 | Detection signal: len(scenario.error_injection) == 0 (scenario config only) | CONTEXT.md §D2 |
| D3 | partial = any(status == 'error'); N/A silent. Phase 1 amendment. | CONTEXT.md §D3 |
| D4 | Surgical removal of `{% if error_steps|length == 0 %}` branch in rubrics.py:178-179. Defer rest of rubric work to Phase 4. | CONTEXT.md §D4 |

## Cross-phase impact

D3 amends Phase 1's `partial` semantic. Phase 2 PLAN.md will include the model amendment as the FIRST task (so subsequent test-judge changes can rely on the corrected semantic).

## Scope creep redirected

None during this discussion. User's selections stayed within Phase 2 (error_recovery N/A) boundary. The rubric prompt rewrite question (Area 4) explicitly tested whether the user wanted to expand scope into Phase 4 territory — they correctly chose the surgical option.
