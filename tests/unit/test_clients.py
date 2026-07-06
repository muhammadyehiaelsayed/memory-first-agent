"""OpenAIChatLLM usage mapping (FR-M4-01/02) + build_openai_clients pinned params (FR-M4-03/04).

The real client construction and token-usage seam that the FakeLLM fakes bypass entirely: a
swapped prompt/completion mapping, a changed model/max_tokens/temperature, or a lost shared
transport would all ship green before M7. Driven against a stubbed SDK — no key, no network.
"""

import asyncio
from types import SimpleNamespace

from memagent.analytics.classify import QueryClassification
from memagent.config import Settings
from memagent.llm.clients import (
    ANALYTICS_MAX_TOKENS,
    CONVERSATION_MAX_TOKENS,
    OpenAIChatLLM,
    build_openai_clients,
)


def _run(coro):
    return asyncio.run(coro)


def _resp(content, prompt_tokens, completion_tokens, parsed=None):
    message = SimpleNamespace(content=content, parsed=parsed)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class FakeSDK:
    """Stand-in for AsyncOpenAI: exposes chat.completions.create()/parse()."""

    def __init__(self, resp):
        self._resp = resp

        async def create(**kw):
            return self._resp

        async def parse(**kw):
            return self._resp

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create, parse=parse))


def test_complete_maps_prompt_and_completion_tokens():
    llm = OpenAIChatLLM(FakeSDK(_resp("hello world", 11, 7)), "gpt-x", 100, temperature=0.0)
    result = _run(llm.complete("sys", [{"role": "user", "content": "hi"}]))
    assert result.text == "hello world"
    # prompt_tokens -> input_tokens, completion_tokens -> output_tokens (not the reverse).
    assert result.usage == {"model": "gpt-x", "input_tokens": 11, "output_tokens": 7}


def test_parse_returns_parsed_and_maps_usage():
    obj = QueryClassification(
        topic="redis", category="technology", question_type="factual", language="en", confidence=0.9
    )
    llm = OpenAIChatLLM(FakeSDK(_resp("", 5, 2, parsed=obj)), "gpt-y", 100, temperature=0.0)
    parsed, usage = _run(llm.parse("sys", "user", QueryClassification))
    assert parsed is obj
    assert usage == {"model": "gpt-y", "input_tokens": 5, "output_tokens": 2}


def test_usage_is_zero_when_sdk_returns_no_usage():
    resp = _resp("x", 0, 0)
    resp.usage = None
    llm = OpenAIChatLLM(FakeSDK(resp), "gpt-z", 100, temperature=0.0)
    assert _run(llm.complete("s", [])).usage == {
        "model": "gpt-z",
        "input_tokens": 0,
        "output_tokens": 0,
    }


def test_build_openai_clients_pins_params_and_shares_one_transport():
    conv, analytics, embedder = build_openai_clients(
        Settings(_env_file=None, openai_api_key="sk-test")
    )
    assert (conv._model, conv._max_tokens, conv._temperature) == (
        "gpt-5.4-mini",
        CONVERSATION_MAX_TOKENS,
        0.0,
    )
    assert (analytics._model, analytics._max_tokens, analytics._temperature) == (
        "gpt-5.4-nano",
        ANALYTICS_MAX_TOKENS,
        0.0,
    )
    assert (embedder._model, embedder.dim) == ("text-embedding-3-small", 1536)
    assert (CONVERSATION_MAX_TOKENS, ANALYTICS_MAX_TOKENS) == (2048, 256)
    assert conv._client is analytics._client is embedder._client  # ONE shared transport
    assert conv._client.max_retries == 0  # tenacity is the single retry owner
    assert conv._client.timeout == 45.0  # settings.llm_timeout_s
