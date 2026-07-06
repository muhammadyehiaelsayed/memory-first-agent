"""M6-owned e2e lifecycle test — THE assignment core proof (FR-010, FR-011, FR-012).

Real Redis + real web/search + real web/fetch (respx-intercepted) + FakeLLM/FakeEmbedder.
Turn 1 misses and searches the web; the identical turn 2 hits memory without touching the web.
Only memory_miss_web_search -> memory_hit is proven here; blocked/degraded_web/failed are
covered upstream (M5/M2/M4) and consumed green in CI.
"""

import json

import httpx
import pytest
import respx

pytestmark = pytest.mark.e2e

QUESTION = "How does Redis vector search work?"
URL = "https://example.test/redis-vector-search"
# Full HTML document with a block tag: a BARE <article> is dropped by trafilatura (recheck B).
# The query, repeated, dominates the extracted markdown so the stored chunk embeds ~1.0 to it.
PAGE_HTML = "<html><body><article><p>" + (QUESTION + " ") * 40 + "</p></article></body></html>"


async def test_memory_first_lifecycle(agent, settings):
    with respx.mock(assert_all_called=False) as mock:
        tavily = mock.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [{"url": URL, "title": "Redis Vector Search", "content": QUESTION}]
                },
            )
        )
        mock.get(URL).mock(  # 200, text/html, NO redirect (recheck B / D3 / D9)
            return_value=httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE_HTML)
        )

        # ---- Turn 1: miss -> web search (FR-010) ----
        r1 = await agent.answer(QUESTION)
        assert r1.route == "memory_miss_web_search", r1.route
        assert any(s["origin"] == "web" for s in r1.sources), r1.sources
        assert tavily.call_count == 1

        # ---- Turn 2: identical -> memory hit, no web (FR-011) ----
        r2 = await agent.answer(QUESTION)
        assert r2.route == "memory_hit", r2.route
        # >= 0.9 (not just >= threshold 0.70): tests embedding-match quality independently of the
        # route==memory_hit predicate, which already guarantees >= 0.70 (impl-verify finding).
        assert r2.similarity is not None and r2.similarity >= 0.9, r2.similarity
        assert any(s["origin"] == "memory" for s in r2.sources), r2.sources
        assert URL in [s["url"] for s in r2.sources]  # cited URL == turn-1 URL
        assert tavily.call_count == 1  # UNCHANGED — the hit never touched the web

    # ---- Turn log: exactly one record per turn (FR-012) ----
    with open(settings.turn_log_path, encoding="utf-8") as f:
        recs = [json.loads(line) for line in f if line.strip()]
    assert len(recs) == 2, recs
    assert [r["route"] for r in recs] == ["memory_miss_web_search", "memory_hit"]
    assert recs[1]["similarity_top"] is not None and recs[1]["similarity_top"] >= 0.9
    assert recs[0]["tokens"] and recs[1]["tokens"]  # populated tokens block each turn
