"""CLI entry point for the agent trajectory evaluator."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_evaluator.providers import DEFAULT_MODEL

load_dotenv()


def _build_parser() -> argparse.ArgumentParser:
    """Build the agent-eval CLI argparse parser.

    Extracted so tests can construct and parse without invoking main().
    See .planning/phases/03-vendor-coupling-fix/03-PLAN.md T2.
    """
    parser = argparse.ArgumentParser(
        description="Agent Trajectory Evaluator — assess LLM agent tool-calling quality",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- run: execute a scenario against a live LLM ---
    run_parser = sub.add_parser("run", help="Run scenario(s) against a model")
    run_parser.add_argument(
        "--scenario", "-s",
        default="all",
        help="Scenario ID or 'all' (default: all)",
    )
    run_parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help="Model ID to test",
    )
    run_parser.add_argument(
        "--output-dir", "-o",
        default="results",
        help="Directory to save trajectory JSON files",
    )

    # --- evaluate: score a recorded trajectory ---
    eval_parser = sub.add_parser("evaluate", help="Evaluate recorded trajectories")
    eval_parser.add_argument(
        "--trajectory", "-t",
        help="Path to a trajectory JSON file",
    )
    eval_parser.add_argument(
        "--results-dir", "-d",
        default="results",
        help="Directory containing trajectory JSON files",
    )
    eval_parser.add_argument(
        "--judge-model",
        default=DEFAULT_MODEL,
        help="Model to use as judge (auto-routes to vendor by prefix)",
    )

    # --- report: generate a Markdown report ---
    report_parser = sub.add_parser("report", help="Generate evaluation report")
    report_parser.add_argument(
        "--results-dir", "-d",
        default="results",
        help="Directory with evaluation result JSON files",
    )
    report_parser.add_argument(
        "--output", "-o",
        default="results/report.md",
        help="Output Markdown file path",
    )

    # --- compare: run same scenarios on multiple models ---
    compare_parser = sub.add_parser("compare", help="Compare multiple models")
    compare_parser.add_argument(
        "--models",
        required=True,
        help=f"Comma-separated model IDs (e.g., {DEFAULT_MODEL},gpt-5.4-mini)",
    )
    compare_parser.add_argument(
        "--judge-model",
        default=None,
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

    # --- dispatch: run the synthetic dispatch benchmark end-to-end ---
    dispatch_parser = sub.add_parser(
        "dispatch",
        help="Run the synthetic freight-dispatch benchmark",
    )
    dispatch_parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help="Anthropic or OpenAI model to evaluate",
    )
    dispatch_parser.add_argument(
        "--judge-model",
        default=None,
        help="Model for L2 reasoning judgment (defaults to --model)",
    )
    dispatch_parser.add_argument(
        "--scenario", "-s",
        default="all",
        help="Dispatch scenario ID or 'all'",
    )
    dispatch_parser.add_argument(
        "--deterministic-reasoning",
        action="store_true",
        help="Use the offline scenario-aware reasoning check instead of an LLM judge",
    )
    dispatch_parser.add_argument(
        "--output", "-o",
        default="results/dispatch-report.md",
        help="Markdown report path; structured JSON is written beside it",
    )

    # --- list: show available scenarios ---
    sub.add_parser("list", help="List available scenarios")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "list":
        _cmd_list()
    elif args.command == "run":
        asyncio.run(_cmd_run(args))
    elif args.command == "evaluate":
        asyncio.run(_cmd_evaluate(args))
    elif args.command == "report":
        _cmd_report(args)
    elif args.command == "compare":
        asyncio.run(_cmd_compare(args))
    elif args.command == "dispatch":
        _cmd_dispatch(args)


def _cmd_list() -> None:
    from scenarios.registry import load_all_scenarios
    scenarios = load_all_scenarios()
    print(f"\nAvailable scenarios ({len(scenarios)}):\n")
    for sid, scenario in sorted(scenarios.items()):
        print(f"  {sid:<25} [{scenario.difficulty.value}]  {scenario.name}")
    print()


async def _cmd_run(args: argparse.Namespace) -> None:
    from agent_evaluator.runner import AgentRunner
    from scenarios.registry import load_all_scenarios, load_scenario

    runner = AgentRunner(model=args.model)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.scenario == "all":
        scenarios = load_all_scenarios()
    else:
        scenarios = {args.scenario: load_scenario(args.scenario)}

    failures: list[str] = []
    for sid, scenario in scenarios.items():
        print(f"Running scenario: {sid}...", end=" ", flush=True)
        try:
            trajectory = await runner.run_scenario(scenario)
            path = output_dir / f"trajectory_{sid}_{args.model.replace('/', '_')}.json"
            runner.save_trajectory(trajectory, path)
            print(f"done ({len(trajectory.steps)} steps) → {path}")
        except Exception as e:
            print(f"FAILED: {e}")
            failures.append(f"{sid}: {e}")
    if failures:
        print(f"{len(failures)} scenario(s) failed.", file=sys.stderr)
        raise SystemExit(1)


async def _cmd_evaluate(args: argparse.Namespace) -> None:
    from agent_evaluator.judge import make_judge
    from agent_evaluator.runner import AgentRunner
    from scenarios.registry import load_all_scenarios

    judge = make_judge(args.judge_model)
    scenarios = load_all_scenarios()
    results_dir = Path(args.results_dir)

    if args.trajectory:
        trajectory_files = [Path(args.trajectory)]
    else:
        trajectory_files = sorted(results_dir.glob("trajectory_*.json"))

    if not trajectory_files:
        print("No trajectory files found.")
        sys.exit(1)

    skipped = 0
    for tf in trajectory_files:
        trajectory = AgentRunner.load_trajectory(tf)
        scenario = scenarios.get(trajectory.scenario_id)
        if not scenario:
            print(f"Skipping {tf.name}: unknown scenario '{trajectory.scenario_id}'")
            skipped += 1
            continue

        print(f"Evaluating: {tf.name}...", end=" ", flush=True)
        result = await judge.evaluate_trajectory(trajectory, scenario)
        result_path = tf.with_name(tf.name.replace("trajectory_", "eval_"))
        result_path.write_text(result.model_dump_json(indent=2))
        print(f"overall={result.overall_score:.2f} → {result_path}")
    if skipped:
        print(f"{skipped} trajectory file(s) could not be evaluated.", file=sys.stderr)
        raise SystemExit(1)


def _cmd_report(args: argparse.Namespace) -> None:
    from agent_evaluator.models import EvaluationResult
    from agent_evaluator.report import generate_report

    results_dir = Path(args.results_dir)
    eval_files = sorted(results_dir.glob("eval_*.json"))

    if not eval_files:
        print("No evaluation result files found.")
        sys.exit(1)

    # Use from_json (not model_validate_json) so legacy/pre-TRUST eval files
    # emit a DeprecationWarning and get tagged with legacy=True. The report
    # will then surface them in a separate "Legacy evaluations excluded"
    # section instead of silently aggregating their (potentially silent-zero)
    # scores. See .planning/research/JUDGMENT.md F-A.
    results = [EvaluationResult.from_json(f.read_text()) for f in eval_files]

    report = generate_report(results)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report)
    print(f"Report generated: {output}")


async def _cmd_compare(args: argparse.Namespace) -> None:
    from agent_evaluator.judge import make_judge
    from agent_evaluator.report import generate_comparison_report
    from agent_evaluator.runner import AgentRunner
    from scenarios.registry import load_all_scenarios, load_scenario

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        print("At least one model is required.", file=sys.stderr)
        raise SystemExit(2)
    # Phase 3 D3: default judge to the first model in --models. The user
    # can override with --judge-model. Self-judging caveat is in --help.
    judge_model = args.judge_model or models[0]
    judge = make_judge(judge_model)

    if args.scenario == "all":
        scenarios = load_all_scenarios()
    else:
        scenarios = {args.scenario: load_scenario(args.scenario)}

    results_by_model: dict[str, list] = {}

    failures: list[str] = []
    for model in models:
        print(f"\n=== Model: {model} ===")
        runner = AgentRunner(model=model)
        results = []

        for sid, scenario in scenarios.items():
            print(f"  Running {sid}...", end=" ", flush=True)
            try:
                trajectory = await runner.run_scenario(scenario)
                result = await judge.evaluate_trajectory(trajectory, scenario)
                results.append(result)
                print(f"overall={result.overall_score:.2f}")
            except Exception as e:
                print(f"FAILED: {e}")
                failures.append(f"{model}/{sid}: {e}")

        results_by_model[model] = results

    report = generate_comparison_report(results_by_model)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report)
    print(f"\nComparison report: {output}")
    if failures:
        print(
            f"Comparison is partial: {len(failures)} model/scenario run(s) failed.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _cmd_dispatch(args: argparse.Namespace) -> None:
    from agent_evaluator.dispatch import (
        EvaluationReport,
        LLMDispatchAgent,
        LLMReasoningJudge,
        deterministic_reasoning_judge,
        evaluate_all,
        render_dispatch_report,
        scenario_by_id,
        score_scenario,
    )

    judge_model = None if args.deterministic_reasoning else (args.judge_model or args.model)
    judge = (
        deterministic_reasoning_judge
        if args.deterministic_reasoning
        else LLMReasoningJudge(model=judge_model)
    )
    agent = LLMDispatchAgent(model=args.model)

    if args.scenario == "all":
        report = evaluate_all(
            agent,
            judge,
            model_id=args.model,
            judge_model_id=judge_model or "deterministic",
        )
    else:
        try:
            scenario = scenario_by_id(args.scenario)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(2) from None
        report = EvaluationReport(
            results=[score_scenario(scenario, agent, judge)],
            model_id=args.model,
            judge_model_id=judge_model or "deterministic",
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dispatch_report(report))
    json_output = output.with_suffix(".json")
    json_output.write_text(report.model_dump_json(indent=2))
    signal, why = report.release_signal()
    print(f"Dispatch report: {output}")
    print(f"Structured results: {json_output}")
    print(f"Release signal: {signal} — {why}")


if __name__ == "__main__":
    main()
