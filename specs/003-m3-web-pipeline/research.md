# Phase 0 Research: Milestone 3 — Web Pipeline

**Date**: 2026-07-05 · **Plan**: [plan.md](plan.md) · All decisions below resolve the
plan's Technical Context; live checks were executed on this machine today.

## D1 — Search provider: Tavily key provided; live probe verified

- **Decision**: M3 live searches run on the user-provided **free-tier Tavily key**
  (Clarifications 2026-07-05, Option A); ddgs remains the built-and-tested keyless
  fallback. Key stored ONLY in the git-ignored `memory-first-agent/.env`.
- **Live verification (2026-07-05)**: `POST https://api.tavily.com/search` with
  `Authorization: Bearer <key>`, body `{"query":..., "max_results":2,
  "include_raw_content":false}` → **HTTP 200**; result objects carry
  `['content','raw_content','score','title','url']`.
- **Consequences**: `SearchResult.snippet` maps from Tavily's **`content`** field
  (resolves the source §6.6 spec note); `rank` is assigned by result order (no rank field
  in the response; `score` exists but is unused — anti-churn); `raw_content` arrives
  `null` when excluded, confirming `include_raw_content=False` behaves as documented.
- **Alternatives considered**: keyless-only ddgs (rejected — demo fragility, primary path
  live-unverified); defer to demo time (rejected — user decided now).

## D2 — ddgs fallback: live field mapping verified

- **Decision**: `DdgsSearcher` calls `DDGS().text(query, max_results=k)` inside
  `asyncio.to_thread` and maps `title→title`, `href→url`, `body→snippet`, order→`rank`.
- **Live verification (2026-07-05)**: keyless `DDGS().text("redis vector search",
  max_results=2)` returned 2 rows with keys exactly `['body','href','title']`
  (ddgs 9.14.4).
- **Rationale**: ddgs is synchronous — `asyncio.to_thread` keeps the event loop unblocked
  (source §10 "async is all-or-nothing").

## D3 — Node file layout

- **Decision**: `nodes/search.py` (web_search), `nodes/fetch.py` (fetch_pages),
  `nodes/ingest.py` (ingest_content); `answer_from_web` is added to the existing
  `nodes/answer.py`.
- **Rationale**: matches M2's per-concern node naming; the answer family shares helpers
  (`_dedupe_sources`, prompts usage, FAILURE_APOLOGY) already living in `nodes/answer.py`.
  The source §6.1 names no node filenames (minimal-assumption slot).
- **Alternatives**: one `nodes/web.py` for all four (rejected — diverges from M2's
  established pattern and makes M4/M5 diffs noisier).

## D4 — Freshness gate: `is_fresh(h)` joins the MemoryStore Protocol (additive)

- **Decision**: `interfaces.py`'s `MemoryStore` Protocol gains
  `async def is_fresh(self, h: str) -> bool: ...`. `ingest_content` computes
  `h = url_hash(canonicalize(doc["url"]))` (needed for keys anyway) and calls
  `memory.is_fresh(h)`.
- **Verified (2026-07-05)**: the concrete method has existed since M2 —
  `RedisMemoryStore.is_fresh(self, h: str) -> bool` reads `doc:{h}.fetched_at` and
  compares against `freshness_window_seconds` (`src/memagent/memory/store.py:140`).
- **Rationale**: the Protocol printed in source §6.4 lists `knn`/`store` only, but the
  freshness gate (FR-024) must read through the injected store. Extending the Protocol is
  additive — zero call-site changes, and M6's conftest fakes implement it trivially.
- **Alternatives**: duck-typing off the Protocol (rejected — defeats the DI contract);
  reading `doc:{h}` directly from the node via a raw Redis handle (rejected — nodes don't
  own storage access; P-III).
- **Companion delta (analyze I1, 2026-07-05)**: the M2 placeholder
  `PageFetcher.fetch(self, results: list[SearchResult])` is replaced with the M3 design
  signature `fetch(self, urls: list[str]) -> list[FetchedDoc]` in the same `interfaces.py`
  edit (T003). Authorized: the placeholder's docstring says "M3 fleshes this out"; the
  `fetch_pages` node applies `filter_urls` first and hands plain URLs to the fetcher.
  The only implementer of the old shape (`_NoopFetcher`) is deleted in the same milestone.

## D5 — Fallback trigger set (no retries in M3)

- **Decision**: `FallbackProvider` switches Tavily→ddgs on `httpx.HTTPStatusError`
  (any non-2xx after `raise_for_status()`) and `httpx.TransportError` (connect/read/
  timeout/protocol failures) — one plain `try/except`, no retry loop, no sleep.
- **Rationale**: source §6.6 — fast-fail on 400/401/403 auth and quota/transport errors;
  in M3 *every* Tavily failure falls back immediately because the tenacity policy
  (3 attempts, jitter) is M5-owned (Ruling A/D). M5 narrows 429 into retry-then-fallback
  without touching the seam.
- **Both-fail behavior**: ddgs exceptions are caught too → `search_results=[]` →
  `route_after_search` → `answer_failure` (FR-005; source §10 ddgs-fragility note).

## D6 — `provider_used` exposure: attribute, not return-shape change

- **Decision**: `FallbackProvider` sets `self.provider_used: str | None`
  (`"tavily"`/`"ddgs"`) at the end of each `search()`; the `web_search` node reads
  `getattr(searcher, "provider_used", None)` and writes it into
  `state["search_provider"]`; the same value is emitted on the structlog line.
- **Rationale**: keeps the `WebSearcher` Protocol signature
  (`search(query, k) -> list[SearchResult]`) unchanged (fixed in M2). The source §6.6
  explicitly offers both options; the attribute avoids touching a frozen contract.
  Sequential graph execution makes the read race-free.

## D7 — Module constants (no new Settings fields)

- **Decision**: `MIN_MARKDOWN_CHARS=200`, `MAX_MARKDOWN_CHARS=20_000` in
  `web/to_markdown.py`; `SUMMARY_INPUT_CHARS=6000`, `SUMMARY_SYSTEM` (wording authored at
  implement time; finalised under M5's L2 pass) in `nodes/ingest.py`;
  `LOW_CONFIDENCE_DISCLAIMER` in `nodes/answer.py`; `ALLOWED_SCHEMES`,
  `ACCEPTED_CONTENT_TYPES`, `JS_ONLY_DENYLIST` (7 domains per source §6.7), and
  `USER_AGENT = "memagent/1.0 (+https://github.com/muhammadyehiaelsayed/memory-first-agent)"`
  in `web/fetch.py` — the `<owner>` placeholder resolves to the published repo.
- **Rationale**: PLAN's `.env.example` defines no env names for these (source §6.8 spec
  note); `Settings` stays exactly 32 fields — adding fields would drift the generated
  `.env.example` (P-III). Acceptance checks reference the constant symbols, not hardcoded
  strings.

## D8 — `fetched_docs` ownership across fetch→ingest

- **Decision**: `fetch_pages` creates `fetched_docs`; `ingest_content` re-emits the same
  key with per-page `summary` populated. Documented as single-owner-in-time: the nodes
  are strictly sequential, LangGraph replaces the (non-reducer) key, and no other node
  writes it.
- **Rationale**: source §6.3 spec note pre-documents exactly this to avoid a later "who
  owns fetched_docs?" churn.

## D9 — trafilatura 2.1.0 API verified

- **Decision**: `to_markdown` uses `trafilatura.extract(html, output_format="markdown",
  include_tables=True, include_links=False, favor_precision=True)` with one
  `favor_recall=True` retry on empty.
- **Live verification (2026-07-05)**: `inspect.signature(trafilatura.extract)` on the
  installed 2.1.0 confirms all five kwargs exist (`output_format`, `include_tables`,
  `include_links`, `favor_precision`, `favor_recall`).

## D10 — Summary calls on GitHub Models free tier

- **Decision**: per-page summaries call `resources.analytics_llm.complete(...)` — the M2
  thin client, dev-aliased to `openai/gpt-4.1-nano` in `.env` (M2 findings; gpt-5.4 ids
  are unavailable on the free catalogue). Production default `ANALYTICS_MODEL=gpt-5.4-nano`
  in `Settings` is untouched.
- **Rate-limit posture**: a miss turn makes ≤5 summary calls + ≤5 embed batches + 1 chat
  call; free-tier per-minute limits absorbed this during M2's live work and daily limits
  are accepted for dev (M2 clarification). If a 429 lands mid-demo, re-run — no retry
  code may be added (Ruling A/D).
- **Failure tolerance is behavior, not retry**: a failed summary → `summary=None`, chunk
  the sanitized markdown, no summary doc (FR-026).
