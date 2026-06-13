# Requirements — agent-evaluator (v1 Remediation)

**Milestone:** v1 — make eval artifacts trustworthy.
**Source of truth for failure modes:** `~/.claude/system-judge/judgments/2026-05-04_agent-evaluator_full.md` (linked at `.planning/research/JUDGMENT.md`).

REQ-ID format: `[CATEGORY]-[NUMBER]`. Categories: `EVAL` (validated brownfield), `TRUST` (Phase 1), `DIM` (Phase 2), `VEND` (Phase 3), `DET` (Phase 4), `TEST` (Phase 5).

---

## Validated Requirements (existing capabilities)

These were verified by the System Judge evidence manifest (live `agent-eval list`, 19/19 tests passing, codebase inspection). They are NOT in scope for re-implementation; they constrain the remediation work — anything that would break a Validated requirement is a regression.

### Brownfield-Validated

- ✓ **EVAL-01** — Run agent scenarios against the Anthropic SDK with mocked tools. *Source:* `src/agent_evaluator/runner.py::AgentRunner._run_anthropic`.
- ✓ **EVAL-02** — Run agent scenarios against the OpenAI SDK with mocked tools. *Source:* `src/agent_evaluator/runner.py::AgentRunner._run_openai`. *Note:* F-G annotation/runtime divergence at line 267 must not regress further.
- ✓ **EVAL-03** — 13 prebuilt scenarios across easy/medium/hard difficulty, registered via `@register` decorator and discoverable via `pkgutil.iter_modules`. *Source:* `scenarios/registry.py` + 13 scenario files.
- ✓ **EVAL-04** — Capture full agent trajectories (turns, thoughts, tool calls, token counts) and serialize as `AgentTrajectory` Pydantic-modeled JSON. *Source:* `src/agent_evaluator/models.py::AgentTrajectory`.
- ✓ **EVAL-05** — Five-dimension LLM-judged rubric with weighted overall score. Weights: task_completion 0.25, tool_usage 0.20, efficiency 0.20, reasoning_quality 0.20, error_recovery 0.15. *Source:* `src/agent_evaluator/rubrics.py`.
- ✓ **EVAL-06** — Markdown reports for single-model and cross-model comparison runs. *Source:* `src/agent_evaluator/report.py::generate_report`, `generate_comparison_report`.
- ✓ **EVAL-07** — CLI with `list / run / evaluate / report / compare` subcommands. *Source:* `src/agent_evaluator/cli.py::main`.

---

## v1 Active Requirements

### Phase 1 — Trustworthy Score Schema (TRUST)

The dependency root. No other phase delivers durable value without this. Per the System Judge: silent-zero amplifier (F-A) is INEVITABLE / HIGH blast / HIGH confidence; the artifact `eval_*.json` cannot be trusted to distinguish real low scores from transport errors until the schema carries a failure channel.

- [ ] **TRUST-01** — `DimensionScore` carries an explicit status discriminator. Either `status: Literal["ok", "error", "na"]` field, or `score: Optional[float]` with `None` reserved for non-ok. The discriminator must be persisted in `eval_*.json`. *Acceptance:* a judge call that raises any exception type produces a `DimensionScore` whose `status != "ok"` (or `score is None`), distinguishable from a legitimate `score=0.0`.
- [ ] **TRUST-02** — `EvaluationResult` exposes a `partial: bool` (or equivalent) flag that is `True` when at least one dimension's `status != "ok"`. Persisted in `eval_*.json`. *Acceptance:* `EvaluationResult.partial` is correctly set when any dimension errored.
- [ ] **TRUST-03** — `compute_overall_score` excludes non-`ok` dimensions from BOTH numerator AND denominator (NOT averaging them as zeros, NOT counting them in the weight total). *Acceptance:* a partial evaluation with one errored dim returns the same overall score as it would if the rubric were re-weighted across the remaining four dims.
- [ ] **TRUST-04** — Eval JSON files self-identify as partial via `partial: true` at the top level when any dim errored. Reports surface this clearly. *Acceptance:* `report.py` renders a visible "PARTIAL" marker on rows whose backing eval is partial; never silently averages partial overalls into the overall column.
- [ ] **TRUST-05** — Existing artifacts (`results/comparison.md`, any historical `eval_*.json`) are either regenerated under the new schema or explicitly labeled as legacy/known-corrupt. *Acceptance:* no v1 artifact contains scores produced under the pre-TRUST schema without a labeled disclaimer.

### Phase 2 — Error Recovery Dimension Fix (DIM)

The constant-as-signal defect. Per System Judge F-B (INEVITABLE / HIGH blast / HIGH confidence): empirically proven by `results/comparison.md` (26/26 cells = 1.00, including the 2 scenarios with injected errors). Depends on Phase 1's TRUST schema.

- [ ] **DIM-01** — `error_recovery` dimension returns `status="na"` (or `score=None`) when the trajectory's source scenario has no `error_injection`. The rubric's "score this as 1.0" instruction in `rubrics.py:178-179` is removed or replaced with N/A semantics. *Acceptance:* eval results for `book_flight`, `calendar_scheduling`, `data_analysis`, `database_query`, `email_compose`, `file_management`, `math_calculation`, `multi_step_research`, `research_topic`, `weather_lookup`, `web_scraping` all carry `error_recovery.status == "na"` (these 11 have no error injection).
- [ ] **DIM-02** — `compute_overall_score` treats `error_recovery.status == "na"` correctly: dimension is excluded from the weighted sum and weight total. (Implementation lands via TRUST-03; this requirement asserts the behavior on the specific dimension.) *Acceptance:* on a perfect agent run on a no-error scenario, `overall_score` is computed across 4 dimensions with weights renormalized; on `code_generation` / `debug_code`, all 5 dimensions contribute as before.

### Phase 3 — Vendor Coupling Fix (VEND)

Per System Judge F-C (INEVITABLE / MEDIUM blast / HIGH confidence) plus F-D (dead code) and F-E (prefix routing). The headline `compare` use case is currently unrunnable for OpenAI-only users.

- [ ] **VEND-01** — `AnthropicJudge` is constructed lazily, conditional on actual model selection. It is NOT instantiated eagerly in `_cmd_evaluate` or `_cmd_compare`. *Acceptance:* `agent-eval compare --models gpt-4o,gpt-4o-mini` succeeds with only `OPENAI_API_KEY` set (no `ANTHROPIC_API_KEY` required), provided the user explicitly selects an OpenAI-family judge.
- [ ] **VEND-02** — `compare` subcommand accepts `--judge-model` flag (parity with `evaluate`). Default judge is preserved if flag is omitted, but its identity is documented and the documented identity matches code. *Acceptance:* `agent-eval compare --help` lists `--judge-model`; passing `--judge-model gpt-4o` selects an OpenAI judge.
- [ ] **VEND-03** — Judge is auto-routed by model name prefix (mirrors `AgentRunner._is_openai_model`). The dispatcher chooses `AnthropicJudge` or `OpenAIJudge` (or, alternatively, a single judge implementation that internally branches by SDK). The currently-dead `OpenAIJudge` is either reached by the dispatcher or removed. *Acceptance:* no dead judge class; given a judge model name, exactly one SDK is constructed.
- [ ] **VEND-04** — README accurately describes which API keys are required when. `.env.example` is corrected: `JUDGE_MODEL` and `AGENT_MODEL` are either implemented (read from env in `cli.py`) or removed from `.env.example`. *Acceptance:* zero claims in README/`.env.example` are contradicted by code (verified by an explicit doc-vs-code check during phase verification).

### Phase 4 — Deterministic Detectors First (DET)

Per the post-judgment discussion: many "judged" dimensions are actually arithmetic. Reduces failure surface (fewer LLM calls = fewer silent-zero opportunities), reduces cost, increases reproducibility. Depends on Phase 1's TRUST schema for the `status` field that lets a deterministic dim coexist with a judged one.

- [ ] **DET-01** — Token efficiency dimension is computed deterministically from the trajectory's tokens-per-step. No LLM judge call. Threshold-based or normalized-against-scenario-budget; specific definition decided during Phase 4 discuss. *Acceptance:* `efficiency` dimension's score is reproducible bit-for-bit on the same trajectory; no SDK call is made for it.
- [ ] **DET-02** — Action-loop detection (consecutive identical or near-identical tool calls) is a deterministic check. *Acceptance:* given a trajectory with two identical `read_file` calls in a row, the detector flags it; given a trajectory with diverse tool use, it does not.
- [ ] **DET-03** — Termination correctness check (did the agent stop appropriately — e.g., emitted a final answer rather than hitting `max_reasonable_steps + 5`) is deterministic. *Acceptance:* trajectory with `stopped_reason == "no_tool_use"` passes; trajectory with `stopped_reason == "max_steps"` fails the check.
- [ ] **DET-04** — LLM-judged dimensions are reduced to genuinely subjective ones: `reasoning_quality` and `task_completion` (subjective interpretation of "did the user's intent get satisfied"). `tool_usage` and `error_recovery` may stay LLM-judged or be partly deterministic — decided during Phase 4 discuss. *Acceptance:* count of LLM-judged dimensions decreases; rationale documented in the phase's CONTEXT.md.

### Phase 5 — Test Coverage and CI (TEST)

Per System Judge F-F: `runner.py` and `judge.py` are the longest, riskiest modules and have zero automated coverage. Without tests, every TRUST/DIM/VEND/DET fix is unprotected against regression.

- [ ] **TEST-01** — Integration tests for `runner.py::_run_anthropic` and `_run_openai` using recorded SDK responses. Pattern: VCR-style cassettes or hand-crafted response fixtures. Cover: happy path multi-turn loop, max-steps termination, malformed tool_use blocks, missing `usage` (Anthropic — F-H regression guard), `choice.message`-as-dict round-trip (OpenAI — F-G regression guard).
- [ ] **TEST-02** — Integration tests for `judge.py` retry, fence-strip, and `asyncio.gather` paths. Cover: `JSONDecodeError` triggers retry; non-retry exception (e.g., `AttributeError` from non-text first content block) routes to TRUST-01 status path (NOT silent zero); fence-strip handles fence-then-no-fence variations; gather aggregates 5 dim results with mixed ok/error correctly.
- [ ] **TEST-03** — Tests for `report.py::generate_report` and `generate_comparison_report` rendering edge cases: empty results dir, single scenario, single model, all-partial evaluations, mixed ok/partial, missing dimensions due to TRUST-03 exclusion.
- [ ] **TEST-04** — CI configured. `.github/workflows/ci.yml` runs `pytest` and `ruff check` on every push and PR. Required for merge once enabled.

---

## v2 Requirements (deferred)

- Public calibrated judge benchmark (1000 trajectories × 5 human annotators × inter-judge κ reporting)
- Cost / latency SLOs and error budgets per scenario
- Drift detection — re-score historical inputs and flag distribution changes >2σ
- N-trials variance reporting (mean ± std across N runs of the same trajectory)
- Production shadow comparison on the same trajectory across multiple judge models
- Failure-mode taxonomy (CWE-for-agents) with deterministic detectors mapped to each
- Trajectory-aware diff testing: "what behaviors did this harness change introduce/remove"

---

## Out of Scope

- **Real (non-mocked) tool execution** — anti-feature. Mocked tools are the design choice that makes process-introspection possible.
- **Hosted / SaaS deployment** — local CLI is the deliverable.
- **Field-wide vocabulary standardization** — coordination problem this project alone cannot solve.
- **Replacing LLM-as-judge entirely with deterministic checks** — some dimensions (reasoning quality) are genuinely subjective and benefit from LLM judgment. DET reduces but does not eliminate the judge surface.
- **Restructuring scenarios into subpackages** — F-K (non-recursive `pkgutil.iter_modules`) is documented but not in v1; flat-dir convention is preserved.
- **Migrating off Pydantic v2** — current forward-ref pattern relies on auto-rebuild; pinning to v1 is out of scope.

---

## Traceability

Filled in by `/gsd-roadmapper` (or by hand in this case during ROADMAP.md creation). Each REQ-ID maps to exactly one phase.

| REQ-ID    | Phase | Notes |
|-----------|-------|-------|
| TRUST-01..05 | Phase 1 | Schema work — blocks everything |
| DIM-01..02 | Phase 2 | Depends on Phase 1's status field |
| VEND-01..04 | Phase 3 | Independent of Phase 1; could parallelize but small project keeps it serial |
| DET-01..04 | Phase 4 | Depends on Phase 1's status field (deterministic dims need to coexist with judged ones using same schema) |
| TEST-01..04 | Phase 5 | After all fixes land — locks them in |

---
*Last updated: 2026-05-05 from System Judge findings 2026-05-04.*
