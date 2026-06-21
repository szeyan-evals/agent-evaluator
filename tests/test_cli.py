"""Tests for CLI parsing and command-level failure contracts.

Two test classes:
- TestCompareArgparse — verifies the new --judge-model flag on compare
- TestBuildParserSmoke — defends the _build_parser() extraction (T2 refactor)
"""

import argparse
import asyncio
import json

import pytest

from agent_evaluator.cli import _build_parser, _cmd_dispatch, _cmd_run
from agent_evaluator.providers import DEFAULT_MODEL


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

    def test_evaluate_uses_shared_default_model(self):
        parser = _build_parser()
        args = parser.parse_args(["evaluate"])
        assert args.judge_model == DEFAULT_MODEL

    def test_evaluate_accepts_openai_judge(self):
        """Anti-regression: evaluate accepts --judge-model gpt-4o (T2 enables this
        via make_judge auto-routing; pre-Phase-3 this was silently broken)."""
        parser = _build_parser()
        args = parser.parse_args(["evaluate", "--judge-model", "gpt-4o"])
        assert args.judge_model == "gpt-4o"

    def test_compare_help_mentions_self_judging(self):
        """The --help text must include the self-judging caveat per D3."""
        parser = _build_parser()
        compare_parser = parser._subparsers._group_actions[0].choices["compare"]
        help_text = compare_parser.format_help()
        assert "--judge-model" in help_text
        assert "self-judging" in help_text.lower() or "bias" in help_text.lower()


class TestBuildParserSmoke:
    """Defends the _build_parser() extraction (plan-checker concern C1).
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

    def test_main_parser_parses_dispatch(self):
        parser = _build_parser()
        args = parser.parse_args([
            "dispatch", "--model", "gpt-5.4-mini", "--scenario", "l1_equipment"
        ])
        assert args.command == "dispatch"
        assert args.model == "gpt-5.4-mini"
        assert args.scenario == "l1_equipment"


def test_dispatch_command_writes_markdown_and_json(monkeypatch, tmp_path):
    import agent_evaluator.dispatch as dispatch

    monkeypatch.setattr(dispatch, "LLMDispatchAgent", lambda **_kwargs: dispatch.reference_solver)
    output = tmp_path / "dispatch.md"
    args = argparse.Namespace(
        model="test-model",
        judge_model=None,
        scenario="all",
        deterministic_reasoning=True,
        output=str(output),
    )

    _cmd_dispatch(args)

    assert output.is_file()
    payload = json.loads(output.with_suffix(".json").read_text())
    assert payload["model_id"] == "test-model"
    assert len(payload["results"]) == len(dispatch.all_scenarios())


def test_run_command_exits_nonzero_when_any_scenario_fails(monkeypatch, tmp_path):
    import agent_evaluator.runner as runner_module
    import scenarios.registry as registry

    class FailingRunner:
        def __init__(self, model):
            self.model = model

        async def run_scenario(self, scenario):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(runner_module, "AgentRunner", FailingRunner)
    monkeypatch.setattr(registry, "load_scenario", lambda _sid: object())
    args = argparse.Namespace(
        model=DEFAULT_MODEL,
        output_dir=str(tmp_path),
        scenario="broken",
    )

    with pytest.raises(SystemExit) as exc:
        asyncio.run(_cmd_run(args))
    assert exc.value.code == 1
