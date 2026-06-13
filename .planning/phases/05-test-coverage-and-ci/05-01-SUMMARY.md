---
phase: "05-test-coverage-and-ci"
plan: "01"
subsystem: "test-infrastructure"
tags: ["fixtures", "conftest", "pytest-marker", "integration-test-infra"]

dependency_graph:
  requires: []
  provides:
    - "tests/conftest.py FixtureAnthropicClient + FixtureOpenAIClient"
    - "tests/fixtures/anthropic/*.json (5 files)"
    - "tests/fixtures/openai/*.json (2 files)"
    - "live pytest marker in pyproject.toml"
  affects:
    - "05-02: test_runner_integration.py (imports FixtureAnthropicClient, FixtureOpenAIClient)"
    - "05-03: test_judge_integration.py (imports FixtureAnthropicClient)"
    - "05-04: CI workflow (uses live marker)"

tech_stack:
  added: []
  patterns:
    - "SimpleNamespace fixture client (FixtureAnthropicClient / FixtureOpenAIClient)"
    - "pytest marker registration via pyproject.toml markers array"
    - "IndexError for async exhaustion (StopIteration -> RuntimeError via PEP 479)"

key_files:
  created:
    - "tests/conftest.py"
    - "tests/fixtures/anthropic/agent_response_tool_use.json"
    - "tests/fixtures/anthropic/agent_response_final.json"
    - "tests/fixtures/anthropic/agent_response_no_usage.json"
    - "tests/fixtures/anthropic/judge_response_ok.json"
    - "tests/fixtures/anthropic/judge_response_malformed.json"
    - "tests/fixtures/openai/agent_response_tool_use.json"
    - "tests/fixtures/openai/agent_response_final.json"
  modified:
    - "pyproject.toml"

decisions:
  - "IndexError used for client exhaustion instead of StopIteration: Python PEP 479 converts StopIteration raised inside async coroutines to RuntimeError at the asyncio boundary; IndexError propagates cleanly and signals the same out-of-fixtures condition"
  - "FixtureOpenAIClient.tool_calls is None (not []) when empty: matches runner.py line 260 which does `choice.message.tool_calls or []` — None and [] are both falsy"

metrics:
  duration: "~8 minutes"
  completed_date: "2026-06-13"
  tasks_completed: 3
  tasks_total: 3
  files_created: 8
  files_modified: 1
---

# Phase 05 Plan 01: Test Infrastructure (Fixture Clients + Markers) Summary

Shared test infrastructure for Phase 5: SimpleNamespace replay clients (`FixtureAnthropicClient`, `FixtureOpenAIClient`) in `tests/conftest.py`, seven hand-rolled JSON fixture files in `tests/fixtures/`, and the `live` pytest marker in `pyproject.toml`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Register live pytest marker | 0b25bcc | pyproject.toml |
| 2 | Author hand-rolled fixture JSON files | 21b96ec | 7 fixture JSON files |
| 3 | Build FixtureAnthropicClient + FixtureOpenAIClient | 953217f | tests/conftest.py |

## What Was Built

### Task 1 — live pytest marker

Added a `markers` array to `[tool.pytest.ini_options]` in `pyproject.toml` with the D3-locked description:

```toml
markers = [
    "live: requires live API keys; skipped by default. Run with `pytest -m live`.",
]
```

### Task 2 — Fixture JSON files

Seven hand-rolled JSON files encoding SDK response shapes:

- `anthropic/agent_response_tool_use.json` — tool-call turn: text + tool_use blocks, usage, stop_reason
- `anthropic/agent_response_final.json` — final answer turn: text block, usage, stop_reason  
- `anthropic/agent_response_no_usage.json` — F-H regression guard: no `usage` key → `FixtureAnthropicClient` returns `usage=None`
- `anthropic/judge_response_ok.json` — fenced JSON with score=0.9 for LLM path happy path
- `anthropic/judge_response_malformed.json` — `{score: 0.9 BROKEN` inside fence → `json.loads` raises
- `openai/agent_response_tool_use.json` — tool-call turn: `function.arguments` is a JSON string (not dict)
- `openai/agent_response_final.json` — final answer turn with empty tool_calls and string content

### Task 3 — conftest.py fixture clients

`FixtureAnthropicClient`:
- Constructor: `list[Path]` → eagerly loads all fixtures, `_idx=0`, `calls=[]`
- `messages` property returns `self`
- `async create(**kwargs)`: appends kwargs to calls, returns `SimpleNamespace(content=[...], usage=..., stop_reason=...)`
- `usage` is `SimpleNamespace(**data["usage"])` or `None` if key absent (F-H condition)
- Raises `IndexError` when exhausted

`FixtureOpenAIClient`:
- `chat` and `completions` properties return `self`
- `async create(**kwargs)`: builds `choice.message` as `SimpleNamespace` with `tool_calls` (list of `SimpleNamespace` or `None`) and `content`
- F-G regression guard: `choice.message` is `SimpleNamespace`, not raw dict — matches runner.py line 267 which appends it directly to `messages=`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] StopIteration replaced with IndexError for async exhaustion**
- **Found during:** Task 3 verification
- **Issue:** Python PEP 479 converts `StopIteration` raised inside `async def` coroutines to `RuntimeError` at the asyncio event-loop boundary. The plan specified `StopIteration` but `asyncio.run(...)` would surface `RuntimeError: coroutine raised StopIteration` instead.
- **Fix:** Changed both clients to raise `IndexError("... exhausted")` which propagates cleanly through asyncio and signals the same out-of-fixtures condition.
- **Files modified:** tests/conftest.py
- **Commit:** 953217f

## Verification Results

```
.venv/bin/python -m pytest -m 'not live' -q   → 86 passed
.venv/bin/ruff check src/ tests/              → All checks passed!
All 7 fixture files parse as valid JSON       → FIXTURES_OK 7
conftest importable with correct shapes       → CONFTEST_OK
```

## Known Stubs

None. All fixture clients return correct SDK-shaped data; no placeholder text or empty-value stubs.

## Threat Flags

None. No new network endpoints, auth paths, or trust-boundary changes introduced. Fixture clients are hermetic by construction and never access environment variables or SDK auth.

## Self-Check: PASSED

- tests/conftest.py: FOUND
- tests/fixtures/anthropic/agent_response_tool_use.json: FOUND
- tests/fixtures/anthropic/agent_response_final.json: FOUND
- tests/fixtures/anthropic/agent_response_no_usage.json: FOUND
- tests/fixtures/anthropic/judge_response_ok.json: FOUND
- tests/fixtures/anthropic/judge_response_malformed.json: FOUND
- tests/fixtures/openai/agent_response_tool_use.json: FOUND
- tests/fixtures/openai/agent_response_final.json: FOUND
- pyproject.toml markers: FOUND (grep -c '^markers' = 1)
- Commit 0b25bcc: FOUND
- Commit 21b96ec: FOUND
- Commit 953217f: FOUND
