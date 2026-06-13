# Phase 5 Context — Test Coverage and CI

**Phase:** 05 — Test Coverage and CI
**Goal:** Lock in the Phase 1-4 fixes with integration tests on the load-bearing modules + a CI gate. After this phase, regressions to TRUST/DIM/VEND/DET fixes get caught automatically. Final phase of v1 milestone.
**Requirements:** TEST-01, TEST-02, TEST-03, TEST-04
**Status:** discussion complete; planning next

---

## Domain

The post-Phase-4 codebase has 69/69 tests covering models, rubrics, detectors, judge dispatch, CLI argparse, and synthetic E2E flows. The two longest modules (`runner.py` agentic loops, `judge.py` LLM dispatch path) and `report.py` end-to-end rendering are still uncovered at integration level. Phase 5 closes those gaps with hand-rolled fixtures + a standard CI gate.

This is the **closure phase** for v1: when Phase 5 lands, the System Judge can be re-run as `judge ship` to flip NO-GO → CONDITIONAL GO or GO.

## Canonical refs

- `.planning/research/JUDGMENT.md` — F-G, F-H, F-I (regression guards) + F-F (test coverage gap is the Phase 5 target)
- `.planning/REQUIREMENTS.md` — TEST-01..04
- `.planning/ROADMAP.md` — Phase 5 success criteria
- `.planning/codebase/ARCHITECTURE.md` — call paths to test
- All prior phase CONTEXT.md files (Phase 5 tests must exercise the fixes from each)

## Carried-forward (locked from prior phases)

- TRUST schema (Phase 1): tests must verify error path produces `status="error"`, not silent zero
- Phase 2 short-circuit: tests must verify `error_recovery` short-circuits to `status="na"` on no-injection
- `make_judge` factory (Phase 3): tests must verify dispatch + `_build_parser` extraction
- 3 deterministic detectors (Phase 4): tests must verify dispatch routes deterministic dims to DETECTORS, not SDK
- Schema_version v3, judge_method field, partial=any(error) — all locked

## Decisions

### D1 — Cassette / replay strategy: hand-rolled fixtures (taken as default)

**Not selected for discussion by user — locked recommended default:**

Use hand-rolled fixtures alongside the existing `_FakeAnthropicClient` / `_FakeOpenAIClient` / `_FakeClient` patterns from Phases 2-3.

- Recorded SDK responses live as JSON files in `tests/fixtures/anthropic/` and `tests/fixtures/openai/`.
- A `_FixtureClient` class reads the JSON for each call and returns it as a SimpleNamespace (or a small dataclass) matching the SDK response shape.
- No new dependency (`vcrpy` not added).
- Aligns with Phases 2-3 fake-client conventions.

**Why hand-rolled (not vcrpy):**
- vcrpy adds a runtime dependency for test infrastructure — out of scope hygiene given Phase 3 just removed `rich`.
- vcrpy records real HTTP traffic, which requires a live key during recording. Hand-rolled fixtures are author-written based on SDK docs/types — no key needed even for fixture creation.
- Phase 2/3 already have `_FakeClient` patterns that work; extending them is smaller delta.

### D2 — Coverage targets: standard (taken as default)

**Not selected for discussion by user — locked recommended default:**

Target ~12-15 new tests covering:

**runner.py integration (TEST-01):**
- `_run_anthropic` happy-path multi-turn loop (1 test)
- `_run_anthropic` with `usage` field present (regression guard for F-H — verify guarded vs unguarded behavior)
- `_run_anthropic` max-steps termination (1 test — verify the `+ 5` grace from `max_reasonable_steps`)
- `_run_openai` happy-path multi-turn loop (1 test)
- `_run_openai` regression guard for F-G (`choice.message` round-trip — verify the SDK Pydantic object pattern doesn't break the next turn's `messages=` parameter)

**judge.py integration (TEST-02):**
- LLM dispatch path: `_evaluate_dimension` calls SDK, parses fenced JSON response (1 test)
- Retry on `JSONDecodeError`: SDK returns malformed JSON twice, then valid → succeeds (1 test)
- Retry exhaustion: SDK returns malformed JSON 3 times → final ValueError → `status="error"` via gather (1 test — F-A regression guard)
- Fence-stripper edge cases (TEST-02 + F-I regression guard):
  - Standard fenced response with closing fence → parses correctly
  - Fenced without closing fence → parse fails → retry (verifies F-I doesn't silently corrupt)
- `asyncio.gather` mixed: 4 ok dims + 1 raising → result has 4 ok + 1 status="error" (1 test)

**report.py rendering (TEST-03):**
- Empty results dir → "No results to report" (1 test)
- Single scenario, all-ok → standard report shape (1 test)
- Mixed ok + partial → asterisks + footnote section (1 test)
- All-legacy results → "No non-legacy results to report" + legacy footnote (1 test)
- Comparison with one ok-row + one partial-row → asterisks on partial cells, footnote (1 test)

**Total target: ~15 tests** (11 integration + 4 report).

**Why standard, not minimum or comprehensive:**
- Minimum (smoke happy-paths only) wouldn't deliver F-G/F-H/F-I regression guards — defeats the "lock in" point of Phase 5.
- Comprehensive would expand to ~25+ tests with diminishing returns; calibration against human ground truth is deferred to v2.

### D3 — Live-API tests: marker-skipped opt-in

Add a `live` marker to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
markers = [
    "live: requires live API keys; skipped by default. Run with `pytest -m live`.",
]
```

Add `tests/test_live_smoke.py` with ~3 marker-skipped tests:

```python
@pytest.mark.live
@pytest.mark.asyncio
async def test_live_anthropic_judge_short_circuit():
    """Live verification of Phase 2 short-circuit: error_recovery on a
    no-injection scenario returns status='na' without consuming Anthropic
    tokens for that dim."""
    judge = AnthropicJudge()  # real client; uses ANTHROPIC_API_KEY
    scenario = load_scenario("weather_lookup")
    trajectory = AgentTrajectory(scenario_id=scenario.id, model_id="real",
                                  steps=[])  # empty trajectory acceptable
    result = await judge._evaluate_dimension("error_recovery", trajectory, scenario)
    assert result.status == "na"
    assert result.judge_method == "deterministic"


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_anthropic_judge_llm_dim():
    """Live verification of LLM dispatch path: parameter_quality returns a
    non-error DimensionScore from the real Anthropic API."""
    judge = AnthropicJudge()
    scenario = load_scenario("weather_lookup")
    trajectory = AgentTrajectory(...)
    result = await judge._evaluate_dimension("parameter_quality", trajectory, scenario)
    assert result.status == "ok"
    assert result.judge_method == "llm"
    assert 0.0 <= result.score <= 1.0


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_make_judge_routes_openai():
    """Live verification of Phase 3 F-C closure: make_judge('gpt-4o')
    constructs an OpenAIJudge that can actually call the OpenAI API."""
    judge = make_judge("gpt-4o")  # real client; uses OPENAI_API_KEY
    # Minimal smoke — just construct + parse a fixture
    assert isinstance(judge, OpenAIJudge)
```

CI runs `pytest -m 'not live'` so these are skipped by default. Local opt-in: `pytest -m live` (requires `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` in env).

**Why marker-skipped (not pure-mock-only):**
- The "user-required handoff" pattern from Phases 1-4 (always deferring live verification) finally has a structured opt-in. The user can run `pytest -m live` once at v1 closure to validate end-to-end against real APIs.
- CI stays hermetic — no API keys needed in CI environment.

### D4 — CI scope: standard (pytest + ruff)

`.github/workflows/ci.yml`:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Lint
        run: ruff check src/ scenarios/ tests/
      - name: Test
        run: pytest -m 'not live'
```

**Triggers:** push to `main` (catch direct commits) + every PR (catch incoming changes).

**Why standard (not minimal, not full):**
- Minimal (pytest only) misses ruff regressions until PR review.
- Full (matrix + coverage + cache) is overkill for a single-developer project. Coverage thresholds tend to discourage tests for hard-to-cover paths (runner LLM loops). Matrix doubles CI minutes for minimal benefit on a project pinned to Python 3.11.
- Standard catches the regressions we care about (test failures + lint drift) at ~30-second total CI runtime.

**Out of scope for D4:**
- Coverage reporting (deferred to v2 if metric-driven progress matters)
- Multi-version testing (project pins 3.11; v2 can add 3.12+ when it matters)
- Branch protection rules / required status checks (GitHub UI configuration; out of scope for Phase 5 code)

## Implementation surface (for planner)

### Files to create

- `tests/fixtures/anthropic/judge_response_ok.json` — recorded valid Anthropic response with fenced JSON content (D1)
- `tests/fixtures/anthropic/judge_response_malformed.json` — recorded malformed JSON for retry test
- `tests/fixtures/anthropic/agent_response_*.json` — agent loop fixtures (1-2 turns) for runner tests
- `tests/fixtures/openai/agent_response_*.json` — same for OpenAI runner
- `tests/test_runner_integration.py` (NEW) — runner.py integration tests
- `tests/test_judge_integration.py` (NEW) — judge.py integration tests (LLM path)
- `tests/test_report.py` (NEW) — report.py edge-case tests
- `tests/test_live_smoke.py` (NEW) — marker-skipped live tests
- `.github/workflows/ci.yml` (NEW) — CI workflow

### Files to modify

- `pyproject.toml` — add `live` marker under `[tool.pytest.ini_options].markers`
- `tests/test_judge.py` — possibly add a `_FixtureClient` helper class (or place it in a `tests/conftest.py` for shared use)

### Test infrastructure: `_FixtureClient` pattern

```python
# tests/_fixture_client.py (NEW shared helper)
import json
from pathlib import Path
from types import SimpleNamespace


class FixtureAnthropicClient:
    """Reads fixture JSON and returns SDK-shaped responses.

    Each call to messages.create returns the next fixture in queue;
    raises StopIteration when exhausted.
    """

    def __init__(self, fixture_paths: list[Path]):
        self.fixtures = [json.loads(p.read_text()) for p in fixture_paths]
        self._idx = 0
        self.calls = []

    @property
    def messages(self):
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._idx >= len(self.fixtures):
            raise StopIteration("FixtureAnthropicClient exhausted")
        data = self.fixtures[self._idx]
        self._idx += 1
        # Convert dict to SDK-shaped object via SimpleNamespace
        return SimpleNamespace(
            content=[SimpleNamespace(**block) for block in data["content"]],
            usage=SimpleNamespace(**data["usage"]) if "usage" in data else None,
            stop_reason=data.get("stop_reason"),
        )


class FixtureOpenAIClient:
    """Parallel implementation for OpenAI responses."""
    # similar pattern, different shape
```

### Anti-regression checks

- All 69 Phase 1+2+3+4 tests continue to pass.
- New tests don't break by introducing fragile internal-state assertions; verify via observable behavior (return values, status, judge_method).
- F-G regression guard: `_run_openai` test asserts the SDK Pydantic object round-trip works (or, if it doesn't in the user's pinned SDK version, the test fails loudly with a clear message).
- F-H regression guard: `_run_anthropic` test asserts behavior with `usage` present AND with `usage=None` (latter currently raises AttributeError per Risk #2 in Phase 1 — this test FAILS pre-fix and PASSES if a future fix lands; could be marked xfail today).
- F-I regression guard: judge fence-stripper test asserts behavior on standard-fenced + no-closing-fence inputs.

## Open in planning (executor decides, not user)

1. (D1) Whether `_FixtureClient` lives in `tests/_fixture_client.py`, `tests/conftest.py`, or `tests/fixtures/__init__.py`. **Recommendation:** `tests/conftest.py` — pytest auto-discovers it; importable from any test file without explicit import.
2. (D2) Whether the F-H regression guard for `_run_anthropic` (unguarded `usage`) should be xfail (documents the pending fix) or skip (since fix is out of scope for v1). **Recommendation:** xfail with a strict=True flag — surfaces if the bug is incidentally fixed by SDK changes.
3. (D3) Whether to also add a live test for `_cmd_compare` end-to-end. **Recommendation:** no — too expensive in tokens; the per-judge live tests cover the path.
4. (D4) Whether to add a status badge in README pointing to the CI workflow. **Recommendation:** yes (one line of Markdown), small win for trust signaling. Add to README hygiene during T4 if convenient.

## Code context (reusable assets)

- Phase 2 `_FakeAnthropicClient` (raises on call) — shape is right; `_FixtureClient` is its lookup-and-return cousin.
- Phase 3 `_FakeOpenAIClient` (no-op stub) — extend similarly to `FixtureOpenAIClient`.
- Phase 3 `_build_parser()` — Phase 5 `test_runner_integration.py` doesn't need it (runner doesn't go through argparse).
- All 13 scenarios from registry — Phase 5 integration tests can pick small ones (`weather_lookup`, `math_calculation`) for fixture brevity.

## Deferred ideas

- **Coverage reporting** (`pytest-cov`, threshold gates) — v2 ops milestone.
- **Multi-version test matrix** (3.11 + 3.12 + 3.13) — v2 when project pin loosens.
- **`vcrpy` integration** — v2 if hand-rolled fixtures become a maintenance burden.
- **Cassette refresh tooling** (a `make refresh-fixtures` that runs against live and saves) — v2.
- **Property-based testing** (hypothesis) for detector formulas — v2.
- **Mutation testing** (mutmut) for confidence in detector test thoroughness — v2.

## Next steps

1. `/gsd-plan-phase 5` — produce 05-PLAN.md.
2. Plan should be medium-sized (5-7 atomic tasks): fixture infrastructure, runner integration tests, judge integration tests, report tests, live tests + marker, CI workflow, verification.
3. Plan-checker pass.
4. Execute. Verify TEST-01..04 acceptance.
5. **v1 closure milestone:** after Phase 5 lands, re-run System Judge as `judge ship` to validate the milestone.

---
*Discussion complete: 2026-05-07. 2 areas selected (live tests, CI scope); 2 areas (cassette strategy, coverage targets) locked at recommended defaults. No cross-phase amendments.*
