"""Shared fixture-replay clients for Phase 5 integration tests.

FixtureAnthropicClient and FixtureOpenAIClient are plain classes (not pytest
fixtures) that read hand-rolled JSON files and return SDK-shaped SimpleNamespace
responses. Import them in any test file via:

    from conftest import FixtureAnthropicClient, FixtureOpenAIClient

or simply reference them at module level since pytest auto-discovers conftest.py.
"""

import json
from pathlib import Path
from types import SimpleNamespace


class FixtureAnthropicClient:
    """Reads fixture JSON and returns SDK-shaped responses.

    Each call to messages.create returns the next fixture in queue;
    raises StopIteration when exhausted.

    Attribute paths returned match runner.py lines 166-212 and judge.py line 139:
      response.content[i].type / .text / .name / .input / .id
      response.usage.input_tokens / .output_tokens  (None if fixture has no usage key)
      response.stop_reason
    """

    def __init__(self, fixture_paths: list[Path]):
        self.fixtures = [json.loads(p.read_text()) for p in fixture_paths]
        self._idx = 0
        self.calls: list[dict] = []

    @property
    def messages(self):
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._idx >= len(self.fixtures):
            raise IndexError("FixtureAnthropicClient exhausted")
        data = self.fixtures[self._idx]
        self._idx += 1
        return SimpleNamespace(
            content=[SimpleNamespace(**block) for block in data["content"]],
            usage=SimpleNamespace(**data["usage"]) if "usage" in data else None,
            stop_reason=data.get("stop_reason"),
        )


class FixtureOpenAIClient:
    """Parallel implementation for OpenAI responses.

    Each call to chat.completions.create returns the next fixture in queue;
    raises StopIteration when exhausted.

    F-G regression guard: choice.message is a SimpleNamespace, NOT a raw dict,
    so that runner.py line 267 (messages.append(choice.message)) doesn't break
    the next turn's messages= parameter on the OpenAI SDK.

    Attribute paths returned match runner.py lines 254-297 and judge.py line 284:
      response.choices[0].message.tool_calls[i].id / .function.name / .function.arguments
      response.choices[0].message.content
      response.usage.prompt_tokens / .completion_tokens  (None if fixture has no usage key)
    """

    def __init__(self, fixture_paths: list[Path]):
        self.fixtures = [json.loads(p.read_text()) for p in fixture_paths]
        self._idx = 0
        self.calls: list[dict] = []

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._idx >= len(self.fixtures):
            raise IndexError("FixtureOpenAIClient exhausted")
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
