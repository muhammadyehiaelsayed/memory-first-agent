# Contract: Web Search — `web/search.py` + `nodes/search.py`

**FRs**: FR-001…FR-005 · **Consumers**: `fetch_pages` (results), M4 TurnRecord
(`search_provider`), M5 retry policies (wrap points). No retries in M3 (Ruling A/D).

## TavilySearcher

```python
class TavilySearcher:
    def __init__(self, settings: Settings) -> None:
        self._client = httpx.AsyncClient(...)   # REUSABLE; M5's guard test asserts isinstance
        ...
    async def search(self, query: str, k: int) -> list[SearchResult]: ...
```

- Raw `httpx` POST to `https://api.tavily.com/search` — headers
  `{"Authorization": f"Bearer {settings.tavily_api_key}", "Content-Type": "application/json"}`,
  JSON body `{"query": query, "max_results": k, "include_raw_content": False}`.
- `response.raise_for_status()` then map `results[*]`: `url→url`, `title→title`,
  **`content`→snippet** (live-verified 2026-07-05, research D1), enumeration order→`rank`.
- MUST NOT import `tavily` / use `tavily-python` (DoD grep); MUST hold an
  `httpx.AsyncClient` instance (FR-002; respx-visibility for M5).
- `include_raw_content` stays `False` — flipping it outsources the graded fetch+markdown
  step (source §10).

## DdgsSearcher

```python
class DdgsSearcher:
    async def search(self, query: str, k: int) -> list[SearchResult]: ...
```

- Runs `DDGS().text(query, max_results=k)` via `asyncio.to_thread` (ddgs is synchronous —
  FR-003). Keyless. Map `title→title`, `href→url`, `body→snippet` (live-verified
  2026-07-05, research D2), order→`rank`. Returns up to `k` items.

## FallbackProvider (implements `WebSearcher`)

```python
class FallbackProvider:
    provider_used: str | None          # "tavily" | "ddgs" | None — set per search (research D6)
    async def search(self, query: str, k: int) -> list[SearchResult]: ...
```

- Order: Tavily first **iff** `settings.tavily_api_key` is non-blank; on
  `httpx.HTTPStatusError | httpx.TransportError` (auth/quota/transport — research D5)
  fall back to ddgs. Blank key ⇒ straight to ddgs.
- ddgs failure is also caught → return `[]` (never raise into the graph); both-fail turns
  route to `answer_failure` via `route_after_search` (FR-005).
- After every `search()`: set `self.provider_used` and emit ONE structlog line including
  `provider_used` (first structlog use in the repo).
- NO tenacity, NO sleeps, NO retry loops — plain try/except only (M5 seam).

## `web_search` node (`nodes/search.py`, factory `make_web_search(resources)`)

- Calls `resources.searcher.search(state["sanitized_query"], settings.search_max_results)`.
- Returns partial state:
  `{"search_results": results, "search_provider": getattr(searcher, "provider_used", None)}`
  (+ `latency_ms` entry; `errors` append on caught failure with `search_results=[]`).
- Never raises; an exception inside search ⇒ `search_results=[]` → failure route.

## Routing (M2-delivered, activates now)

```python
def route_after_search(s): return "fetch_pages" if s["search_results"] else "answer_failure"
```
