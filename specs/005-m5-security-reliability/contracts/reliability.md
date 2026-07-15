# Contract — Reliability (`utils/reliability.py`, `utils/errors.py`, client wraps, redis retry)

Single retry owner (P-III). Policies are **factories over `Settings`** so tests drive the
production path with `wait_cap_scale=0`. `before_sleep_log` uses a stdlib
`logging.getLogger("memagent.reliability")` (routed to stderr by `configure_logging`).
FR-M5-17..23; degradation wiring FR-M5-24..28.

## `utils/errors.py`

Four exceptions (`LLMUnavailableError`, `SearchUnavailableError`, `PageFetchError`,
`MemoryUnavailableError`) + `redis_down_in_chain(exc) -> bool` (moved from `cli.py`;
walks `__cause__`, returns True if any link is a redis `ConnectionError`/`TimeoutError`
or `OSError`). `cli.py` imports it from here (no behavior change to the CLI's startup
guard).

## `utils/reliability.py`

```python
def _max_wait(cap_s: float, settings) -> float:  # cap_s * settings.wait_cap_scale
def llm_retry(settings)  -> Callable   # decorator; 4 attempts, cap 20s
def tavily_retry(settings) -> Callable # decorator; 3 attempts, cap 8s
def fetch_retry(settings) -> Callable  # decorator; 2 attempts, cap 2s
```

Each built with tenacity `AsyncRetrying`/`retry`: `stop_after_attempt(N)`,
`wait_random_exponential(multiplier=1, max=_max_wait(cap, settings))` (full jitter),
`before_sleep=before_sleep_log(logger, logging.WARNING)`, `reraise=True`.

**Retry / fast-fail predicates and typed raises:**

| Policy | Attempts | Retry on | Fast-fail on | Raises |
|---|---|---|---|---|
| `llm_retry` | `settings.llm_max_attempts` (4) | `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `InternalServerError` | `APIStatusError` with `status_code ∈ {400,401,403,404,422}` | `LLMUnavailableError` on fast-fail AND on exhaustion (chain original) |
| `tavily_retry` | 3 | `httpx.TimeoutException`, `httpx.TransportError`, `HTTPStatusError` status 429 or ≥500 | `HTTPStatusError` status ∈ {400,401,403} → **re-raise original** (→ fallback) | `SearchUnavailableError` on exhaustion |
| `fetch_retry` | 2 | `httpx.TimeoutException`, `httpx.TransportError`, `HTTPStatusError` status ∈ {502,503,504} | any other `HTTPStatusError` → `PageFetchError` | `PageFetchError` on exhaustion |

Implementation note: use a `retry=retry_if_exception(pred)` where `pred` returns True only
for the retryable set; do the fast-fail typed-error translation *inside* the wrapped
coroutine (a thin `try/except` that inspects `exc.status_code` and raises the typed error
or re-raises), so non-retryable errors never consume an attempt. On exhaustion, tenacity
re-raises the last exception; the wrapper's outer `except` maps it to the typed error.

## Client wraps (single call-site each — Rulings A/D)

- **`llm/clients.py`**: `OpenAIChatLLM.__init__` and `OpenAIEmbedder.__init__` gain
  `retrying: Callable | None = None`. When set, it decorates `_call`/`_parse_call` (chat)
  and the `embeddings.create` seam (embed) — the ONLY network call-sites. `complete()`,
  `parse()`, `embed()` bodies unchanged. `build_openai_clients` passes
  `retrying=llm_retry(settings)` to the **conversation client and embedder ONLY**; the
  **analytics client keeps `retrying=None`** (its classifier owns `wait_for(8s)` +
  `stop_after_attempt(2)` — D3; wrapping it would break M4's exactly-2-calls tests).
  `AsyncOpenAI(max_retries=0)` stays (verify in test).
- **`web/search.py`**: `TavilySearcher.search`'s POST is wrapped by `tavily_retry`.
  `TavilySearcher.__init__` sets `httpx.AsyncClient(timeout=httpx.Timeout(`
  `settings.read_timeout_s, connect=settings.connect_timeout_s), headers=…)` (today it has
  no explicit timeout — research #5). `FallbackProvider.search` catches
  `(httpx.HTTPStatusError, httpx.TransportError, SearchUnavailableError)` from Tavily →
  ddgs; if ddgs also fails it raises `SearchUnavailableError` (today returns `[]`).
  `TavilySearcher` continues to hold an `httpx.AsyncClient` (regression-guard assertion).
- **`web/fetch.py`**: `HttpxPageFetcher._fetch_one` wrapped by `fetch_retry`. The
  `asyncio.wait_for(page_deadline_s)` in `_fetch_guarded` stays outside the retry (bounds
  both attempts). `None`-skip returns (non-HTML, oversize, unconvertible) are not errors →
  never retried. `_fetch_guarded`'s broad catch keeps per-URL failures non-fatal.

## Redis native retry (`memory/store.py`, D7)

```python
def make_redis_client(settings):
    return aioredis.from_url(
        settings.redis_url,
        retry=Retry(ExponentialBackoff(cap=1.0), 3),  # 3 RETRIES after the initial try = 4 total attempts
        retry_on_error=[redis.exceptions.ConnectionError, redis.exceptions.TimeoutError],
        socket_timeout=2.0, socket_connect_timeout=2.0,
    )
```

> **Retry semantics note**: redis-py's `Retry(backoff, retries=3)` means 3 *retries* after
> the first attempt (4 total tries) — unlike tenacity's `stop_after_attempt(N)`, which is N
> *total*. The source §6.6 table's "3 attempts" for the Redis row is this `retries=3`
> value. Acceptance pins the config (`Retry.retries == 3`), never a call count, so the
> distinction is documentation-only; do not "correct" it to `Retry(..., 2)`.

Used by `app.build_resources` and `cli._wipe` (both drop the bare `from_url`).
`RedisMemoryStore.knn`, `.store`, `.is_fresh` wrap their redis calls: catch
`(redis ConnectionError, redis TimeoutError, OSError)` OR
`RedisSearchError` where `redis_down_in_chain(exc)` → raise `MemoryUnavailableError` (chain
original). `redis.exceptions.ResponseError` is NOT caught (programming bug surfaces loudly).

## Node degradation wiring

- **`memory_search`**: wrap the `knn` call in `try/except MemoryUnavailableError` → return
  `{"memory_hits": [], "top_similarity": None, "skip_store": True,`
  `"degradation": "redis_down", "errors": [one entry]}`. Only this typed error is caught.
- **`answer_from_web`** (D9): `degradation = state.get("degradation")` on the fetched
  path; `degradation = state.get("degradation") or "snippets_only"` on the snippets path
  (disclaimer still prepended whenever snippets path runs);
  `route = "degraded_web" if degradation else "memory_miss_web_search"`. The existing
  broad LLM catch (→ `route="failed"`) is unchanged.
- **`web_search`, `fetch_pages`, `embed_query`, `answer_from_memory`**: keep their existing
  broad catches — the typed errors raised by the wrapped clients flow through them exactly
  as today (research #2), producing the same routes with better-named `errors[]` entries.
- **`ingest_content`**: degradation behavior and the `sanitize()` call-site are unchanged
  (skip_store honored since M3), but the node is additively edited to enrich each output
  doc with `"sanitizer_flags": flags` — the producer side of the web-provenance chain,
  owned by `contracts/prompts-l2.md` (D10). `log_turn`: unchanged (analytics null-tolerant
  since M4).

## Contract tests

`test_search_retry.py` (respx intercepts the **Tavily** transport only; `wait_cap_scale=0`):
- 429→429→200 → success, Tavily `call_count == 3`.
- 401 → Tavily `call_count == 1`, `FallbackProvider` falls through to ddgs
  (`provider_used == "ddgs"`).
- 503×∞ → `TavilySearcher.search` raises `SearchUnavailableError`, `call_count == 3`.

> **ddgs leg must be stubbed (keyless + no-network, Principle VIII)**: `ddgs` uses the
> `primp` (Rust) HTTP client, NOT httpx, so respx cannot intercept it — a real
> `FallbackProvider` would hit DuckDuckGo live (flaky, source risk #10) or, offline, raise
> and leave `provider_used=None` (failing the 401 assertion). The 401 scenario therefore
> monkeypatches `DdgsSearcher.search` (or injects a fake into `FallbackProvider._ddgs`) to
> return a canned result. This mirrors the respx-escape reasoning the source already
> applies to Tavily (`tavily-python` banned), now applied to the ddgs fallback it
> deliberately exercises.

`test_fetch_retry.py` (respx, `wait_cap_scale=0`):
- read-timeout then 200 → success, `call_count == 2`.
- 404 → `PageFetchError`, `call_count == 1`.
- body > `fetch_max_bytes` → skipped (no retry). non-HTML content-type → skipped.
- three URLs, middle 404s → `fetch_pages` returns 2 docs, turn continues.

`test_reliability.py` (D13, inline fakes):
- `AsyncOpenAI` constructed with `max_retries=0`; no node module imports tenacity
  (`grep`-style import check).
- fake chat client raising `RateLimitError` ×3 then success → success under 4 attempts,
  one `before_sleep` log per retry.
- fake chat client raising a 401 (`APIStatusError` status 401) → `LLMUnavailableError`,
  exactly 1 call.
- `wait_cap_scale=0`: a 4-attempt sequence runs with wall-time < 1 s, underlying
  call_count == 4.
- redis client built via `make_redis_client` has a `Retry` with `retries == 3`; a fake
  redis whose op raises `ConnectionError` → `store`/`knn` raise `MemoryUnavailableError`.
- degradation-matrix node scenarios (redis_down → `degraded_web`/`redis_down`;
  snippets_only; search down → `failed`; chat/embed down → `failed`; analytics down →
  `analytics` null, route unchanged) using inline fake resources + `Agent`/graph.
