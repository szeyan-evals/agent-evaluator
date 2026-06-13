---
phase: 05-test-coverage-and-ci
plan: "02"
subsystem: tests
tags: [integration-tests, runner, report, fixture-clients, f-g, f-h, max-steps, partial-rendering]
dependency_graph:
  requires: [05-01]
  provides: [test_runner_integration, test_report]
  affects: [tests/test_runner_integration.py, tests/test_report.py]
tech_stack:
  added: []
  patterns: [AgentRunner.__new__ client injection, FixtureAnthropicClient/OpenAI replay, bold-safe asterisk assertion]
key_files:
  created:
    - tests/test_runner_integration.py
    - tests/test_report.py
  modified: []
decisions:
  - "sys.path injection used to import FixtureAnthropicClient/FixtureOpenAIClient from conftest.py (pytest auto-discovers conftest but does not add tests/ to sys.path for direct imports)"
  - "Max-steps test feeds 9 fixtures (max_reasonable_steps=3, max_steps=8, loop exhausts for-range else-branch)"
  - "F-H marked strict=True xfail: fires AttributeError at runner.py line 166 when usage=None; deferred fix preserved as regression guard"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-13"
  tasks_completed: 2
  files_modified: 2
---

# Phase 5 Plan 02: Runner + Report Integration Tests Summary

**One-liner:** Fixture-backed runner loop integration tests with F-G/F-H/max-steps guards and report edge-case tests asserting exact rendered strings (err*, Partial evaluations footnote, legacy exclusion messages).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | runner.py integration tests (TEST-01) | 6c2372b | tests/test_runner_integration.py |
| 2 | report.py edge-case tests (TEST-03) | 2bc417e | tests/test_report.py |

## What Was Built

### Task 1 — `tests/test_runner_integration.py`

Five async tests covering both runner loops via `AgentRunner.__new__` client injection:

- **`test_run_anthropic_happy_path`**: feeds `agent_response_tool_use.json` + `agent_response_final.json`; asserts `AgentTrajectory` shape, 1 step, `final_answer is not None`, `total_input_tokens == 350` (150+200).
- **`test_run_anthropic_usage_none_raises`**: `@pytest.mark.xfail(strict=True)` — F-H regression guard; `agent_response_no_usage.json` causes `AttributeError` at runner.py line 166 (`response.usage.input_tokens`). Strict xfail means an incidental fix will be caught as `xpassed`.
- **`test_run_anthropic_max_steps_terminates`**: feeds 9 `agent_response_tool_use.json` fixtures (exceeds `max_steps = 3 + 5 = 8`); for-range else-branch sets `final_answer = None`; asserts `trajectory.final_answer is None`.
- **`test_run_openai_happy_path`**: analogous OpenAI path; `total_input_tokens == 350`, 1 step.
- **`test_run_openai_choice_message_round_trip`** (F-G guard): runner appends `choice.message` (a `SimpleNamespace`) directly to `messages=` at runner.py line 267; asserts second `create()` call's `messages` kwarg contains the `SimpleNamespace` object from the prior turn — proving the F-G round-trip survives without Pydantic rejection.

Results: 4 passed, 1 xfailed.

### Task 2 — `tests/test_report.py`

Five synchronous tests covering `generate_report` and `generate_comparison_report`:

- **`test_generate_report_empty`**: `generate_report([])` → `"No results to report."` (report.py line 77, verbatim).
- **`test_generate_report_all_ok`**: one all-ok result; asserts scenario id present, `"Partial evaluations" not in report`, clean `**0.80**` cell, bold-safe negative: `"0.80*" not in report.replace("**", "")`.
- **`test_generate_report_partial_row`**: one `DimensionScore(status="error", score=None, error_type="ValueError")` for `parameter_quality`; asserts `"Partial evaluations"` footnote heading, `"err*"` cell, `"ValueError"` in footnote.
- **`test_generate_report_all_legacy`**: `schema_version=1, legacy=True` result; asserts `"No non-legacy results to report."` (line 85) and `"Legacy evaluations excluded"` (line 62).
- **`test_generate_comparison_report_partial`**: two-model comparison, `m2` has `error_recovery` errored; asserts `"err*"` in comparison table and `"Partial evaluations"` footnote.

All five dimension names are the five real RUBRICS keys (`tool_selection`, `parameter_quality`, `efficiency`, `error_recovery`, `final_correctness`). No `final_answer_quality`.

## Verification

```
.venv/bin/python -m pytest -m 'not live' -q
95 passed, 1 xfailed in 0.60s

.venv/bin/ruff check src/ tests/
All checks passed!
```

Previous suite was 86 passing. New total: 95 passing + 1 xfailed (+9 new tests, no regressions).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Direct `from conftest import ...` fails at collection time**
- **Found during:** Task 1 test collection
- **Issue:** `from conftest import FixtureAnthropicClient, FixtureOpenAIClient` raised `ModuleNotFoundError: No module named 'conftest'`. pytest auto-discovers conftest.py but does NOT add `tests/` to `sys.path` before module-level imports run.
- **Fix:** Added `sys.path` injection at module top of `test_runner_integration.py` to insert `tests/` directory before the import. This is the standard pattern for conftest imports in projects where `tests/` is not a package.
- **Files modified:** `tests/test_runner_integration.py`

**2. [Rule 1 - Bug] Unused `pytest` import in `test_report.py`**
- **Found during:** Task 2 ruff check
- **Issue:** `import pytest` was included as boilerplate but not used in the sync tests.
- **Fix:** `ruff check --fix` removed the unused import automatically.
- **Files modified:** `tests/test_report.py`

## Known Stubs

None. Both test files exercise real code paths and assert on real rendered strings from `runner.py` and `report.py`.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Tests are hermetic (FixtureAnthropicClient/FixtureOpenAIClient; no API keys accessed).

## Self-Check: PASSED

- tests/test_runner_integration.py: EXISTS
- tests/test_report.py: EXISTS
- Commit 6c2372b: EXISTS (`git log --oneline | grep 6c2372b`)
- Commit 2bc417e: EXISTS (`git log --oneline | grep 2bc417e`)
- Full suite: 95 passed, 1 xfailed — no regressions
