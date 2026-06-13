# Research Summary — agent-evaluator v1 Remediation

This research milestone is **driven by an existing System Judge artifact**, not by fresh domain investigation. The judgment supplies stack/features/architecture/pitfalls equivalents directly, grounded in the codebase rather than synthesized from web sources.

**Primary source:** `.planning/research/JUDGMENT.md` (copied from `~/.claude/system-judge/judgments/2026-05-04_agent-evaluator_full.md`, 23KB).

## Key Findings (compressed for downstream agents)

### What's working (validated)
- 13 scenarios load and run via `agent-eval list` (confirmed live).
- Pydantic round-trip for `AgentTrajectory` and `EvaluationResult` is tested and correct.
- Rubric weights sum to 1.0; `compute_overall_score` math is correct on the inputs it receives.
- `MockToolExecutor` dispatch (matched / default / unknown / error-injected) is tested across 4 cases.
- 19/19 unit tests pass in 0.10s.

### What's broken (structural, all HIGH confidence)
1. **F-A Silent-zero amplifier** (HIGH blast). `judge.py` `asyncio.gather(return_exceptions=True)` collapses every non-parse exception into `DimensionScore(score=0.0)`, persisted to `eval_*.json`, indistinguishable from a real low score. No error/status field on `DimensionScore`.
2. **F-B Error Recovery constant** (HIGH blast). 11/13 default scenarios have empty `error_injection`; rubric instructs the judge to score 1.0 in that case. Empirically: `results/comparison.md` shows Error Recovery = 1.00 in 26/26 cells, including the 2 scenarios that DO inject errors.
3. **F-C `compare` requires `ANTHROPIC_API_KEY`** (MEDIUM blast). Even for OpenAI-only comparisons. README says `OPENAI_API_KEY` is "Optional, for model comparison" — implies the inverse.

### Composing failures (NEAR-INEVITABLE)
- **F-G** OpenAI runner appends an SDK Pydantic object into `list[dict]` (`runner.py:267`).
- **F-H** Anthropic runner reads `response.usage.input_tokens` unguarded (asymmetric with OpenAI guard).
- **F-I** Fence-stripper drops the last line unconditionally (`judge.py:127-128`); composes with F-A.

### Documentation drift (LOW blast, hygiene)
- `.env.example` documents `JUDGE_MODEL` and `AGENT_MODEL` — neither is read anywhere in code.
- `pyproject.toml` declares `rich>=13.0` — never imported (dead dep).
- `book_flight.py:8` imports `ErrorInjection` unused; `cli.py:7` imports `json` unused.
- `OpenAIJudge` (109 LOC in `judge.py`) is unreachable from the CLI — dead code.

### Test surface
- Covered: Pydantic round-trips, weight arithmetic, `compute_overall_score` math, `MockToolExecutor` table dispatch.
- **Uncovered (load-bearing):** entire `runner.py` agentic loops (~165 LOC), entire `judge.py` (256 LOC), `report.py`, `cli.py` argparse, `scenarios/registry.py` discovery.
- No CI configured.

## Stack (cross-reference)
See `.planning/codebase/STACK.md`. Notable:
- Python ≥3.11, Pydantic v2 (relies on auto-rebuild for forward refs in `models.py`).
- Anthropic SDK ≥0.40, OpenAI SDK ≥1.50.
- `rich>=13.0` declared but unused.

## Architecture (cross-reference)
See `.planning/codebase/ARCHITECTURE.md`. Notable:
- `models.py` is the dependency hub.
- 5 critical call paths documented (scenario discovery, Anthropic agent loop, OpenAI agent loop, trajectory eval, reporting).
- Pydantic JSON files are the persistence layer — schema changes ripple to all writers/readers and on-disk artifacts.

## Pitfalls (cross-reference: judgment Tier 1-3)

| # | Pitfall | Where in code | Phase that addresses it |
|---|---|---|---|
| 1 | Silent-zero amplifier (F-A) | `judge.py:55-75, 101-118, 173-192`; `rubrics.py:233-239`; `models.py:111-128` | Phase 1 (TRUST) |
| 2 | Error Recovery constant (F-B) | `rubrics.py:178-179`; scenario inventory | Phase 2 (DIM) |
| 3 | `compare` Anthropic key coupling (F-C) | `cli.py:71-86, 200`; `judge.py:39-47` | Phase 3 (VEND) |
| 4 | OpenAI list[dict] divergence (F-G) | `runner.py:235, 267` | Phase 5 (TEST regression guard) |
| 5 | Anthropic usage unguarded (F-H) | `runner.py:166 vs 256-258` | Phase 5 (TEST regression guard) |
| 6 | Fence-stripper drops last line (F-I) | `judge.py:127-128, 237-242` | Phase 5 (TEST) — composes with Phase 1's TRUST schema; F-I no longer corrupts data once exception → status="error" instead of silent 0.0 |
| 7 | `OPENAI_PREFIXES` allow-list misroutes (F-E) | `runner.py:30-34, 124-133` | Out of scope v1 — could fold into Phase 3 |
| 8 | Scenario discovery non-recursive (F-K) | `scenarios/registry.py:23-31` | Out of scope v1 — flat-dir convention preserved |
| 9 | Per-row report shows 0.00 for missing dims (F-L) | `report.py:32-36` | Phase 1 (TRUST) — partial markers |
| 10 | Doc drift, dead deps (F-J) | `.env.example`, `pyproject.toml`, `book_flight.py:8`, `cli.py:7` | Phase 3 (VEND-04) |

## Why no fresh domain research

The judgment **already produced**:
- Stack inventory (verified line-by-line)
- Failure mode taxonomy (Tier 1-4 with confidence + blast)
- Empirical proof of failure (`results/comparison.md` Error Recovery column)
- Reusable laws (Law Extractor output: silent-coercion indistinguishability, test-coverage inversion, type-vs-reachable parity, etc.)

A fresh `gsd-project-researcher` run would either (a) duplicate this work or (b) hallucinate new findings without the structural evidence the judgment grounded its claims on. The judgment is more authoritative than fresh research would be.

## Downstream agent guidance

- **`gsd-discuss-phase 1`** — gray areas to discuss are listed in STATE.md `Open Questions`. Schema choice (`status` field vs `Optional[float]`), legacy artifact handling, judge consolidation, deterministic-vs-judged split.
- **`gsd-phase-researcher` (any phase)** — primary references are `.planning/research/JUDGMENT.md` (full structural analysis), `.planning/codebase/ARCHITECTURE.md` (call paths and data flow), `.planning/codebase/STACK.md` (dependency surface).
- **`gsd-planner`** — every phase's affected files are pre-listed in `.planning/ROADMAP.md`. Use them as the starting point; expand if the phase's CONTEXT.md surfaces new ones.
