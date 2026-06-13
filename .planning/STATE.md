---
gsd_state_version: 1.0
project: agent-evaluator
milestone: v1-remediation
milestone_name: v1 — Remediation
status: phase-5-in-progress
current_phase: 5
phases_total: 5
phases_completed: 4
last_updated: "2026-06-13T07:45:00.000Z"
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 8
  completed_plans: 5
  percent: 85
last_session: 2026-06-13 — Phase 5 Plan 01 executed (fixture infra, live marker, conftest replay clients)
last_action: 05-01-PLAN.md complete. FixtureAnthropicClient + FixtureOpenAIClient in conftest.py, 7 fixture JSON files, live marker. 86 tests passing, ruff clean. Decision: IndexError replaces StopIteration for async exhaustion (PEP 479).
next_step: Execute 05-02-PLAN.md (runner + report integration tests)
stopped_at: Phase 5 Plan 01 complete; Plan 02 not started
notes: |
  Project is brownfield with NO-GO verdict from System Judge full-pipeline review.
  Source of truth for failure modes and remediation scope:
  ~/.claude/system-judge/judgments/2026-05-04_agent-evaluator_full.md
  (also linked at .planning/research/JUDGMENT.md).

  Project is NOT a git repository in v1 scope. config.json sets
  commit_docs=false; .planning/ stays local-only. Plan 05-04's "CI green"
  acceptance is a human-verify checkpoint — requires git init + GitHub push first.

  gsd-sdk binary now exposes the query API (was missing in May 2026 sessions);
  the autonomous workflow path works again. Note: `state.planned-phase` rewrites
  STATE.md frontmatter to its own schema — session fields restored by hand.
---

# Project State — agent-evaluator

## Milestone

**v1 — Remediation.** Goal: make eval artifacts trustworthy. Originated from System Judge NO-GO verdict on 2026-05-04. See `.planning/ROADMAP.md` for the 5-phase plan.

## Phase Progress

| # | Phase | Status |
|---|---|---|
| 1 | Trustworthy Score Schema | structurally complete (35/35 tests after Phase 2 amendment); partial semantics tightened by Phase 2 D3 |
| 2 | Error Recovery Dimension Fix | structurally complete (35/35 tests; T1-T5 executed; F-B empirically eliminated; live-API smoke optional) |
| 3 | Vendor Coupling Fix | structurally complete (47/47 tests; ruff clean; F-C closed; F-D closed; F-J hygiene done) |
| 4 | Deterministic Detectors First | structurally complete (69/69 tests; ruff clean; 3 det/2 LLM split shipped; ~54% LLM call reduction) |
| 5 | Test Coverage and CI | in progress — Plan 01 complete (fixture infra); Plans 02-04 pending |

## Recent Sessions

- **2026-05-04** — System Judge full-pipeline review. Verdict: NO-GO (HIGH confidence). 14 assumption-registry entries written at `2026-05-04T05:44:15Z`. Archived at `~/.claude/system-judge/judgments/2026-05-04_agent-evaluator_full.md`.
- **2026-05-05** — Manual project initialization. Created `.planning/` artifacts (PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md, config.json, codebase/, research/) from the System Judge findings. No code changes.
- **2026-05-06/07** — Phases 1-4 executed (TRUST schema, error-recovery N/A short-circuit, make_judge vendor factory, deterministic detectors). 69/69 tests, ruff clean. Phase 5 discussion locked D1-D4.
- **2026-06-11** — Phase 5 planned: 05-PATTERNS.md (pattern map), 4 PLAN.md files in 2 waves, plan-checker verified after 2 revision rounds (blockers: fictional `final_answer_quality` dimension name; bare-asterisk assertions colliding with Markdown bold). STATE/ROADMAP updated. No code changes.
- **2026-06-13** — Phase 5 Plan 01 executed: `pyproject.toml` live marker, 7 fixture JSON files, `tests/conftest.py` with `FixtureAnthropicClient` + `FixtureOpenAIClient`. 86 tests passing. Deviation: `IndexError` used instead of `StopIteration` for async exhaustion (PEP 479). Commits: 0b25bcc, 21b96ec, 953217f, 06d3974.

## Next Steps

1. Execute 05-02-PLAN.md — runner.py + report.py integration tests (TEST-01, TEST-03).
2. Execute 05-03-PLAN.md — judge.py LLM-path integration tests + live smoke tests (TEST-02).
3. Execute 05-04-PLAN.md — CI workflow + README badge (TEST-04); checkpoint for post-push CI verification.
4. **v1 closure:** after Phase 5 lands, regenerate `results/comparison.md` under the new schema and re-run System Judge as `judge ship` to flip NO-GO → GO.

## Open Questions (raised during init, deferred to phase discussion)

- **Schema choice (Phase 1):** `status: Literal["ok","error","na"]` field vs `score: Optional[float]` with `None` as the non-ok sentinel. Trade-off: explicit status is more readable in JSON; Optional[float] is fewer field changes.
- **Legacy artifact handling (Phase 1, TRUST-05):** label `results/comparison.md` with a disclaimer vs delete vs regenerate. Regenerate requires re-running `compare` which costs LLM tokens; the existing artifact's structural defect is documented anyway.
- **Judge consolidation (Phase 3, VEND-03):** keep two judge classes with a dispatcher vs single judge that branches on SDK internally. Two classes is more code; single class is more conditionals.
- **Deterministic vs judged split (Phase 4, DET-04):** how aggressive to be. Conservative: only obvious-arithmetic dims (efficiency, termination). Aggressive: also try to deterministically detect "tool usage correctness" via expected-call patterns.
