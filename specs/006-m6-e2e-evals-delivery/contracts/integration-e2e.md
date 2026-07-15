# Contract — Redis Integration + E2E Lifecycle (`tests/integration/test_redis_store.py`, `tests/e2e/test_lifecycle.py`)

FR-006..012. M6 creates `tests/integration/` and `tests/e2e/` (both absent — D15). Marks:
`@pytest.mark.integration` / `@pytest.mark.e2e` (declared in pyproject, unused until now).

## `tests/integration/test_redis_store.py` (`@integration`, real `redis:8.2`)

Uses `clean_index` + `fake_embedder`. Four checks:

1. **Idempotent create (FR-006, D4)**: `await ensure_index(index)` twice → first `True`, second
   `False`, no error; exactly one `web_memory` index (`await index.exists()` truthy; not
   duplicated). **NOT** `create(overwrite=False)` twice (which raises).
2. **Round-trip (FR-007)**: build a `FetchedDoc` + one `Chunk` (`text="Redis stores vectors next
   to data"`), `vecs = await fake_embedder.embed([chunk["text"]])`, `await store.store(page,
   [chunk], vecs, source_query=q, flags=[])`; then `hits = await store.knn(await
   fake_embedder.embed([chunk["text"]])[0]... , k=5)`; assert `hits[0]["text"]/["url"]/["title"]`
   equal the stored chunk.
3. **Metadata survives (FR-008, D5)**: `monkeypatch.setattr(store_module.time, "time", lambda:
   1751625600.0)` (or patch the `time.time` reference used by `store`), store, `knn`; assert
   `hits[0]["stored_at"] == _epoch_to_iso(1751625600.0)` and `datetime.fromisoformat(stored_at)`
   succeeds; `url`/`title` intact. (Fallback: assert parses-as-ISO + epoch ≈ now.)
4. **Known-vector similarity (FR-009, D6)**: store a hand-built unit vector `e0=[1,0,0,…]` (via a
   chunk whose vector is supplied directly). Query with:
   - `e0` → `similarity == 1.0`
   - `e1=[0,1,0,…]` (orthogonal) → `similarity == 0.0`
   - `w=[0.7, sqrt(1-0.49), 0,…]` (unit, cos(e0,w)=0.70) → `abs(similarity - 0.70) <= 1e-6`
     (Redis `vector_distance == 0.30`; `similarity = 1 - 0.30`). With `SIMILARITY_THRESHOLD=0.7`
     this is an inclusive hit.

> `store.store` embeds are passed as the `vectors` arg (float32 via `array_to_buffer`), so the
> known-vector test supplies the exact unit vectors as `vectors=[e0]` and queries with raw
> vectors — bypassing the FakeEmbedder for the pure distance math.

## `tests/e2e/test_lifecycle.py` (`@e2e`, THE core proof)

Wiring: `settings` (WAIT_CAP_SCALE=0, tmp turn-log) + `monkeypatch.setenv("TAVILY_API_KEY",
"test-key")` (forces the Tavily-httpx path — D3); `clean_index` (empty index); `resources =
build_test_resources(settings, redis_client)`; `agent = Agent(resources)`.
(Shipped `Agent.__init__(resources)` builds the graph **itself** — do NOT wrap in `build_graph()`; a compiled graph in `self.resources` makes `answer()` raise `AttributeError` on `.settings`. recheck A, app.py:99-101.)

**respx routes (D3 — happy-path 200, no redirect):**

```python
QUESTION = "How does Redis vector search work?"
URL = "https://example.test/redis-vector-search"
@respx.mock
async def test_lifecycle(...):
    respx.post("https://api.tavily.com/search").mock(return_value=httpx.Response(
        200, json={"results": [{"url": URL, "title": "Redis Vector Search", "content": QUESTION}]}))
    tavily = respx.routes[...]                      # keep the POST route handle for call_count
    respx.get(URL).mock(return_value=httpx.Response(
        200, headers={"content-type": "text/html"},
        text="<html><body><article><p>" + (QUESTION + " ") * 40 + "</p></article></body></html>"))
        #  ^ FULL HTML doc with block tags — a BARE <article> makes trafilatura return None (page
        #    dropped -> degraded_web, nothing stored, core proof fails). Wrapped form extracts ~1399
        #    chars (>200 floor) -> 1 query-dominated chunk -> sim ~1.0. Matches shipped test_fetch_retry.py. (recheck B, D8)
```

- **Turn 1 (FR-010)**: `r1 = await agent.answer(QUESTION)` →
  `r1.route == "memory_miss_web_search"`; `any(s["origin"]=="web" for s in r1.sources)`;
  the Tavily POST `route.call_count == 1`.
- **Turn 2 (FR-011)**: `r2 = await agent.answer(QUESTION)` →
  `r2.route == "memory_hit"`; `r2.similarity >= 0.70`; `any(s["origin"]=="memory")` and the cited
  URL == `URL` (D9); the Tavily POST `route.call_count` **still 1** (unchanged — no web touch).
- **Turn log (FR-012, D7)**: read `settings.turn_log_path`:
  ```python
  recs = [json.loads(l) for l in open(settings.turn_log_path) if l.strip()]
  assert len(recs) == 2
  assert [r["route"] for r in recs] == ["memory_miss_web_search", "memory_hit"]
  assert recs[1]["similarity_top"] >= 0.70
  assert recs[0]["tokens"] and recs[1]["tokens"]           # non-empty (fakes return usage)
  ```

> **Why 200-only, no-redirect (D3)**: `TavilySearcher._post`/`_fetch_one` are retry-wrapped, so a
> retryable status would inflate `call_count`; `HttpxPageFetcher` records the post-redirect URL as
> doc identity, so a redirect would break the FR-011 cited-URL == turn-1-URL check. `respx` patches
> httpx only — `redis.asyncio` traffic to the real `clean_index` is untouched.

> **Why turn 2 clears 0.70 (D8)**: the query-dominated `<article>` (QUESTION × 40, > 200 chars
> after trafilatura) chunks into query-dominated chunks that embed ~1.0 to the repeated query under
> the bag-of-words `FakeEmbedder`; the FakeLLM summary doc is also indexed but scores lower and is
> never the KNN max. `top_similarity` is the max hit ⇒ ≥ 0.70.

## Non-happy-path routes (D12) — NOT here

`blocked`/`degraded_web`/`failed` are proven upstream (M5 `test_guardrails`/`test_reliability`,
M2 `test_routing`, M4 `test_turnlog`) and consumed green in CI. The e2e proves only
`memory_miss_web_search` → `memory_hit`.
