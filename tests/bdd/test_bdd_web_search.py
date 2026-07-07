"""Executable binding for features/web_search.feature.

Exercises the REAL web-search boundary (src/memagent/web/search.py) that serves the
root "memory_miss_web_search" route. Keyless + no-network:
- Tavily's raw httpx POST is intercepted with respx (the whole reason the source holds an
  httpx.AsyncClient instead of the tavily-python SDK), mirroring tests/unit/test_search_provider.py
  and tests/unit/test_search_retry.py.
- The ddgs leg uses the primp/Rust client which respx cannot see, so it is stubbed locally
  (monkeypatching DdgsSearcher.search or memagent.web.search.DDGS), exactly as the reference tests do.

Steps are sync (pytest-bdd generates sync tests); coroutines are driven with asyncio.run(...).
The `settings` fixture (conftest) supplies TAVILY_API_KEY="test-key" (forces the interceptable
Tavily path) and WAIT_CAP_SCALE=0 (instant retries through the production tenacity policy).
"""

import asyncio
import json
import re
from pathlib import Path

import httpx
from pytest_bdd import given, scenarios, then, when

from memagent.utils.errors import SearchUnavailableError
from memagent.web.search import (
    TAVILY_ENDPOINT,
    DdgsSearcher,
    FallbackProvider,
    TavilySearcher,
)

scenarios("features/web_search.feature")


# --------------------------------------------------------------------------- #
# TavilySearcher.__init__                                                      #
# --------------------------------------------------------------------------- #
@given("a Tavily searcher constructed from the keyless test settings", target_fixture="tavily")
def _tavily(settings):
    return TavilySearcher(settings)


@then("its HTTP client is a reusable httpx.AsyncClient")
def _client_is_httpx(tavily):
    assert isinstance(tavily._client, httpx.AsyncClient)


@then(
    'the client carries an "Authorization: Bearer <key>" header and the module '
    "never imports the tavily package"
)
def _client_auth_and_no_tavily(tavily, settings):
    assert tavily._client.headers.get("Authorization") == f"Bearer {settings.tavily_api_key}"
    import memagent.web.search as search_mod

    src = Path(search_mod.__file__).read_text(encoding="utf-8")
    offending = [
        line
        for line in src.splitlines()
        if re.match(r"^\s*(import\s+tavily(\s|$)|from\s+tavily(\s|\.))", line)
    ]
    assert offending == [], f"web/search.py must not import the tavily SDK: {offending}"


# --------------------------------------------------------------------------- #
# TavilySearcher._post (retry at the single call-site)                        #
# --------------------------------------------------------------------------- #
@given("the Tavily endpoint responds 429, then 429, then 200", target_fixture="route")
def _route_429_429_200(respx_mock):
    return respx_mock.post(TAVILY_ENDPOINT).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(200, json={"results": [{"url": "u", "title": "t", "content": "c"}]}),
        ]
    )


@when("the Tavily searcher posts the query directly", target_fixture="post_response")
def _post_directly(tavily):
    return asyncio.run(tavily._post("redis", 5))


@then("the POST call site is invoked three times and yields a 200 response")
def _post_retried_three_times(route, post_response):
    assert route.call_count == 3
    assert post_response.status_code == 200


# --------------------------------------------------------------------------- #
# TavilySearcher.search                                                        #
# --------------------------------------------------------------------------- #
@given("the Tavily endpoint returns three search results", target_fixture="route")
def _route_three_results(respx_mock):
    return respx_mock.post(TAVILY_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://a.test/1", "title": "A", "content": "snippet A"},
                    {"url": "https://b.test/2", "title": "B", "content": "snippet B"},
                    {"url": "https://c.test/3", "title": "C", "content": "snippet C"},
                ]
            },
        )
    )


@when('the Tavily searcher searches for "redis vector search" with k of 3', target_fixture="hits")
def _tavily_search(tavily):
    return asyncio.run(tavily.search("redis vector search", 3))


@then("three ranked SearchResults are returned mapping the response content field to snippet")
def _tavily_results_mapped(hits):
    assert len(hits) == 3
    assert [h["url"] for h in hits] == ["https://a.test/1", "https://b.test/2", "https://c.test/3"]
    assert [h["snippet"] for h in hits] == ["snippet A", "snippet B", "snippet C"]
    assert [h["title"] for h in hits] == ["A", "B", "C"]
    assert [h["rank"] for h in hits] == [0, 1, 2]


@then("the POST body sets include_raw_content to false and max_results to 3")
def _tavily_body_flags(route):
    body = json.loads(route.calls[0].request.content)
    assert body["include_raw_content"] is False
    assert body["max_results"] == 3
    assert body["query"] == "redis vector search"


# --------------------------------------------------------------------------- #
# DdgsSearcher.search                                                          #
# --------------------------------------------------------------------------- #
@given("a stubbed ddgs backend returning two rows")
def _stub_ddgs(monkeypatch):
    rows = [
        {"href": "https://a.test/1", "title": "First", "body": "body one"},
        {"href": "https://b.test/2", "title": "Second", "body": "body two"},
    ]

    class FakeDDGS:
        def text(self, query, max_results):
            return rows[:max_results]

    monkeypatch.setattr("memagent.web.search.DDGS", FakeDDGS)


@when("the ddgs searcher searches without any API key", target_fixture="hits")
def _ddgs_search():
    return asyncio.run(DdgsSearcher().search("how does redis persist data", 2))


@then("two SearchResults come back mapping href to url and body to snippet, ranked by row order")
def _ddgs_results_mapped(hits):
    assert [h["url"] for h in hits] == ["https://a.test/1", "https://b.test/2"]  # href -> url
    assert [h["snippet"] for h in hits] == ["body one", "body two"]  # body -> snippet
    assert [h["title"] for h in hits] == ["First", "Second"]
    assert [h["rank"] for h in hits] == [0, 1]


# --------------------------------------------------------------------------- #
# FallbackProvider.__init__                                                    #
# --------------------------------------------------------------------------- #
@given("a fallback search provider built from settings", target_fixture="provider")
def _provider(settings):
    return FallbackProvider(settings)


@then("it holds both a Tavily searcher and a keyless ddgs searcher")
def _provider_holds_both(provider):
    assert isinstance(provider._tavily, TavilySearcher)
    assert isinstance(provider._ddgs, DdgsSearcher)


@then("it has recorded no provider_used yet")
def _provider_no_provider_used(provider):
    assert provider.provider_used is None


# --------------------------------------------------------------------------- #
# FallbackProvider.search — Tavily-first, ddgs fallback                        #
# --------------------------------------------------------------------------- #
@given("the Tavily endpoint returns results successfully", target_fixture="route")
def _route_success(respx_mock):
    return respx_mock.post(TAVILY_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"url": "https://tavily.test/x", "title": "T", "content": "c"}]},
        )
    )


@given("the Tavily endpoint rejects the request with HTTP 401", target_fixture="route")
def _route_401(respx_mock):
    return respx_mock.post(TAVILY_ENDPOINT).mock(return_value=httpx.Response(401))


@given("a ddgs backend that must not be called", target_fixture="ddgs_probe")
def _ddgs_forbidden(monkeypatch):
    probe = {"calls": 0}

    async def fake(self, query, k):
        probe["calls"] += 1
        return [{"url": "ddgs-should-not-run", "title": "x", "snippet": "x", "rank": 0}]

    monkeypatch.setattr(DdgsSearcher, "search", fake)
    return probe


@given("a ddgs backend that returns one result")
def _ddgs_one_result(monkeypatch):
    async def fake(self, query, k):
        return [{"url": "https://ddgs.test/d", "title": "ddgs", "snippet": "s", "rank": 0}]

    monkeypatch.setattr(DdgsSearcher, "search", fake)


@given("a ddgs backend that raises")
def _ddgs_raises(monkeypatch):
    async def fake(self, query, k):
        raise RuntimeError("ddgs unavailable")

    monkeypatch.setattr(DdgsSearcher, "search", fake)


@when("the fallback provider searches on a memory miss", target_fixture="fallback_result")
def _fallback_search(settings):
    provider = FallbackProvider(settings)
    out = {"provider": provider, "results": None, "error": None}
    try:
        out["results"] = asyncio.run(provider.search("redis persistence", 5))
    except Exception as exc:  # noqa: BLE001 — capture typed error for assertion
        out["error"] = exc
    return out


@then('Tavily supplies the results and provider_used is "tavily"')
def _served_by_tavily(fallback_result):
    assert fallback_result["error"] is None
    assert fallback_result["provider"].provider_used == "tavily"
    assert fallback_result["results"]
    assert fallback_result["results"][0]["url"] == "https://tavily.test/x"


@then("the ddgs backend was never called")
def _ddgs_not_called(ddgs_probe):
    assert ddgs_probe["calls"] == 0


@then('ddgs supplies the results and provider_used is "ddgs"')
def _served_by_ddgs(fallback_result):
    assert fallback_result["error"] is None
    assert fallback_result["provider"].provider_used == "ddgs"
    assert fallback_result["results"][0]["url"] == "https://ddgs.test/d"


@then("Tavily was called exactly once without retrying the 401")
def _tavily_not_retried(route):
    assert route.call_count == 1


@then("a SearchUnavailableError is raised and provider_used is cleared")
def _typed_error(fallback_result):
    assert isinstance(fallback_result["error"], SearchUnavailableError)
    assert fallback_result["provider"].provider_used is None
