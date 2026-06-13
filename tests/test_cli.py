"""Tests for cli argparse parsing (Phase 3 VEND-02 + plan-checker C1).

Two test classes:
- TestCompareArgparse — verifies the new --judge-model flag on compare
- TestBuildParserSmoke — defends the _build_parser() extraction (T2 refactor)
"""

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
