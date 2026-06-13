# agent-evaluator — Project Context

## What This Is

A Python CLI harness that runs LLM agents through scripted scenarios with mocked tools, captures full reasoning trajectories (turns, thoughts, tool calls, tokens), and judges those trajectories with another LLM along a five-dimension rubric. The mocked tools are a deliberate design choice: they hold the environment constant so reasoning is the only variable. **75% of the rubric weight measures *how* the agent reasoned, not *whether* it succeeded** — this is a process-introspection tool, not an outcome benchmark.

## Who It's For

Single user, local CLI use. Used to compare model behavior on the same task and to understand how agents reason under controlled conditions. Not multi-tenant, not a service, no SaaS.

## Project Stage

**Brownfield, in remediation.** The codebase exists and is largely written. A System Judge full-pipeline review on 2026-05-04 returned **NO-GO with HIGH confidence** because the eval artifacts the tool produces are structurally untrustworthy. This planning workspace exists to drive the remediation milestone (v1) so artifacts can be relied on.

## Core Value

**Trustworthy multi-dimensional reasoning analysis.** The deliverable is the eval artifact — `eval_*.json`, `comparison.md`. If artifacts encode failures as real-looking scores, or contain dimensions that are constants masquerading as signal, every downstream use is corrupted. Trustworthiness of artifacts is the project's whole reason to exist.

## Requirements

### Validated

These are working today, inferred from the existing codebase. Verified by the System Judge evidence manifest (19/19 tests pass, live `agent-eval list` returns 13 scenarios).

- ✓ **EVAL-01** — Run agent scenarios against the Anthropic SDK with mocked tools (`runner.py::_run_anthropic`)
- ✓ **EVAL-02** — Run agent scenarios against the OpenAI SDK with mocked tools (`runner.py::_run_openai` — partial; F-G annotation/runtime divergence flagged)
- ✓ **EVAL-03** — 13 prebuilt scenarios across easy/medium/hard difficulty (`scenarios/*.py`)
- ✓ **EVAL-04** — Capture full agent trajectories (turns, thoughts, tool calls, token counts) as `AgentTrajectory` Pydantic-modeled JSON
- ✓ **EVAL-05** — Five-dimension LLM-judged rubric with weighted overall score (`rubrics.py`, `judge.py::AnthropicJudge`)
- ✓ **EVAL-06** — Markdown reports for single-model and cross-model comparison runs (`report.py`)
- ✓ **EVAL-07** — CLI with `list / run / evaluate / report / compare` subcommands (`cli.py`)

### Active (Remediation milestone v1)

Hypotheses until the artifact-trustworthiness condition holds and a clean comparison run reproduces.

- [ ] **TRUST-01** — `DimensionScore` schema distinguishes "errored" from "scored 0.0"
- [ ] **TRUST-02** — `EvaluationResult` flags partial evaluations when any dimension errored
- [ ] **TRUST-03** — `compute_overall_score` excludes error/N/A dimensions from numerator AND denominator
- [ ] **TRUST-04** — Eval JSON files self-identify as partial when any dim errored; legacy `eval_*.json` are migratable or labeled as known-corrupt
- [ ] **TRUST-05** — Existing `results/comparison.md` is regenerated under the new schema or labeled as legacy
- [ ] **DIM-01** — `error_recovery` dimension returns `score=None` (or status `"na"`) when no errors are injected, not a constant `1.0`
- [ ] **DIM-02** — `compute_overall_score` correctly handles the `None` / N/A case (depends on TRUST-03)
- [ ] **VEND-01** — `AnthropicJudge` is constructed conditionally on actual model selection — not eagerly in every code path
- [ ] **VEND-02** — `compare` subcommand accepts `--judge-model` flag (parity with `evaluate`)
- [ ] **VEND-03** — Judge auto-routes by model name prefix (mirrors `AgentRunner` behavior)
- [ ] **VEND-04** — README accurately states which API keys are required when
- [ ] **DET-01** — Token efficiency dimension computed deterministically from trajectory tokens (no LLM judge call)
- [ ] **DET-02** — Action-loop detection (consecutive identical tool calls) is a deterministic check
- [ ] **DET-03** — Termination correctness check (did the agent stop appropriately) is deterministic
- [ ] **DET-04** — LLM-judged dimensions reduced to genuinely subjective ones (reasoning quality, plan coherence)
- [ ] **TEST-01** — Integration tests for `runner.py` agentic loops using recorded SDK responses (e.g., VCR / cassette pattern)
- [ ] **TEST-02** — Integration tests for `judge.py` retry, fence-strip, and `asyncio.gather` paths
- [ ] **TEST-03** — Tests for `report.py` rendering edge cases (empty results, missing dims, single-scenario, single-model)
- [ ] **TEST-04** — CI configured (GitHub Actions running `pytest` and `ruff` on every push)

### Out of Scope (v1)

- **Public calibrated judge benchmark** (1000 trajectories × 5 human annotators) — research project, separate scope, distinct cost profile
- **Cost / latency SLOs and error budgets** — operational concern, defer to a v2 reliability milestone
- **Drift detection / longitudinal studies** — operational, defer to v2
- **Variance / N-trials reporting** — meaningful but adds runtime; defer to v2 once trust foundation lands
- **Field-wide vocabulary standardization** — coordination problem this project can't solve alone
- **Real (non-mocked) tool execution** — explicit anti-feature; mocked tools are a design choice (process-introspection over outcome benchmark)
- **Hosted / SaaS deployment** — local CLI is the deliverable
- **OpenAIJudge as a user-reachable judge implementation** — defer; current code has it as type-system-only parity. Either reach it (as part of VEND-03 auto-routing) or delete it. v1 picks one route and removes the dead code if VEND-03 collapses to "Anthropic-only judge with explicit `--judge-model` override."

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| Schema-first remediation | Per System Judge: failure-channel-on-`DimensionScore` is the dependency root for every other fix. Without it, dimension-level fixes leak structurally invalid data. | TRUST phase locked as Phase 1, blocks everything |
| Process-eval framing kept | The mocked-tool design is intentional, not a limitation. 75% of rubric weight is process. The remediation preserves this framing rather than pivoting to outcome eval. | EVAL-01..07 stay validated; mocked tools NOT replaced with real ones |
| Deterministic detectors before judges | Token efficiency, action-loop detection, termination correctness are arithmetic — should not be LLM-judged. Reduces failure surface and frees judge budget for genuinely subjective dims. | DET-01..04 added to v1 |
| Existing artifacts treated as known-corrupt | `results/comparison.md` empirically demonstrates the Error Recovery constant (26/26 cells = 1.00). Cannot be retroactively trusted. | Regenerate or label as legacy; don't carry forward |
| Single-vendor judge by default, explicit override allowed | `OpenAIJudge` exists as dead code today. Either auto-route by model prefix (mirrors `AgentRunner`) or pick Anthropic-only with explicit override and delete the unreachable class. | VEND-03 holds the choice; resolved during Phase 3 discuss |
| No git repo in v1 scope | Project is currently NOT a git repo. Initializing git is out of scope for v1; can be done by user when convenient. | `commit_docs: false` in config.json; `.planning/` is local-only |

## Context

- **Source of truth for findings:** `~/.claude/system-judge/judgments/2026-05-04_agent-evaluator_full.md` (also linked into `.planning/research/`)
- **Codebase entry point:** `agent-eval` console script → `src/agent_evaluator/cli.py`
- **Hub module:** `src/agent_evaluator/models.py` — every other module imports from it. Schema changes ripple to runner, judge, report, registry, cli, all 13 scenarios, all `eval_*.json` on disk.
- **Tests:** 19/19 pass in 0.10s; coverage concentrated on Pydantic round-trips, weight arithmetic, mock dispatch. The two longest modules (`runner.py` 354 LOC, `judge.py` 256 LOC) are entirely uncovered.
- **No CI** — manual quality gates only.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-05 after manual initialization from System Judge findings (judgment 2026-05-04).*
