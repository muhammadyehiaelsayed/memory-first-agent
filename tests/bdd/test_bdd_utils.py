"""Executable bindings for the `utils` batch feature files.

Covers src/memagent/utils/{reliability,errors,timing}.py. Every step exercises the REAL
function under test:
- reliability: the tenacity policy factories run through their production code path with
  WAIT_CAP_SCALE=0 (instant retries, never a monkeypatched sleep); transport errors are
  built with httpx/openai and asserted to translate into the typed dependency errors.
- errors: redis_down_in_chain walks a hand-built __cause__ chain.
- timing: timed() wraps genuine async nodes and the merged latency_ms is asserted.

Keyless and network-free: no Redis, no API keys, no httpx transport is opened (the retry
predicates and decorators are fed already-constructed exception objects).
"""

import asyncio
import time

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pytest_bdd import given, scenarios, then, when
from redis import exceptions as redis_exceptions

from memagent.config import Settings
from memagent.utils.errors import (
    LLMUnavailableError,
    PageFetchError,
    SearchUnavailableError,
    redis_down_in_chain,
)
from memagent.utils.reliability import (
    _is_retryable_fetch,
    _is_retryable_llm,
    _is_retryable_tavily,
    _max_wait,
    _status,
    fetch_retry,
    llm_retry,
    summary_retry,
    tavily_retry,
)
from memagent.utils.timing import timed

scenarios("features/utils_reliability.feature")
scenarios("features/utils_errors.feature")
scenarios("features/utils_timing.feature")


# --- shared helpers ----------------------------------------------------------
_REQ = httpx.Request("POST", "https://api.example.com/v1/x")


def _instant_settings() -> Settings:
    """Production Settings with the wait cap collapsed to 0 (no real sleep)."""
    return Settings(_env_file=None, wait_cap_scale=0.0)


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError("boom", request=_REQ, response=httpx.Response(code, request=_REQ))


def _api_status_error(code: int) -> APIStatusError:
    return APIStatusError("boom", response=httpx.Response(code, request=_REQ), body=None)


# ============================================================================
# reliability.py :: _max_wait
# ============================================================================
@given("a retry wait cap of 20 seconds", target_fixture="ctx")
def _cap_20():
    return {"cap": 20.0}


@when("the wait cap is scaled by a WAIT_CAP_SCALE of 0")
def _scale_zero(ctx):
    ctx["scaled_zero"] = _max_wait(ctx["cap"], Settings(_env_file=None, wait_cap_scale=0.0))


@then("the effective maximum wait is 0 seconds")
def _wait_zero(ctx):
    assert ctx["scaled_zero"] == 0.0


@then("the same cap scaled by 1 stays at its full value")
def _wait_full(ctx):
    assert _max_wait(ctx["cap"], Settings(_env_file=None, wait_cap_scale=1.0)) == ctx["cap"]


# ============================================================================
# reliability.py :: _status
# ============================================================================
@when(
    "the status helper inspects an OpenAI 401 status error, an httpx 503 status error, "
    "and a plain ValueError",
    target_fixture="ctx",
)
def _inspect_statuses():
    return {
        "sdk": _status(_api_status_error(401)),
        "transport": _status(_http_status_error(503)),
        "unrelated": _status(ValueError("nope")),
    }


@then(
    "it reports 401 for the SDK error, 503 for the transport error, and nothing for the "
    "unrelated error"
)
def _statuses_reported(ctx):
    assert ctx["sdk"] == 401
    assert ctx["transport"] == 503
    assert ctx["unrelated"] is None


# ============================================================================
# reliability.py :: _is_retryable_llm
# ============================================================================
@when(
    "the LLM retry predicate classifies a timeout, a connection error, and a 400 status error",
    target_fixture="ctx",
)
def _classify_llm():
    return {
        "timeout": _is_retryable_llm(APITimeoutError(request=_REQ)),
        "conn": _is_retryable_llm(APIConnectionError(request=_REQ)),
        "client": _is_retryable_llm(_api_status_error(400)),
    }


@then("the timeout and the connection error are retryable and the 400 status error is not")
def _llm_classified(ctx):
    assert ctx["timeout"] is True
    assert ctx["conn"] is True
    assert ctx["client"] is False


# ============================================================================
# reliability.py :: _is_retryable_tavily
# ============================================================================
@when(
    "the search retry predicate classifies a connect timeout, a 429, a 500, and a 401",
    target_fixture="ctx",
)
def _classify_tavily():
    return {
        "timeout": _is_retryable_tavily(httpx.ConnectTimeout("t")),
        "rate": _is_retryable_tavily(_http_status_error(429)),
        "server": _is_retryable_tavily(_http_status_error(500)),
        "auth": _is_retryable_tavily(_http_status_error(401)),
    }


@then("the timeout, the 429, and the 500 are retryable and the 401 is not")
def _tavily_classified(ctx):
    assert ctx["timeout"] is True
    assert ctx["rate"] is True
    assert ctx["server"] is True
    assert ctx["auth"] is False


# ============================================================================
# reliability.py :: _is_retryable_fetch
# ============================================================================
@when(
    "the fetch retry predicate classifies a read timeout, a 503, a 404, and a 429",
    target_fixture="ctx",
)
def _classify_fetch():
    return {
        "timeout": _is_retryable_fetch(httpx.ReadTimeout("t")),
        "gateway": _is_retryable_fetch(_http_status_error(503)),
        "not_found": _is_retryable_fetch(_http_status_error(404)),
        "rate": _is_retryable_fetch(_http_status_error(429)),
    }


@then("the timeout and the 503 are retryable and the 404 and 429 are not")
def _fetch_classified(ctx):
    assert ctx["timeout"] is True
    assert ctx["gateway"] is True
    assert ctx["not_found"] is False
    assert ctx["rate"] is False


# ============================================================================
# reliability.py :: llm_retry
# ============================================================================
@given("an LLM call guarded by the llm_retry policy with instant retries", target_fixture="ctx")
def _llm_ctx():
    return {"settings": _instant_settings()}


@when("the call raises a transient connection error three times then returns a result")
def _llm_transient(ctx):
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] <= 3:
            raise APIConnectionError(request=_REQ)
        return "ok"

    start = time.perf_counter()
    ctx["result"] = asyncio.run(llm_retry(ctx["settings"])(flaky)())
    ctx["elapsed"] = time.perf_counter() - start
    ctx["calls"] = calls["n"]


@then("the guarded call returns the result after exactly 4 attempts without real sleeping")
def _llm_recovered(ctx):
    assert ctx["result"] == "ok"
    assert ctx["calls"] == 4  # 3 transient failures + 1 success under the 4-attempt policy
    assert ctx["elapsed"] < 1.0  # WAIT_CAP_SCALE=0 -> no real backoff sleep


@when("a guarded LLM call fails immediately with an HTTP 401")
def _llm_auth(ctx):
    calls = {"n": 0}

    async def auth_fail():
        calls["n"] += 1
        raise _api_status_error(401)

    try:
        asyncio.run(llm_retry(ctx["settings"])(auth_fail)())
    except Exception as exc:  # noqa: BLE001 — assert the exact typed translation below
        ctx["raised"] = exc
    ctx["auth_calls"] = calls["n"]


@then("it raises LLMUnavailableError after a single attempt")
def _llm_fast_fail(ctx):
    assert isinstance(ctx["raised"], LLMUnavailableError)
    assert ctx["auth_calls"] == 1  # 401 is never retried


# ============================================================================
# reliability.py :: tavily_retry
# ============================================================================
@given(
    "a search call guarded by the tavily_retry policy with instant retries", target_fixture="ctx"
)
def _tavily_ctx():
    return {"settings": _instant_settings()}


@when("a guarded search fails with an HTTP 401")
def _tavily_auth(ctx):
    calls = {"n": 0}

    async def auth_fail():
        calls["n"] += 1
        raise _http_status_error(401)

    try:
        asyncio.run(tavily_retry(ctx["settings"])(auth_fail)())
    except Exception as exc:  # noqa: BLE001
        ctx["auth_raised"] = exc
    ctx["auth_calls"] = calls["n"]


@then("the original transport error propagates unchanged so the ddgs fallback can run")
def _tavily_reraises(ctx):
    # 400/401/403 must NOT become SearchUnavailableError, so FallbackProvider hits ddgs.
    assert isinstance(ctx["auth_raised"], httpx.HTTPStatusError)
    assert not isinstance(ctx["auth_raised"], SearchUnavailableError)
    assert ctx["auth_calls"] == 1


@when("a guarded search keeps returning HTTP 503")
def _tavily_exhaust(ctx):
    calls = {"n": 0}

    async def always_503():
        calls["n"] += 1
        raise _http_status_error(503)

    try:
        asyncio.run(tavily_retry(ctx["settings"])(always_503)())
    except Exception as exc:  # noqa: BLE001
        ctx["exhaust_raised"] = exc
    ctx["exhaust_calls"] = calls["n"]


@then("it raises SearchUnavailableError after exactly 3 attempts")
def _tavily_typed_exhaustion(ctx):
    assert isinstance(ctx["exhaust_raised"], SearchUnavailableError)
    assert ctx["exhaust_calls"] == 3


# ============================================================================
# reliability.py :: fetch_retry
# ============================================================================
@given("a page fetch guarded by the fetch_retry policy with instant retries", target_fixture="ctx")
def _fetch_ctx():
    return {"settings": _instant_settings()}


@when("a guarded fetch fails with an HTTP 404")
def _fetch_404(ctx):
    calls = {"n": 0}

    async def not_found():
        calls["n"] += 1
        raise _http_status_error(404)

    try:
        asyncio.run(fetch_retry(ctx["settings"])(not_found)())
    except Exception as exc:  # noqa: BLE001
        ctx["nf_raised"] = exc
    ctx["nf_calls"] = calls["n"]


@then("it raises PageFetchError after a single attempt")
def _fetch_typed(ctx):
    assert isinstance(ctx["nf_raised"], PageFetchError)
    assert ctx["nf_calls"] == 1  # 404 is not retryable


@when("a guarded fetch times out once then returns the page")
def _fetch_recover(ctx):
    calls = {"n": 0}

    async def flaky_fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("t")
        return "page-markdown"

    ctx["fetch_result"] = asyncio.run(fetch_retry(ctx["settings"])(flaky_fetch)())
    ctx["recover_calls"] = calls["n"]


@then("the guarded call returns the page after exactly 2 attempts")
def _fetch_recovered(ctx):
    assert ctx["fetch_result"] == "page-markdown"
    assert ctx["recover_calls"] == 2  # 1 retryable timeout + 1 success, capped at 2 attempts


# ============================================================================
# reliability.py :: summary_retry
# ============================================================================
@given(
    "a summary call guarded by the summary_retry policy with instant retries",
    target_fixture="ctx",
)
def _summary_ctx():
    return {"settings": _instant_settings()}


@when("a guarded summary times out once then returns the summary")
def _summary_recover(ctx):
    calls = {"n": 0}

    async def flaky_summary():
        calls["n"] += 1
        if calls["n"] == 1:
            raise APIConnectionError(request=_REQ)
        return "a-summary"

    ctx["summary_result"] = asyncio.run(summary_retry(ctx["settings"])(flaky_summary)())
    ctx["summary_recover_calls"] = calls["n"]


@then("the guarded call returns the summary after exactly 2 attempts")
def _summary_recovered(ctx):
    assert ctx["summary_result"] == "a-summary"
    assert ctx["summary_recover_calls"] == 2  # 1 retryable failure + 1 success, capped at 2


@when("a guarded summary keeps failing with a transient connection error")
def _summary_persistent(ctx):
    calls = {"n": 0}

    async def always_fail():
        calls["n"] += 1
        raise APIConnectionError(request=_REQ)

    try:
        asyncio.run(summary_retry(ctx["settings"])(always_fail)())
    except Exception as exc:  # noqa: BLE001
        ctx["summary_raised"] = exc
    ctx["summary_fail_calls"] = calls["n"]


@then("the original error propagates after exactly 2 attempts so ingest degrades")
def _summary_reraised(ctx):
    # re-raised original (NOT a typed error) so ingest_content's guard degrades to
    # chunking-without-summary rather than treating it as a hard dependency failure.
    assert isinstance(ctx["summary_raised"], APIConnectionError)
    assert ctx["summary_fail_calls"] == 2


# ============================================================================
# errors.py :: redis_down_in_chain
# ============================================================================
@given("a wrapper error whose __cause__ is a redis ConnectionError", target_fixture="ctx")
def _wrapped_redis():
    inner = redis_exceptions.ConnectionError("connection refused")
    wrapper = RuntimeError("RedisSearchError: query failed")
    wrapper.__cause__ = inner  # redisvl nests the real error here
    return {"wrapper": wrapper}


@when("redis_down_in_chain inspects the wrapper")
def _inspect_chain(ctx):
    ctx["wrapped_result"] = redis_down_in_chain(ctx["wrapper"])


@then("it reports a redis outage")
def _reports_outage(ctx):
    assert ctx["wrapped_result"] is True


@then("it also reports an outage for a bare redis timeout error and for an OSError")
def _reports_bare(ctx):
    assert redis_down_in_chain(redis_exceptions.TimeoutError("timed out")) is True
    assert redis_down_in_chain(OSError("socket boom")) is True


@then("it does not report an outage for an unrelated error with no redis cause")
def _no_false_positive(ctx):
    assert redis_down_in_chain(ValueError("totally unrelated")) is False


# ============================================================================
# timing.py :: timed
# ============================================================================
@given("an async node that returns its own inner latency entry", target_fixture="ctx")
def _timing_node():
    async def node(state):
        return {"latency_ms": {"inner": 5}}

    return {"node": node}


@when('it is wrapped by timed for the "embed" stage and awaited')
def _wrap_and_run(ctx):
    ctx["out"] = asyncio.run(timed("embed", ctx["node"])({}))


@then("the returned state keeps the node's own inner latency entry")
def _keeps_inner(ctx):
    assert ctx["out"]["latency_ms"]["inner"] == 5


@then('the wrapper adds an integer millisecond timing for the "embed" stage')
def _adds_stage(ctx):
    assert isinstance(ctx["out"]["latency_ms"]["embed"], int)


@then('a node that returns None still yields only the "embed" stage timing')
def _tolerates_none(ctx):
    async def none_node(state):
        return None

    out = asyncio.run(timed("embed", none_node)({}))
    assert set(out["latency_ms"]) == {"embed"}
