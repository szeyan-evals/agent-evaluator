# Phase 3 Context — Vendor Coupling Fix

**Phase:** 03 — Vendor Coupling Fix
**Goal:** Decouple judge construction from agent vendor; restore parity between `evaluate` and `compare`. Make `compare --models gpt-4o,gpt-4o-mini` runnable with only `OPENAI_API_KEY`. Reach the currently-dead `OpenAIJudge` via auto-routing. Reconcile docs with code.
**Requirements:** VEND-01, VEND-02, VEND-03, VEND-04
**Status:** discussion complete; planning next

---

## Domain

Three independent System Judge findings converge in this phase:
- **F-C** (INEVITABLE / MEDIUM blast / HIGH confidence) — `compare` silently requires `ANTHROPIC_API_KEY` for OpenAI-only comparisons.
- **F-D** (NOT INEVITABLE / hygiene) — `OpenAIJudge` (109 LOC) is unreachable from CLI. Dead code.
- **F-J** (LOW blast / hygiene) — `.env.example` documents `JUDGE_MODEL`/`AGENT_MODEL` env vars that no code reads; `pyproject.toml` declares `rich>=13.0` never imported; `scenarios/book_flight.py:8` imports `ErrorInjection` unused.

Phase 3 is the smallest cross-cutting change that closes all three.

## Canonical refs

- `.planning/research/JUDGMENT.md` — F-C, F-D, F-J targets
- `.planning/REQUIREMENTS.md` — VEND-01..04 acceptance
- `.planning/ROADMAP.md` — Phase 3 success criteria 1–4
- `.planning/codebase/ARCHITECTURE.md` — call paths showing where AnthropicJudge is constructed unconditionally
- `src/agent_evaluator/cli.py:71-86, 200` — current `compare` argparse + judge instantiation
- `src/agent_evaluator/judge.py:147+` — `OpenAIJudge` class (currently dead)
- `src/agent_evaluator/runner.py:30-34` — `OPENAI_PREFIXES` and `_is_openai_model` (the source of truth Phase 3 reuses)

## Carried-forward decisions (locked, not re-asked)

From Phases 1+2:
- TRUST schema (status field, partial computed_field, schema_version, legacy)
- Short-circuit pattern in `_evaluate_dimension` (Phase 2)
- Both judge classes already have the short-circuit shipped — they continue to work after Phase 3 consolidation

## Decisions

### D1 — Judge consolidation: two classes + factory dispatcher

Keep `AnthropicJudge` and `OpenAIJudge` as parallel classes. Add a small factory function in `judge.py` that picks one based on model prefix.

```python
# src/agent_evaluator/judge.py
def make_judge(model: str) -> AnthropicJudge | OpenAIJudge:
    """Auto-route judge construction by model name prefix.

    Mirrors AgentRunner's vendor dispatch: OpenAI prefixes route to
    OpenAIJudge; everything else routes to AnthropicJudge. See
    .planning/phases/03-.../03-CONTEXT.md D1+D2.
    """
    from agent_evaluator.runner import _is_openai_model
    if _is_openai_model(model):
        return OpenAIJudge(model=model)
    return AnthropicJudge(model=model)
```

**Why two classes + factory (not single class, not delete-OpenAIJudge):**
- Smallest delta. Two classes already exist and are tested (well, AnthropicJudge has unit + 3 short-circuit tests; OpenAIJudge inherits the short-circuit code path). Refactoring to a single class is bigger work with no functional gain in v1 scope.
- `OpenAIJudge` becomes reachable (closes F-D) — VEND-03 acceptance "no dead judge class" satisfied.
- Loses no functionality. A future phase can collapse to a single-class design if duplication becomes painful; for now, the duplication is bounded (~110 LOC) and the parallel structure mirrors `AgentRunner`'s vendor branching.

### D2 — Routing signal: reuse `runner._is_openai_model`

`judge.py::make_judge` imports `_is_openai_model` from `runner.py`. Single source of truth for the prefix tuple `("gpt-", "o1-", "o3-", "o4-")`.

**Why reuse (not duplicate, not new module):**
- DRY. If OpenAI ships `o5-` or `o6-` next year, only `runner.py::OPENAI_PREFIXES` updates.
- No new module. `routing.py` / `constants.py` would be over-engineering for a single tuple + one-line function.
- One-way dependency (`judge.py` → `runner.py`); `runner.py` does not import judge. No circular-import risk.

### D3 — `--judge-model` default on `compare`: first model in `--models`

```python
# src/agent_evaluator/cli.py — _cmd_compare
models = [m.strip() for m in args.models.split(",")]
judge_model = args.judge_model or models[0]  # NEW: default to first
judge = make_judge(judge_model)
```

`compare --help` includes the caveat:
```
--judge-model JUDGE_MODEL   Model used to judge trajectories.
                            Defaults to the first model in --models.
                            Note: defaulting to a model from --models means
                            self-judging, which can introduce bias toward
                            the judge's own family. For more rigor, specify
                            an independent judge (e.g., a Claude model when
                            comparing GPT models).
```

**Why first-model-default (not required, not env var, not hardcoded):**
- Most ergonomic. `compare --models gpt-4o,gpt-4o-mini` works with only `OPENAI_API_KEY` (delivers VEND-01 + closes F-C).
- Self-judging caveat is real but transparent — explicit in `--help`. The user can override.
- "Required flag" is annoying for the common case and adds friction without proportional rigor benefit.
- "Env var fallback" was deferred — see D4. We picked NOT to implement `JUDGE_MODEL` env var, so `.env.example` will be cleaned up rather than wired up.
- "Hardcoded claude-sonnet-4 default" re-creates F-C (the bug we're closing). Not an option.

### D4 — Hygiene: strict minimum

JUDGMENT F-J items + the doc updates Phase 3's code changes force:

1. **`pyproject.toml`** — remove `rich>=13.0` from runtime deps. Verified by grep that no module imports `rich`.
2. **`.env.example`** — remove `JUDGE_MODEL=` and `AGENT_MODEL=` lines. Update commentary to reflect actual key requirements (one-of: `ANTHROPIC_API_KEY` for Anthropic models, `OPENAI_API_KEY` for OpenAI models).
3. **`scenarios/book_flight.py:8`** — remove unused `ErrorInjection` import (the last remaining ruff F401).
4. **`README.md`** — update the API-key section to reflect auto-routing post-Phase 3:
   - "Required: at least one of `ANTHROPIC_API_KEY` (for Claude models) or `OPENAI_API_KEY` (for GPT models). The judge auto-routes to whichever vendor's model you specify."
   - Add `--judge-model` to the `compare` usage example.
   - Drop any claims about `JUDGE_MODEL`/`AGENT_MODEL` env vars.
5. **`results/legacy/comparison-2026-04-08.md`** disclaimer — already done in Phase 1 T6; not re-touched.

**Out of Phase 3 scope:**
- README architecture diagram, top-down rewrite, "when to use which judge model" section — Phase 5 territory or v2.
- Phase 5's Test/CI work doesn't pre-empt these doc edits because the doc edits are direct consequences of Phase 3 code changes.

## Implementation surface (for planner)

### Files to modify

- `src/agent_evaluator/judge.py` — add `make_judge(model)` factory function with `from agent_evaluator.runner import _is_openai_model` import. No changes to AnthropicJudge or OpenAIJudge themselves; both classes remain.
- `src/agent_evaluator/cli.py` —
  - `_cmd_evaluate`: change `judge = AnthropicJudge(model=args.judge_model)` → `judge = make_judge(args.judge_model)`. Default `args.judge_model` (currently `claude-sonnet-4-20250514`) preserved in argparse — auto-routes correctly.
  - `_cmd_compare`: add `--judge-model JUDGE_MODEL` arg to the subparser (parity with `evaluate`); default `None`. Body: `judge_model = args.judge_model or models[0]`; `judge = make_judge(judge_model)` (replaces the unconditional `AnthropicJudge()`).
- `src/agent_evaluator/cli.py` `_cmd_compare`'s argparse `--help` text — include the self-judging caveat from D3.
- `pyproject.toml` — remove `rich>=13.0` from `[project] dependencies` list.
- `.env.example` — remove the `JUDGE_MODEL`/`AGENT_MODEL` lines. Update header comment.
- `scenarios/book_flight.py` — remove `from agent_evaluator.models import ... ErrorInjection ...` (just drop `ErrorInjection` from the import list).
- `README.md` — update API-key section + `compare` usage example.

### Tests to add

- `tests/test_judge.py` — new tests for `make_judge`:
  - `test_make_judge_routes_openai`: pass `"gpt-4o"` → returns `OpenAIJudge` instance.
  - `test_make_judge_routes_anthropic`: pass `"claude-sonnet-4-20250514"` → returns `AnthropicJudge` instance.
  - `test_make_judge_unknown_routes_anthropic`: pass `"mistral-large"` → returns `AnthropicJudge` (existing behavior of `_is_openai_model` — unknown routes to Anthropic).
- `tests/test_cli.py` — *(NEW FILE — minimal)*. Phase 3 introduces argparse changes; we want a thin assertion layer on the parser shape:
  - `test_compare_has_judge_model_flag`: import `cli.main`'s argparse parser, parse `["compare", "--models", "a,b", "--judge-model", "x"]`, assert `args.judge_model == "x"`.
  - `test_compare_judge_model_default_none`: parse without `--judge-model`, assert `args.judge_model is None` (so the body's `or models[0]` fallback triggers).
  - **Skip:** end-to-end execution of `_cmd_compare` (requires SDK keys; deferred to Phase 5 TEST-04 or live-API smoke).

### Anti-regression checks

- All 35 Phase 1+2 tests continue to pass.
- `agent-eval list` returns 13 scenarios (unchanged).
- `agent-eval evaluate <traj.json>` defaults to claude-sonnet-4 — same behavior as before, just routed through `make_judge` (returns AnthropicJudge — identical instance shape).
- `agent-eval evaluate --judge-model gpt-4o <traj.json>` now works (was previously broken because `_cmd_evaluate` constructed `AnthropicJudge(model="gpt-4o")` which would call Anthropic SDK with a GPT name — confused 400/404).
- The 3 short-circuit tests in test_judge.py continue to pass (no changes to `_evaluate_dimension`).
- ruff is clean (the F401 in book_flight.py — last remaining finding — is now fixed by D4 #3).

## Open in planning (executor decides, not user)

- (Tests) Whether `test_make_judge_*` should also assert that the returned instance has the right `model` attribute set. Recommendation: yes, one-line addition.
- (CLI) Whether to add `--judge-model` to subcommands beyond `compare` and `evaluate` (e.g., `report` doesn't construct judges so doesn't need it). Recommendation: only `compare` and `evaluate` — keep argparse surface minimal.
- (Tests) Whether `test_cli.py` should mock `dotenv.load_dotenv` to avoid loading the real `.env`. Recommendation: argparse parsing happens before SDK construction; doesn't matter for the parse-only tests.
- (`.env.example` content) Exact wording of the rewrite. Plan can finalize from D4 #2 spec.

## Code context (reusable assets)

- `runner._is_openai_model` already exists with the correct prefix tuple — Phase 3 doesn't touch it.
- The `_FakeAnthropicClient` pattern from `tests/test_judge.py` Phase 2 — extends to `make_judge` tests (no fake needed; `make_judge` doesn't construct a client until `__init__`, but checking `isinstance(judge, AnthropicJudge)` is enough).
- argparse parser is built inside `cli.main` — for `test_cli.py` we either expose a `_build_parser()` helper or use `argparse`'s test patterns. Either works.

## Deferred ideas

- **`JUDGE_MODEL` env var implementation** — D3 picked first-model-default over env var fallback. If a future user wants env-var-driven defaults, add as v2 work.
- **Single Judge class refactor** — D1 chose two classes + factory; collapsing to one class is a v2 cleanup if duplication becomes painful.
- **Auto-detect available API keys and skip incompatible judges** — UX nicety, e.g., warn before running `compare --models gpt-4o,gpt-4o-mini --judge-model claude-sonnet-4` without `ANTHROPIC_API_KEY`. v2.
- **Comprehensive README rewrite** (architecture diagram, "when to use which judge", canonical-refs cross-link) — v2 doc milestone.
- **Telemetry: track which vendor each `compare` run uses** — v2 SLO/observability milestone.

## Next steps

1. `/gsd-plan-phase 3` — produce 03-PLAN.md from this CONTEXT and the canonical refs.
2. Plan should be small (4-5 atomic tasks): factory function, cli updates (both subcommands), pyproject edit, .env.example + README + book_flight cleanup, tests.
3. Plan-checker pass (same flow as Phases 1+2).
4. Execute. Verify VEND-01..04 acceptance + the 4 ROADMAP success criteria.

---
*Discussion complete: 2026-05-06. 4 areas selected, 4 decisions locked. No cross-phase impact (no Phase 1+2 amendments needed).*
