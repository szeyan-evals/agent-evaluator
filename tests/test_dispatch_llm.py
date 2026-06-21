"""LLM dispatch agent + reasoning judge.

The loop mechanics and judge parsing are tested hermetically with a scripted
fake client (no API). One marker-skipped live test exercises the real path; it
is deselected by default (pyproject addopts `-m 'not live'`), so a normal run
spends no tokens.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest  # noqa: E402

from agent_evaluator.dispatch import (  # noqa: E402
    LLMDispatchAgent,
    LLMReasoningJudge,
    run_once,
    scenario_by_id,
)


# ── scripted fake Anthropic client (sync) ────────────────────────────────
def _text_block(t):
    return SimpleNamespace(type="text", text=t)


def _tool_block(name, inp, block_id="t1"):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=block_id)


class _ScriptedClient:
    """Returns a pre-scripted sequence of responses from messages.create."""

    def __init__(self, response_blocks):
        self._responses = list(response_blocks)
        self.create_calls = []

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        blocks = self._responses.pop(0)
        return SimpleNamespace(content=blocks, stop_reason=None, usage=None)


def _openai_tool_call(name, arguments, call_id="call-1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _openai_message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


class _ScriptedOpenAIClient:
    def __init__(self, messages):
        self._messages = list(messages)
        self.create_calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        message = self._messages.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_agent_loop_executes_tools_and_books_assignment():
    # list -> assign D2 -> final justification text.
    client = _ScriptedClient([
        [_tool_block("list_available_drivers", {})],
        [_tool_block("assign_driver_to_load", {"driver_id": "D2", "load_id": "L1"})],
        [_text_block("D2 has the reefer equipment this load requires; D1 does not.")],
    ])
    agent = LLMDispatchAgent(client=client, model="fake")
    rec = run_once(scenario_by_id("l1_equipment"), agent)

    assert rec.final_world.loads["L1"].assigned_driver_id == "D2"
    assert "reefer" in rec.rationale
    # The agent fed tool schemas + system prompt on each turn.
    assert client.create_calls[0]["tools"]
    assert "dispatch agent" in client.create_calls[0]["system"].lower()


def test_agent_handles_unknown_tool_and_bad_args():
    assert "error" in LLMDispatchAgent._invoke(object(), "no_such_tool", {})

    class _Tools:
        def get_driver(self, driver_id):
            return {"id": driver_id}

    # wrong kwarg -> TypeError -> error dict, not a crash
    assert "error" in LLMDispatchAgent._invoke(_Tools(), "get_driver", {"wrong": "x"})
    assert LLMDispatchAgent._invoke(_Tools(), "get_driver", {"driver_id": "D1"}) == {"id": "D1"}


def test_agent_stops_when_no_tool_calls():
    client = _ScriptedClient([[_text_block("No legal driver; I will not assign anyone.")]])
    agent = LLMDispatchAgent(client=client, model="fake")
    rec = run_once(scenario_by_id("l4_no_legal_option_injection"), agent)
    assert rec.final_world.loads["L1"].status == "unassigned"
    assert "not assign" in rec.rationale.lower()


def test_openai_agent_loop_executes_tools_and_uses_reasoning_token_parameter():
    client = _ScriptedOpenAIClient([
        _openai_message(tool_calls=[_openai_tool_call("list_available_drivers", "{}")]),
        _openai_message(tool_calls=[
            _openai_tool_call(
                "assign_driver_to_load",
                '{"driver_id":"D2","load_id":"L1"}',
                "call-2",
            )
        ]),
        _openai_message(content="D2 has the required reefer equipment."),
    ])
    agent = LLMDispatchAgent(client=client, model="gpt-5.4-mini")
    rec = run_once(scenario_by_id("l1_equipment"), agent)

    assert rec.final_world.loads["L1"].assigned_driver_id == "D2"
    assert "reefer" in rec.rationale
    assert client.create_calls[0]["max_completion_tokens"] == 1024
    assert client.create_calls[0]["tools"][0]["type"] == "function"


def test_openai_agent_returns_invalid_argument_error_to_model():
    function = SimpleNamespace(name="get_driver", arguments="not-json")
    output = LLMDispatchAgent._invoke_openai_call(object(), function)
    assert "invalid arguments" in output["error"]


# ── reasoning judge ──────────────────────────────────────────────────────
def _judge_client(reply_text):
    class _C:
        @property
        def messages(self):
            return self

        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=reply_text)])

    return _C()


def test_judge_parses_fenced_pass_verdict():
    judge = LLMReasoningJudge(
        client=_judge_client('```json\n{"pass": true, "reason": "cites equipment match"}\n```'),
        model="fake",
    )
    ok, why = judge(scenario_by_id("l1_equipment"), "D2 has reefer equipment")
    assert ok is True and "equipment" in why


def test_judge_handles_unparseable_reply():
    judge = LLMReasoningJudge(client=_judge_client("sorry, no JSON here"), model="fake")
    ok, why = judge(scenario_by_id("l1_equipment"), "whatever")
    assert ok is False and "unparseable" in why


def test_openai_reasoning_judge_parses_verdict():
    client = _ScriptedOpenAIClient([
        _openai_message(content='{"pass": true, "reason": "correct tiebreak"}')
    ])
    judge = LLMReasoningJudge(client=client, model="gpt-5.4-mini")
    ok, why = judge(scenario_by_id("l2_tier_tiebreak"), "D2 wins the tier tiebreak")
    assert ok is True
    assert "tiebreak" in why
    assert client.create_calls[0]["response_format"] == {"type": "json_object"}


# ── live smoke (opt-in; deselected by default) ───────────────────────────
@pytest.mark.live
def test_live_llm_dispatch_agent_smoke():
    """Real model picks the reefer-equipped driver for the equipment scenario."""
    rec = run_once(scenario_by_id("l1_equipment"), LLMDispatchAgent())
    assert rec.rationale, "agent should produce a justification"
    assert rec.final_world.loads["L1"].assigned_driver_id == "D2"
