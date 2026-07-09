"""Executable binding for features/llm_clients.feature (batch: llm_clients).

Drives the REAL AsyncOpenAI wrappers in src/memagent/llm/clients.py against an
inline stubbed SDK (the FakeSDK technique from tests/unit/test_clients.py) — no
key, no network. Steps are sync (pytest-bdd generates sync tests); coroutines are
run with asyncio.run(...). The retry scenario uses the production llm_retry policy
with WAIT_CAP_SCALE=0 so retries fire instantly through the real code path.
"""

import asyncio
from types import SimpleNamespace

import httpx
from openai import APITimeoutError
from pytest_bdd import given, parsers, scenarios, then, when

from memagent.analytics.classify import QueryClassification
from memagent.config import Settings
from memagent.interfaces import CompletionResult
from memagent.llm.clients import (
    ANALYTICS_MAX_TOKENS,
    CONVERSATION_MAX_TOKENS,
    OpenAIChatLLM,
    OpenAIEmbedder,
    build_openai_clients,
)
from memagent.utils.reliability import llm_retry

scenarios("features/llm_clients.feature")


# --------------------------------------------------------------------------- #
# Local fakes (mirror tests/unit/test_clients.py's FakeSDK)                    #
# --------------------------------------------------------------------------- #
def _chat_resp(content, prompt_tokens, completion_tokens, parsed=None):
    message = SimpleNamespace(content=content, parsed=parsed)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class FakeChatSDK:
    """Stand-in for AsyncOpenAI: exposes chat.completions.create()/parse()."""

    def __init__(self, resp):
        async def create(**kw):
            return resp

        async def parse(**kw):
            return resp

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create, parse=parse))


class FakeEmbSDK:
    """Stand-in for AsyncOpenAI: exposes embeddings.create() returning out-of-order data.

    ``fail_times`` retryable timeouts are raised before the successful response, so the
    retry seam can be observed by call count.
    """

    def __init__(self, data, fail_times=0):
        self._data = data
        self._fail_times = fail_times
        self.calls = 0
        req = httpx.Request("POST", "https://api.openai.com/v1/embeddings")

        async def create(**kw):
            self.calls += 1
            if self.calls <= self._fail_times:
                raise APITimeoutError(req)
            return SimpleNamespace(data=self._data)

        self.embeddings = SimpleNamespace(create=create)


# --------------------------------------------------------------------------- #
# Scenario: complete() text + usage                                           #
# --------------------------------------------------------------------------- #
@given("a conversation chat client backed by a stubbed OpenAI SDK", target_fixture="chat_ctx")
def _conv_ctx():
    return {"model": "gpt-x"}


@given(
    parsers.parse(
        'the SDK returns the reply "{text}" using {prompt:d} prompt and {completion:d} completion tokens'
    )
)
def _conv_resp(chat_ctx, text, prompt, completion):
    resp = _chat_resp(text, prompt, completion)
    chat_ctx["llm"] = OpenAIChatLLM(FakeChatSDK(resp), chat_ctx["model"], 100, temperature=0.0)
    chat_ctx["prompt"] = prompt
    chat_ctx["completion"] = completion


@when("the agent asks the client to complete a system-and-user exchange")
def _do_complete(chat_ctx):
    chat_ctx["result"] = asyncio.run(
        chat_ctx["llm"].complete("sys", [{"role": "user", "content": "hi"}])
    )


@then(parsers.parse('the completion text is "{text}"'))
def _check_text(chat_ctx, text):
    result = chat_ctx["result"]
    assert isinstance(result, CompletionResult)
    assert result.text == text


@then(
    parsers.re(
        r'the reported usage maps prompt tokens to input and completion tokens to output for model "(?P<model>[^"]+)"'
    )
)
def _check_usage_map(chat_ctx, model):
    assert chat_ctx["result"].usage == {
        "model": model,
        "input_tokens": chat_ctx["prompt"],
        "output_tokens": chat_ctx["completion"],
    }


# --------------------------------------------------------------------------- #
# Scenario: parse() schema instance + usage                                   #
# --------------------------------------------------------------------------- #
@given("an analytics chat client backed by a stubbed OpenAI SDK", target_fixture="parse_ctx")
def _analytics_ctx():
    return {"model": "gpt-5.4-nano"}


@given(
    parsers.parse(
        "the SDK returns a parsed QueryClassification object using {prompt:d} prompt and {completion:d} completion tokens"
    )
)
def _parse_resp(parse_ctx, prompt, completion):
    obj = QueryClassification(
        topic="redis",
        category="technology",
        question_type="factual",
        language="en",
        confidence=0.9,
    )
    resp = _chat_resp("", prompt, completion, parsed=obj)
    parse_ctx["obj"] = obj
    parse_ctx["llm"] = OpenAIChatLLM(FakeChatSDK(resp), parse_ctx["model"], 100, temperature=0.0)
    parse_ctx["prompt"] = prompt
    parse_ctx["completion"] = completion


@when("the agent asks the client to parse a query into the QueryClassification schema")
def _do_parse(parse_ctx):
    parsed, usage = asyncio.run(
        parse_ctx["llm"].parse("sys", "<query>x</query>", QueryClassification)
    )
    parse_ctx["parsed"] = parsed
    parse_ctx["usage"] = usage


@then("the first result is the parsed QueryClassification instance")
def _check_parsed(parse_ctx):
    assert parse_ctx["parsed"] is parse_ctx["obj"]
    assert isinstance(parse_ctx["parsed"], QueryClassification)


@then("the second result reports usage keyed by input_tokens, output_tokens and model")
def _check_parse_usage(parse_ctx):
    assert parse_ctx["usage"] == {
        "model": parse_ctx["model"],
        "input_tokens": parse_ctx["prompt"],
        "output_tokens": parse_ctx["completion"],
    }


# --------------------------------------------------------------------------- #
# Scenario: _usage zero when SDK returns no usage                             #
# --------------------------------------------------------------------------- #
@given(
    "a conversation chat client whose stubbed SDK response has no usage block",
    target_fixture="usage_ctx",
)
def _no_usage_ctx():
    resp = _chat_resp("x", 0, 0)
    resp.usage = None
    return {"llm": OpenAIChatLLM(FakeChatSDK(resp), "gpt-z", 100, temperature=0.0)}


@when("the client completes an exchange")
def _complete_no_usage(usage_ctx):
    usage_ctx["result"] = asyncio.run(usage_ctx["llm"].complete("s", []))


@then(
    parsers.re(
        r'the reported usage is zero input and zero output tokens for the configured model "(?P<model>[^"]+)"'
    )
)
def _check_zero_usage(usage_ctx, model):
    assert usage_ctx["result"].usage == {
        "model": model,
        "input_tokens": 0,
        "output_tokens": 0,
    }


# --------------------------------------------------------------------------- #
# Scenario: OpenAIChatLLM.__init__ pins params, leaves seams unwrapped        #
# --------------------------------------------------------------------------- #
@given(
    parsers.parse(
        'the pinned conversation configuration model "{model}", max_tokens {max_tokens:d}, temperature {temperature:d}'
    ),
    target_fixture="init_ctx",
)
def _pinned_cfg(model, max_tokens, temperature):
    return {"model": model, "max_tokens": max_tokens, "temperature": float(temperature)}


@when("a chat client is constructed without a retry policy")
def _construct_plain(init_ctx):
    init_ctx["llm"] = OpenAIChatLLM(
        FakeChatSDK(_chat_resp("", 0, 0)),
        init_ctx["model"],
        init_ctx["max_tokens"],
        temperature=init_ctx["temperature"],
    )


@then("the client exposes exactly those pinned settings")
def _check_pinned(init_ctx):
    llm = init_ctx["llm"]
    assert (llm._model, llm._max_tokens, llm._temperature) == (
        init_ctx["model"],
        init_ctx["max_tokens"],
        init_ctx["temperature"],
    )


@then("its complete and parse network seams remain the plain unwrapped methods")
def _check_unwrapped(init_ctx):
    llm = init_ctx["llm"]
    # When retrying is None, __init__ does NOT rebind the seams onto the instance,
    # so they resolve to the class methods (nothing shadowing them in __dict__).
    assert "_call" not in vars(llm)
    assert "_parse_call" not in vars(llm)
    assert llm._call.__func__ is OpenAIChatLLM._call
    assert llm._parse_call.__func__ is OpenAIChatLLM._parse_call


# --------------------------------------------------------------------------- #
# Scenario: embed() preserves index order                                     #
# --------------------------------------------------------------------------- #
@given("an embedder backed by a stubbed OpenAI SDK", target_fixture="emb_ctx")
def _emb_ctx():
    return {}


@given("the SDK returns two embeddings out of index order")
def _emb_data(emb_ctx):
    # Deliberately out of order: index 1 first, index 0 second.
    data = [
        SimpleNamespace(embedding=[0.1, 0.2], index=1),
        SimpleNamespace(embedding=[0.9, 0.8], index=0),
    ]
    emb_ctx["sdk"] = FakeEmbSDK(data)
    emb_ctx["embedder"] = OpenAIEmbedder(emb_ctx["sdk"], "text-embedding-3-small", 2)


@when("the agent embeds a batch of texts")
def _do_embed_batch(emb_ctx):
    emb_ctx["vectors"] = asyncio.run(emb_ctx["embedder"].embed(["alpha", "beta"]))


@then("the vectors come back ordered by their original index")
def _check_order(emb_ctx):
    # index 0's vector must lead, index 1's vector must follow.
    assert emb_ctx["vectors"] == [[0.9, 0.8], [0.1, 0.2]]


# --------------------------------------------------------------------------- #
# Scenario: OpenAIEmbedder.__init__ wraps the seam with a retry policy        #
# --------------------------------------------------------------------------- #
@given(
    "an embedder constructed with the production llm retry policy and zero-wait settings",
    target_fixture="retry_ctx",
)
def _retry_ctx():
    settings = Settings(
        _env_file=None, openai_api_key="sk-test", wait_cap_scale=0.0, llm_max_attempts=4
    )
    return {"retrying": llm_retry(settings)}


@given("its stubbed SDK raises a retryable timeout once before succeeding")
def _retry_sdk(retry_ctx):
    data = [SimpleNamespace(embedding=[0.5, 0.5, 0.5], index=0)]
    sdk = FakeEmbSDK(data, fail_times=1)
    retry_ctx["sdk"] = sdk
    retry_ctx["embedder"] = OpenAIEmbedder(
        sdk, "text-embedding-3-small", 1536, retrying=retry_ctx["retrying"]
    )


@when("the agent embeds a text")
def _do_embed_one(retry_ctx):
    retry_ctx["vectors"] = asyncio.run(retry_ctx["embedder"].embed(["hi"]))


@then("the embedding call is retried and ultimately returns the vector")
def _check_retried(retry_ctx):
    # One failure + one success => at least two calls through the wrapped seam.
    assert retry_ctx["sdk"].calls >= 2
    assert retry_ctx["vectors"] == [[0.5, 0.5, 0.5]]


@then("the embedder records the configured model and dimension")
def _check_emb_fields(retry_ctx):
    emb = retry_ctx["embedder"]
    assert emb._model == "text-embedding-3-small"
    assert emb.dim == 1536
    # retrying is not None => __init__ rebound the seam onto the instance.
    assert "_embed_call" in vars(emb)


# --------------------------------------------------------------------------- #
# Scenario: build_openai_clients pins params + shares one transport           #
# --------------------------------------------------------------------------- #
@given("default settings carrying an OpenAI API key", target_fixture="build_ctx")
def _build_ctx():
    return {"settings": Settings(_env_file=None, openai_api_key="sk-test")}


@when("the three OpenAI clients are built")
def _do_build(build_ctx):
    conv, analytics, embedder = build_openai_clients(build_ctx["settings"])
    build_ctx["conv"] = conv
    build_ctx["analytics"] = analytics
    build_ctx["embedder"] = embedder


@then('the conversation client uses model "gpt-5.4-mini", max_tokens 2048 and temperature 0')
def _check_conv(build_ctx):
    conv = build_ctx["conv"]
    assert (conv._model, conv._max_tokens, conv._temperature) == (
        "gpt-5.4-mini",
        CONVERSATION_MAX_TOKENS,
        0.0,
    )
    assert CONVERSATION_MAX_TOKENS == 2048


@then('the analytics client uses model "gpt-5.4-nano" and max_tokens 256')
def _check_analytics(build_ctx):
    analytics = build_ctx["analytics"]
    assert (analytics._model, analytics._max_tokens) == ("gpt-5.4-nano", ANALYTICS_MAX_TOKENS)
    assert ANALYTICS_MAX_TOKENS == 256


@then("all three clients share one AsyncOpenAI transport with max_retries 0 and timeout 45.0")
def _check_shared_transport(build_ctx):
    conv, analytics, embedder = build_ctx["conv"], build_ctx["analytics"], build_ctx["embedder"]
    assert conv._client is analytics._client is embedder._client
    assert conv._client.max_retries == 0
    assert conv._client.timeout == 45.0


# --------------------------------------------------------------------------- #
# Scenario Outline: base URL routing + key fail-fast                          #
# --------------------------------------------------------------------------- #
@given(
    # [^"]* (not parsers.parse) so an empty key and/or empty base URL cell still matches.
    parsers.re(r'an OpenAI API key "(?P<key>[^"]*)" and base URL "(?P<base>[^"]*)"'),
    target_fixture="url_ctx",
)
def _url_ctx(key, base):
    return {"settings": Settings(_env_file=None, openai_api_key=key, openai_base_url=base or None)}


@when("the OpenAI clients are built")
def _build_maybe_fail(url_ctx):
    try:
        conv, _analytics, _embedder = build_openai_clients(url_ctx["settings"])
        url_ctx["conv"] = conv
        url_ctx["exc"] = None
    except SystemExit as exc:
        url_ctx["conv"] = None
        url_ctx["exc"] = exc


@then(parsers.parse('the outcome is "{outcome}"'))
def _check_outcome(url_ctx, outcome):
    if outcome == "openai default host":
        assert url_ctx["exc"] is None
        assert str(url_ctx["conv"]._client.base_url).startswith("https://api.openai.com")
    elif outcome == "github models host":
        assert url_ctx["exc"] is None
        assert "models.github.ai" in str(url_ctx["conv"]._client.base_url)
    elif outcome == "readable systemexit":
        assert isinstance(url_ctx["exc"], SystemExit)
        assert "OPENAI_API_KEY" in str(url_ctx["exc"])
    else:  # pragma: no cover - guards against a mistyped Examples cell
        raise AssertionError(f"unexpected outcome: {outcome!r}")


# --------------------------------------------------------------------------- #
# Scenario: LangSmith wraps the shared transport only when FULLY opted in     #
# --------------------------------------------------------------------------- #
@given(
    "settings that fully opt in to LangSmith tracing, settings that half opt in "
    "and settings that do not",
    target_fixture="wrap_ctx",
)
def _wrap_ctx():
    return {
        "on": Settings(
            _env_file=None,
            openai_api_key="sk-test",
            langsmith_tracing=True,
            langsmith_api_key="ls-test",
        ),
        # the AND gate's documented boundary: flag set, key blank -> tracing stays off
        "half": Settings(
            _env_file=None,
            openai_api_key="sk-test",
            langsmith_tracing=True,
            langsmith_api_key="",
        ),
        "off": Settings(
            _env_file=None,
            openai_api_key="sk-test",
            langsmith_tracing=False,
            langsmith_api_key="",
        ),
    }


@when("the OpenAI clients are built for each configuration")
def _build_each_configuration(wrap_ctx, monkeypatch):
    wrapped: list = []

    def _recording_wrap(client):  # stands in for langsmith.wrappers.wrap_openai (no upload)
        wrapped.append(client)
        return client

    monkeypatch.setattr("langsmith.wrappers.wrap_openai", _recording_wrap)
    conv_on, _analytics, _embedder = build_openai_clients(wrap_ctx["on"])
    wrap_ctx["wrapped_on"] = list(wrapped)
    wrap_ctx["conv_on"] = conv_on
    for kind in ("half", "off"):
        wrapped.clear()
        build_openai_clients(wrap_ctx[kind])
        wrap_ctx[f"wrapped_{kind}"] = list(wrapped)


@then(
    "the fully-opted-in build passes the shared transport through the LangSmith wrapper "
    "exactly once"
)
def _wrapped_exactly_once(wrap_ctx):
    assert wrap_ctx["wrapped_on"] == [wrap_ctx["conv_on"]._client]


@then("neither the tracing-off build nor the keyless half-opt-in ever touches the wrapper")
def _wrapper_untouched(wrap_ctx):
    assert wrap_ctx["wrapped_off"] == []
    assert wrap_ctx["wrapped_half"] == []
