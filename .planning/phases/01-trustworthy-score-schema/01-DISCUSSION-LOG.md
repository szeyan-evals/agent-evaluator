# Phase 1 Discussion Log — Trustworthy Score Schema

**Date:** 2026-05-05
**Phase:** 01 — Trustworthy Score Schema
**Mode:** default (4 single-question turns, manual fallback because installed `gsd-sdk` (`@gsd-build/sdk v0.1.0`) does not expose the `query` API the workflow expects)

This log is for human reference only (audits, retrospectives). It is NOT consumed by downstream agents — they read `01-CONTEXT.md`.

---

## Areas presented

User was offered 4 phase-specific gray areas via `AskUserQuestion`:

1. Schema shape — How does the failure channel look on `DimensionScore`?
2. Migration strategy — How do existing `eval_*.json` files load under the new schema?
3. Partial markers in report — How does `report.py` surface partial evaluations?
4. Legacy `comparison.md` (TRUST-05) — What happens to the Apr 8 artifact?

User selected: **all four**.

---

## Area 1 — Schema shape

**Options presented:**
- Status field (Recommended) — `status: Literal["ok","error","na"]`, score stays float
- Optional[float] — score as `float | None`, no status field
- Both: Optional[float] + status — explicit but redundant
- Discriminated union — tagged union OkScore | ErrorScore | NAScore

**User selection:** Status field (Recommended)

**Notes:** No additions / overrides from user. Recommendation accepted as-is.

**Locked decision:** D1 in CONTEXT.md.

---

## Area 2 — Migration strategy

**Options presented:**
- Version field + warn (Recommended) — `schema_version: int = 2` + `legacy: bool` flag, model validator detects v<2 and emits warning
- Fail loudly — no defaults; loading legacy eval_*.json raises ValidationError
- Silent default — `status="ok"` default applies to legacy files transparently

**User selection:** Version field + warn (Recommended)

**Notes:** Recommendation accepted. The hybrid was the natural middle path — preserves files for users who want them as historical reference, but tags them so v1+ aggregations exclude them.

**Locked decision:** D2 in CONTEXT.md.

---

## Area 3 — Partial markers in report

**Options presented:**
- Asterisk + footnote (Recommended) — cell values get `*` for partial; footnote section lists details per row
- Status column — explicit "OK/PARTIAL" column added to the table
- Emoji + italics — leading ⚠️ + italicized model name on partial rows

**User selection:** Asterisk + footnote (Recommended)

**Notes:** Recommendation accepted. The N/A cell rendering as `--` (vs partial as `0.00*` vs ok as `0.00`) creates three visually distinguishable states for legitimate-zero / partial-zero / not-applicable.

**Locked decision:** D3 in CONTEXT.md.

---

## Area 4 — Legacy `results/comparison.md` disposition

**Options presented:**
- Move to results/legacy/ + disclaimer (Recommended)
- Disclaimer banner, keep in place
- Delete

**User selection:** Move to results/legacy/ + disclaimer (Recommended)

**Notes:** Recommendation accepted. Final filename: `results/legacy/comparison-2026-04-08.md`. Disclaimer text drafted in CONTEXT.md D4.

**Locked decision:** D4 in CONTEXT.md.

---

## Scope creep redirected

None during this discussion. User's selections stayed within Phase 1 (TRUST schema) boundary. No deferred ideas captured during the discussion itself; the four "Open in planning" items in CONTEXT.md are implementation details for the planner, not user-facing scope.

## Claude's discretion items

The following were marked in CONTEXT.md as "planner decides" and not asked of the user (they're implementation details, not vision):
- `model_validator(mode="before")` vs `mode="after"`
- Exact warning class subclass
- Whether `compute_overall_score` opt-in for legacy is a parameter or separate function
- Migration helper script scope (Phase 1 vs deferred)

## Decisions summary

| ID | Decision | Captured in |
|----|----------|-------------|
| D1 | `status: Literal["ok","error","na"]` field on DimensionScore + `error_type: str \| None`. score stays float. Default status="ok". | CONTEXT.md §Decisions D1 |
| D2 | `schema_version: int = 2` + `legacy: bool` on EvaluationResult. Model validator detects v<2, emits DeprecationWarning, tags legacy. Aggregations exclude legacy by default. | CONTEXT.md §Decisions D2 |
| D3 | Asterisk on partial cells + dash on N/A cells + footnote section listing partial rows with errored dim and error_type. | CONTEXT.md §Decisions D3 |
| D4 | Move results/comparison.md → results/legacy/comparison-2026-04-08.md with prepended disclaimer banner. | CONTEXT.md §Decisions D4 |
