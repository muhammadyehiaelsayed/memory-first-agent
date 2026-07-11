"""M5-owned: Tavily search retry policy (FR-M5-19/21), respx-driven, WAIT_CAP_SCALE=0.

respx intercepts the Tavily httpx transport ONLY. The ddgs leg is stubbed (ddgs uses the
primp/Rust client, invisible to respx) so the file stays keyless + no-network — mirroring
the tavily-python ban the source applies to the primary provider.
"""

import asyncio

import httpx
import respx

from memagent.config import Settings
from memagent.utils.errors import SearchUnavailableError
from memagent.web.search import TAVILY_ENDPOINT, DdgsSearcher, FallbackProvider, TavilySearcher

SETTINGS = Settings(_env_file=None, wait_cap_scale=0.0, tavily_api_key="test-key")


def _run(coro):
    return asyncio.run(coro)


@respx.mock
def test_transient_ratelimit_then_success_three_calls():
    route = respx.post(TAVILY_ENDPOINT).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(200, json={"results": [{"url": "u", "title": "t", "content": "c"}]}),
        ]
    )
    searcher = TavilySearcher(SETTINGS)
    results = _run(searcher.search("redis", 5))
    assert route.call_count == 3
    assert results and results[0]["url"] == "u"


@respx.mock
def test_auth_error_fast_fails_and_fallback_uses_ddgs(monkeypatch):
    route = respx.post(TAVILY_ENDPOINT).mock(return_value=httpx.Response(401))

    async def fake_ddgs(self, query, k):
        return [{"url": "d", "title": "ddgs", "snippet": "s", "rank": 0}]

    monkeypatch.setattr(
        DdgsSearcher, "search", fake_ddgs
    )  # stub the primp leg (respx can't see it)
    provider = FallbackProvider(SETTINGS)
    results = _run(provider.search("redis", 5))
    assert route.call_count == 1  # 401 not retried
    assert provider.provider_used == "ddgs"
    assert results[0]["url"] == "d"


@respx.mock
def test_persistent_503_exhausts_and_raises_typed():
    route = respx.post(TAVILY_ENDPOINT).mock(return_value=httpx.Response(503))
    searcher = TavilySearcher(SETTINGS)
    raised = False
    try:
        _run(searcher.search("redis", 5))
    except SearchUnavailableError:
        raised = True
    assert raised
    assert route.call_count == 3


def test_tavily_holds_httpx_client():  # regression guard: never swap in tavily-python
    searcher = TavilySearcher(SETTINGS)
    assert isinstance(searcher._client, httpx.AsyncClient)


# --- A9: the keyless ddgs leg also owns an agent-side deadline + bounded retry ----------


def test_ddgs_retries_transient_failure_then_succeeds(monkeypatch):
    # A single transient ddgs blip is retried within the bounded budget, not fatal.
    calls = {"n": 0}

    class FlakyDDGS:
        def text(self, query, max_results):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("transient ddgs blip")
            return [{"href": "https://d.test/1", "title": "D", "body": "b"}]

    monkeypatch.setattr("memagent.web.search.DDGS", FlakyDDGS)
    results = _run(DdgsSearcher(SETTINGS).search("redis", 2))
    assert calls["n"] == 2  # retried once after the transient failure
    assert results[0]["url"] == "https://d.test/1"


def test_ddgs_persistent_failure_degrades_to_search_unavailable(monkeypatch):
    # Persistent ddgs failure exhausts the bounded budget and degrades to the typed error.
    calls = {"n": 0}

    class DeadDDGS:
        def text(self, query, max_results):
            calls["n"] += 1
            raise RuntimeError("ddgs down")

    monkeypatch.setattr("memagent.web.search.DDGS", DeadDDGS)
    raised = False
    try:
        _run(DdgsSearcher(SETTINGS).search("redis", 2))
    except SearchUnavailableError:
        raised = True
    assert raised
    assert calls["n"] == 2  # bounded: exactly 2 attempts, then typed degradation


def test_ddgs_deadline_fires_and_degrades(monkeypatch):
    # An agent-owned deadline (asyncio.wait_for) bounds a hanging ddgs call and degrades typed.
    async def hang(_fn):
        await asyncio.sleep(3600)  # never completes within the deadline; cancellable

    monkeypatch.setattr(asyncio, "to_thread", hang)
    tight = Settings(_env_file=None, read_timeout_s=0)  # deadline fires immediately
    raised = False
    try:
        _run(DdgsSearcher(tight).search("redis", 2))
    except SearchUnavailableError:
        raised = True
    assert raised
