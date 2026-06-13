# Phase 5: Test Coverage and CI — Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 9 new files + 1 modified
**Analogs found:** 9 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tests/conftest.py` (FixtureClient helpers) | utility/fixture | request-response | `tests/test_judge.py` `_FakeAnthropicClient` | role-match |
| `tests/fixtures/anthropic/*.json` | config/data | N/A (static) | SDK response shape from `runner.py` lines 159-176 | data-shape |
| `tests/fixtures/openai/*.json` | config/data | N/A (static) | SDK response shape from `runner.py` lines 247-270 | data-shape |
| `tests/test_runner_integration.py` | test | request-response | `tests/test_judge.py` async fake-client tests | role-match |
| `tests/test_judge_integration.py` | test | request-response | `tests/test_judge.py` `_FakeAnthropicClient` tests | exact |
| `tests/test_report.py` | test | transform | `tests/test_models.py` (sync unit tests) | role-match |
| `tests/test_live_smoke.py` | test | request-response | `tests/test_judge.py` `@pytest.mark.asyncio` tests | role-match |
| `.github/workflows/ci.yml` | config | N/A | none in repo (new) | no-analog |
| `pyproject.toml` (markers addition) | config | N/A | `pyproject.toml` `[tool.pytest.ini_options]` lines 32-33 | exact |

---

## Pattern Assignments

### `tests/conftest.py` — FixtureAnthropicClient + FixtureOpenAIClient

**Analog:** `tests/test_judge.py` — `_FakeAnthropicClient` (lines 72–84) and `_FakeOpenAIClient` (lines 138–142)

**Existing fake-client pattern to extend** (`tests/test_judge.py` lines 72–84):
```python
class _FakeAnthropicClient:
    """Records SDK calls to verify short-circuit means no API call."""

    def __init__(self):
        self.call_count = 0

    @property
    def messages(self):
        return self

    async def create(self, **kwargs):
        self.call_count += 1
        raise AssertionError("Short-circuit failed: SDK was called")
```

**Existing OpenAI stub** (`tests/test_judge.py` lines 138–142):
```python
class _FakeOpenAIClient:
    """Minimal stub for OpenAI SDK client. The factory just stores it;
    tests don't invoke anything on it."""
    pass
```

**FixtureAnthropicClient — copy this shape, wire to JSON files:**
```python
# tests/conftest.py
import json
from pathlib import Path
from types import SimpleNamespace
import pytest


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
        return SimpleNamespace(
            content=[SimpleNamespace(**block) for block in data["content"]],
            usage=SimpleNamespace(**data["usage"]) if "usage" in data else None,
            stop_reason=data.get("stop_reason"),
        )


class FixtureOpenAIClient:
    """Parallel implementation for OpenAI responses."""

    def __init__(self, fixture_paths: list[Path]):
        self.fixtures = [json.loads(p.read_text()) for p in fixture_paths]
        self._idx = 0
        self.calls = []

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._idx >= len(self.fixtures):
            raise StopIteration("FixtureOpenAIClient exhausted")
        data = self.fixtures[self._idx]
        self._idx += 1
        # Build SDK-shaped response: response.choices[0].message.tool_calls / .content
        # response.usage.prompt_tokens / .completion_tokens
        message = SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    id=tc["id"],
                    function=SimpleNamespace(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    ),
                )
                for tc in data["choices"][0]["message"].get("tool_calls", [])
            ] or None,
            content=data["choices"][0]["message"].get("content"),
        )
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(**data["usage"]) if "usage" in data else None
        return SimpleNamespace(choices=[choice], usage=usage)
```

**Key note on OpenAI F-G regression (runner.py line 267):**
The runner appends `choice.message` directly to `messages=` on the next turn:
```python
messages.append(choice.message)  # runner.py line 267
```
The fixture's `choice.message` must be a `SimpleNamespace` (not a raw dict), so that the round-trip doesn't break OpenAI's SDK Pydantic validation. The `FixtureOpenAIClient` above returns `SimpleNamespace` objects for this reason.

---

### `tests/fixtures/anthropic/*.json` — Anthropic SDK response shapes

**Derived from:** `src/agent_evaluator/runner.py` lines 159–213 and `src/agent_evaluator/judge.py` lines 124–132

**Exact attribute accesses in `_run_anthropic`** (runner.py lines 166–213):
```python
# Token counting:
total_input_tokens += response.usage.input_tokens   # line 166
total_output_tokens += response.usage.output_tokens  # line 167

# Content dispatch:
tool_use_blocks = [b for b in response.content if b.type == "tool_use"]  # line 169-171
text_blocks = [b for b in response.content if b.type == "text"]           # line 173-175
final_answer = text_blocks[0].text if text_blocks else None               # line 176

# Per tool_use block:
block.name   # tool name (line 183)
block.input  # tool parameters dict (line 184, 186)
block.id     # tool_use_id for tool_result (line 203)
block.type   # "tool_use" or "text" (lines 169, 173)

# Thought extraction:
block.type == "text" → block.text  # runner.py line 341
block.type == "tool_use" → break   # runner.py line 343

# Appended to messages as-is (SDK object):
messages.append({"role": "assistant", "content": response.content})  # line 212
```

**Exact attribute accesses in `_evaluate_dimension` LLM path** (judge.py lines 126–132):
```python
response = await self.client.messages.create(...)
return self._parse_score(response.content[0].text, dimension)  # line 132
# _parse_score strips ``` fences, then json.loads the text
```

**Required fixture JSON shapes:**

`tests/fixtures/anthropic/agent_response_tool_use.json` — a turn with tool calls:
```json
{
  "content": [
    {"type": "text", "text": "I'll look up the weather for you."},
    {"type": "tool_use", "id": "tu_01", "name": "get_weather", "input": {"city": "San Francisco"}}
  ],
  "usage": {"input_tokens": 150, "output_tokens": 42},
  "stop_reason": "tool_use"
}
```

`tests/fixtures/anthropic/agent_response_final.json` — final answer turn (no tool calls):
```json
{
  "content": [
    {"type": "text", "text": "San Francisco is warmest at 62°F."}
  ],
  "usage": {"input_tokens": 200, "output_tokens": 25},
  "stop_reason": "end_turn"
}
```

`tests/fixtures/anthropic/judge_response_ok.json` — judge LLM response with fenced JSON:
```json
{
  "content": [
    {"type": "text", "text": "```json\n{\"score\": 0.9, \"reasoning\": \"Good parameter quality.\", \"evidence\": [\"Used correct city parameter\"]}\n```"}
  ],
  "usage": {"input_tokens": 300, "output_tokens": 60},
  "stop_reason": "end_turn"
}
```

`tests/fixtures/anthropic/judge_response_malformed.json` — malformed JSON for retry test:
```json
{
  "content": [
    {"type": "text", "text": "```json\n{score: 0.9 BROKEN\n```"}
  ],
  "usage": {"input_tokens": 300, "output_tokens": 20},
  "stop_reason": "end_turn"
}
```

`tests/fixtures/anthropic/agent_response_no_usage.json` — F-H regression guard (usage=None path):
```json
{
  "content": [
    {"type": "text", "text": "Done."}
  ],
  "stop_reason": "end_turn"
}
```
Note: no `"usage"` key — `FixtureAnthropicClient` returns `usage=None`, which triggers the `response.usage.input_tokens` AttributeError guarded by F-H.

---

### `tests/fixtures/openai/*.json` — OpenAI SDK response shapes

**Derived from:** `src/agent_evaluator/runner.py` lines 247–298 and `src/agent_evaluator/judge.py` lines 260–270

**Exact attribute accesses in `_run_openai`** (runner.py lines 254–297):
```python
choice = response.choices[0]          # line 254
usage = response.usage                 # line 255
if usage:
    total_input_tokens += usage.prompt_tokens      # line 257
    total_output_tokens += usage.completion_tokens  # line 258

tool_calls = choice.message.tool_calls or []        # line 260
final_answer = choice.message.content               # line 263

messages.append(choice.message)  # F-G: appends SDK object directly (line 267)

for tc in tool_calls:
    args = json.loads(tc.function.arguments)   # line 270 — args is a JSON string
    tc.function.name                            # line 272
    tc.id                                       # line 294 — tool_call_id
```

**Exact attribute accesses in OpenAI judge path** (judge.py lines 261–269):
```python
response = await self.client.chat.completions.create(...)
text = response.choices[0].message.content   # line 269
```

`tests/fixtures/openai/agent_response_tool_use.json`:
```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "id": "call_01",
            "function": {
              "name": "get_weather",
              "arguments": "{\"city\": \"San Francisco\"}"
            }
          }
        ],
        "content": null
      }
    }
  ],
  "usage": {"prompt_tokens": 150, "completion_tokens": 42}
}
```

`tests/fixtures/openai/agent_response_final.json`:
```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [],
        "content": "San Francisco is warmest at 62°F."
      }
    }
  ],
  "usage": {"prompt_tokens": 200, "completion_tokens": 25}
}
```

---

### `tests/test_runner_integration.py` (test, request-response)

**Analog:** `tests/test_judge.py` — async tests with injected fake clients (lines 87–133)

**Imports pattern** (copy from `tests/test_judge.py` lines 1–15, adapt):
```python
import pytest
from types import SimpleNamespace
from pathlib import Path

from agent_evaluator.runner import AgentRunner
from agent_evaluator.models import AgentTrajectory, Scenario, ToolDefinition, MockResponse
```

**Fake-client injection pattern** (copy from `tests/test_judge.py` lines 91–92):
```python
fake = _FakeAnthropicClient()
judge = AnthropicJudge(client=fake, model="claude-test")
```
Adapt for runner: `AgentRunner.__init__` constructs the client internally, so tests must monkeypatch:
```python
runner = AgentRunner.__new__(AgentRunner)
runner.model = "claude-test"
runner._use_openai = False
runner._anthropic_client = FixtureAnthropicClient([Path("tests/fixtures/anthropic/agent_response_tool_use.json"), ...])
```

**Async test structure** (copy from `tests/test_judge.py` lines 87–102):
```python
@pytest.mark.asyncio
async def test_run_anthropic_happy_path():
    runner = AgentRunner.__new__(AgentRunner)
    runner.model = "claude-test"
    runner._use_openai = False
    runner._anthropic_client = FixtureAnthropicClient([
        Path("tests/fixtures/anthropic/agent_response_tool_use.json"),
        Path("tests/fixtures/anthropic/agent_response_final.json"),
    ])
    scenario = _weather_scenario()
    trajectory = await runner._run_anthropic(scenario)
    assert isinstance(trajectory, AgentTrajectory)
    assert len(trajectory.steps) == 1
    assert trajectory.final_answer is not None
    assert trajectory.total_input_tokens == 350  # 150 + 200
```

**F-H xfail pattern** (runner.py line 166 — `response.usage.input_tokens` raises if usage is None):
```python
@pytest.mark.xfail(strict=True, reason="F-H: usage=None raises AttributeError; fix deferred to post-v1")
@pytest.mark.asyncio
async def test_run_anthropic_usage_none_raises():
    runner = AgentRunner.__new__(AgentRunner)
    runner.model = "claude-test"
    runner._use_openai = False
    runner._anthropic_client = FixtureAnthropicClient([
        Path("tests/fixtures/anthropic/agent_response_no_usage.json"),
    ])
    scenario = _weather_scenario()
    await runner._run_anthropic(scenario)  # should raise AttributeError
```

**Max-steps termination pattern** — verify `max_steps = scenario.max_reasonable_steps + 5` (runner.py line 152):
```python
async def test_run_anthropic_max_steps_terminates():
    # Feed 8 tool_use fixtures (more than max_reasonable_steps+5=8 for a 3-step scenario)
    # Runner exhausts loop → final_answer = None
    ...
    assert trajectory.final_answer is None
```

---

### `tests/test_judge_integration.py` (test, request-response)

**Analog:** `tests/test_judge.py` — all async tests (lines 87–234) — this is the closest analog, exact match by role + data flow.

**Imports pattern** (lines 1–15 of `tests/test_judge.py`):
```python
import pytest

from agent_evaluator.judge import AnthropicJudge
from agent_evaluator.models import AgentTrajectory, Scenario, ToolDefinition
```

**LLM dispatch happy-path pattern** (extend `_FakeAnthropicClient` → use `FixtureAnthropicClient`):
```python
@pytest.mark.asyncio
async def test_evaluate_dimension_llm_path_parses_fenced_json():
    client = FixtureAnthropicClient([
        Path("tests/fixtures/anthropic/judge_response_ok.json")
    ])
    judge = AnthropicJudge(client=client, model="claude-test")
    result = await judge._evaluate_dimension(
        "parameter_quality",
        _empty_trajectory("weather_lookup"),
        _scenario_no_injection(),
    )
    assert result.status == "ok"
    assert result.judge_method == "llm"
    assert result.score == pytest.approx(0.9)
    assert client.calls[0]["model"] == "claude-test"
```

**Retry-on-JSONDecodeError pattern** (judge.py lines 124–142 — loop with `max_retries=2`):
```python
@pytest.mark.asyncio
async def test_evaluate_dimension_retries_on_malformed_json():
    # Feed: malformed, malformed, then ok — succeeds on 3rd attempt
    client = FixtureAnthropicClient([
        Path("tests/fixtures/anthropic/judge_response_malformed.json"),
        Path("tests/fixtures/anthropic/judge_response_malformed.json"),
        Path("tests/fixtures/anthropic/judge_response_ok.json"),
    ])
    judge = AnthropicJudge(client=client, model="claude-test", max_retries=2)
    result = await judge._evaluate_dimension("parameter_quality", ...)
    assert result.status == "ok"
    assert len(client.calls) == 3
```

**Retry exhaustion → ValueError → status="error" via gather** (judge.py lines 59–77):
```python
@pytest.mark.asyncio
async def test_evaluate_dimension_exhausts_retries_produces_error_status():
    # Feed 3 malformed → ValueError raised → gather catches as Exception
    client = FixtureAnthropicClient([
        Path("tests/fixtures/anthropic/judge_response_malformed.json"),
        Path("tests/fixtures/anthropic/judge_response_malformed.json"),
        Path("tests/fixtures/anthropic/judge_response_malformed.json"),
    ])
    judge = AnthropicJudge(client=client, model="claude-test", max_retries=2)
    # Call evaluate_trajectory so asyncio.gather wraps the ValueError
    # Use a scenario where parameter_quality is the only LLM dim that matters
    result = await judge.evaluate_trajectory(...)
    param_score = next(s for s in result.dimension_scores if s.dimension == "parameter_quality")
    assert param_score.status == "error"
    assert param_score.error_type == "ValueError"
```

**F-I fence-stripper edge cases** (`judge.py` `_parse_score` lines 145–158):
```python
# Standard fenced (closing fence present) — parses:
#   "```json\n{...}\n```"  → lines[1:-1] joined → valid JSON

# No closing fence — "```json\n{...}" → lines[1:-1] = ["{...}"] → still parses if only one line
# But "```json\n{\n  score: 0.9\n..." (multi-line, no closing) → lines[-1] is last data line,
# not empty, so join produces truncated/corrupt JSON → json.loads raises → retry fires
```

**asyncio.gather mixed results pattern** (judge.py lines 55–77 — exact code path for F-A):
```python
# 4 ok dims + 1 raising → result has 4 ok + 1 status="error"
# Pattern from judge.py lines 59-77:
for dim_name, result in zip(RUBRICS, dimension_scores):
    if isinstance(result, Exception):
        valid_scores.append(DimensionScore(
            dimension=dim_name, score=None, ..., status="error",
            error_type=type(result).__name__,
        ))
    else:
        valid_scores.append(result)
```

---

### `tests/test_report.py` (test, transform)

**Analog:** `tests/test_models.py` and `tests/test_rubrics.py` — synchronous unit tests with inline fixture construction.

**Imports pattern** (from `tests/test_models.py` style):
```python
import pytest
from agent_evaluator.models import DimensionScore, EvaluationResult
from agent_evaluator.report import generate_report, generate_comparison_report
```

**IMPORTANT — dimension names are load-bearing.** The five RUBRICS keys (confirmed from
`src/agent_evaluator/rubrics.py` line 61 onward) are EXACTLY:
`tool_selection`, `parameter_quality`, `efficiency`, `error_recovery`, `final_correctness`.
There is NO `final_answer_quality`. `DimensionScore.dimension` is a free-form `str`, so
Pydantic will NOT reject a wrong name — but `generate_report` iterates `RUBRICS.keys()`
(report.py line 94), so any score under an unknown dimension name is silently dropped from
the summary table, making the fixture malformed and the test meaningless. The executor MUST
use the five real names above.

**EvaluationResult factory for report tests** — construct inline per `models.py` schema:
```python
def _make_result(
    scenario_id="s1",
    model_id="m1",
    scores: list[DimensionScore] | None = None,
    overall_score: float = 0.8,
    schema_version: int = 3,
    legacy: bool = False,
) -> EvaluationResult:
    if scores is None:
        scores = [DimensionScore(dimension=d, score=0.8, reasoning="ok", status="ok")
                  for d in ["tool_selection", "parameter_quality", "efficiency",
                             "error_recovery", "final_correctness"]]
    return EvaluationResult(
        schema_version=schema_version,
        legacy=legacy,
        scenario_id=scenario_id,
        model_id=model_id,
        dimension_scores=scores,
        overall_score=overall_score,
        summary="test",
    )
```

**Empty results test** — `generate_report` lines 76–78:
```python
def test_generate_report_empty():
    report = generate_report([])
    assert "No results to report" in report
```

**All-ok test** — verify standard table shape.

NOTE on asterisk assertions: `generate_report` UNCONDITIONALLY renders Markdown bold markers
(`**Average**`, `**0.80**` in `_render_overall_cell` / the averages row — report.py lines 33,
139). Those `**` contain `*`, so `assert "*" not in report` is ALWAYS false and is the wrong
gate. The partial signal is specific: the `**Partial evaluations:**` footnote heading
(report.py line 45) and the `*` SUFFIX appended INSIDE a score cell (e.g. `0.80*` from
`_render_dim_cell` line 27 / the partial overall marker line 33). Assert on those specifics,
not on bare `"*"`.
```python
def test_generate_report_all_ok():
    result = _make_result()
    report = generate_report([result])
    assert "s1" in report
    assert "Partial evaluations" not in report  # no partial footnote section
    # No partial score-suffix: the overall cell for an all-ok row is **0.80** (no trailing *).
    assert "**0.80**" in report      # overall cell, clean (no asterisk suffix)
    # CAUTION: `assert "0.80*" not in report` is WRONG — "**0.80**" itself contains
    # "0.80*" as a substring (digits + first closing-bold asterisk). Strip bold
    # markers first so only a genuine partial suffix (e.g. dim cell `0.80*`,
    # partial overall `**0.80***`) can match:
    assert "0.80*" not in report.replace("**", "")  # no partial-marked score cell anywhere
```

**Mixed ok + partial** — `report.py` lines 36–56, `_render_dim_cell` lines 20–28:
```python
def test_generate_report_partial_row():
    error_score = DimensionScore(
        dimension="parameter_quality", score=None, reasoning="failed",
        status="error", error_type="ValueError",
    )
    scores = [DimensionScore(dimension=d, score=0.8, reasoning="ok", status="ok")
              for d in ["tool_selection", "efficiency", "error_recovery", "final_correctness"]]
    scores.append(error_score)
    result = _make_result(scores=scores)
    report = generate_report([result])
    assert "Partial evaluations" in report   # footnote heading present
    assert "err*" in report                  # errored param_quality cell (score=None → "err*")
    assert "ValueError" in report
```

**All-legacy results** — `report.py` lines 84–87:
```python
def test_generate_report_all_legacy():
    result = _make_result(schema_version=1, legacy=True)
    report = generate_report([result])
    assert "No non-legacy results to report" in report
    assert "Legacy evaluations excluded" in report
```

**Comparison with partial row** — `generate_comparison_report` lines 182–265:
```python
def test_generate_comparison_report_partial():
    ok_result = _make_result(scenario_id="s1", model_id="m1")
    partial_result = _make_result(scenario_id="s1", model_id="m2", scores=[error_score, ...])
    report = generate_comparison_report({"m1": [ok_result], "m2": [partial_result]})
    assert "err*" in report                  # errored cell (score=None → "err*")
    assert "Partial evaluations" in report
```

---

### `tests/test_live_smoke.py` (test, request-response)

**Analog:** `tests/test_judge.py` `@pytest.mark.asyncio` tests (lines 87–102)

**Marker + async pattern** — copy `@pytest.mark.asyncio` from test_judge.py, add `@pytest.mark.live`:
```python
import pytest
from agent_evaluator.judge import AnthropicJudge, OpenAIJudge, make_judge
from agent_evaluator.models import AgentTrajectory
from scenarios.registry import get_scenario  # or load_scenario — check registry API


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_anthropic_judge_short_circuit():
    """Live: error_recovery on no-injection returns status='na' without API call."""
    judge = AnthropicJudge()  # real client, uses ANTHROPIC_API_KEY
    ...
    assert result.status == "na"
    assert result.judge_method == "deterministic"
```

**Scenario loading pattern** — from `scenarios/weather_lookup.py` lines 15–57:
```python
# Registry pattern:
from scenarios.registry import register
@register("weather_lookup")
def build_scenario() -> Scenario: ...
# Load via: from scenarios import weather_lookup; scenario = weather_lookup.build_scenario()
# Or use the registry's get function if it exists
```

---

### `.github/workflows/ci.yml` (config)

No analog in repo. Use the verbatim template from CONTEXT.md D4 (lines 149–172):
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

---

### `pyproject.toml` — add `live` marker (modify)

**Analog:** existing `[tool.pytest.ini_options]` block (pyproject.toml lines 31–33):
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
```

**Target state** — add `markers` key (CONTEXT.md D3):
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
markers = [
    "live: requires live API keys; skipped by default. Run with `pytest -m live`.",
]
```

---

## Shared Patterns

### Async test decoration
**Source:** `tests/test_judge.py` lines 87, 105, 121, 185, 201, 219
**Apply to:** All async tests in `test_runner_integration.py`, `test_judge_integration.py`, `test_live_smoke.py`
```python
@pytest.mark.asyncio
async def test_...:
```
Note: `asyncio_mode = "auto"` in `pyproject.toml` means `@pytest.mark.asyncio` is technically optional, but all existing async tests include it explicitly — follow that convention.

### Inline scenario factory pattern
**Source:** `tests/test_judge.py` lines 18–61 (`_scenario_no_injection`, `_scenario_with_injection`, `_empty_trajectory`)
**Apply to:** `test_runner_integration.py`, `test_judge_integration.py`, `test_live_smoke.py`
```python
def _scenario_no_injection() -> Scenario:
    return Scenario(
        id="weather_test",
        name="Weather Test",
        ...
        error_injection=[],
    )

def _empty_trajectory(scenario_id: str) -> AgentTrajectory:
    return AgentTrajectory(scenario_id=scenario_id, model_id="claude-test", steps=[])
```
For runner integration tests, use actual scenarios from `scenarios/weather_lookup.py` (has `mock_responses`) rather than bare `_scenario_no_injection()`.

### Client injection via `__new__` (runner tests only)
**Source:** `AgentRunner.__init__` (`runner.py` lines 124–133) — constructs real SDK client eagerly; not injectable via constructor.
**Apply to:** `test_runner_integration.py`
```python
# Pattern: bypass __init__ to inject fixture client
runner = AgentRunner.__new__(AgentRunner)
runner.model = "claude-test"
runner._use_openai = False
runner._anthropic_client = FixtureAnthropicClient([...])
```
This mirrors the `_FakeOpenAIClient` injection pattern in test_judge.py lines 151–155 for `OpenAIJudge` (which also accepts `client=` in its constructor, unlike `AgentRunner`).

### Error status assertion pattern
**Source:** `tests/test_judge.py` lines 92–102
**Apply to:** All integration tests asserting dimension scores
```python
assert result.status == "na"
assert result.dimension == "error_recovery"
assert result.error_type is None
assert result.judge_method == "deterministic"
```

### Module-level helper functions (not classes)
**Source:** `tests/test_judge.py` lines 18–69 — helpers defined as module-level functions, not `@pytest.fixture`
**Apply to:** All new test files — use plain `def _make_...(...)` helpers for reusable test objects; reserve `@pytest.fixture` only if conftest-level sharing is needed.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.github/workflows/ci.yml` | config | N/A | No CI configuration exists in repo yet |

---

## SDK Response Shape Reference (critical for fixture authoring)

### Anthropic `messages.create` response — fields accessed by runner.py + judge.py

| Attribute path | Type | Used in |
|---|---|---|
| `response.content` | `list` of content blocks | runner.py:169, judge.py:132 |
| `response.content[i].type` | `str` — `"text"` or `"tool_use"` | runner.py:169,173 |
| `response.content[i].text` | `str` | runner.py:176, judge.py:132 |
| `response.content[i].name` | `str` | runner.py:183 (tool_use only) |
| `response.content[i].input` | `dict` | runner.py:184,186 (tool_use only) |
| `response.content[i].id` | `str` | runner.py:203 (tool_use only) |
| `response.usage.input_tokens` | `int` | runner.py:166 |
| `response.usage.output_tokens` | `int` | runner.py:167 |
| `response.stop_reason` | `str` | not directly accessed; safe to include |

### OpenAI `chat.completions.create` response — fields accessed by runner.py + judge.py

| Attribute path | Type | Used in |
|---|---|---|
| `response.choices[0]` | choice object | runner.py:254 |
| `response.choices[0].message` | message object | runner.py:260,263,267 |
| `response.choices[0].message.tool_calls` | `list` or `None` | runner.py:260 |
| `response.choices[0].message.tool_calls[i].id` | `str` | runner.py:294 |
| `response.choices[0].message.tool_calls[i].function.name` | `str` | runner.py:272 |
| `response.choices[0].message.tool_calls[i].function.arguments` | `str` (JSON) | runner.py:270 |
| `response.choices[0].message.content` | `str` or `None` | runner.py:263, judge.py:269 |
| `response.usage` | usage object or `None` | runner.py:255-258 |
| `response.usage.prompt_tokens` | `int` | runner.py:257 |
| `response.usage.completion_tokens` | `int` | runner.py:258 |

---

## Metadata

**Analog search scope:** `tests/`, `src/agent_evaluator/`, `scenarios/`
**Files scanned:** 10 source/test files + pyproject.toml
**Pattern extraction date:** 2026-06-11
