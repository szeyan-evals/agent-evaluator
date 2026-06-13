# Architecture — agent-evaluator (brownfield)

Sourced from the System Judge Scanner stage (2026-05-04). Component boundaries, data flow, and call paths reflect the code as it stands at the start of the v1 remediation milestone.

## Component Map

```
                   ┌──────────────────┐
                   │  cli.py (main)   │   argparse + dotenv.load_dotenv()
                   └────────┬─────────┘
                            │
          ┌─────────────────┼──────────────────┬────────────────┐
          ▼                 ▼                  ▼                ▼
   ┌────────────┐    ┌────────────┐     ┌────────────┐   ┌──────────┐
   │  scenarios │    │ AgentRunner│     │AnthropicJ. │   │ report.py│
   │  registry  │    │ (runner.py)│     │ (judge.py) │   │          │
   └─────┬──────┘    └──────┬─────┘     └──────┬─────┘   └─────┬────┘
         │                  │                  │                │
         │ pkgutil          │ Anthropic OR     │ Anthropic SDK  │ glob eval_*.json
         │ iter_modules     │ OpenAI SDK       │ (always)       │ Pydantic load
         │ + @register      │ + MockToolExec.  │ asyncio.gather │ Markdown render
         │                  │                  │  × 5 dims      │
         ▼                  ▼                  ▼                │
   13 scenarios      AgentTrajectory     EvaluationResult ──────┘
   (scenarios/        (eval_*.json /     (eval_*.json)
    *.py with         trajectory_*.json)
    @register)
```

**Hub:** `src/agent_evaluator/models.py` — every other in-scope module imports from it. Pydantic schemas are the de-facto contracts for trajectory and eval JSON.

## Modules (current state)

| Module | LOC | Tested? | Purpose |
|---|---|---|---|
| `models.py` | ~150 | yes (round-trips) | Pydantic models: `Scenario`, `ToolDefinition`, `MockResponse`, `ErrorInjection`, `AgentTrajectory`, `DimensionScore`, `EvaluationResult`. **Hub.** |
| `cli.py` | ~210 | partial (manual smoke for `list` only) | argparse dispatch for `list / run / evaluate / report / compare`. |
| `runner.py` | 354 | partial (`MockToolExecutor` only — ~165 LOC of agent loops uncovered) | `AgentRunner` with vendor branching by model-name prefix. |
| `judge.py` | 256 | **none** | `AnthropicJudge` (live), `OpenAIJudge` (dead). 5-dimension parallel evaluation via `asyncio.gather`. |
| `rubrics.py` | ~250 | yes (weights + score arithmetic) | 5 rubric dimensions with Jinja templates and weights. |
| `report.py` | 143 | **none** | Markdown rendering for single-model and comparison reports. |
| `scenarios/registry.py` | ~50 | none | `pkgutil.iter_modules` + `@register` decorator. |
| `scenarios/*.py` | varies | none | 13 scenario builders. Only `code_generation.py` and `debug_code.py` use `error_injection`. |

## Critical Call Paths

### 1. Scenario discovery
```
cli.py::_cmd_list
  → scenarios.registry.load_all_scenarios()
    → pkgutil.iter_modules(scenarios.__path__)         [non-recursive]
    → importlib.import_module("scenarios.<name>")
    → triggers @register decorator                     [last-writer-wins on duplicate IDs]
    → returns dict[id, Scenario]
```
Verified live: returns 13 entries.

### 2. Live agent run (Anthropic path)
```
cli.py::_cmd_run
  → AgentRunner(model)                                  [_is_openai_model() branch]
    → _run_anthropic(scenario)
      → loop up to scenario.max_reasonable_steps + 5:
          anthropic.messages.create(...)
          for each tool_use block:
            MockToolExecutor.execute()                  [error_injection + mock_responses]
          assemble tool_result content
        stop when no tool_use blocks in response
      → AgentTrajectory persisted to trajectory_*.json
```
**Untested.** ~85 LOC of loop logic, message-shape construction, token accumulation, and `_extract_thought_anthropic` are unverified.

**Known fragility:** `runner.py:166` reads `response.usage.input_tokens` unguarded (asymmetric with the OpenAI guard at `runner.py:256-258`).

### 3. Live agent run (OpenAI path)
Parallel structure to (2). Uses `chat.completions.create` and `tc.function.name/arguments`.
- `runner.py:267` appends `choice.message` (an SDK `ChatCompletionMessage` Pydantic object) into a `messages: list[dict]` — type annotation says `dict`, runtime appends an SDK object. SDK-version-sensitive.
- **Untested.**

### 4. Trajectory evaluation
```
cli.py::_cmd_evaluate
  → AgentRunner.load_trajectory(json)
  → AnthropicJudge(model=args.judge_model).evaluate_trajectory(trajectory, scenario)
    → asyncio.gather(_evaluate_dimension × 5, return_exceptions=True)   [outer net]
    → for each result:
        if isinstance(result, Exception):
          DimensionScore(score=0.0, reasoning=f"Evaluation failed: {result}")    [SILENT-ZERO]
    → compute_overall_score(dims)                       [includes any score >= 0]
    → EvaluationResult persisted to eval_*.json
  
  _evaluate_dimension:
    → render Jinja prompt from RUBRICS[dim]
    → messages.create(...)
    → _parse_score(response):
        strip ``` fences via lines[1:-1]                 [drops last line unconditionally]
        json.loads()
    → retry up to max_retries=2 on (JSONDecodeError, KeyError, IndexError)   [inner net — narrower than outer]
```

**This is the silent-zero amplifier (System Judge F-A).** Every exception type outside the inner net's catch tuple flows into the outer net and becomes a structurally valid `DimensionScore(score=0.0)` — indistinguishable from a legitimate low score in `eval_*.json`.

### 5. Reporting
```
cli.py::_cmd_report
  → glob eval_*.json
  → EvaluationResult.model_validate_json
  → report.py::generate_report
    → for each result:
        per-row cells: score_map.get(dim, 0.0)          [renders 0.00 for missing dim]
        overall column: result.overall_score             [excludes missing dim correctly]
        average row: mean over present dimension_scores  [mixes silent-zeros with real zeros]
```
**Untested.** `results/comparison.md` (Apr 8, 3,305 bytes) is the only historical evidence the path runs. That artifact also empirically demonstrates the F-B Error Recovery constant defect.

## Data Flow

```
                                          ┌─────────────────────────┐
   user ─── CLI args ───►  cli.py ───────►│ trajectory_*.json       │
                            │              │ (AgentTrajectory)        │
                            │              └──────────┬──────────────┘
                            │                         │
                            │                         ▼
                            │              ┌─────────────────────────┐
                            └─── judge ───►│ eval_*.json             │
                                           │ (EvaluationResult)       │
                                           └──────────┬──────────────┘
                                                      │
                                                      ▼
                                           ┌─────────────────────────┐
                                           │ comparison.md / report   │
                                           │ (Markdown)               │
                                           └─────────────────────────┘
```

JSON files are the persistence layer. Schema changes in `models.py` ripple to:
- `runner.py` (writer of trajectory_*.json)
- `judge.py` (writer of eval_*.json)
- `report.py` (reader of eval_*.json)
- ALL existing on-disk eval/trajectory files

This is why Phase 1 (TRUST schema) is the dependency root: every other fix changes data flowing through the same Pydantic models.

## Build Order (for v1 remediation)

Per ROADMAP.md sequencing:

1. **Phase 1 (TRUST)** — change `models.py` first. Cascades to runner/judge/report/cli writers and readers.
2. **Phase 2 (DIM)** — relies on Phase 1's status field flowing through `compute_overall_score`.
3. **Phase 3 (VEND)** — independent of 1/2 in code; can be sequenced before, after, or in parallel.
4. **Phase 4 (DET)** — relies on Phase 1's `DimensionScore` shape supporting deterministic dims with the same status discriminator as judged dims.
5. **Phase 5 (TEST)** — after the surface stabilizes; tests reflect post-remediation behavior.

## Anti-Regression Surface

EVAL-01..07 from REQUIREMENTS.md must continue to work through every phase. Specifically:

- The 13 scenarios continue to load via `agent-eval list`.
- The 19 existing tests continue to pass (with schema migration where applicable).
- `agent-eval run --scenario <id> --model <name>` produces a trajectory_*.json that Pydantic can round-trip.
- `agent-eval evaluate <trajectory>` produces an eval_*.json (with the new schema fields after Phase 1).
- `agent-eval compare --models a,b` runs end-to-end (with the loosened key requirement after Phase 3).

## Out-of-Scope Architectural Changes

- No restructuring of `scenarios/` into subpackages (F-K is documented but not addressed in v1; flat-dir convention is preserved).
- No migration off Pydantic v2 — current forward-ref pattern relies on auto-rebuild.
- No replacement of `MockToolExecutor` with real tool execution.
- No change to the 5-dimension rubric framing — Phase 4 may collapse to 2 LLM-judged dims, but the rubric.py interface stays.
