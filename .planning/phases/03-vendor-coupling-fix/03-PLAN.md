# Phase 3 Plan — Vendor Coupling Fix

**Phase:** 03 — Vendor Coupling Fix
**Source decisions:** `03-CONTEXT.md` (D1–D4)
**Source artifacts:**
- `.planning/research/JUDGMENT.md` (F-C, F-D, F-J targets)
- `.planning/REQUIREMENTS.md` (VEND-01..04)
- `.planning/ROADMAP.md` (Phase 3 success criteria 1–4)
- `.planning/codebase/ARCHITECTURE.md`

**Goal restatement:** Decouple judge construction from agent vendor; restore parity between `evaluate` and `compare`. Make `compare --models gpt-4o,gpt-4o-mini` runnable with only `OPENAI_API_KEY`. Reach `OpenAIJudge` via auto-routing. Reconcile docs with code.

---

## Pre-flight notes

### Current code shape (verified by spot-check)

- `src/agent_evaluator/cli.py:51` — `evaluate` subparser already has `--judge-model` with default `"claude-sonnet-4-20250514"`.
- `src/agent_evaluator/cli.py:71-85` — `compare` subparser does NOT have `--judge-model`. T2 adds it.
- `src/agent_evaluator/cli.py:142` — `_cmd_evaluate` constructs `AnthropicJudge(model=args.judge_model)` unconditionally. Needs `make_judge`.
- `src/agent_evaluator/cli.py:201` — `_cmd_compare` constructs `AnthropicJudge()` (no model passed — uses class default `claude-sonnet-4-20250514`). Needs `make_judge` + a default chain (`args.judge_model or models[0]`).
- `src/agent_evaluator/runner.py:30-34` — `OPENAI_PREFIXES = ("gpt-", "o1-", "o3-", "o4-")` and `_is_openai_model(model)` exist. Reused in `make_judge`.
- `src/agent_evaluator/judge.py:147` — `OpenAIJudge` class exists but has zero call sites (verified by grep).

### Build-green-after-every-commit ordering

| T# | Lands | Why build stays green |
|----|-------|-----------------------|
| T1 | `make_judge(model, *, client=None)` factory + 4 tests | New function not yet called by anything; isolated addition. New tests cover dispatch logic. **Client injection critical for OpenAI test** (SDK constructor eager — raises without `OPENAI_API_KEY`). |
| T2 | cli.py call-site updates + new compare flag | T1 already shipped `make_judge`. Tests pass (no integration tests touch `_cmd_*`). |
| T3 | NEW `tests/test_cli.py` argparse parsing tests (5 + 3 smoke = 8) | Covers the new `--judge-model` flag + default-None behavior + 3 smoke tests defending the `_build_parser()` extraction (plan-checker C1). Independent of T2 logic; passes after T2. |
| T4 | Hygiene cleanup (5 items) | No code-behavior change; ruff F401 in book_flight cleared. |
| T5 | Verification | Synthetic E2E + ruff + agent-eval list smoke; live-API path noted as user-required. |

---

## Tasks

### T1 — `make_judge` factory + dispatch tests

**Files:** `src/agent_evaluator/judge.py`, `tests/test_judge.py`

**Changes:**

1. In `judge.py`, add factory function (placement: at module top-level after class definitions, near the bottom of the file):

```python
def make_judge(
    model: str,
    *,
    client: Any | None = None,
) -> AnthropicJudge | OpenAIJudge:
    """Auto-route judge construction by model name prefix.

    Mirrors AgentRunner's vendor dispatch (runner.py::_is_openai_model):
    OpenAI prefixes ("gpt-", "o1-", "o3-", "o4-") route to OpenAIJudge;
    everything else routes to AnthropicJudge. Closes JUDGMENT F-D
    (OpenAIJudge previously unreachable). See 03-CONTEXT.md D1+D2.

    Args:
        model: Model name; routed by prefix.
        client: Optional pre-constructed SDK client. Pass-through to the
            judge class constructor. **Required for testing** when no
            real API key is available — OpenAI's SDK constructor is eager
            and raises without OPENAI_API_KEY. See plan-checker B1.
    """
    from agent_evaluator.runner import _is_openai_model
    if _is_openai_model(model):
        return OpenAIJudge(model=model, client=client)
    return AnthropicJudge(model=model, client=client)
```

Add `from typing import Any` to imports if not already present.

The `from agent_evaluator.runner import _is_openai_model` is INSIDE the function body — defensive against future circular-import risk (no actual cycle today; cheap because Python caches sys.modules).

**Asymmetry resolved by client injection:** `AnthropicJudge.__init__` lazily constructs `anthropic.AsyncAnthropic()` only if `client is None`; `OpenAIJudge.__init__` does the same with `AsyncOpenAI()`. **However:** `AsyncOpenAI()` raises `OpenAIError` immediately if `OPENAI_API_KEY` is unset, while `AsyncAnthropic()` defers the auth check to the first request. So `make_judge("gpt-4o")` without an injected client will raise in unkeyed environments (including standard CI). **Tests MUST pass `client=fake`** to construct an `OpenAIJudge` without a real key. (Production callers — `cli.py::_cmd_*` — pass `client=None` and rely on the user's env keys.)

2. In `tests/test_judge.py`, append three new tests. **OpenAI tests must inject a fake client** (the existing `_FakeAnthropicClient` pattern doesn't fit the OpenAI SDK shape, so introduce a parallel `_FakeOpenAIClient` minimal stub):

```python
class _FakeOpenAIClient:
    """Minimal stub matching the OpenAI SDK shape we need for construction.
    The factory just stores the client; we don't invoke anything on it."""
    pass


class TestMakeJudge:
    def test_make_judge_routes_openai(self):
        """OpenAI's SDK constructor is eager and raises without OPENAI_API_KEY,
        so we inject a fake client to keep this test hermetic. Production
        callers (cli.py) pass client=None and rely on env keys."""
        from agent_evaluator.judge import make_judge, OpenAIJudge
        fake = _FakeOpenAIClient()
        judge = make_judge("gpt-4o", client=fake)
        assert isinstance(judge, OpenAIJudge)
        assert judge.model == "gpt-4o"
        assert judge.client is fake

    def test_make_judge_routes_anthropic(self):
        from agent_evaluator.judge import make_judge, AnthropicJudge
        judge = make_judge("claude-sonnet-4-20250514")
        assert isinstance(judge, AnthropicJudge)
        assert judge.model == "claude-sonnet-4-20250514"

    def test_make_judge_unknown_routes_anthropic(self):
        """Unknown prefixes (mistral, llama, etc.) route to Anthropic per
        the existing _is_openai_model semantics (anything-not-OpenAI ⇒ Anthropic).
        Phase 3 does NOT change that; tighter routing (third vendor support
        or strict-allow-list) is deferred."""
        from agent_evaluator.judge import make_judge, AnthropicJudge
        judge = make_judge("mistral-large")
        assert isinstance(judge, AnthropicJudge)
        assert judge.model == "mistral-large"

    def test_make_judge_passes_client_to_anthropic(self):
        """Same client-injection contract for AnthropicJudge."""
        from agent_evaluator.judge import make_judge, AnthropicJudge
        fake = _FakeAnthropicClient()  # already defined in this file (Phase 2)
        judge = make_judge("claude-sonnet-4-20250514", client=fake)
        assert isinstance(judge, AnthropicJudge)
        assert judge.client is fake
```

(4 tests total in the new `TestMakeJudge` class — was 3 before plan-checker fix; the additional one verifies the client-injection contract for AnthropicJudge symmetrically.)

**Acceptance:**
- `make_judge("gpt-4o", client=fake)` → `OpenAIJudge` instance with `model="gpt-4o"`, `judge.client is fake`.
- `make_judge("claude-sonnet-4-20250514")` → `AnthropicJudge` instance with that model (no client needed; Anthropic SDK is lazy).
- `make_judge("mistral-large")` → `AnthropicJudge` instance (existing fallback behavior preserved).
- `make_judge("claude-sonnet-4-20250514", client=fake)` → AnthropicJudge with the injected client.
- `OpenAIJudge` is now reachable from at least one call site (the test). Closes F-D structurally. Closure of F-D for the live CLI happens in T2.
- All 4 tests in `TestMakeJudge` pass in an unkeyed CI environment.

**Anti-regression:**
- All 35 existing tests pass.
- Both judge classes' `_evaluate_dimension` short-circuit (Phase 2) continues to work — `make_judge` returns instances of the same shape; `_evaluate_dimension` is unchanged.

**Dependency:** none.

**Atomic commit:** `feat(judge): add make_judge factory dispatching by model prefix (VEND-03)`

**Note on `OpenAIJudge.__init__`** — the existing constructor has a defensive `try: from openai import AsyncOpenAI` guard. The factory simply constructs `OpenAIJudge(model=model)` without a client; the constructor handles SDK-import + key-fetch. If `OPENAI_API_KEY` is missing at this point, the SDK constructor will raise — the user gets a clear error pointing at the right vendor. (No silent failure; consistent with the AnthropicJudge path.)

---

### T2 — cli.py: route through `make_judge`; add `--judge-model` to `compare`

**File:** `src/agent_evaluator/cli.py`

**Changes:**

1. **`_cmd_evaluate`** (currently `cli.py:138-166`) — replace the unconditional `AnthropicJudge` import + construction:

```python
# BEFORE
async def _cmd_evaluate(args: argparse.Namespace) -> None:
    from agent_evaluator.judge import AnthropicJudge
    from agent_evaluator.runner import AgentRunner
    from scenarios.registry import load_all_scenarios

    judge = AnthropicJudge(model=args.judge_model)
    ...

# AFTER
async def _cmd_evaluate(args: argparse.Namespace) -> None:
    from agent_evaluator.judge import make_judge
    from agent_evaluator.runner import AgentRunner
    from scenarios.registry import load_all_scenarios

    judge = make_judge(args.judge_model)
    ...
```

The argparse default for `--judge-model` (currently `"claude-sonnet-4-20250514"`) is preserved — `make_judge` returns AnthropicJudge for that name, so behavior is identical to before. Net effect: `agent-eval evaluate --judge-model gpt-4o ...` now WORKS (was previously broken — would construct `AnthropicJudge(model="gpt-4o")` which the SDK would reject).

2. **`_cmd_compare`** (currently `cli.py:194-231`) — same import swap + add the default-chain logic:

```python
# BEFORE
async def _cmd_compare(args: argparse.Namespace) -> None:
    from agent_evaluator.judge import AnthropicJudge
    ...
    models = [m.strip() for m in args.models.split(",")]
    judge = AnthropicJudge()
    ...

# AFTER
async def _cmd_compare(args: argparse.Namespace) -> None:
    from agent_evaluator.judge import make_judge
    from agent_evaluator.report import generate_comparison_report
    from agent_evaluator.runner import AgentRunner
    from scenarios.registry import load_all_scenarios, load_scenario

    models = [m.strip() for m in args.models.split(",")]
    judge_model = args.judge_model or models[0]  # NEW: D3 default chain
    judge = make_judge(judge_model)
    ...
```

3. **argparse `compare` subparser** (currently `cli.py:70-85`) — add the new `--judge-model` arg with explicit help text matching D3's caveat:

```python
compare_parser = sub.add_parser("compare", help="Compare multiple models")
compare_parser.add_argument(
    "--models",
    required=True,
    help="Comma-separated model IDs (e.g., claude-sonnet-4-20250514,gpt-4o)",
)
compare_parser.add_argument(
    "--judge-model",
    default=None,  # NEW: None → fall back to first --models entry
    help=(
        "Model used to judge trajectories. Defaults to the first model "
        "in --models. Note: defaulting to a model from --models means "
        "self-judging, which can introduce bias toward the judge's own "
        "family. For more rigor, specify an independent judge "
        "(e.g., a Claude model when comparing GPT models)."
    ),
)
compare_parser.add_argument(
    "--scenario", "-s",
    default="all",
    help="Scenario ID or 'all'",
)
compare_parser.add_argument(
    "--output", "-o",
    default="results/comparison.md",
    help="Output comparison report path",
)
```

**Acceptance:**
- `agent-eval compare --help` lists `--judge-model` with the self-judging caveat in the description.
- `agent-eval compare --models gpt-4o,gpt-4o-mini` (no `--judge-model`) defaults `judge_model = "gpt-4o"` → constructs `OpenAIJudge`. Does NOT require `ANTHROPIC_API_KEY` (closes F-C).
- `agent-eval compare --models claude-3-haiku,claude-sonnet-4` defaults to `claude-3-haiku` → `AnthropicJudge`.
- `agent-eval compare --models gpt-4o,gpt-4o-mini --judge-model claude-sonnet-4-20250514` overrides to AnthropicJudge — requires both keys (cross-vendor judging).
- `agent-eval evaluate --judge-model gpt-4o <traj>` now works (was broken pre-Phase-3).

**Anti-regression:**
- `agent-eval evaluate <traj>` (no `--judge-model`) defaults to `claude-sonnet-4-20250514` → AnthropicJudge — same shape and behavior as pre-Phase-3.
- All 35 existing tests pass (no test reaches into `_cmd_*` execution).
- `agent-eval list` returns 13 scenarios.
- `_cmd_run`, `_cmd_report` unchanged.

**Dependency:** T1 (calls `make_judge`).

**Atomic commit:** `feat(cli): route judges through make_judge + add --judge-model to compare (VEND-01, VEND-02)`

---

### T3 — `tests/test_cli.py` NEW: argparse parsing tests

**File:** `tests/test_cli.py` (NEW)

**Why a new file:** Phase 3 introduces argparse changes. The `cli.main` parser is built inside `main()` and not exposed; we extract it via a tiny refactor OR reach into `main` differently. Cleanest approach: factor the parser construction into a `_build_parser()` helper inside `cli.py`, then test that helper.

**Optional small refactor (part of T2 or T3):** extract the argparse building block into a private helper. **Decision:** include this minor refactor as part of T2 (one extra rename of the inline argparse to `_build_parser()`). T3 then imports it cleanly.

```python
# src/agent_evaluator/cli.py — extract the existing parser construction
def _build_parser() -> argparse.ArgumentParser:
    """Build the agent-eval CLI argparse parser. Public-ish so tests can
    parse without invoking main()."""
    parser = argparse.ArgumentParser(prog="agent-eval", ...)
    sub = parser.add_subparsers(dest="command", required=True)
    # ... existing subparser definitions
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    # ... rest of dispatch
```

**Tests:**

```python
"""Tests for cli argparse parsing (Phase 3 VEND-02)."""

import pytest

from agent_evaluator.cli import _build_parser


class TestCompareArgparse:
    def test_compare_has_judge_model_flag(self):
        parser = _build_parser()
        args = parser.parse_args(
            ["compare", "--models", "a,b", "--judge-model", "x"]
        )
        assert args.judge_model == "x"
        assert args.models == "a,b"

    def test_compare_judge_model_defaults_to_none(self):
        """The default-None enables the body fallback to args.judge_model or models[0]."""
        parser = _build_parser()
        args = parser.parse_args(["compare", "--models", "gpt-4o,gpt-4o-mini"])
        assert args.judge_model is None

    def test_evaluate_judge_model_default_unchanged(self):
        """Anti-regression: evaluate's --judge-model still defaults to claude-sonnet-4."""
        parser = _build_parser()
        args = parser.parse_args(["evaluate"])
        assert args.judge_model == "claude-sonnet-4-20250514"

    def test_evaluate_accepts_openai_judge(self):
        """Anti-regression: evaluate accepts --judge-model gpt-4o (T2 enables this)."""
        parser = _build_parser()
        args = parser.parse_args(["evaluate", "--judge-model", "gpt-4o"])
        assert args.judge_model == "gpt-4o"


class TestCompareUsageDocs:
    def test_compare_help_mentions_self_judging(self):
        """The --help text must include the self-judging caveat per D3."""
        parser = _build_parser()
        # Find compare subparser via _subparsers_action
        compare_parser = parser._subparsers._group_actions[0].choices["compare"]
        help_text = compare_parser.format_help()
        assert "--judge-model" in help_text
        # The caveat is in the help description for --judge-model:
        assert "self-judging" in help_text.lower() or "bias" in help_text.lower()


class TestBuildParserSmoke:
    """Defense for the _build_parser() extraction (plan-checker concern C1).
    Ensures the extracted helper produces a parser that handles the same
    invocations main() relies on — catches an extraction-mistake regression."""

    def test_main_parser_parses_list(self):
        parser = _build_parser()
        args = parser.parse_args(["list"])
        assert args.command == "list"

    def test_main_parser_parses_run(self):
        parser = _build_parser()
        args = parser.parse_args(["run", "--scenario", "weather_lookup"])
        assert args.command == "run"
        assert args.scenario == "weather_lookup"

    def test_main_parser_parses_evaluate(self):
        parser = _build_parser()
        args = parser.parse_args(["evaluate"])
        assert args.command == "evaluate"
```

**Acceptance:**
- All 5 tests pass.
- `_build_parser()` exists and is importable.
- The `--judge-model` flag is listed in the `compare` subparser's `--help` output.

**Anti-regression:**
- All 35 existing tests + 3 new T1 tests = 38 → with T3 = 43 tests pass.

**Dependency:** T2 (the parser additions and `_build_parser` extraction land in T2).

**Atomic commit:** `test(cli): add argparse tests for VEND-02 --judge-model flag`

---

### T4 — Hygiene cleanup (5 items)

**Files:** `pyproject.toml`, `.env.example`, `scenarios/book_flight.py`, `README.md`

**Changes:**

1. **`pyproject.toml`** — remove `"rich>=13.0",` from the `dependencies` list. Verify by grep that no in-tree code imports `rich` (already verified by JUDGMENT but re-confirm during execution).

2. **`.env.example`** — remove the `JUDGE_MODEL` and `AGENT_MODEL` lines. Update the comment to reflect actual key requirements:

```bash
# Existing .env.example (current — to be replaced):
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...           # Optional, for model comparison
JUDGE_MODEL=claude-sonnet-4-20250514
AGENT_MODEL=claude-sonnet-4-20250514

# New .env.example:
# At least one of these is required, depending on which models you use.
# The judge auto-routes to the matching vendor based on model name prefix.
# (gpt-, o1-, o3-, o4- ⇒ OpenAI; everything else ⇒ Anthropic.)
ANTHROPIC_API_KEY=sk-ant-...    # Required when using Claude models
OPENAI_API_KEY=sk-...           # Required when using GPT/o1/o3/o4 models
```

3. **`scenarios/book_flight.py:8`** — drop `ErrorInjection` from the import list (the unused F401):

```python
# BEFORE
from agent_evaluator.models import (
    Difficulty,
    ErrorInjection,
    MockResponse,
    Scenario,
    ToolDefinition,
)

# AFTER
from agent_evaluator.models import (
    Difficulty,
    MockResponse,
    Scenario,
    ToolDefinition,
)
```

4. **`README.md`** — update the API-key section (typically near the "Setup" or "Configuration" section). Specifics:
   - "**Required:** at least one of `ANTHROPIC_API_KEY` (for Claude models) or `OPENAI_API_KEY` (for GPT models). The judge auto-routes to whichever vendor's model you specify."
   - In the `compare` usage example, add `--judge-model` either as an example invocation or in the flag list:
     - `agent-eval compare --models gpt-4o,gpt-4o-mini` (judges with gpt-4o by default — self-judging caveat applies)
     - `agent-eval compare --models gpt-4o,gpt-4o-mini --judge-model claude-sonnet-4-20250514` (cross-vendor judging — requires both API keys)
   - Drop any mention of `JUDGE_MODEL` / `AGENT_MODEL` env vars (they no longer exist in `.env.example`).

5. **No change to `results/legacy/comparison-2026-04-08.md`** — already disclaimed in Phase 1 T6.

**Acceptance:**
- `grep -r "rich" pyproject.toml src/ scenarios/` returns zero matches outside `dependencies` historical references in commit messages.
- `grep -E "JUDGE_MODEL|AGENT_MODEL" .env.example` returns zero matches.
- `ruff check src/ scenarios/ tests/` returns zero findings (the F401 in book_flight is gone).
- README's API-key section accurately describes post-Phase-3 routing behavior.
- README's `compare` usage example includes `--judge-model`.

**Anti-regression:**
- `agent-eval list` still works (book_flight import change is purely removal of unused name).
- `python -c "import scenarios.book_flight"` succeeds.
- `pip install -e .` (or equivalent) succeeds without `rich` (no module imports it).

**Dependency:** none in code; logically follows T1+T2 since the README documents the new behavior.

**Atomic commit:** `chore: hygiene cleanup — remove rich dep, dead env vars, unused imports, update README (VEND-04, JUDGMENT F-J)`

---

### T5 — End-to-end verification

**No file changes.** Verification step.

**Verification checklist:**

1. `cd /Users/szeyan/Documents/Dev/agent-evaluator && pytest -v` — all tests pass: 35 from Phase 2 + 4 from T1 (`make_judge` dispatch + client-injection symmetry) + 5 from T3 argparse + 3 from T3 `_build_parser` smoke = **47 total**. (No tests removed; no semantic loss.)

2. `ruff check src/ scenarios/ tests/` — zero findings (the lone F401 in book_flight is now fixed by T4).

3. `agent-eval list` — returns 13 scenarios (anti-regression for EVAL-03).

4. `agent-eval compare --help` — lists `--judge-model` with self-judging caveat. Smoke-test by running and grepping the output:
   ```bash
   agent-eval compare --help | grep -E "judge-model|self-judging|bias"
   ```

5. **Synthetic E2E (no live API needed for closure):**
   - `make_judge("gpt-4o")` → `OpenAIJudge` with `model="gpt-4o"`. ✓
   - `make_judge("claude-sonnet-4-20250514")` → `AnthropicJudge`. ✓
   - `make_judge("mistral-large")` → `AnthropicJudge`. ✓
   - parser parses `["compare", "--models", "gpt-4o,gpt-4o-mini"]` → `args.judge_model is None` → body computes `models[0] == "gpt-4o"` → `make_judge("gpt-4o")` would construct `OpenAIJudge` (we don't actually run it; we just verify the parser shape).

6. **(Optional, user-required for live closure)** Live-API smoke if API keys are available:
   - With ONLY `OPENAI_API_KEY` set: `agent-eval compare --models gpt-4o,gpt-4o-mini --scenario weather_lookup` should succeed (no Anthropic key required). This is the canonical F-C closure verification — only meaningful with a real key.

7. **ROADMAP success-criteria mapping:**

| ROADMAP SC | Verified by |
|-----------|-------------|
| 1 (compare succeeds with only OPENAI_API_KEY) | T2 logic + T3 argparse default-None test + T5 step 5 (synthetic) + T5 step 6 (live, optional) |
| 2 (compare --help lists --judge-model) | T2 argparse change + T5 step 4 |
| 3 (no dead judge class — OpenAIJudge reached or removed) | T1 `make_judge` reaches OpenAIJudge for gpt prefixes; T1's `test_make_judge_routes_openai` is the proof of reach |
| 4 (README + .env.example claims match code) | T4 hygiene; T5 step 2 ruff confirms unused imports gone; manual diff of README claims against post-Phase-3 behavior |

**Atomic commit:** None — verification only.

---

## Risks and watch-items

1. **`_build_parser()` extraction is a small refactor.** It's part of T2. The risk: if the existing `main()` body has tightly coupled state (it doesn't — argparse construction is self-contained), the extraction could break things. Mitigation: T3 tests verify the extracted parser parses identical to before.

2. **`OpenAIJudge.__init__` calls `from openai import AsyncOpenAI` lazily — but the SDK constructor itself is eager.** When `make_judge` returns an `OpenAIJudge` instance with no injected client, `AsyncOpenAI()` is constructed and that raises `OpenAIError` immediately if `OPENAI_API_KEY` is unset. **AnthropicJudge does NOT have this asymmetry** — `AsyncAnthropic()` defers the auth check to first request. **Implications:**
   - Production callers (`cli.py::_cmd_*`) are unaffected — `cli.py:12` calls `load_dotenv()` so the user's `.env` is loaded before any judge construction.
   - Tests bypass `cli.py:load_dotenv()` (no `conftest.py` does it), so OpenAI-construction tests MUST inject a fake client (T1's design).
   - **Risk: low (failure is loud) BUT the asymmetry is non-obvious.** A future contributor adding an OpenAI integration test could rediscover this. Documented here + in `make_judge`'s docstring.

3. **`_is_openai_model` returns False for unknown prefixes** (e.g., `mistral-large`, `llama-3`). Per existing semantics, those route to AnthropicJudge — which then fails when calling Anthropic's API with an invalid model name. Phase 3 does NOT change this; it's a documented JUDGMENT F-E item deferred to v2. T1 test `test_make_judge_unknown_routes_anthropic` documents the behavior so it doesn't silently regress.

4. **`compare`'s `--scenario all` default + 13 scenarios + N models** — the synthetic E2E doesn't run the full loop (would consume real tokens). Phase 5 will add fixture-backed integration tests if needed.

5. **README content changes are subjective.** Plan defines the WHAT (which sections, which claims to update); plan-checker should verify the diff doesn't make NEW claims that aren't backed by code.

## Open questions deferred to executor

1. **Exact placement of `make_judge`** in `judge.py`. **Recommendation:** at the bottom of the file, after both class definitions. This is the natural reading order.
2. **Whether `_build_parser()` should be public (no underscore)** to allow tests to import without warning. **Recommendation:** keep underscored (`_build_parser`) — internal helper; tests can still import private names per Python convention.
3. ~~**Whether to add a `client` kwarg to `make_judge`**~~ **LOCKED post plan-check:** yes, `client: Any | None = None` is REQUIRED in T1's signature — not optional. The OpenAI SDK constructor is eager (raises `OpenAIError` without `OPENAI_API_KEY`); without injectable client, `test_make_judge_routes_openai` fails in unkeyed CI. Resolution propagated into T1 spec + 4th test added.

## Estimated work

- T1: 20 min (factory with client kwarg + 4 tests including OpenAI client injection)
- T2: 25 min (argparse + 2 call-site updates + `_build_parser` refactor)
- T3: 25 min (NEW test file + 5 argparse tests + 3 `_build_parser` smoke tests)
- T4: 30 min (4 file edits including README — most time on README rewrite)
- T5: 15 min (verification checklist)
- **Total: ~115 min** (was 105 pre plan-check; added 10 min for client-injection + smoke tests)

## Out of scope (reaffirmed)

- Single Judge class refactor — D1 chose two-classes + factory; v2 cleanup if duplication grows.
- `JUDGE_MODEL` env var implementation — D3 picked first-model-default; deferred.
- Comprehensive README rewrite — D4 strict-minimum; v2 doc milestone.
- Tighter routing for unknown model prefixes (F-E remediation) — Phase 5 or v2.
- Real (non-mocked) tool execution — anti-feature per PROJECT.md.
- DET / TEST requirements — their own phases.

---
*Plan written: 2026-05-06 from CONTEXT.md decisions D1–D4 + canonical refs. Same SDK-API caveat as Phases 1+2; manual planning equivalent quality. Verification by `gsd-plan-checker` next.*
