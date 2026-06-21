from agent_evaluator.providers import (
    DEFAULT_MODEL,
    is_openai_model,
    openai_token_limit_parameter,
)


def test_shared_default_is_current_anthropic_model():
    assert DEFAULT_MODEL == "claude-sonnet-4-6"


def test_provider_routing():
    assert is_openai_model("gpt-5.4-mini")
    assert is_openai_model("o4-mini")
    assert not is_openai_model("claude-sonnet-4-6")


def test_openai_token_limit_parameter():
    assert openai_token_limit_parameter("gpt-5.4-mini") == "max_completion_tokens"
    assert openai_token_limit_parameter("o3-mini") == "max_completion_tokens"
    assert openai_token_limit_parameter("gpt-4o") == "max_tokens"
