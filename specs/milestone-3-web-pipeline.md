# Milestone 3 — Web pipeline: search, fetch, markdown, summarize, ingest

| Estimated effort | Depends on | Enables | PLAN.md sections covered |
|---|---|---|---|
| 4–5 h | M1 (scaffold, `config.py`, `state.py`, `memory/schema.py`, index create/wipe), M2 (embeddings client, chunker, `memory/store.py`, `memory/urls.py`, `embed_query`/`memory_search`/`answer_from_memory` nodes, all 5 routers, compiled graph skeleton, `llm/prompts.py` API) | M4 (real `log_turn` + TurnLogger + classifier + analytics consume the turns this milestone produces; finalises the LLM clients M3 uses for summaries), M5 (replaces the sanitizer pass-through stub with real L3, wraps M3's clients with tenacity, finalises the L2 prompt hardening M3 wires), M6 (the e2e lifecycle test + eval scripts prove the miss→ingest→hit behaviour M3 delivers) | 2 (architecture + graph), 3.2 (web nodes), 5 (search → fetch → markdown → summarise → ingest, all), 12 (test ownership), 13 (M3 row), 14 (Tavily / ddgs / trafilatura verify rows) |

---

## 1. Goal & context

Milestone 3 turns the agent from memory-only into a full **memory-first web agent**. M2 delivered the memory path (embed → KNN → answer from memory) and left the miss branch pointing at a temporary `answer_failure` edge. This milestone builds the entire web branch and rewires the graph so that a **memory miss** flows through the real pipeline:

```
memory_search (miss) → web_search → fetch_pages → ingest_content → answer_from_web → log_turn
```

Concretely it delivers three web modules — `web/search.py`, `web/fetch.py`, `web/to_markdown.py` — and four real graph nodes — `web_search`, `fetch_pages`, `ingest_content`, `answer_from_web` — plus the pass-through sanitizer seam (`security/sanitizer.py`) that Milestone 5 later fills in.

This is the milestone that makes the **core thing the assignment grades** demonstrable end to end: ask a novel question (memory miss → search the web → fetch pages → convert to markdown → summarise → store chunks + metadata → answer with source URLs), then ask the same question again and get a **memory hit** answered without any web call. Assignment requirements advanced:

- *"Miss → web search, fetch top pages, convert to markdown, summarise, store chunks & metadata, answer"* — the whole `web_search → fetch_pages → ingest_content → answer_from_web` chain.
- *"Any web search API; fetch pages; convert to markdown"* — Tavily (raw httpx) with keyless ddgs fallback + httpx streamed fetch + trafilatura markdown.
- *"Grounded answer with source URLs"* — `answer_from_web` emits `sources` with `origin="web"` and the system prompt enforces a "Sources:" section.
- *"Prompt-injection guardrails (basic) — memory poisoning"* — the sanitize-before-store seam is invoked from day one (T3 defence wiring), even though its internals arrive in M5.

**Demoable outcome (PLAN §13):** full miss→ingest→hit lifecycle live, and the first demo transcript captured into `docs/demo_transcript.md`.

> **Proof strategy (Orchestrator Ruling A):** M3 ships **no** retry tests — those land in M5 alongside `reliability.py`. M3's proof is the live miss→ingest→hit demo transcript plus **optional light unit tests for `to_markdown` gating only**. The e2e lifecycle test and the eval scripts are owned by M6.

---

## 2. Scope

### In scope

- **`web/search.py`**
  - `TavilySearcher`: a **raw httpx POST** to `https://api.tavily.com/search`, bearer auth, `include_raw_content=False`, returns `SEARCH_MAX_RESULTS`=8 results as `list[SearchResult]`. Never `tavily-python`.
  - `DdgsSearcher`: keyless DuckDuckGo via `ddgs`, wrapped in `asyncio.to_thread` (ddgs is synchronous).
  - `FallbackProvider`: implements `WebSearcher`, tries Tavily first, falls back to ddgs on quota / auth / transport errors, and logs `provider_used` per turn via structlog.
  - The concrete searcher holds an `httpx.AsyncClient` (protects respx test coverage in M5).
- **`web/fetch.py`**
  - URL filter: scheme allowlist (`http`/`https` only), private-IP/localhost SSRF guard, JS-only domain denylist, max 2 URLs per domain (diversity).
  - `PageFetcher`: `httpx.AsyncClient` streamed GET; connect 5 s / read 10 s / 20 s wall-clock deadline per URL; 2.5 MB streamed body cap; content-type gate (`text/html`, `application/xhtml+xml`, `text/plain`); redirects followed with the **final** URL stored; `asyncio.Semaphore(5)` concurrency; honest User-Agent carrying the repo link; per-URL failures skipped, others continue.
- **`web/to_markdown.py`**
  - trafilatura `extract(html, output_format="markdown", include_tables=True, include_links=False, favor_precision=True)`; recall retry (`favor_recall=True`) if the first pass is empty; reject results < 200 chars; cap at 20 000 chars/page.
- **`security/sanitizer.py`** — created here as a **pass-through stub** (`sanitize(text) -> (text, [])`); internals filled in by M5, `ingest_content` unchanged then (Ruling C).
- **Nodes** (`nodes/`): `web_search`, `fetch_pages`, `ingest_content`, `answer_from_web` implemented for real.
  - `ingest_content`: call the sanitizer seam → per-page nano summary (5–8 sentences from first 6 000 chars, via the analytics LLM) → chunk (1600/200) → batch-embed → store N chunk docs + 1 summary doc per page with `{url, title, fetched_at, source_query, sanitizer_flags}` and `doc_type ∈ {chunk, summary}`; freshness gate skips re-ingest of a URL fetched < 24 h ago; honours `skip_store`; tolerates summary failure (chunk the raw sanitized markdown) and store failure (answering never depends on persistence).
  - `answer_from_web`: build context from **each page's summary + first `WEB_CONTEXT_CHUNKS_PER_PAGE`(=2) chunks per page — never all chunks**; answer from the **in-hand** content (no second Redis round-trip); set `route="memory_miss_web_search"`; on the snippets-only degraded path set `route="degraded_web"`, `degradation="snippets_only"`, and add a low-confidence disclaimer.
- **Graph rewiring** (`graph.py`): remove M2's temporary `memory_search`-miss→`answer_failure` edge and wire the real branch; `route_after_search` and `route_after_fetch` (delivered as pure functions in M2) now route to live nodes.
- **`cli.py` `ask` miss banner + web sources (M3 owns this update)**: M2 shipped `ask` printing a bare `[MEMORY MISS]` (its miss path was the temporary miss→`answer_failure`). Now that the miss path produces a real web answer, M3 updates `ask` to print the **canonical** banner `[MEMORY MISS → searching the web]` (the exact string the M4 `chat` REPL uses) and to list the web `sources` on a miss (M2 printed sources only on a hit). This closes the "who updates `ask`'s miss banner?" gap — the one canonical miss-banner string is `[MEMORY MISS → searching the web]`, used by both `ask` (M3) and `chat` (M4).

### Out of scope (belongs to other milestones — do not build here)

- **Retry / backoff behaviour and its tests** (`test_search_retry.py`, `test_fetch_retry.py`, 429→429→200 assertions, 401→ddgs fast-fail, the "search client holds an `httpx.AsyncClient`" guard assertion) — **M5** owns these; M3's clients rely on the SDK/httpx default timeout only until `reliability.py` wraps them (Ruling A + Ruling D).
- **`utils/reliability.py`, `utils/errors.py` typed errors, and the full degradation matrix** (Redis-down → `degraded_web/redis_down`, LLM-down → `failed`) — **M5**.
- **Real L3 sanitizer internals** (script/style/iframe/comment/`data:`/base64/markdown-image stripping, injection-phrase neutralisation, `content_sha256` provenance, `sanitizer_flags` population) — **M5** replaces the stub internals; `ingest_content` code is frozen now (Ruling C).
- **Full L2 prompt hardening** (per-source provenance headers, tag-breakout escaping, cite-only-`source_url` rule text) — **M5** finalises `llm/prompts.py`; M3 uses the basic `<untrusted_context>` wrapping API fixed in M2 (Ruling E).
- **`TurnLogger`, `log_turn` node body, per-turn classifier, `analytics` CLI, web-stats block in `TurnRecord`, LLM client usage plumbing / structured `parse()` / temperature validation / `max_tokens`** — **M4**; `log_turn` stays a no-op stub through M3 (Ruling B + Ruling D).
- **`guard_input` node + `route_after_guard` activation** — **M5**; graph entry stays `embed_query`, `guard_verdict` defaults to `"allow"` (Ruling F).
- **e2e lifecycle test (`tests/e2e/test_lifecycle.py`), integration store test, eval scripts, `render_graph.py`, `capture_demo.py` automation, conftest fixtures** — **M6** (Ruling A).

### Deferred by design (anti-churn — do not "helpfully" add)

- **Snippet-based salvage / 0.50 weak-memory route** — cut permanently; the only routes are `memory_hit | memory_miss_web_search | degraded_web | blocked | failed` (PLAN §2.1).
- **Output URL-defang allowlist / canary token** — stretch/rejected; do not add to `answer_from_web` (PLAN §7.3, DECISIONS anti-churn).
- **Consulting `robots.txt`** — explicitly a documented limitation, not built (PLAN §5.2).
- **`include_raw_content=True` / using a hosted extractor (Jina/Firecrawl) for fetch+markdown** — the assignment grades our own fetch+markdown step; keep it in-house (PLAN §5.1, §5.3).
- **Per-chunk `topic` tag** — classification happens later in `log_turn`; turn records are the sole analytics source (PLAN §4.2).
- **HNSW / SVS-VAMANA index tuning** — FLAT stays; growth-path note only (DECISIONS).

---

## 3. Prerequisites & interfaces consumed

Everything below must already exist (from M1/M2) before M3 starts. Signatures are the contracts M3 codes against.

### From M1

- **`config.py` — `Settings`** (pydantic-settings). M3 reads (defaults verbatim from PLAN §10.3 / IMPLEMENTATION_GUIDE §5.1):
  `TAVILY_API_KEY` (optional, blank ⇒ keyless), `SEARCH_MAX_RESULTS=8`, `FETCH_TOP_N=5`, `FETCH_CONCURRENCY=5`, `CONNECT_TIMEOUT_S=5`, `READ_TIMEOUT_S=10`, `PAGE_DEADLINE_S=20`, `FETCH_MAX_BYTES=2500000`, `FRESHNESS_WINDOW_SECONDS=86400`, `CHUNK_SIZE_CHARS=1600`, `CHUNK_OVERLAP_CHARS=200`, `MAX_CHUNKS_PER_PAGE=25`, `WEB_CONTEXT_CHUNKS_PER_PAGE=2`, `MEMORY_TTL_SECONDS=604800`, `MEMORY_TOP_K=5`, `SIMILARITY_THRESHOLD=0.7`, `EMBEDDING_MODEL=text-embedding-3-small`, `EMBEDDING_DIM=1536`, `ANALYTICS_MODEL=gpt-5.4-nano`, `CONVERSATION_MODEL=gpt-5.4-mini`.
- **`state.py`** — `AgentState`, `Route`, and the TypedDicts `SearchResult`, `FetchedDoc`, `Chunk`, `SourceRef`, `MemoryHit` (see §6 for the fields M3 writes).
- **`memory/schema.py`** — the `web_memory` FLAT/cosine/float32 HASH index (prefix `chunk:`) and `doc:` meta hash convention; `wipe-memory` command.

### From M2

- **`llm/clients.py`**
  ```python
  class Embedder(Protocol):
      dim: int
      async def embed(self, texts: list[str]) -> list[list[float]]: ...

  class CompletionResult(NamedTuple):
      text: str
      usage: dict            # {"input_tokens": int, "output_tokens": int, "model": str}

  class ChatLLM(Protocol):
      async def complete(self, system: str, messages: list[dict]) -> CompletionResult: ...
      async def parse(self, system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel, dict]: ...
  ```
  M3 consumes `resources.embedder.embed(...)` (batch chunk embeddings) and `resources.analytics_llm.complete(...)` (per-page nano summaries). Clients are constructed `AsyncOpenAI(max_retries=0, timeout=45.0)`; **no tenacity wrapping until M5** (Ruling D — the single call-site seam must already exist so M5 is a drop-in).
- **`memory/store.py` — `MemoryStore` Protocol** (M3 calls `store`, and `knn` is used by M2's `memory_search`):
  ```python
  class MemoryStore(Protocol):
      async def knn(self, vector: list[float], k: int) -> list[MemoryHit]: ...   # RAW top-k, NO filtering
      async def store(self, page: FetchedDoc, chunks: list[Chunk], vectors: list[list[float]],
                      source_query: str, flags: list[str]) -> list[str]: ...
  ```
  `store` writes N chunk docs + 1 summary doc under prefix `chunk:` and the non-indexed `doc:{url_hash}` meta hash, applies per-key `EXPIRE` (`MEMORY_TTL_SECONDS`), and deletes stale `chunk:{hash}:*` on re-ingest via `doc:{hash}.num_chunks`. Returns the stored chunk ids.
- **`memory/urls.py`** — `canonicalize(url) -> str` (lowercase scheme/host, strip `#fragment` and `utm_*`) and `url_hash(canonical) -> str` (`sha256(...)[:16]`). Used to compute keys and the freshness lookup.
- **`memory/chunking.py`** — the markdown-aware `RecursiveCharacterTextSplitter` wrapper, exposed as the callable `chunk_markdown(text) -> list[str]` (M2's contract; invoked in §6.10): 1600 chars / 200 overlap, 100-char floor, max 25 chunks/page. It returns **plain chunk strings**, not `Chunk` records; `ingest_content` wraps them into `Chunk` records (adding `chunk_id`/`url`/`title`/`chunk_index`) before calling `store(..., chunks=chunks, ...)` (§6.10).
- **`routers.py`** — all five pure routers already delivered + unit-tested in M2. M3 activates two:
  ```python
  def route_after_search(s): return "fetch_pages" if s["search_results"] else "answer_failure"
  def route_after_fetch(s):  return "ingest_content" if s["fetched_docs"] else "answer_from_web"
  ```
- **`llm/prompts.py`** — `build_system_prompt() -> str` (no args) and `wrap_context(sources, origin) -> str` (basic `<untrusted_context>` wrapping). Both signatures — including `wrap_context`'s `origin` argument — are the FINAL API fixed in M2 (Ruling E); M5 finalises the full L2 body without changing them. `answer_from_web` calls `wrap_context(sources, origin="web")` from day one and is unchanged into M5.
- **`resources.py` / `interfaces.py`** — `AgentResources` (frozen dataclass) already exposes `searcher: WebSearcher` and `fetcher: PageFetcher` slots. M3 populates them with the real implementations. `AgentResources` also carries `settings, memory, embedder, chat_llm, analytics_llm, turn_logger`.
- **`graph.py`** — `build_graph(resources)` compiles one async `StateGraph`. The M2 skeleton has **5 nodes** (`embed_query`, `memory_search`, `answer_from_memory`, `answer_failure`, and the no-op `log_turn` stub) with the miss branch temporarily mapped to `answer_failure` (Ruling B) — the four web nodes are **not** present yet. M3 **creates and adds** `web_search`, `fetch_pages`, `ingest_content`, `answer_from_web`, and **remaps** `route_after_memory`'s `"web_search"` path from `answer_failure` to the real `web_search` node (M2 §6.12's note pre-authorises exactly this remap).

### Seams touching this milestone (state them so the six files interlock)

- **Ruling B** — M2 wired a **temporary** `memory_search`-miss → `answer_failure` edge and a **no-op `log_turn` stub**. M3 removes that temporary edge and wires the real web branch; `log_turn` stays a no-op stub (M4 fills it).
- **Ruling C** — `ingest_content` calls `sanitize(text) -> (clean_text, flags)` from `security/sanitizer.py`; M3 ships that function as a **pass-through stub** (`return text, []`). M5 replaces its internals with the real L3; `ingest_content` code does not change in M5.
- **Ruling D** — M3 uses the **analytics client** for nano summaries via the existing thin wrapper (`analytics_llm.complete`). M4 finalises client usage plumbing / `parse()` / temperature validation / `max_tokens`. The single call-site seam must exist now so M5's tenacity wrap is a drop-in.
- **Ruling E** — `answer_from_web` uses `build_system_prompt`/`wrap_context` from M2's `llm/prompts.py`; M5 finalises the full L2 hardening. The module API is fixed.
- **Ruling F** — `guard_input`/`route_after_guard` activate in M5; graph entry stays `embed_query`; `guard_verdict` defaults to `"allow"`.
- **Ruling G** — the `skip_store` state field exists from M2; `ingest_content` honours it from day one (Redis-down and flagged-query paths set it; when set, ingest skips persistence but still summarises + chunks for the in-hand answer).

---

## 4. Interfaces provided

Contracts this milestone exposes to later milestones.

| Symbol | File | Contract | Consumed by / replaced by |
|---|---|---|---|
| `TavilySearcher` | `web/search.py` | `async search(query, k) -> list[SearchResult]`; holds an `httpx.AsyncClient` | M5 wraps its httpx call with the tenacity Tavily policy; M5's guard test asserts it holds an `httpx.AsyncClient` |
| `DdgsSearcher` | `web/search.py` | `async search(query, k) -> list[SearchResult]` via `asyncio.to_thread` | M5 (fast-fail fallback target) |
| `FallbackProvider` | `web/search.py` | implements `WebSearcher`; Tavily→ddgs on quota/auth/transport; logs `provider_used` | resources wiring; M5 retry policies |
| `filter_urls(urls, settings) -> list[str]` | `web/fetch.py` | scheme allowlist + SSRF guard + JS-only denylist + max 2/domain, order-preserving | `fetch_pages` node; M5 (unchanged) |
| `PageFetcher` | `web/fetch.py` | `async fetch(urls) -> list[FetchedDoc]` (markdown filled, `summary=None`, `ok` set) | `fetch_pages` node; M5 wraps per-URL fetch with the tenacity page-fetch policy |
| `to_markdown(html) -> str \| None` | `web/to_markdown.py` | trafilatura extract + recall retry + <200-char reject + 20k cap | `PageFetcher`; optional M3 unit test; unchanged after |
| `sanitize(text) -> tuple[str, list[str]]` | `security/sanitizer.py` | **PASS-THROUGH STUB** — returns `(text, [])` | **M5 replaces internals**; `ingest_content` code frozen |
| `web_search` / `fetch_pages` / `ingest_content` / `answer_from_web` nodes | `nodes/` | real graph nodes returning partial state updates | graph; M4 (`log_turn` reads their state); M6 (e2e lifecycle) |
| rewired miss branch | `graph.py` | `memory_search`→`web_search`→`fetch_pages`→(`ingest_content`→)`answer_from_web`→`log_turn` | M6 e2e; `render_graph.py` diagram |

> **Spec note:** PLAN.md names `PageFetcher` in `AgentResources` but does not print its method signature. Chosen minimal-assumption default: `async def fetch(self, urls: list[str]) -> list[FetchedDoc]:` returning one `FetchedDoc` per successfully fetched-and-extracted URL (`markdown` populated, `summary=None`, `ok=True`; failed URLs are omitted rather than returned with `ok=False`). `filter_urls` is applied by the `fetch_pages` node before calling `fetch`. Change freely if a later milestone prefers a different split.

---

## 5. Functional requirements

Each is one testable statement with an explicit acceptance criterion. IDs are stable.

**Search**

- **FR-M3-01** — `TavilySearcher.search(query, k)` issues a raw `httpx` POST to `https://api.tavily.com/search` with an `Authorization: Bearer <TAVILY_API_KEY>` header and JSON body including `"include_raw_content": false` and `"max_results": k`. *Accept:* with `SEARCH_MAX_RESULTS=8`, a mocked 200 response yields exactly 8 `SearchResult` items each with `url`, `title`, `snippet`, `rank`; the request body contains `include_raw_content=false`.
- **FR-M3-02** — the Tavily searcher holds a reusable `httpx.AsyncClient` (not `tavily-python`, not `requests`). *Accept:* `isinstance(searcher._client, httpx.AsyncClient)` is true (the assertion M5's guard test formalises); no import of `tavily` anywhere in `web/search.py`.
- **FR-M3-03** — `DdgsSearcher.search(query, k)` runs the synchronous `ddgs` call inside `asyncio.to_thread`, needs no key, and returns up to `k` `SearchResult` items. *Accept:* calling it from an event loop does not block; results map `title/href/body` → `title/url/snippet` with `rank` assigned by order.
- **FR-M3-04** — `FallbackProvider` implements `WebSearcher`, calls Tavily first, and falls back to `DdgsSearcher` on quota/auth/transport errors, logging `provider_used` for the turn; the `web_search` node writes that provider into `state["search_provider"]` (`"tavily"`/`"ddgs"`) for the turn log. *Accept:* when Tavily raises an auth/quota/transport error the ddgs path returns results, the structlog line records `provider_used="ddgs"`, and `state["search_provider"] == "ddgs"`; on Tavily success both are `"tavily"`.
- **FR-M3-05** — an empty search result set routes to `answer_failure`. *Accept:* when both providers return `[]`, `state["search_results"] == []` and `route_after_search(state) == "answer_failure"`.

**URL filtering & fetch**

- **FR-M3-06** — `filter_urls` accepts only `http`/`https` schemes. *Accept:* `ftp://…`, `file://…`, `data:…`, `javascript:…` are dropped; `http://…` and `https://…` survive.
- **FR-M3-07** — `filter_urls` rejects localhost and private/loopback/link-local IP literals (mini-SSRF guard). *Accept:* `http://localhost/x`, `http://127.0.0.1/x`, `http://10.0.0.5/x`, `http://192.168.1.1/x`, `http://169.254.169.254/x`, `http://[::1]/x` are all dropped; a public host survives.
- **FR-M3-08** — `filter_urls` drops JS-only denylisted domains. *Accept:* a `youtube.com` / `x.com` / `facebook.com` URL is removed; a normal article domain survives.
- **FR-M3-09** — `filter_urls` keeps at most 2 URLs per registrable domain, order-preserving. *Accept:* given 3 URLs on `example.com` and 1 on `other.com`, the output keeps the first 2 `example.com` URLs and the `other.com` URL.
- **FR-M3-10a** — `PageFetcher` is *configured* with connect 5 s / read 10 s (`httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=READ_TIMEOUT_S, …)`) and a hard `PAGE_DEADLINE_S`-second wall-clock wrapper (`asyncio.wait_for(fetch_one, PAGE_DEADLINE_S)`) per URL. *Accept:* constructing a `PageFetcher` wires those values from `CONNECT_TIMEOUT_S=5`/`READ_TIMEOUT_S=10`/`PAGE_DEADLINE_S=20` — a construction/inspection check (no network). Per Ruling A this assertion is **M5-owned** (`tests/unit/test_fetch_retry.py`, alongside the other httpx-wiring guards); M3 delivers the wiring, not the test.
- **FR-M3-10b** — a URL exceeding the wall-clock deadline is abandoned and skipped while the others continue (behaviour). *Accept:* a URL stalling past `PAGE_DEADLINE_S` is skipped and the rest complete; behaviour test tagged `@manual`, **M5-owned** (`tests/unit/test_fetch_retry.py`).
- **FR-M3-11** — the fetch body is capped at `FETCH_MAX_BYTES=2500000` while streaming. *Accept:* a response exceeding 2 500 000 bytes stops reading at the cap and the page is skipped (not truncated-and-kept).
- **FR-M3-12** — the fetch applies a content-type gate accepting only `text/html`, `application/xhtml+xml`, `text/plain`. *Accept:* an `application/pdf` or `image/png` response is skipped; a `text/html` response proceeds.
- **FR-M3-13** — redirects are followed and the **final** resolved URL is stored on the `FetchedDoc`. *Accept:* a 301→200 chain results in `FetchedDoc.url == <final URL>`, not the original.
- **FR-M3-14** — concurrent fetching is bounded by `asyncio.Semaphore(FETCH_CONCURRENCY=5)`. *Accept:* at most 5 fetches are in flight simultaneously when given ≥ 5 filtered URLs.
- **FR-M3-15** — requests carry an honest User-Agent that includes the repo link. *Accept:* every fetch request has a `User-Agent` header matching the configured identifier and containing a URL.
- **FR-M3-16** — a single URL failing (timeout, non-HTML, oversize, non-2xx) is skipped and the rest continue. *Accept:* given 3 URLs where 1 fails, `fetch` returns the 2 successful `FetchedDoc`s.

**Markdown**

- **FR-M3-17** — `to_markdown(html)` calls `trafilatura.extract(html, output_format="markdown", include_tables=True, include_links=False, favor_precision=True)`. *Accept:* the call uses exactly those keyword arguments; tables survive, inline links are dropped.
- **FR-M3-18** — if the precision pass returns empty, `to_markdown` retries once with `favor_recall=True`. *Accept:* first call empty + second call non-empty ⇒ the non-empty recall result is returned.
- **FR-M3-19** — a markdown result shorter than 200 characters is rejected (page treated as unusable). *Accept:* a 199-char result returns `None` (page skipped); a 200-char result is kept.
- **FR-M3-20** — markdown is capped at 20 000 characters per page. *Accept:* a 25 000-char extraction is truncated to exactly 20 000 chars.

**Ingest**

- **FR-M3-21** — `ingest_content` calls `sanitize(markdown) -> (clean, flags)` before chunking/embedding, and stores the flags with each record. *Accept:* the pass-through stub returns `(markdown, [])`; the store call receives `flags=[]`; the sanitize call happens strictly before chunking (order is the T3 defence).
- **FR-M3-22** — per fetched page, `ingest_content` produces a 5–8 sentence summary from the **first 6 000 characters** using the analytics LLM. *Accept:* `analytics_llm.complete` is called with input capped at 6 000 chars; the resulting summary is attached to the page and stored as a `doc_type="summary"` record.
- **FR-M3-23** — chunks are produced (1600/200, ≤ 25/page), batch-embedded, and stored as `doc_type="chunk"` records alongside one `doc_type="summary"` record, each carrying `{url, title, fetched_at, source_query, sanitizer_flags}`. *Accept:* a page yielding 3 chunks stores 3 `chunk:{hash}:{0..2}` + 1 `chunk:{hash}:summary`; `stored_chunk_ids` reflects them; keys use `url_hash(canonicalize(final_url))`.
- **FR-M3-24** — the freshness gate skips re-ingest of a URL whose stored `fetched_at` is < `FRESHNESS_WINDOW_SECONDS`=86400 (24 h) old. *Accept:* re-ingesting a URL fetched 1 h ago performs no re-embed/re-store for that URL; a URL fetched 25 h ago is re-ingested.
- **FR-M3-25** — `ingest_content` honours `skip_store`: when true it skips all persistence but still summarises + chunks for the in-hand answer. *Accept:* with `skip_store=True`, no Redis writes occur, `stored_chunk_ids == []`, yet `chunks` and per-page summaries are still populated in state.
- **FR-M3-26** — summary failure is tolerated: if the summary LLM call fails, ingestion continues by chunking the raw sanitized markdown (summary omitted). *Accept:* a raised summary error leaves `chunks` populated, `route` unaffected, and the turn still answerable; no summary doc is stored for that page.
- **FR-M3-27** — store failure is tolerated: answering never depends on persistence. *Accept:* a raised store error is caught; `state["answer"]` is still produced from the in-hand chunks; the turn does not route to `failed` because of it.

**Answer from web**

- **FR-M3-28** — `answer_from_web` builds context from each page's summary + first `WEB_CONTEXT_CHUNKS_PER_PAGE`=2 chunks per page, never all chunks. *Accept:* a page with 10 chunks contributes its summary + exactly its first 2 chunks to the prompt context.
- **FR-M3-29** — on the normal path `answer_from_web` sets `route="memory_miss_web_search"` and emits `sources` with `origin="web"` covering the pages used. *Accept:* `state["route"] == "memory_miss_web_search"`; `state["sources"]` is non-empty and every entry has `origin="web"`; the answer text ends with a "Sources:" section (per the M2 prompt).
- **FR-M3-30** — the snippets-only degraded path: when no page was fetched, `answer_from_web` answers from search snippets, sets `route="degraded_web"`, `degradation="snippets_only"`, and includes a low-confidence disclaimer. *Accept:* with `fetched_docs == []` and non-empty `search_results`, `route == "degraded_web"`, `degradation == "snippets_only"`, and the answer contains the disclaimer text.
- **FR-M3-31** — on a miss, the answer uses the **in-hand** chunks/summaries directly with **no second Redis round-trip**. *Accept:* `answer_from_web` performs zero `memory.knn` / Redis read calls; the context is assembled from `state["fetched_docs"]` + `state["chunks"]` only.

**Graph rewiring**

- **FR-M3-32** — the graph miss branch is rewired: `memory_search` (miss) → `web_search` → `fetch_pages` → `ingest_content` → `answer_from_web` → `log_turn`, with `route_after_search` and `route_after_fetch` active and M2's temporary miss→`answer_failure` edge removed. *Accept:* `build_graph(resources)` compiles; `draw_mermaid()` shows the four M3 nodes on the miss path; a miss reaches `answer_from_web`; every M3-active route (`memory_hit`, `memory_miss_web_search`, `degraded_web`, `failed`) stays reachable. *(Note:* `blocked` becomes reachable only when `guard_input`/`route_after_guard` activate in M5 — Ruling F; in M3 the graph entry is `embed_query` and `guard_verdict` defaults to `"allow"`, so no M3 path sets `route="blocked"`.)

---

## 6. Technical specification

Self-contained: a developer new to this repo builds M3 from this section without opening PLAN.md.

### 6.1 File paths created / modified

```
src/memagent/
├── web/
│   ├── search.py        # NEW  — TavilySearcher, DdgsSearcher, FallbackProvider
│   ├── fetch.py         # NEW  — filter_urls(), PageFetcher
│   └── to_markdown.py   # NEW  — to_markdown()
├── security/
│   └── sanitizer.py     # NEW  — sanitize() PASS-THROUGH STUB (Ruling C)
├── nodes/               # web_search / fetch_pages / ingest_content / answer_from_web implemented
├── graph.py             # MODIFIED — rewire miss branch (Ruling B)
├── resources.py         # MODIFIED — construct real searcher + fetcher into AgentResources
tests/unit/
└── test_to_markdown.py  # NEW (OPTIONAL, M3-owned) — to_markdown gating only
docs/
├── demo_transcript.md   # NEW — captured miss→ingest→hit session
└── ai_prompts/milestone-3.md  # NEW — this milestone's prompt log
```

### 6.2 Route enum (verbatim; single definition, unchanged by M3)

```python
Route = Literal["memory_hit", "memory_miss_web_search", "degraded_web", "blocked", "failed"]
```

`degradation` field: `"redis_down" | "snippets_only" | None`. M3 writes `route="memory_miss_web_search"` (normal miss) and `route="degraded_web"` + `degradation="snippets_only"` (all-fetch-fail). The `redis_down` degradation label and its `degraded_web` routing are finalised in M5's degradation matrix; in M3 a `skip_store=True` miss still answers and is labelled `memory_miss_web_search`.

### 6.3 State fields M3 reads/writes (verbatim TypedDicts)

```python
class SearchResult(TypedDict):  url: str; title: str; snippet: str; rank: int
class FetchedDoc(TypedDict):    url: str; title: str; markdown: str; summary: str | None; ok: bool
class Chunk(TypedDict):         chunk_id: str; text: str; url: str; title: str; chunk_index: int
class SourceRef(TypedDict):     url: str; title: str; origin: Literal["memory", "web"]
```

`AgentState` fields M3 touches:
`query`, `sanitized_query`, `skip_store` (read), `search_results` + `search_provider` (write in `web_search`), `fetched_docs` (write in `fetch_pages`; annotate summaries in `ingest_content`), `chunks` + `stored_chunk_ids` (write in `ingest_content`), `route` + `degradation` + `answer` + `sources` (write in `answer_from_web`), `errors` (append), `latency_ms`/`tokens` (merged reducers). (`search_provider` is the M2-declared channel that feeds `TurnRecord.web.provider` in M4 — §6.6.)

> **Spec note:** PLAN's single-writer rule lists only `errors`/`latency_ms`/`tokens` as merged. `fetched_docs` is created by `fetch_pages` and then re-emitted by `ingest_content` with per-page `summary` populated. This is deterministic because the two nodes never run concurrently and `ingest_content` is strictly downstream; LangGraph replaces the `fetched_docs` key with the ingest version. Documented here to avoid a later "who owns `fetched_docs`?" churn.

### 6.4 Protocols (verbatim, consumed)

```python
class WebSearcher(Protocol):
    async def search(self, query: str, k: int) -> list[SearchResult]: ...

class Embedder(Protocol):
    dim: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class MemoryStore(Protocol):
    async def knn(self, vector: list[float], k: int) -> list[MemoryHit]: ...   # RAW top-k, NO filtering
    async def store(self, page: FetchedDoc, chunks: list[Chunk], vectors: list[list[float]],
                    source_query: str, flags: list[str]) -> list[str]: ...
```

`PageFetcher` (see §4 spec note):

```python
class PageFetcher(Protocol):
    async def fetch(self, urls: list[str]) -> list[FetchedDoc]: ...
```

### 6.5 Active routing functions (verbatim)

```python
def route_after_search(s): return "fetch_pages" if s["search_results"] else "answer_failure"
def route_after_fetch(s):  return "ingest_content" if s["fetched_docs"] else "answer_from_web"
```

### 6.6 Search — `web/search.py`

Tavily request shape (raw httpx POST, PLAN §5.1 / §14):

```python
# POST https://api.tavily.com/search
# headers: {"Authorization": f"Bearer {settings.tavily_api_key}", "Content-Type": "application/json"}
# json body:
{
    "query": query,
    "max_results": k,              # k = SEARCH_MAX_RESULTS = 8
    "include_raw_content": False,  # deliberate: the assignment grades OUR fetch+markdown step
}
# response .json()["results"] -> [{"title", "url", "content"/snippet, ...}]
```

`FallbackProvider` fast-fails Tavily on 400/401/403 (auth) and on quota/transport errors → ddgs, and records `provider_used` (`"tavily"`/`"ddgs"`). In M3 the switch is a plain `try/except` on the mapped exceptions; the tenacity retry policy (3 attempts, jitter max 8 s, 10 s timeout / 5 s connect) is added in M5 — do **not** add retries here.

The `web_search` **node** reads `FallbackProvider.provider_used` (expose it as an attribute set on each `search`, or return it alongside the results) and **writes it into `state["search_provider"]`** (the M2-declared channel), so M4's `build_turn_record` can populate `TurnRecord.web.provider` (PLAN §8.2). Without this write `web.provider` is always `None`.

> **Spec note:** PLAN gives the JSON field for the snippet as the human "content"/snippet; map the Tavily result body field to `SearchResult.snippet`. If the live API field name differs at build time, adjust the mapping only — verify against Tavily docs (PLAN §14).

### 6.7 Fetch — `web/fetch.py`

- `filter_urls(urls, settings)` — order-preserving; drops non-`http(s)` schemes; drops hosts that are `localhost`, an IP literal in a private/loopback/link-local/reserved range (use `ipaddress`), or a denylisted JS-only domain; caps at 2 URLs per registrable domain.
- Constants:
  ```python
  ALLOWED_SCHEMES = {"http", "https"}
  ACCEPTED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
  JS_ONLY_DENYLIST = {"youtube.com", "youtu.be", "x.com", "twitter.com",
                      "facebook.com", "instagram.com", "tiktok.com"}   # spec note below
  USER_AGENT = "memagent/1.0 (+https://github.com/<owner>/memory-first-agent)"  # spec note below
  ```
- `PageFetcher.fetch(urls)` — `httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=READ_TIMEOUT_S, ...))`; `asyncio.Semaphore(FETCH_CONCURRENCY)`; per-URL `asyncio.wait_for(..., PAGE_DEADLINE_S)`; stream the body and abort at `FETCH_MAX_BYTES`; content-type gate; store `str(response.url)` (final) as `FetchedDoc.url`; call `to_markdown(html)` and keep only pages with non-`None` markdown; `summary=None`, `ok=True`. The node takes the first `FETCH_TOP_N`=5 of the filtered list before fetching.

> **Spec note:** PLAN says the SSRF guard rejects "localhost/private IPs" and lists the denylist as "youtube/x/facebook/…" and the User-Agent as "honest … with repo link" without exact strings. Chosen minimal-assumption defaults are above (registrable-domain matching for the denylist; literal-IP + `localhost` checks for SSRF, with optional best-effort DNS resolution of hostnames left to M5 hardening). Change the denylist set, the UA string, and the SSRF depth freely.

### 6.8 Markdown — `web/to_markdown.py`

```python
import trafilatura

MIN_MARKDOWN_CHARS = 200      # reject cookie-wall / JS-shell pages
MAX_MARKDOWN_CHARS = 20_000   # cap token cost on huge articles

def to_markdown(html: str) -> str | None:
    md = trafilatura.extract(html, output_format="markdown", include_tables=True,
                             include_links=False, favor_precision=True)
    if not md:
        md = trafilatura.extract(html, output_format="markdown", include_tables=True,
                                 include_links=False, favor_recall=True)
    if not md or len(md) < MIN_MARKDOWN_CHARS:
        return None
    return md[:MAX_MARKDOWN_CHARS]
```

> **Spec note:** PLAN gives no env names for the 200/20 000 char limits or the 6 000-char summary input, so they are module constants (`MIN_MARKDOWN_CHARS`, `MAX_MARKDOWN_CHARS`, `SUMMARY_INPUT_CHARS=6000`). If you prefer env-tunability, add them to `Settings` — but PLAN's `.env.example` does not list them. Two more literals referenced by later sections are likewise **named module constants, not invented in this spec**: `SUMMARY_SYSTEM` (the nano-summary system prompt used in §6.10 — a short 5–8-sentence summarisation instruction; its exact wording is authored at implementation and, like all prompt text, is finalised under M5's L2 hardening, Ruling E) and `LOW_CONFIDENCE_DISCLAIMER` (the exact string `answer_from_web` prepends on the snippets-only path, §6.11 / FR-M3-30). Acceptance checks substring-match the **constant symbol**, not a hard-coded string, so no wording is pinned prematurely.

### 6.9 Sanitizer seam — `security/sanitizer.py` (PASS-THROUGH STUB, Ruling C)

```python
def sanitize(text: str) -> tuple[str, list[str]]:
    """L3 sanitize-before-store. M3 stub: pass-through.
    M5 replaces the internals (strip script/style/iframe, HTML comments, data: URIs,
    long base64, markdown images; neutralise injection phrases to
    '[removed-suspicious-instruction]'; return provenance flags).
    ingest_content must NOT change when M5 lands."""
    return text, []
```

### 6.10 `ingest_content` node contract

Order is load-bearing (the T3 defence): sanitize → summarise → chunk → embed → store.

1. For each `FetchedDoc` with `ok` and markdown:
   - `clean, flags = sanitize(doc["markdown"])`
   - **Freshness gate:** compute `h = url_hash(canonicalize(doc["url"]))`; if `doc:{h}.fetched_at` exists and is `< FRESHNESS_WINDOW_SECONDS` old, skip re-embed/re-store for that URL (still keep its already-in-hand markdown/summary for answering).
   - **Summary:** `summary = analytics_llm.complete(SUMMARY_SYSTEM, [{"role":"user","content": clean[:6000]}]).text` (5–8 sentences). *(After M4 the analytics client caps output at `max_tokens=256`, which is sufficient for a 5–8-sentence summary — ≈120–210 tokens — see M4 §6.2; before M4 it ran under the default 2048.)* On failure, set `summary=None` and continue (FR-M3-26).
   - **Chunk:** `chunk_texts = chunk_markdown(clean)` → `list[str]` (1600/200, ≤ 25), then wrap into `Chunk` records: `chunks = [Chunk(chunk_id=f"{h}:{i}", text=t, url=doc["url"], title=doc["title"], chunk_index=i) for i, t in enumerate(chunk_texts)]` (`chunk_markdown` returns strings; `store` takes `list[Chunk]`).
   - **Embed:** batch-embed `([summary] if summary else []) + chunk_texts` via `embedder.embed`, so **`vectors[0]` is the summary embedding when a summary exists and `vectors[1:]` align 1:1 to `chunks`**; when `summary is None`, `vectors` aligns 1:1 to `chunks` (the §6.7 / M2 store alignment contract).
   - **Store (unless `skip_store`):** `stored = await memory.store(page=doc_with_summary, chunks=chunks, vectors=vectors, source_query=state["query"], flags=flags)`; wrap in try/except and tolerate failure (FR-M3-27). `store` writes `chunk:{h}:summary` (text `page["summary"]`, embedding `vectors[0]`) only when the page has a summary, plus `chunk:{h}:{i}`; meta `doc:{h}`.
2. Emit `{"fetched_docs": <enriched with summary>, "chunks": <all chunks>, "stored_chunk_ids": stored_or_[]}`.

If `skip_store` is true, do everything except the `store` call; `stored_chunk_ids=[]` (FR-M3-25).

### 6.11 `answer_from_web` node contract

- **Normal path** (chunks/fetched_docs present): for each page build `summary + first WEB_CONTEXT_CHUNKS_PER_PAGE(=2) chunks` (FR-M3-28); wrap with `wrap_context(sources, origin="web")` (M2 basic wrapping; `origin="web"` is the fixed API arg, Ruling E); call `chat_llm.complete(build_system_prompt(), messages)`; set `answer`, `sources=[SourceRef(url, title, origin="web") …]`, `route="memory_miss_web_search"`.
  - **None-summary handling:** if a page's `summary` is `None` (the summary LLM failed during ingest — FR-M3-26 allows this while chunks are still produced), omit the summary line for that page and use only its first `WEB_CONTEXT_CHUNKS_PER_PAGE` chunks; the page still contributes and the answer stays grounded with `origin="web"` sources.
- **Snippets-only path** (`fetched_docs == []`): assemble context from `search_results` snippets; prepend a low-confidence disclaimer; set `route="degraded_web"`, `degradation="snippets_only"` (FR-M3-30).
- **No second Redis round-trip** — context comes only from in-hand state (FR-M3-31).

### 6.12 Environment variables (defaults verbatim)

```bash
TAVILY_API_KEY=                  # optional — blank = keyless DuckDuckGo fallback
SEARCH_MAX_RESULTS=8
FETCH_TOP_N=5
FETCH_CONCURRENCY=5
CONNECT_TIMEOUT_S=5
READ_TIMEOUT_S=10
PAGE_DEADLINE_S=20
FETCH_MAX_BYTES=2500000
FRESHNESS_WINDOW_SECONDS=86400   # don't re-fetch a URL seen within 24h
CHUNK_SIZE_CHARS=1600
CHUNK_OVERLAP_CHARS=200
MAX_CHUNKS_PER_PAGE=25
WEB_CONTEXT_CHUNKS_PER_PAGE=2    # answer_from_web: summary + this many chunks per page
MEMORY_TTL_SECONDS=604800        # 7 days; 0 disables
ANALYTICS_MODEL=gpt-5.4-nano     # nano — used for page summaries in M3
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
```

### 6.13 Dependency pins used by M3 (verbatim, verified 2026-07-04)

```
httpx>=0.28                 # search POST + streamed fetch
trafilatura>=2.1,<3         # HTML → markdown
ddgs>=9,<10                 # keyless fallback (9.14.4 verified alive); DDGS().text()
langchain-text-splitters    # markdown-aware chunker (consumed from M2)
openai>=2                   # analytics_llm summaries + embeddings (consumed from M2)
```

Dropped / never add: `tavily-python` (invisible to respx), `markdownify` (trafilatura wins), `fakeredis`.

### 6.13a `cli.py` — `ask` miss banner + web sources (M3 update)

M2's `ask` printed `[MEMORY HIT sim=X.XX]` on a hit and a bare `[MEMORY MISS]` on its temporary miss→`answer_failure` path, and listed sources only on a hit. M3 updates the `ask` command so that, once the real web miss path exists:

- a miss prints the **canonical banner** `[MEMORY MISS → searching the web]` (byte-identical to the M4 `chat` REPL banner — the single canonical miss-banner string across all commands), and
- the web `sources` (from `TurnResult.sources`, each `origin="web"`) are printed on a miss, rendered as `(web) {title} <{url}>`.

A hit still prints `[MEMORY HIT sim=X.XX]` + `(memory)` sources. This is the sole owner of the `ask` miss-banner/source-printing update; M4 does not re-touch it.

### 6.14 Exact commands

```bash
uv run memagent wipe-memory                       # start from an empty index
uv run memagent ask "<novel question>"            # expect [MEMORY MISS → searching the web] + web Sources
uv run memagent ask "<same question verbatim>"    # expect [MEMORY HIT sim=0.9x] + memory Sources, no web call
OPENAI_API_KEY=dummy uv run python -c "from memagent.app import build_resources; from memagent.graph import build_graph; print(build_graph(build_resources()).get_graph().draw_mermaid())"   # confirm the miss branch inline (dummy key: AsyncOpenAI needs a non-empty key at construction; scripts/render_graph.py itself ships in M6)
uv run pytest tests/unit/test_to_markdown.py      # optional M3 gating tests
uv run ruff check src/memagent/web src/memagent/nodes src/memagent/security/sanitizer.py
```

---

## 7. BDD acceptance scenarios

Gherkin below. Tags: `@unit` (no network/docker/keys), `@integration` (real Redis), `@e2e` (whole system), `@manual` (live keys / demo).

> **These scenarios are behavioural acceptance criteria for the code M3 delivers — they are NOT all automated in M3.** Per Ruling A, M3 builds exactly one automated test file (`tests/unit/test_to_markdown.py`, the `@unit` `to_markdown` gating scenarios) plus the `@manual` demo transcript. Every other scenario is automated in the milestone that owns its test file (PLAN §12): the **search/fetch** scenarios (including URL filtering and the httpx-wiring guards) land in **M5**'s respx suites (`test_search_retry.py` / `test_fetch_retry.py`) and `test_guardrails.py`; the **`ingest_content` / `answer_from_web`** node scenarios are proven by **M6**'s e2e lifecycle test (`tests/e2e/test_lifecycle.py`) and the `@integration` store test (`test_redis_store.py`), with the sanitize seam covered by **M5**'s `test_sanitizer.py`. Each `Feature` below carries a `#`-comment naming its owning milestone/file; the pre-existing `# M5-owned …` / `# M6-owned …` comments on individual scenarios are authoritative where present.

```gherkin
Feature: Web search provider selection and fallback
  # Ownership (Ruling A / PLAN §12): the @unit scenarios here are M5-owned (tests/unit/test_search_retry.py, respx); the httpx.AsyncClient guard is M5 test_guardrails.py. M3 delivers the code, not these tests.

  @unit
  Scenario: Tavily returns eight results via a raw httpx POST
    Given SEARCH_MAX_RESULTS is 8
    And a mocked 200 response from https://api.tavily.com/search with 8 results
    When TavilySearcher.search("redis vector search", 8) runs
    Then the POST body contains "include_raw_content": false and "max_results": 8
    And exactly 8 SearchResult items are returned each with url, title, snippet, rank

  @unit
  Scenario: The Tavily searcher holds an httpx.AsyncClient
    # M5-owned tests/unit/test_guardrails.py (guard assertion)
    Given a TavilySearcher
    When it is constructed
    Then its HTTP client is an instance of httpx.AsyncClient
    And the module does not import the "tavily" package

  @unit
  Scenario: ddgs fallback runs off the event loop and is keyless
    Given no TAVILY_API_KEY is configured
    When DdgsSearcher.search("how does redis persist data", 8) runs inside the event loop
    Then the synchronous ddgs call executes via asyncio.to_thread
    And up to 8 SearchResult items are returned

  @unit
  Scenario Outline: FallbackProvider switches to ddgs and records provider_used
    Given Tavily raises a <error> error
    When FallbackProvider.search runs
    Then ddgs supplies the results
    And the turn logs provider_used="ddgs"
    Examples:
      | error     |
      | auth      |
      | quota     |
      | transport |

  @unit
  Scenario: FallbackProvider records tavily on success
    Given Tavily returns results successfully
    When FallbackProvider.search runs
    Then the turn logs provider_used="tavily"
    And ddgs is not called

  @unit
  Scenario: No results routes to answer_failure
    Given both Tavily and ddgs return an empty list
    When web_search completes
    Then state["search_results"] is []
    And route_after_search(state) returns "answer_failure"

  @manual
  Scenario: Tavily 401 fast-fails to ddgs without retrying
    # M5-owned tests/unit/test_search_retry.py (respx): 401 => 1 Tavily call + ddgs fallback
    Given a Tavily API key that the server rejects with HTTP 401
    When FallbackProvider.search runs
    Then Tavily is called exactly once (no retry on 401)
    And ddgs produces the results

  @manual
  Scenario: Tavily 429 then 429 then 200 succeeds after retries
    # M5-owned tests/unit/test_search_retry.py (respx) — retries arrive with reliability.py in M5
    Given Tavily responds 429, then 429, then 200
    When the M5-wrapped searcher runs
    Then Tavily is called exactly 3 times and returns results
```

```gherkin
Feature: URL filtering and SSRF guard
  # Ownership (Ruling A / PLAN §12): the @unit scenarios here are M5-owned (tests/unit/test_fetch_retry.py — filter_urls is pure, no respx). M3 delivers filter_urls, not these tests.

  @unit
  Scenario Outline: Only http and https schemes survive
    When filter_urls(["<url>"], settings) runs
    Then the result <kept_or_dropped> the URL
    Examples:
      | url                        | kept_or_dropped |
      | https://example.com/a      | keeps           |
      | http://example.com/a       | keeps           |
      | ftp://example.com/a        | drops           |
      | file:///etc/passwd         | drops           |
      | javascript:alert(1)        | drops           |
      | data:text/html,<h1>x</h1>  | drops           |

  @unit
  Scenario Outline: Private, loopback and link-local targets are rejected
    When filter_urls(["<url>"], settings) runs
    Then the result drops the URL
    Examples:
      | url                          |
      | http://localhost/x           |
      | http://127.0.0.1/x           |
      | http://10.0.0.5/x            |
      | http://192.168.1.1/x         |
      | http://169.254.169.254/x     |
      | http://[::1]/x               |

  @unit
  Scenario: JS-only domains are denylisted
    Given URLs for youtube.com, x.com and a normal article domain
    When filter_urls runs
    Then the youtube.com and x.com URLs are dropped
    And the article-domain URL survives

  @unit
  Scenario: At most two URLs per domain, order preserved
    Given three URLs on example.com and one on other.com
    When filter_urls runs
    Then the first two example.com URLs and the other.com URL survive in order
    And the third example.com URL is dropped
```

```gherkin
Feature: Page fetching with caps, timeouts and content gates
  # Ownership (Ruling A / PLAN §12): the @unit scenarios here are M5-owned (tests/unit/test_fetch_retry.py, respx — size cap / non-HTML / timeout / redirect / concurrency). M3 delivers PageFetcher, not these tests.

  @unit
  Scenario: A single failing URL is skipped and the rest continue
    Given three filtered URLs where the second times out
    When PageFetcher.fetch runs
    Then two FetchedDocs are returned for the first and third URLs

  @unit
  Scenario Outline: Content-type gate accepts only text formats
    Given a fetched response with Content-Type "<ctype>"
    When PageFetcher.fetch processes it
    Then the page is <accepted_or_skipped>
    Examples:
      | ctype                     | accepted_or_skipped |
      | text/html                 | accepted            |
      | application/xhtml+xml     | accepted            |
      | text/plain                | accepted            |
      | application/pdf           | skipped             |
      | image/png                 | skipped             |

  @unit
  Scenario: Body larger than the cap is skipped
    Given FETCH_MAX_BYTES is 2500000
    And a response body of 3000000 bytes
    When PageFetcher.fetch streams it
    Then reading stops at 2500000 bytes and the page is skipped

  @unit
  Scenario: Redirects are followed and the final URL is stored
    Given a URL that 301-redirects to https://example.com/final
    When PageFetcher.fetch follows it to a 200
    Then the FetchedDoc.url is "https://example.com/final"

  @unit
  Scenario: Concurrency is bounded by the semaphore
    Given FETCH_CONCURRENCY is 5 and eight filtered URLs
    When PageFetcher.fetch runs
    Then no more than 5 fetches are in flight at any moment

  @unit
  Scenario: Requests carry an honest User-Agent with the repo link
    When PageFetcher.fetch issues a request
    Then the User-Agent header matches the configured identifier and contains a URL

  @manual
  Scenario: A URL exceeding the wall-clock deadline is abandoned
    # FR-M3-10b; M5-owned tests/unit/test_fetch_retry.py exercises the timeout path with respx
    Given PAGE_DEADLINE_S is 20 and a URL that stalls past 20 seconds
    When PageFetcher.fetch runs
    Then that URL is abandoned and skipped while the others complete
```

```gherkin
Feature: HTML to Markdown extraction (to_markdown gating)
  # M3-owned OPTIONAL unit tests: tests/unit/test_to_markdown.py

  @unit
  Scenario: Precision pass produces markdown with tables and no inline links
    Given article HTML containing a table and inline links
    When to_markdown(html) runs
    Then trafilatura.extract is called with output_format="markdown", include_tables=True, include_links=False, favor_precision=True
    And the returned markdown keeps the table and omits inline links

  @unit
  Scenario: Empty precision pass retries once with recall
    Given HTML where the precision pass returns empty
    And the recall pass returns 500 characters of markdown
    When to_markdown(html) runs
    Then favor_recall=True is used on the second call
    And the 500-character recall result is returned

  @unit
  Scenario Outline: The 200-character floor gates unusable pages
    Given an extraction result of <length> characters
    When to_markdown evaluates it
    Then it returns <outcome>
    Examples:
      | length | outcome        |
      | 199    | None (skipped) |
      | 200    | the markdown   |

  @unit
  Scenario Outline: Markdown is capped at 20000 characters
    Given an extraction result of <length> characters
    When to_markdown returns
    Then the result is exactly <kept> characters long
    Examples:
      | length | kept  |
      | 25000  | 20000 |
      | 20000  | 20000 |
```

```gherkin
Feature: Content ingestion and storage
  # Ownership (Ruling A / PLAN §12): the @unit ingest scenarios are proven by M6's e2e lifecycle (tests/e2e/test_lifecycle.py) + the @integration store test (M6 test_redis_store.py); the sanitize seam is M5 test_sanitizer.py. M3 delivers ingest_content, not these tests.

  @unit
  Scenario: Sanitize runs before chunking as a pass-through stub
    Given fetched markdown "clean article body ..."
    When ingest_content processes the page
    Then sanitize(markdown) is called before any chunking
    And the stub returns (markdown_unchanged, [])
    And store is called with flags == []

  @unit
  Scenario: A page stores N chunk docs plus one summary doc with metadata
    Given a sanitized page that yields 3 chunks
    And a successful 6-sentence summary from the analytics LLM
    When ingest_content stores it
    Then keys chunk:{hash}:0, chunk:{hash}:1, chunk:{hash}:2 and chunk:{hash}:summary are written
    And each record carries url, title, fetched_at, source_query and sanitizer_flags
    And the summary record has doc_type="summary" and the chunks have doc_type="chunk"

  @unit
  Scenario: Summary input is capped at the first 6000 characters
    Given a sanitized page of 12000 characters
    When ingest_content requests the summary
    Then the analytics LLM receives at most the first 6000 characters

  @unit
  Scenario Outline: Freshness gate skips recent re-ingest
    Given a stored doc:{hash} with fetched_at <age> old
    And FRESHNESS_WINDOW_SECONDS is 86400
    When ingest_content re-processes the same URL
    Then re-embed and re-store are <action>
    Examples:
      | age          | action    |
      | 1 hour       | skipped   |
      | exactly 24h  | performed |
      | 25 hours     | performed |

  @unit
  Scenario: skip_store persists nothing but still prepares the in-hand answer
    Given skip_store is True
    When ingest_content runs on a fetched page
    Then no Redis writes occur and stored_chunk_ids is []
    And chunks and the per-page summary are still populated in state

  @unit
  Scenario: Summary failure is tolerated
    Given the analytics summary call raises an error
    When ingest_content continues
    Then chunks are produced from the raw sanitized markdown
    And no summary doc is stored, and ingestion continues without routing the turn to "failed"

  @unit
  Scenario: Store failure never fails the turn
    Given memory.store raises an error
    When ingest_content handles it
    Then the error is caught and chunks remain available in state
    And the turn does not route to "failed" because of the store error

  @integration
  Scenario: Stored chunks and summary round-trip through real Redis
    # deeper store/KNN math owned by M6 tests/integration/test_redis_store.py
    Given a running redis:8.2 with the web_memory index
    When ingest_content stores a 3-chunk page
    Then RedisInsight shows chunk:{hash}:0..2, chunk:{hash}:summary and doc:{hash}
    And a KNN query over the summary vector returns that summary doc
```

```gherkin
Feature: Answering from web context
  # Ownership (Ruling A / PLAN §12): the @unit scenarios here are proven by M6's e2e lifecycle (tests/e2e/test_lifecycle.py). M3 delivers answer_from_web, not these tests.

  @unit
  Scenario: Context uses each page summary plus only the first two chunks
    Given WEB_CONTEXT_CHUNKS_PER_PAGE is 2
    And a fetched page with a summary and 10 chunks
    When answer_from_web builds its context
    Then the context includes the summary and exactly the first 2 chunks of that page
    And none of the remaining 8 chunks appear

  @unit
  Scenario: A page whose summary is None still contributes its chunks
    Given WEB_CONTEXT_CHUNKS_PER_PAGE is 2
    And a fetched page whose summary is None and that has 3 chunks
    When answer_from_web builds its context
    Then the context omits the summary line and includes the first 2 chunks
    And the answer is still grounded with origin="web" sources

  @unit
  Scenario: A page with fewer than two chunks contributes them without error
    Given WEB_CONTEXT_CHUNKS_PER_PAGE is 2
    And a fetched page with a summary and only 1 chunk
    When answer_from_web builds its context
    Then the context includes the summary and that single chunk
    And no error is raised

  @unit
  Scenario: Normal miss answer is grounded with web sources
    Given ingest produced chunks and summaries for two web pages
    When answer_from_web completes
    Then route is "memory_miss_web_search"
    And sources is non-empty and every entry has origin="web"
    And the answer ends with a "Sources:" section

  @unit
  Scenario: No page fetched falls back to snippets with a disclaimer
    Given fetched_docs is [] and search_results has 5 snippets
    When answer_from_web completes
    Then route is "degraded_web"
    And degradation is "snippets_only"
    And the answer contains a low-confidence disclaimer

  @unit
  Scenario: The miss answer never re-queries Redis
    Given a miss with in-hand chunks and summaries
    When answer_from_web builds the answer
    Then no memory.knn or Redis read call is made
    And the context is assembled only from fetched_docs and chunks in state
```

```gherkin
Feature: Graph rewiring of the miss branch
  # Ownership: route_after_fetch is an M2-owned pure router (test_routing.py); the compiled-graph/mermaid scenario is a structural check via draw_mermaid() (M3 confirms it in T-M3-12); the lifecycle is M6-owned.

  @unit
  Scenario: The compiled graph routes a miss through the full web pipeline
    Given build_graph(resources) is compiled
    When the mermaid diagram is generated
    Then the miss path shows web_search -> fetch_pages -> ingest_content -> answer_from_web -> log_turn
    And the M2 temporary memory_search->answer_failure edge is absent
    And the four M3-active routes memory_hit, memory_miss_web_search, degraded_web, failed remain reachable
    # blocked activates with guard_input/route_after_guard in M5 (Ruling F); M3's graph entry is embed_query

  @unit
  Scenario Outline: route_after_fetch chooses ingest when pages exist, else answer_from_web
    Given <fetched_docs>
    When route_after_fetch(state) runs
    Then it returns "<route>"
    Examples:
      | fetched_docs          | route           |
      | one fetched page      | ingest_content  |
      | an empty fetched_docs | answer_from_web |

  @e2e
  Scenario: Full miss then hit lifecycle
    # M6-owned tests/e2e/test_lifecycle.py; M3 proves it via the @manual live demo
    Given an empty web_memory index and a novel question
    When the question is asked the first time
    Then the route is "memory_miss_web_search" with web source URLs
    And chunks and a summary are stored in Redis
    When the identical question is asked again
    Then the route is "memory_hit" with similarity >= 0.70
    And the search endpoint call count is unchanged from turn 1

  @manual
  Scenario: Live demo transcript capture
    Given a real OPENAI_API_KEY and Docker Redis running
    When the same novel question is asked twice via "memagent ask"
    Then turn 1 prints [MEMORY MISS → searching the web] with web Sources
    And turn 2 prints [MEMORY HIT sim=0.9x] with (memory) Sources and makes no web call
    And the session is captured into docs/demo_transcript.md
```

---

## 8. Task breakdown

Ordered; each ≤ ~1 h. `[P]` = parallel-safe (independent file, no ordering dependency on an unfinished sibling). Each task names the FR(s) it satisfies.

- **T-M3-01 [P]** — `web/to_markdown.py`: trafilatura extract + recall retry + 200-char reject + 20k cap; add optional `tests/unit/test_to_markdown.py`. *(FR-M3-17..20)*
- **T-M3-02 [P]** — `security/sanitizer.py`: pass-through `sanitize(text) -> (text, [])` with the M5-replacement docstring (Ruling C). *(FR-M3-21)*
- **T-M3-03 [P]** — `web/search.py` `TavilySearcher`: raw httpx POST, bearer auth, `include_raw_content=False`, 8 results, holds `httpx.AsyncClient`. *(FR-M3-01, FR-M3-02)*
- **T-M3-04** — `web/search.py` `DdgsSearcher` (`asyncio.to_thread`) + `FallbackProvider` (Tavily→ddgs on quota/auth/transport, log `provider_used`). *(FR-M3-03, FR-M3-04)*
- **T-M3-05 [P]** — `web/fetch.py` `filter_urls`: scheme allowlist, SSRF guard, JS-only denylist, max 2/domain. *(FR-M3-06..09)*
- **T-M3-06** — `web/fetch.py` `PageFetcher.fetch`: streamed GET, timeouts + 20 s deadline, 2.5 MB cap, content-type gate, final-URL storage, semaphore(5), honest UA, per-URL skip; calls `to_markdown`. *(FR-M3-10..16)*
- **T-M3-07** — `nodes/web_search`: call `resources.searcher.search(query, SEARCH_MAX_RESULTS)`, write `search_results` and `search_provider` (the provider the `FallbackProvider` used, for `TurnRecord.web.provider`). *(FR-M3-04, FR-M3-05 wiring)*
- **T-M3-08** — `nodes/fetch_pages`: `filter_urls` → take first `FETCH_TOP_N` → `fetcher.fetch` → write `fetched_docs`. *(FR-M3-09..16 wiring)*
- **T-M3-09a** — `nodes/ingest_content` core path: sanitize seam → nano summary (first 6k chars, via analytics LLM) → chunk (1600/200) → batch-embed → store N chunk docs + 1 summary doc per page with `{url, title, fetched_at, source_query, sanitizer_flags}` + `doc_type`. *(FR-M3-21, FR-M3-22, FR-M3-23)*
- **T-M3-09b** — `ingest_content` gating: freshness gate (`doc:{h}.fetched_at` read + `< FRESHNESS_WINDOW_SECONDS` skip) and `skip_store` honouring (no persistence, still summarise + chunk for the in-hand answer). *(FR-M3-24, FR-M3-25)*
- **T-M3-09c** — `ingest_content` failure tolerance: summary-failure (chunk the raw sanitized markdown, no summary doc) and store-failure (caught; the answer never depends on persistence; never routes to `failed`). *(FR-M3-26, FR-M3-27)* — 09a→09b→09c are sequential in the **same file** (`nodes/ingest_content`), each ≤ ~1 h; this keeps the single riskiest node's estimate honest.
- **T-M3-10** — `nodes/answer_from_web`: bounded context (summary + first 2 chunks/page); normal `memory_miss_web_search` path with `origin="web"` sources; snippets-only `degraded_web` path with disclaimer; no second Redis round-trip. *(FR-M3-28..31)*
- **T-M3-11** — `resources.py`: construct `FallbackProvider` + `PageFetcher` into `AgentResources`. *(supports FR-M3-01..16)*
- **T-M3-12** — `graph.py`: remove M2 temp miss→`answer_failure` edge; wire `web_search`→`fetch_pages`→(`route_after_fetch`)→`ingest_content`→`answer_from_web`→`log_turn`; confirm compile + inspect the miss branch via `build_graph(...).get_graph().draw_mermaid()` (a langgraph method available now; `scripts/render_graph.py` itself is M6). *(FR-M3-32)*
- **T-M3-13** — live smoke: `wipe-memory`, ask a novel question (miss), re-ask (hit); capture `docs/demo_transcript.md`. *(FR-M3-29, FR-M3-31, lifecycle)*
- **T-M3-14** — append this milestone's prompts to `docs/ai_prompts/milestone-3.md` and update `AI_USAGE.md`. *(DoD requirement §11)*

---

## 9. Definition of Done

Each item has an exact verify command or observable outcome.

- [ ] `web/search.py`, `web/fetch.py`, `web/to_markdown.py`, `security/sanitizer.py` exist and import cleanly — `uv run python -c "import memagent.web.search, memagent.web.fetch, memagent.web.to_markdown, memagent.security.sanitizer"` exits 0.
- [ ] No `tavily` / `tavily-python` / `markdownify` import anywhere — `! grep -rn "tavily-python\|import tavily\|markdownify" src/` .
- [ ] The graph compiles with the rewired miss branch — `OPENAI_API_KEY=dummy uv run python -c "from memagent.app import build_resources; from memagent.graph import build_graph; build_graph(build_resources())"` exits 0 (dummy key: `AsyncOpenAI` requires a non-empty key at construction; `build_resources()` defaults `settings=Settings()`).
- [ ] The mermaid diagram shows `web_search → fetch_pages → ingest_content → answer_from_web` and no `memory_search → answer_failure` edge — `OPENAI_API_KEY=dummy uv run python -c "from memagent.app import build_resources; from memagent.graph import build_graph; print(build_graph(build_resources()).get_graph().draw_mermaid())"` and inspect the output (`draw_mermaid()` is a langgraph method available now; `scripts/render_graph.py` itself is delivered in M6).
- [ ] Optional `to_markdown` gating tests pass — `uv run pytest tests/unit/test_to_markdown.py -q` green (or the file is absent by explicit choice).
- [ ] Lint clean on new code — `uv run ruff check src/memagent/web src/memagent/nodes src/memagent/security/sanitizer.py` exits 0.
- [ ] **Live miss→ingest→hit lifecycle** (the demoable outcome, PLAN §13): with a real `OPENAI_API_KEY` and `make redis-up`, `uv run memagent wipe-memory` then `uv run memagent ask "<novel question>"` prints a MISS with web Sources; the same question asked again prints `[MEMORY HIT sim=0.9x]` with `(memory)` Sources and makes **no** web call.
- [ ] RedisInsight (`localhost:5540`) shows `chunk:{hash}:0..N`, `chunk:{hash}:summary`, and `doc:{hash}` keys after the first (miss) turn.
- [ ] **First demo transcript captured** — `docs/demo_transcript.md` contains the two-turn miss-then-hit session.
- [ ] **AI-assistance disclosure updated for M3** — `docs/ai_prompts/milestone-3.md` holds this milestone's complete prompt log and `AI_USAGE.md` is updated (appended per milestone, never retroactively — PLAN §11).

---

## 10. Risks & gotchas

- **ddgs fragility at demo time** (PLAN §15.4) — ddgs scrapes DuckDuckGo and can break or rate-limit. It is only the fallback; catch its exceptions and surface an explicit "web search unavailable" turn (`answer_failure`). Prefer a working `TAVILY_API_KEY` for the recorded demo.
- **`include_raw_content` must stay `False`** (PLAN §5.1) — flipping it lets Tavily do the fetch+markdown the assignment grades us on; keep our pipeline in-house.
- **Distance ≠ similarity is a downstream trap** (PLAN §4.3 / §15.1) — M3 stores vectors; the 0.70 conversion lives in M2's `memory_search`/store boundary. Do not re-implement the conversion in `ingest_content` or `answer_from_web`.
- **First question always misses** (IMPLEMENTATION_GUIDE §6.2) — empty index ⇒ KNN returns `[]` ⇒ normal miss, not an error. The demo depends on this.
- **0.70 is strict for paraphrases** (PLAN §15.2) — a verbatim re-ask hits; a reworded one may still miss and re-fetch. The freshness gate then prevents duplicate ingestion of the same URL. Demo with a verbatim re-ask.
- **Sanitize BEFORE chunk/embed** (IMPLEMENTATION_GUIDE §6.6) — the ordering *is* the T3 defence. The stub is a no-op, but the call site must sit between `to_markdown` and chunking so M5 is a pure internals swap.
- **Async is all-or-nothing** (IMPLEMENTATION_GUIDE §6.5) — ddgs is the one synchronous holdout; it **must** run via `asyncio.to_thread` or it freezes the event loop.
- **Store failure must never fail the turn** (PLAN §3.2 / §5.4) — answering uses in-hand chunks; wrap `memory.store` so a Redis hiccup degrades storage only, not the answer.
- **No second Redis round-trip on a miss** (PLAN §3.2 note) — `answer_from_web` reads only in-hand state; memory serves the *next* question.
- **No retries here** (Ruling A) — `reliability.py` and the retry tests are M5. Adding tenacity now would double-own retries and break the M5 seam. Clients rely on SDK/httpx timeouts only.
- **redisvl signature drift** (PLAN §14) — `load(ttl=)` / `array_to_buffer` / `VectorQuery` were pinned to re-verify at M1; if the store's TTL/EXPIRE path changed, ingest storage inherits that fix from M2 — do not re-solve it here.
- **Domain diversity vs. FETCH_TOP_N** (IMPLEMENTATION_GUIDE §2.6) — we ask for 8 results but fetch only the top 5 *after* the SSRF/denylist/max-2-per-domain filter discards some; expect fewer than 5 pages on narrow queries.

---

## 11. Spec Kit mapping

- **Feeds `/specify` (spec.md):** §1 Goal & context, §2 Scope (in/out/deferred), §5 Functional requirements, §7 BDD acceptance scenarios — the what and the acceptance criteria.
- **Feeds `/plan` (plan.md):** §3 Prerequisites & interfaces consumed, §4 Interfaces provided (incl. the seams), §6 Technical specification (file paths, protocols, route enum, request shapes, env defaults, dependency pins), §10 Risks & gotchas — the how and the constraints.
- **Feeds `/tasks` (tasks.md):** §8 Task breakdown (T-M3-01..14 with `[P]` markers and FR links) and §9 Definition of Done (verify commands + demoable outcome) — the ordered, checkable work items.
