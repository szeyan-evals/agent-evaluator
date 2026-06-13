# Agent Trajectory Evaluator

<!-- CI badge — replace OWNER with your GitHub org/user after pushing to GitHub -->
[![CI](https://github.com/<OWNER>/agent-evaluator/actions/workflows/ci.yml/badge.svg)](https://github.com/<OWNER>/agent-evaluator/actions/workflows/ci.yml)

Evaluate LLM tool-calling agents by running test scenarios, recording trajectories, and scoring them with an LLM-as-judge.

## Setup

```bash
pip install -e ".[dev]"
```

Create a `.env` file. **At least one** of these is required, depending on which models you use:

```
ANTHROPIC_API_KEY=sk-ant-...    # Required when using Claude models
OPENAI_API_KEY=sk-...           # Required when using GPT/o1/o3/o4 models
```

The judge auto-routes to the matching vendor based on model-name prefix:
`gpt-`, `o1-`, `o3-`, `o4-` route to OpenAI; everything else routes to Anthropic. Cross-vendor judging (e.g., comparing GPT models with a Claude judge) requires both keys.

## Commands

### List available scenarios

```bash
agent-eval list
```

Shows all 13 test scenarios with difficulty levels.

### Run scenarios

```bash
# Run all scenarios against default model (claude-sonnet-4-20250514)
agent-eval run

# Run a specific scenario
agent-eval run -s book_flight

# Run with a different model
agent-eval run -m gpt-4o

# Save results to custom directory
agent-eval run -o my_results
```

| Flag | Default | Description |
|------|---------|-------------|
| `-s, --scenario` | `all` | Scenario ID or `all` |
| `-m, --model` | `claude-sonnet-4-20250514` | Model ID to test |
| `-o, --output-dir` | `results` | Directory for trajectory JSON files |

### Evaluate trajectories

```bash
# Evaluate all trajectories in results/
agent-eval evaluate

# Evaluate a single trajectory file
agent-eval evaluate -t results/trajectory_book_flight_claude-sonnet-4-20250514.json

# Use a different judge model
agent-eval evaluate --judge-model gpt-4o
```

| Flag | Default | Description |
|------|---------|-------------|
| `-t, --trajectory` | — | Path to a specific trajectory JSON |
| `-d, --results-dir` | `results` | Directory containing trajectory files |
| `--judge-model` | `claude-sonnet-4-20250514` | Model to use as judge |

### Generate report

```bash
# Generate markdown report from evaluation results
agent-eval report

# Custom output path
agent-eval report -o my_results/report.md
```

| Flag | Default | Description |
|------|---------|-------------|
| `-d, --results-dir` | `results` | Directory with eval result JSON files |
| `-o, --output` | `results/report.md` | Output markdown file path |

### Compare models

```bash
# Compare two GPT models — only OPENAI_API_KEY required (judge defaults to gpt-4o)
agent-eval compare --models "gpt-4o,gpt-4o-mini"

# Cross-vendor comparison — both API keys required
agent-eval compare --models "claude-sonnet-4-20250514,gpt-4o"

# Use a Claude judge for a GPT-vs-GPT comparison (more rigor — avoids self-judging)
agent-eval compare --models "gpt-4o,gpt-4o-mini" --judge-model claude-sonnet-4-20250514

# Compare on a single scenario
agent-eval compare --models "claude-sonnet-4-20250514,gpt-4o" -s book_flight
```

| Flag | Default | Description |
|------|---------|-------------|
| `--models` | *(required)* | Comma-separated model IDs |
| `--judge-model` | first model in `--models` | Model used to judge trajectories. Default = self-judging by the first compared model — explicit flag recommended for cross-vendor rigor. |
| `-s, --scenario` | `all` | Scenario ID or `all` |
| `-o, --output` | `results/comparison.md` | Output comparison report path |

## Typical workflow

```bash
agent-eval run -m claude-sonnet-4-20250514    # 1. Run scenarios
agent-eval evaluate                            # 2. Score trajectories
agent-eval report                              # 3. Generate report
```

Or do it all at once for multiple models:

```bash
agent-eval compare --models "claude-sonnet-4-20250514,gpt-4o"
```

## Scoring dimensions

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Tool Selection | 25% | Correct tool chosen at each step |
| Parameter Quality | 20% | Well-formed, complete tool inputs |
| Efficiency | 20% | Task solved in reasonable steps |
| Error Recovery | 15% | Adapted after tool failures |
| Final Correctness | 20% | Final answer matches expected output |