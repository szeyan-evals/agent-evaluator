"""Shared provider routing and model defaults.

Keep vendor detection in one place so the trajectory runner, judges, CLI, and
domain benchmarks cannot silently disagree about which SDK or token-limit
parameter a model requires.
"""

from __future__ import annotations

DEFAULT_MODEL = "claude-sonnet-4-6"
OPENAI_PREFIXES = ("gpt-", "o1-", "o3-", "o4-")


def is_openai_model(model: str) -> bool:
    """Return whether ``model`` should route to the OpenAI client."""
    return model.startswith(OPENAI_PREFIXES)


def openai_token_limit_parameter(model: str) -> str:
    """Return the Chat Completions output-token parameter for ``model``.

    OpenAI reasoning families, including GPT-5-class models, use
    ``max_completion_tokens``. Older chat models use ``max_tokens``.
    """
    if model.startswith(("o1", "o3", "o4", "gpt-5")):
        return "max_completion_tokens"
    return "max_tokens"
