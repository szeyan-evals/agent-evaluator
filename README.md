# Agent Trajectory Evaluator

[![CI](https://github.com/szeyan-evals/agent-evaluator/actions/workflows/ci.yml/badge.svg)](https://github.com/szeyan-evals/agent-evaluator/actions/workflows/ci.yml)

Evaluate tool-calling agents from observable behavior: tool selection,
parameter quality, API-turn efficiency, error recovery, and final correctness.
The project supports Anthropic and OpenAI models and includes both reusable
synthetic scenarios and a stateful freight-dispatch benchmark.

## Why this project

- Deterministic scoring is used where ground truth is available.
- LLM judgment is limited to dimensions that require semantic assessment.
- Failed and unavailable scores remain explicit instead of becoming zero.
- Cross-provider trajectories use the same schemas and reports.
- The dispatch benchmark tests hard constraints, tool faults, prompt injection,
  repeated-run stability, and cost-of-error.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create `.env` with the credentials required by the models you run:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

## Trajectory evaluation

```bash
# Show the 13 reusable scenarios
agent-eval list

# Run one scenario with the default Claude model
agent-eval run --scenario book_flight

# Run with OpenAI
agent-eval run --scenario book_flight --model gpt-5.4-mini

# Score trajectories and generate a report
agent-eval evaluate --judge-model claude-sonnet-4-6
agent-eval report
```

Compare models with an explicitly selected judge to avoid accidental
self-judging:

```bash
agent-eval compare \
  --models "claude-sonnet-4-6,gpt-5.4-mini" \
  --judge-model claude-sonnet-4-6
```

Results are written under `results/` by default. Commands return a non-zero
status when any requested run fails, so incomplete evaluations are visible in
CI and scripts.

## Dispatch benchmark

The dispatch benchmark uses a mutable synthetic world and permissive write
tools. An agent can make an illegal assignment; the evaluator detects the
violation from final state instead of silently preventing it.

```bash
# Anthropic agent and judge
agent-eval dispatch --model claude-sonnet-4-6

# OpenAI agent and an independent Claude reasoning judge
agent-eval dispatch \
  --model gpt-5.4-mini \
  --judge-model claude-sonnet-4-6

# Run one dispatch scenario
agent-eval dispatch --scenario l4_equipment_override_injection
```

The command writes a Markdown report and structured JSON. Use
`--deterministic-reasoning` for the hermetic scenario-aware L2 check; live
benchmark runs should use the default LLM reasoning judge.

## Scoring

| Dimension | Weight | Method |
|---|---:|---|
| Tool selection | 25% | Deterministic |
| Parameter quality | 20% | LLM judge |
| Efficiency | 20% | Deterministic, API-turn aware |
| Error recovery | 15% | LLM judge when faults exist |
| Final correctness | 20% | Deterministic |

Dispatch scoring is layer-specific: final-state correctness, reasoning quality,
tool reliability, injection resistance, pass^k stability, and business-risk
severity. A high-cost failure forces a mechanical `NO-GO` signal.

## Development

```bash
ruff check src scenarios tests
pytest
```

Live API smoke tests are excluded by default. Run them explicitly with:

```bash
pytest -m live
```

## Limitations

- LLM judges can be biased and should be validated against human labels.
- The included scenario sets are regression benchmarks, not broad claims of
  real-world model capability.
- Token costs are estimates using standard uncached rates; pricing is versioned
  in `agent_evaluator.pricing` and may require updates.
- Release signals are mechanical evidence, not deployment authorization.

## License

MIT
