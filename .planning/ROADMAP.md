# Roadmap — agent-evaluator v1 (Remediation)

**Goal:** Make eval artifacts trustworthy. The System Judge full-pipeline review on 2026-05-04 returned NO-GO with HIGH confidence. This milestone closes the three INEVITABLE failure modes plus their compose-feeders, locks the fixes in with tests + CI, and ships a clean comparison run that demonstrates artifact trustworthiness.

**Source of truth for failure modes:** `~/.claude/system-judge/judgments/2026-05-04_agent-evaluator_full.md` (linked at `.planning/research/JUDGMENT.md`).

**Sequencing principle:** Phase 1 (TRUST) is the dependency root per the System Judge Decision Engine — without a failure channel on `DimensionScore`, every other fix is decorative. Phases 2 and 4 explicitly depend on Phase 1's schema. Phase 3 is independent of Phase 1 but kept serial for a small project. Phase 5 is the lock-in.

---

## Phase Summary

| # | Phase | Goal | Requirements | Success Criteria |
|---|---|---|---|---|
| 1 | Trustworthy Score Schema | Add a failure channel to `DimensionScore` and propagate it through aggregation, persistence, and reporting | TRUST-01..05 | 5 |
| 2 | Error Recovery Dimension Fix | Eliminate the constant-as-signal defect in `error_recovery` | DIM-01..02 | 3 |
| 3 | Vendor Coupling Fix | Decouple judge construction from agent vendor; restore parity between `evaluate` and `compare` | VEND-01..04 | 4 |
| 4 | Deterministic Detectors First | Replace LLM-judged dims that are actually arithmetic; reduce judge surface | DET-01..04 | 4 |
| 5 | Test Coverage and CI | Lock the fixes in with integration tests on `runner.py` / `judge.py` / `report.py` and a green CI gate | TEST-01..04 | 4 |

**Total:** 5 phases, 19 active requirements, 7 brownfield-validated requirements (see `REQUIREMENTS.md` for full mapping). All v1 active requirements covered.

---

## Phase Details

### Phase 1: Trustworthy Score Schema

**Goal:** Every dimension carries an explicit `status` discriminator (or `Optional[float]` equivalent), and aggregation/persistence/reporting honor it. After this phase, a transient API error or a non-text first content block from the judge is structurally distinguishable from a legitimate low score.

**Requirements:** TRUST-01, TRUST-02, TRUST-03, TRUST-04, TRUST-05

**Affected files:**

- `src/agent_evaluator/models.py` — `DimensionScore`, `EvaluationResult` schema changes
- `src/agent_evaluator/rubrics.py` — `compute_overall_score` semantics
- `src/agent_evaluator/judge.py` — exception → `DimensionScore(status="error")` substitution path (was `score=0.0`)
- `src/agent_evaluator/report.py` — surface partial markers on rows/cells
- `src/agent_evaluator/cli.py::_cmd_evaluate` — persist the new fields
- `results/comparison.md` (legacy) — label or regenerate

**Success criteria:**

1. `DimensionScore` has a status discriminator persisted in `eval_*.json`. A judge call that raises `AttributeError`, `RateLimitError`, or `TimeoutError` produces a non-`ok` `DimensionScore` whose existence cannot be confused with a legitimate `score=0.0`.
2. `EvaluationResult.partial` is `True` whenever any dimension's status != ok; `False` otherwise.
3. `compute_overall_score` excludes non-`ok` dimensions from the weight total. A partial evaluation with one errored dim returns the same overall score as if the rubric were natively re-weighted across the remaining dims.
4. `report.generate_report` and `generate_comparison_report` render a visible "PARTIAL" marker on rows whose backing `EvaluationResult.partial` is `True`. They never silently average partial overalls into the unmarked overall column.
5. Existing `results/comparison.md` is either regenerated under the new schema or labeled with a top-of-file disclaimer pointing to the System Judge findings.

**Dependencies:** none (this phase IS the dependency root).

**Anti-regression:** EVAL-01..07 must continue to work. Existing tests must continue to pass with the schema migration (or be updated to cover the new fields without losing the existing semantic checks).

---

### Phase 2: Error Recovery Dimension Fix

**Goal:** Eliminate the +0.15 weighted constant. After this phase, scenarios with no `error_injection` produce `error_recovery.status == "na"` (excluded from the weighted sum), not a 1.0 contributing 15% bias.

**Requirements:** DIM-01, DIM-02

**Affected files:**

- `src/agent_evaluator/rubrics.py` — `error_recovery` rubric template (lines 178-179 specifically) and any branching on injected-errors
- `src/agent_evaluator/judge.py` — return path that constructs the dimension's `DimensionScore`; ensure N/A flows through TRUST-01 status field

**Success criteria:**

1. For each of the 11 scenarios without `error_injection` (`book_flight`, `calendar_scheduling`, `data_analysis`, `database_query`, `email_compose`, `file_management`, `math_calculation`, `multi_step_research`, `research_topic`, `weather_lookup`, `web_scraping`), `eval_*.json` contains `error_recovery.status == "na"` (or equivalent), NOT `score=1.0`.
2. For `code_generation` and `debug_code` (the 2 scenarios with `error_injection`), `error_recovery` continues to be LLM-judged and contributes to overall.
3. `compute_overall_score` on a no-error scenario returns the same value as if the rubric were natively defined on 4 dimensions with weights renormalized: task_completion 0.294, tool_usage 0.235, efficiency 0.235, reasoning_quality 0.235 (each = original/0.85). A regenerated `comparison.md` shows variance across rows where the previous one had a constant 1.00 column.

**Dependencies:** Phase 1 (TRUST-03 must land first — `compute_overall_score` needs to know how to skip N/A dimensions).

**Anti-regression:** the 2 error-injected scenarios must continue to score `error_recovery` honestly.

---

### Phase 3: Vendor Coupling Fix

**Goal:** `compare` is runnable with only `OPENAI_API_KEY` for OpenAI-only model comparisons. Judge dispatch matches agent dispatch (auto-routed by model prefix). The dead `OpenAIJudge` is either reached or removed. Documentation matches code.

**Requirements:** VEND-01, VEND-02, VEND-03, VEND-04

**Affected files:**

- `src/agent_evaluator/cli.py` — `_cmd_compare` argparse block (add `--judge-model`); judge instantiation no longer eager
- `src/agent_evaluator/judge.py` — judge factory or auto-router; resolve `OpenAIJudge` reachability
- `README.md` — accurate API-key requirements
- `.env.example` — remove `JUDGE_MODEL` and `AGENT_MODEL` if not implemented, OR implement them

**Success criteria:**

1. `agent-eval compare --models gpt-4o,gpt-4o-mini --judge-model gpt-4o` succeeds with only `OPENAI_API_KEY` set (no `ANTHROPIC_API_KEY` required).
2. `agent-eval compare --help` lists `--judge-model` (parity with `evaluate`).
3. No dead judge class. Either `OpenAIJudge` is reached by the dispatcher (model name with OpenAI prefix routes to it) or it's removed and the auto-router dispatches into a single judge implementation that internally branches by SDK.
4. README and `.env.example` make zero claims contradicted by code. A doc-vs-code consistency check passes during phase verification.

**Dependencies:** none structurally on Phase 1 or 2; could parallelize but kept serial for a single-engineer project.

**Anti-regression:** `agent-eval evaluate <trajectory>` continues to work with both default and `--judge-model gpt-4o`. EVAL-07 (CLI subcommands) preserved.

---

### Phase 4: Deterministic Detectors First

**Goal:** Token efficiency, action-loop detection, and termination correctness are computed in code, not judged by an LLM. Reduces failure surface (fewer LLM calls = fewer silent-zero opportunities) and cost; increases reproducibility.

**Requirements:** DET-01, DET-02, DET-03, DET-04

**Affected files:**

- `src/agent_evaluator/rubrics.py` — refactor: split into "deterministic detectors" and "LLM-judged rubrics"
- `src/agent_evaluator/judge.py` — judge invokes deterministic dims directly (no SDK call) and LLM-judged dims through the existing path
- `src/agent_evaluator/models.py` — possibly add a `judge_method: Literal["deterministic", "llm"]` field on `DimensionScore` (decided during Phase 4 discuss)

**Success criteria:**

1. `efficiency` dimension's score is reproducible bit-for-bit on the same trajectory across multiple `agent-eval evaluate` runs. No SDK call is recorded for it.
2. Action-loop detection is correct on a trajectory containing two identical consecutive tool calls (flagged) vs. a trajectory with diverse tool use (not flagged).
3. Termination correctness check returns appropriate scores for `stopped_reason="no_tool_use"` (good) vs `stopped_reason="max_steps"` (bad).
4. The count of LLM-judged dimensions decreases (target: 2 — `task_completion`, `reasoning_quality`); the rationale for which dimensions stay judged is documented in `04-CONTEXT.md`.

**Dependencies:** Phase 1 (TRUST schema must support deterministic dims coexisting with judged ones — same `DimensionScore` shape).

**Anti-regression:** the LLM-judged dims that stay judged must continue to retry/parse/aggregate correctly per Phase 1's status-aware path.

---

### Phase 5: Test Coverage and CI

**Goal:** The fixes from Phases 1-4 are protected against regression by integration tests on the load-bearing modules, and a CI gate enforces them on every push.

**Requirements:** TEST-01, TEST-02, TEST-03, TEST-04

**Plans:** 4 plans in 2 waves (planned 2026-06-11; authoritative implementation surface is `05-CONTEXT.md`).

Plans:
**Wave 1**

- [x] 05-01-PLAN.md — Fixture infrastructure: `conftest.py` replay clients, hand-rolled SDK fixture JSON, `live` pytest marker (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-02-PLAN.md — runner.py integration tests (TEST-01, F-G/F-H/max-steps guards) + report.py edge-case tests (TEST-03) (Wave 2)
- [ ] 05-03-PLAN.md — judge.py LLM-path integration tests (TEST-02, F-A/F-I guards) + marker-skipped live smoke tests (Wave 2)
- [ ] 05-04-PLAN.md — CI workflow `.github/workflows/ci.yml` + README badge (TEST-04); checkpoint for post-push CI verification (Wave 2)

**Affected files** (per `05-CONTEXT.md` — supersedes the original cassette-based sketch):

- `tests/conftest.py` — `FixtureAnthropicClient` / `FixtureOpenAIClient` replay clients (new)
- `tests/fixtures/anthropic/*.json`, `tests/fixtures/openai/*.json` — hand-rolled SDK response fixtures (new; D1 — no `vcrpy`/cassettes)
- `tests/test_runner_integration.py` — new file (runner.py integration tests)
- `tests/test_judge_integration.py` — new file (judge.py LLM-path tests)
- `tests/test_report.py` — new file (report.py edge cases)
- `tests/test_live_smoke.py` — new file (marker-skipped live tests, D3)
- `pyproject.toml` — add `live` marker
- `.github/workflows/ci.yml` — new file

**Success criteria** (refined by `05-CONTEXT.md` — new files `test_runner_integration.py` / `test_judge_integration.py`, hand-rolled fixtures, not cassettes):

1. Runner integration tests cover happy-path multi-turn loops for both Anthropic and OpenAI runners using hand-rolled fixtures. Includes regression guards for F-G (OpenAI `choice.message` round-trip) and F-H (Anthropic missing usage, strict-xfail).
2. Judge integration tests cover retry on `JSONDecodeError`, status="error" on retry exhaustion (F-A), fence-strip variations (F-I), and `asyncio.gather` aggregation with mixed ok/error.
3. `tests/test_report.py` covers empty results dir, single scenario, single model, all-partial, and mixed ok/partial with the partial markers.
4. `.github/workflows/ci.yml` exists and runs `pytest -m 'not live'` + `ruff check` on every push (main) and pull request. CI greenness is verified by the user after the repo is pushed to GitHub (project is not yet a git repo in v1 scope).

**Dependencies:** Phases 1-4 — testing must observe the post-remediation behavior.

**Anti-regression:** the existing 69 tests continue to pass with no semantic loss (some may need updates for the new schema; coverage of weight arithmetic, mock dispatch, and Pydantic round-trips must remain).

---

## Roadmap Coverage Validation

All 19 v1 Active requirements (TRUST-01..05, DIM-01..02, VEND-01..04, DET-01..04, TEST-01..04) are mapped to exactly one phase. All 7 Validated requirements (EVAL-01..07) are protected as anti-regression conditions across phases. No requirement is orphaned.

## Acceptance for v1 Milestone

A regenerated `results/comparison.md` between two distinct models, produced under the new schema, shows:

- Variance across the `error_recovery` column (no longer a constant 1.00)
- A clear "PARTIAL" indicator on any row whose backing eval had a non-ok dimension
- An overall score that excludes non-ok / N/A dimensions from the weight total
- All five (or post-DET-04, however many) dimensions producing meaningful per-cell variance, not constants
- The CI badge (post-Phase 5) showing green on the commit that produced the comparison

When this artifact lands, v1 is complete. The System Judge can be re-run as `judge ship` to flip NO-GO → CONDITIONAL GO or GO.

---
*Last updated: 2026-06-13 — Phase 5 Plan 02 complete (runner + report integration tests; 95 passing, 1 xfailed).*
