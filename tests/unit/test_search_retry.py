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

    monkeypatch.setattr(DdgsSearcher, "search", fake_ddgs)  # stub the primp leg (respx can't see it)
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
