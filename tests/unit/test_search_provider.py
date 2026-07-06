"""Search-provider contracts untested before M7.

- DdgsSearcher (FR-M3-03) is the DEFAULT keyless path (blank TAVILY_API_KEY). Its ddgs
  field mapping (href->url, body->snippet, order->rank) was only ever monkeypatched away.
- The Tavily request body (FR-M3-01 / §10) MUST keep include_raw_content=False so our own
  fetch+markdown pipeline — the graded work — does the extraction, not Tavily.
"""

import asyncio
import json

import httpx
import respx

from memagent.config import Settings
from memagent.web.search import TAVILY_ENDPOINT, DdgsSearcher, TavilySearcher

SETTINGS = Settings(_env_file=None, wait_cap_scale=0.0, tavily_api_key="test-key")


def _run(coro):
    return asyncio.run(coro)


def test_ddgs_maps_href_body_and_ranks_by_order(monkeypatch):
    rows = [
        {"href": "https://a.test/1", "title": "First", "body": "snippet one"},
        {"href": "https://b.test/2", "title": "Second", "body": "snippet two"},
    ]

    class FakeDDGS:
        def text(self, query, max_results):
            return rows[:max_results]

    monkeypatch.setattr("memagent.web.search.DDGS", FakeDDGS)
    results = _run(DdgsSearcher().search("redis", 2))
    assert [r["url"] for r in results] == ["https://a.test/1", "https://b.test/2"]  # href -> url
    assert [r["snippet"] for r in results] == ["snippet one", "snippet two"]  # body -> snippet
    assert [r["title"] for r in results] == ["First", "Second"]
    assert [r["rank"] for r in results] == [0, 1]  # rank by row order


@respx.mock
def test_tavily_post_body_keeps_include_raw_content_false():
    route = respx.post(TAVILY_ENDPOINT).mock(
        return_value=httpx.Response(
            200, json={"results": [{"url": "u", "title": "t", "content": "c"}]}
        )
    )
    _run(TavilySearcher(SETTINGS).search("redis vectors", 3))
    assert route.call_count == 1
    body = json.loads(route.calls[0].request.content)
    assert body["include_raw_content"] is False  # §10 gotcha: we fetch+extract, not Tavily
    assert body["max_results"] == 3
    assert body["query"] == "redis vectors"
