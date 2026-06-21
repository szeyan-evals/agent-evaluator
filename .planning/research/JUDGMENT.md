---
date: 2026-05-04
system: agent-evaluator
slug: agent-evaluator
mode: full
verdict: NO-GO
scope_unit: whole system
scope_depth: transitive within first-party; 1 hop at third-party boundary
evidence_completeness: COMPLETE
registry_timestamps: ["2026-05-04T05:44:15Z"]
---

# System Judge Report — agent-evaluator

## Scope Declaration

**UNIT:** Whole `agent-evaluator` Python project at `/Users/szeyan/Documents/Dev/agent-evaluator`. User invoked `/judge` with no arguments at the project root; the project is small and self-contained, so module-level scope would arbitrarily exclude the runner, judge, or scenarios — all of which form one evaluation loop.

**DEPENDENCY DEPTH:** Transitive closure within first-party code; 1 hop at the third-party boundary. Inspect SDK call sites, not SDK internals.

**IN SCOPE (read):** `src/agent_evaluator/{__init__,cli,runner,judge,models,rubrics,report}.py`, `scenarios/registry.py` + 13 scenario files, `tests/test_{models,rubrics,runner}.py`, `examples/sample_run.py`, `pyproject.toml`, `README.md`, `.env.example`.

**BLACK BOXES:** stdlib, anthropic SDK ≥0.40, openai SDK ≥1.50, pydantic, rich, jinja2, python-dotenv, pytest, ruff, hatchling, `.venv/`, `.pytest_cache/`, `.idea/`, `.DS_Store`, `.env` (do not read; `.env.example` in scope as documentation).

**TIME RANGE:** Current snapshot only — environment confirms NOT a git repo; no commit history available.

**HARD BOUNDARY:** Any agent encountering evidence outside scope must STOP and report the boundary violation rather than explore.

## Evidence Manifest Summary

**Manifest completeness:** COMPLETE.

- Tests executed: **19/19 PASS in 0.10s**.
- Lint executed: ruff produced 6 minor findings (3 auto-fixable; F401 unused imports, F541 redundant f-string, E402 module-level imports after `load_dotenv`). No correctness/security flags.
- CLI smoke-tested: `agent-eval list` returned 13 scenarios as documented.
- Scenario inventory: 13 scenarios verified; only 2 (`code_generation.py`, `debug_code.py`) define `error_injection`. The other 11 are devoid of injected errors.
- Tested surface: Pydantic round-trips, rubric weight arithmetic, `MockToolExecutor` table dispatch, `compute_overall_score` math.
- **Untested surface (load-bearing):** `runner.py::AgentRunner` agentic loops (Anthropic + OpenAI, ~165 LOC), entire `judge.py` (256 LOC including retry, fence-strip, asyncio.gather across 5 dimensions), `report.py` (143 LOC), `scenarios/registry.py`, `cli.py` argparse and dispatch.
- No CI/CD configured.
- One existing artifact: `results/comparison.md` (Apr 8) — 3,305 bytes, claude-sonnet-4 vs gpt-4o.
- 14 assumption-registry entries written by Scanner at `2026-05-04T05:44:15Z`.

## Report

### Verdict — NO-GO  (confidence: HIGH)

The artifact this tool exists to produce — a comparable, weighted, multi-dimensional score across LLMs — is structurally corrupted. Two independent defects guarantee that defect, and a third blocks the headline use case at entry.

### Top findings (ranked, all HIGH structural confidence)

| # | Finding | Tier | Blast | Evidence |
|---|---|---|---|---|
| 1 | **Silent-zero amplifier (F-A)**: `judge.py` `asyncio.gather(return_exceptions=True)` collapses any non-parse exception into `DimensionScore(score=0.0)`, persisted to `eval_*.json` and averaged at full weight, indistinguishable from a legitimate 0.0. Triggers on every transient SDK error, network timeout, or non-text first content block. | INEVITABLE | HIGH | `judge.py:55-75, 101-118, 173-192`; `rubrics.py:233-239`; `models.py:111-128` (no error/status field); `cli.py:166`; `report.py:39-47` |
| 2 | **Error Recovery is a 0.15-weighted constant (F-B)**: `rubrics.py:178-179` instructs the judge to score 1.0 when no errors are injected. 11/13 default scenarios have empty `error_injection`. **Empirical proof in repo:** `results/comparison.md` shows Error Recovery = 1.00 in **26/26 cells**, including the 2 scenarios that DO inject errors. The dimension contributes zero variance and inflates `overall_score` by up to +0.15 on most scenarios. | INEVITABLE | HIGH | `rubrics.py:178-179`; scenario inventory; `results/comparison.md` Error Recovery section |
| 3 | **`compare` silently requires `ANTHROPIC_API_KEY`** for OpenAI-only runs — `cli.py:200` constructs `AnthropicJudge()` unconditionally; README says `OPENAI_API_KEY` is "Optional, for model comparison" — implies the inverse. Also: no `--judge-model` flag on `compare` (parity gap with `evaluate`). | INEVITABLE | MEDIUM | `cli.py:71-86, 200`; `judge.py:39-47`; README L14 |
| 4 | **OpenAI runner appends an SDK Pydantic object into a `list[dict]`** at `runner.py:267` — annotation/runtime divergence. SDK-version-sensitive whether the next `chat.completions.create(messages=...)` accepts it. Untested. | NEAR-INEVITABLE | MEDIUM | `runner.py:235, 267` |
| 5 | **Fence-stripper drops the last line unconditionally** (`judge.py:127-128`: `lines[1:-1]`). Composes with F-A: parse failures retry but exhausted retries produce `ValueError` outside the retry catch → silent zero. | NEAR-INEVITABLE | MEDIUM | `judge.py:127-128, 237-242` |
| 6 | **Asymmetric defense across SDKs**: Anthropic runner reads `response.usage.input_tokens` unguarded (`runner.py:166`); OpenAI path guards the equivalent (`runner.py:256-258`). | NEAR-INEVITABLE | MEDIUM | `runner.py:166 vs 256-258` |
| 7 | **`OPENAI_PREFIXES` allow-list misroutes** (`runner.py:30-34`): any model not matching `("gpt-","o1-","o3-","o4-")` falls through to Anthropic SDK silently — typos, Mistral, Llama, even `gpt4` (no hyphen). | CONDITIONAL | LOW | `runner.py:30-34, 124-133` |
| 8 | **Scenario discovery non-recursive + last-writer-wins** on duplicate IDs. | CONDITIONAL | MEDIUM | `scenarios/registry.py:23-31` |
| 9 | **Per-row report cells show 0.00 for missing dims** while overall column excludes them (`report.py:34`). Cosmetic today; matters once F-A is fixed. | CONDITIONAL | LOW | `report.py:32-36` |

### Truth-Filter calls (HIGH confidence)

- **Success theater**: 19/19 green tests cover Pydantic round-trips, weight arithmetic, mock dispatch — the cheap deterministic parts. Two longest, riskiest modules (runner + judge) have **zero** automated coverage. Green CI here is a proxy for "the dataclasses didn't break," not for "the system works."
- **Self-incriminating artifact**: `results/comparison.md` was sitting in the repo containing the smoking gun (constant Error Recovery column) — an output produced by the system that proves the metric is hollow.
- **Type-system parity ≠ reachable parity**: `OpenAIJudge` (109 LOC) duplicates `AnthropicJudge` line-for-line but has zero call sites in `cli.py`. Dual-vendor in source, single-vendor at runtime.
- **Documentation drift**: `.env.example` documents `JUDGE_MODEL`/`AGENT_MODEL` — neither is read anywhere in the code (zero `getenv` matches). `pyproject.toml` declares `rich>=13.0` — never imported. `scenarios/book_flight.py:8` imports `ErrorInjection` unused. `cli.py:7` imports `json` unused.
- **Hard-coded defaults**: judge model is `"claude-sonnet-4-20250514"` literal in 4 file:line locations, even when the agent under test is OpenAI.

### What would flip this to CONDITIONAL GO

Minimal correctness package:
1. Replace `score=0.0` substitution with a sentinel — add a `status: Literal["ok","error","na"]` field to `DimensionScore`, or use `Optional[float]`. Make `compute_overall_score` exclude error/N/A dims from numerator AND denominator. Mark `EvaluationResult` with a `partial: bool` flag when any dimension errored.
2. In `rubrics.py:178-179`, return `score=None` (or status `"na"`) when no errors injected; teach `compute_overall_score` to skip it. Re-run any historical eval that fed `comparison.md`. Delete or label the existing `results/comparison.md` as known-corrupt.
3. Decide: either (a) gate `AnthropicJudge` construction on actual model selection and add `--judge-model` to `compare`, or (b) update README to state Anthropic key is mandatory.

Defer-to-later: F-G/F-H/F-I (compose with F-A — fix together), F-K, F-E, F-L, dead code/dependency cleanup. Add CI running `pytest` + `ruff` + at least one integration smoke against a recorded judge response fixture.

### Overall Confidence

**HIGH** on the verdict.
- F-A is structurally proven by line-by-line trace across five files; chain composes deterministically.
- F-B is **empirically proven** in the repo's own artifact — not just a theory.
- F-C is reproducible at module-construction level, deterministic.
- The unverified items (F-G/F-H/F-I) reinforce the verdict but are not load-bearing for it; verdict stands without them.

The single dominant law (see Law Extractor): *the silent-coercion indistinguishability law* — when a system substitutes a default value for a failed operation in a type that has no failure channel, the resulting artifacts are evidence of nothing. F-A is a pure instance.

## Agent Outputs

### Scope Scoper

UNIT: Whole `agent-evaluator` Python project at `/Users/szeyan/Documents/Dev/agent-evaluator`.

DEPENDENCY DEPTH: Transitive closure within first-party code; 1 hop at the third-party boundary.

IN SCOPE: All `src/agent_evaluator/*.py`, `scenarios/registry.py` + 13 scenario files, `tests/test_*.py`, `examples/sample_run.py`, `pyproject.toml`, `README.md`, `.env.example`.

BLACK BOXES: Python stdlib, asyncio, anthropic SDK ≥0.40, openai SDK ≥1.50, pydantic ≥2.7, rich ≥13.0, jinja2 ≥3.1, python-dotenv ≥1.0, pytest, pytest-asyncio, ruff, hatchling. Build artifacts (`.venv/`, `__pycache__/`, `.pytest_cache/`, `.idea/`, `.DS_Store`). Secrets file `.env`.

TIME RANGE: Current code only. NOT a git repo (no `.git/`); commit history unavailable. The only temporal signal available is filesystem mtimes (Apr 2 – Apr 28, 2026).

HARD BOUNDARY: any agent discovering evidence outside this declaration must STOP and report the boundary violation, not "just peek."

### Evidence Collector

**MANIFEST COMPLETENESS: COMPLETE.**

- 7 in-scope source files (1,464 LOC) + 15 scenario files (1,098 LOC) + 3 tests (252 LOC) + 1 example (55 LOC).
- Entry points: `agent-eval` console script (verified working — returned 13 scenarios) and `python examples/sample_run.py`.
- pytest: 19/19 PASS in 0.10s.
- ruff: 6 minor findings (3 auto-fixable; F401 unused `json`, F401 unused `ErrorInjection` in `book_flight.py`, F541 redundant f-string in `report.py:52`, 3× E402 in `examples/sample_run.py`).
- Dependency graph: `models.py` is the hub — every other in-scope module depends on it.
- External (1-hop): runtime `pydantic`, `anthropic`, `openai`, `rich`, `jinja2`, `python-dotenv`. **`rich` is declared but no module imports it — dead dependency.**
- Configuration: console script `agent-eval = agent_evaluator.cli:main`. pytest `asyncio_mode = "auto"`, `pythonpath = ["src"]`. ruff `target-version = py311`, `line-length = 100`.
- Required env: `ANTHROPIC_API_KEY` always (judge defaults to Anthropic even for OpenAI agents). `OPENAI_API_KEY` only when an OpenAI model is the agent.
- Model routing: `OPENAI_PREFIXES = ("gpt-", "o1-", "o3-", "o4-")`; everything else routes to Anthropic.
- 13 scenarios load and register correctly (verified live). Only `code_generation` and `debug_code` define `error_injection`; 11 others are empty.
- `JUDGE_MODEL` and `AGENT_MODEL` documented in `.env.example` but **NEITHER is read anywhere in code** (zero `getenv` matches). Dead documentation.
- Critical call paths: scenario discovery → `pkgutil.iter_modules` + `importlib.import_module` + `@register` decorator (non-recursive). Anthropic agent loop in `runner._run_anthropic` (~85 LOC, untested). OpenAI agent loop in `_run_openai` (~80 LOC, untested) — line 267 appends SDK Pydantic object into `list[dict]`. Trajectory eval: `asyncio.gather` 5 dimensions in parallel, retry max=2 on parse errors, on final failure → `DimensionScore(score=0.0)`. Reporting: `eval_*.json` glob → Pydantic load → markdown table. None of (judge, runner, report, registry, cli) tested.

KNOWN GAPS: No tests for `runner.py::AgentRunner`, `judge.py`, `report.py`, `scenarios/registry.py`, `cli.py`. No CI/CD.

### Scanner

Mapped real architecture (CLI → registry/runner/judge/report). 14 assumption registry entries written at `2026-05-04T05:44:15Z`.

Highest-blast hidden assumptions:
1. **Judge dimension exceptions outside `(JSONDecodeError, KeyError, IndexError)` → silent 0.0 averaged into overall.** PHANTOM. HIGH/HIGH. Two-location code inspection (`judge.py:59-73, 101-115`).
2. **`OPENAI_PREFIXES` covers all OpenAI models; everything else is safely Anthropic-routable.** PHANTOM. HIGH/HIGH.
3. **`compare` always uses default Anthropic judge with no override.** IMPLICIT. HIGH/MEDIUM.
4. **`JUDGE_MODEL` / `AGENT_MODEL` env vars in `.env.example` are functional.** PHANTOM. HIGH/MEDIUM.
5. **First content block of judge response is always `type=="text"`.** PHANTOM. HIGH/MEDIUM. (`judge.py:109-110`).
6. **Fenced response always has exactly one closing fence line.** IMPLICIT. HIGH/MEDIUM.
7. **OpenAI SDK accepts its own ChatCompletionMessage object back into `messages=`.** PHANTOM. MEDIUM/MEDIUM.
8. **`@register(scenario_id)` never sees a duplicate.** PHANTOM. HIGH/MEDIUM.
9. **Per-scenario row has every dimension scored.** IMPLICIT. HIGH/MEDIUM.
10. **Average row distinguishes silent-zero from genuine zero.** PHANTOM. HIGH/MEDIUM.
11. **`ANTHROPIC_API_KEY` is set even for OpenAI-only.** IMPLICIT. HIGH/MEDIUM.
12. **Anthropic API responses always include `.usage`.** IMPLICIT. HIGH/LOW.
13. **`error_recovery` rubric produces meaningful scores on the 11 no-error scenarios.** IMPLICIT. HIGH/LOW.
14. **`rich>=13.0` dependency is being used somewhere.** EXPLICIT-FALSE. HIGH/LOW.

Five fragility points:
- **F1 The silent-zero amplifier** — three independent designs converge: `gather(return_exceptions=True)` + `DimensionScore(score=0.0)` substitution + lack of error flag on `DimensionScore`. HIGH/HIGH.
- **F2 Cross-vendor asymmetry**: token-counting unguarded on Anthropic, message round-tripping appends Pydantic object on OpenAI; both SDK-bump-fragile.
- **F3 Scenario discovery via `pkgutil.iter_modules` + decorator + `from __future__ import annotations`**: three implicit contracts (flat dir, top-level register call, unique IDs) plus Pydantic v2 auto-rebuild dependency.
- **F4 `--judge-model` flag exists for `evaluate` but not `compare`** — methodological bias in headline use case.
- **F5 No CI; 0% coverage on the two longest modules** (runner.py 354 LOC, judge.py 256 LOC).

Invisible dependencies:
- `models.py` is the dependency hub.
- Anthropic SDK is implicit on every code path including OpenAI-only `compare`.
- `scenarios/__init__.py` mere existence is required.
- Pydantic v2 auto-rebuild for forward references at `models.py:24, 57`.
- `response.content[0]` indexed in both judge and runner; runner defensively checks, judge does not.

**Structural verdict (Scanner):** the system presents as a clean, dual-vendor, rubric-driven evaluation harness, but in practice has a single load-bearing path (Anthropic judge), three independent designs that collude to silently encode evaluation failures as zero scores, and zero coverage on the two modules where SDK drift is most likely. Eval artifacts look authoritative but are not self-validating against judge errors.

### Truth Filter

**VERIFIED:** 13 scenarios load (live). 5 rubric dimensions sum to 1.0 (tested). README weight table matches code. Console script wired. CLI subcommands wired structurally. Model auto-routing by prefix verified. Pydantic round-trip tested. MockToolExecutor dispatch tested. `compute_overall_score` tested.

**CONTRADICTIONS (HIGH confidence):**
- C1: `.env.example` documents `JUDGE_MODEL`/`AGENT_MODEL` — zero matches in code. Dead docs.
- C2: `pyproject.toml` declares `rich>=13.0` — zero imports. Dead dep.
- C3: `book_flight.py:8` imports `ErrorInjection` unused.
- C4: `cli.py:7` imports `json` unused.
- C5: README implies vendor parity; `compare` constructs `AnthropicJudge()` unconditionally; `OpenAIJudge` is defined but has zero call sites; `compare` has no `--judge-model` flag.
- C6: README "default model" hides hard-coded `"claude-sonnet-4-20250514"` literal in `cli.py:32, 53`, `judge.py:42, 153`, `runner.py:124`.
- C7: **5-dimension rubric collapses to ~4 dimensions on most scenarios**. Empirical: `results/comparison.md` shows Error Recovery = **1.00 in all 26 cells**, including for the 2 scenarios that DO inject errors. Smoking gun.

**UNVERIFIED (high risk):**
- U1: Anthropic agentic loop correctness — no SDK mocks; only `comparison.md` evidences past success.
- U2: OpenAI agentic loop — no test; `runner.py:267` type-divergence flagged. SDK-version-sensitive.
- U3: Judge LLM call + retry + fence-strip — no test. `lines[1:-1]` discards last line unconditionally.
- U4: Report Markdown rendering — no test.
- U5: CLI argparse beyond `list` — manual smoke only for `list`.

**SUCCESS THEATER:**
- T1: 19/19 PASS in 0.10s is structurally shallow. Doesn't cover any I/O- or LLM-bound path.
- T2: `results/comparison.md` proves the artifact existed once, not that the flow is reliable. The artifact itself contains the proof of dimension collapse.
- T3: Two judge classes implies dual-vendor; only one is reachable.
- T4: The "5-dimension rubric" sells more signal than it delivers.

**Ground truth (Truth Filter):** the data-modeling layer is structurally verified and tested. Everything above it (agentic loops, judge LLM calls, retry/parse, report writer, four of five CLI subcommands) is asserted but not tested, and at least three assertions are demonstrably wrong on inspection (`OpenAIJudge` unreachable; `compare` silently requires Anthropic; `error_recovery` is a constant on 11/13 scenarios). The 19/19 green is real but covers the cheap parts; the load-bearing surface is unverified.

### Failure Judge

**TIER 1 — INEVITABLE, BLOCKS SHIP:**

- **F-A Silent-zero amplifier** — INEVITABLE / HIGH blast / HIGH confidence. Four-link chain quoted line-by-line: `judge.py:59` gather + `judge.py:64-73` zero-substitution + `judge.py:110` narrow retry + `rubrics.py:234` `score >= 0` inclusion + `cli.py:166` persistence. Triggers on first 429/529/5xx, on first non-text first content block, on network timeout. False safety: the retry loop appears resilient but is narrower than the gather catch.
- **F-B Error Recovery 0.15-weighted constant** — INEVITABLE / HIGH / HIGH. Empirical proof in `comparison.md`: 26/26 cells = 1.00 including the 2 with injected errors. Already failing on every default-scenario run.
- **F-C `compare` requires Anthropic key for OpenAI-only** — INEVITABLE / MEDIUM / HIGH. Failure at module-construction.

**TIER 2 — NEAR-INEVITABLE:**
- F-G OpenAI message-shape mismatch (`runner.py:267`) — MEDIUM / MEDIUM.
- F-H Unguarded `usage.input_tokens` on Anthropic (`runner.py:166`) — MEDIUM / MEDIUM.
- F-I Fence-stripper drops last line (`judge.py:127-128`) — MEDIUM / HIGH. Composes with F-A.

**TIER 3 — CONDITIONAL:**
- F-E `OPENAI_PREFIXES` allow-list — LOW / HIGH.
- F-K Non-recursive scenario discovery — MEDIUM / MEDIUM.
- F-L Row arithmetic vs overall — LOW / HIGH.

**TIER 4 — NOT FAILURES (hygiene):**
- F-D `OpenAIJudge` dead code (HIGH).
- F-J doc drift, dead deps (MEDIUM).
- F-F coverage gap — credibility multiplier on the others, not itself a runtime failure (HIGH).

**Answers to targeted questions:**
- F-A constitutes a structural certainty under realistic conditions: any single 429/529/5xx, any non-text first content block, any network timeout produces a 0.0 indistinguishable from a legitimate 0.0. The deliverable is the artifact; the artifact is corrupted; the corruption is unrecoverable from the artifact alone.
- F-B is empirically proven, not just structural — `results/comparison.md` is the artifact of the failure.

### Decision Engine

**DECISION: NO-GO** (confidence: HIGH)

Because:
1. The artifact the tool exists to produce — a comparable, weighted, multi-dimensional score — is structurally corrupted: F-B makes Error Recovery a near-constant 1.0 (proven in `results/comparison.md`: 26/26 cells = 1.00), so the weighted total is biased upward by a fixed offset for every model.
2. F-A's silent-zero amplifier turns any judge/transport exception into a real-looking 0.0, indistinguishable from a true low score in persisted JSON — model rankings can flip on infrastructure noise with no surface signal.
3. F-C makes `compare` unrunnable for OpenAI-only users despite README contract, so the headline use case is blocked at entry.

**CONDITION (would flip to CONDITIONAL GO):** tag silent-zero with sentinel + raise; remove Error Recovery from weighted total when not injected; gate AnthropicJudge construction on model prefix; delete stale `results/comparison.md`.

**ONE-LINE:** The evaluator's own outputs cannot be trusted to rank models, because two independent structural defects silently inflate and silently zero the very scores it was built to compare.

### Law Extractor

Seven reusable frameworks derived from cross-system corpus (4 systems in registry):

1. **LAW — Silent-Coercion Indistinguishability Law.** When a system substitutes a default value for a failed operation in a type with no failure channel, the resulting artifacts are evidence of nothing — including their non-failed values, because consumers cannot tell which is which. This recurs across evaluation systems. Apply by demanding a `status` discriminator on every fallible value emission.

2. **PRINCIPLE — Catch-Wider-Than-Retry Trap.** When the outer error envelope is broader than the inner retry/recovery envelope, every error not anticipated by the inner net becomes a silent permanent failure. Apply by ensuring outer ⊆ inner, or making the absorb path observable.

3. **LAW — Test-Coverage Inversion Law.** Test-suite green-ness measures what was easy to test; the modules with the highest LOC × external deps × blast radius are structurally hardest to cover and therefore most likely uncovered — green CI is anti-correlated with risk coverage by default. Universal across the corpus (4/4 systems). Apply by ranking modules by risk and writing integration tests for the top three before unit tests.

4. **PRINCIPLE — Type-Level Parity ≠ Reachable Parity.** The presence of a class/config/route in the source tree is not evidence that any execution path reaches it. Apply by tracing from entry points downward and writing one user-reachable code path per implementation.

5. **PRINCIPLE — Constant-as-Signal Law (Metric Hollowing).** Any quantitative dimension that emits a constant on the dominant input distribution is not measurement — it is a weighted bias. Apply by simulating new dimensions on existing corpus and checking standard deviation; σ ≈ 0 ⇒ decorative.

6. **PRINCIPLE — Compose-Feeding Law.** The blast radius of a finding is its severity multiplied by the largest downstream finding it can reach by data flow. Isolated severity rankings under-report risk in the presence of asymmetric error envelopes.

7. **HEURISTIC — Self-Indicting Artifact.** In any system that produces a tangible output, the artifact itself is the highest-signal evidence about whether the system works — higher than source code, tests, or docs. Apply by reading the most recent output before reading any source. (`results/comparison.md` is the canonical example for this judgment.)

**Most transferable:** Law 1 (Silent-Coercion Indistinguishability) — unifies the dominant failure modes across all four systems in the registry.
