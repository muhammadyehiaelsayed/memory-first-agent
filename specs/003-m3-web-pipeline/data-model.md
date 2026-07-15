# Data Model: Milestone 3 — Web Pipeline

**Date**: 2026-07-05 · **Plan**: [plan.md](plan.md) · All types were DEFINED in M2's
`state.py`/`interfaces.py` — M3 defines no new types. This file records what M3 *writes*
into them, the storage shapes it produces, and the one additive Protocol delta.

## 1. Records M3 populates (defined in `src/memagent/state.py`, unchanged)

| Type | Fields (verbatim) | M3 writer | Notes |
|---|---|---|---|
| `SearchResult` | `url, title, snippet, rank` | `web_search` node via searcher | `snippet` ← Tavily `content` / ddgs `body` (research D1/D2); `rank` = result order (0-based) |
| `FetchedDoc` | `url, title, markdown, summary, ok` | `fetch_pages` (summary=None, ok=True); `ingest_content` re-emits with `summary` set | `url` is the FINAL post-redirect URL (FR-013); failed URLs are omitted, not returned with ok=False (source §4 note) |
| `Chunk` | `chunk_id, text, url, title, chunk_index` | `ingest_content` wraps `chunk_markdown()` strings | `chunk_id = f"{h}:{i}"` where `h = url_hash(canonicalize(final_url))` |
| `SourceRef` | `url, title, origin` | `answer_from_web` | every M3 source has `origin="web"` |
| `StepError` | `node, error, detail` | any web node on caught failure | appended via the `errors` reducer |

## 2. AgentState channels M3 touches (all declared in M2)

| Channel | Writer | Value |
|---|---|---|
| `search_results` | `web_search` | `list[SearchResult]` (possibly `[]` → failure route) |
| `search_provider` | `web_search` | `"tavily" \| "ddgs" \| None` — feeds M4 `TurnRecord.web.provider` |
| `fetched_docs` | `fetch_pages`, re-emitted by `ingest_content` | single-owner-in-time (research D8) |
| `chunks` | `ingest_content` | all pages' `Chunk` records, in page order |
| `stored_chunk_ids` | `ingest_content` | `[]` when `skip_store` or store failure |
| `route` | `answer_from_web` | `"memory_miss_web_search"` normal; `"degraded_web"` snippets-only |
| `degradation` | `answer_from_web` | `"snippets_only"` on the degraded path, else unset |
| `answer`, `sources` | `answer_from_web` | answer ends with "Sources:"; sources deduped, `origin="web"` |
| `errors`, `latency_ms`, `tokens` | all web nodes | merged reducers (M2) |
| `query`, `sanitized_query`, `skip_store`, `threshold` | READ ONLY | set upstream by facade/M2 nodes |

**Route enum (closed, unchanged)**: `memory_hit | memory_miss_web_search | degraded_web |
blocked | failed`. M3 writes the middle two; `blocked` activates in M5 (Ruling F); a
`skip_store=True` miss still labels `memory_miss_web_search` (the `redis_down` degradation
matrix is M5's).

## 3. Storage shapes produced (written through M2's `RedisMemoryStore.store()`)

Per ingested page with `h = url_hash(canonicalize(final_url))`:

```text
chunk:{h}:{i}       i = 0..N-1   HASH, indexed (web_memory)   doc_type="chunk"
chunk:{h}:summary   0 or 1       HASH, indexed (web_memory)   doc_type="summary"
doc:{h}             exactly 1    HASH, NOT indexed            meta: fetched_at, num_chunks, url, title
```

- Every indexed record carries: `url` (final), `title`, `fetched_at`, `source_query`
  (the triggering user query), `sanitizer_flags` (`[]` in M3 — pass-through stub),
  embedding vector (float32 buffer), `doc_type`.
- **Vector alignment contract (M2, reused verbatim)**: summary present →
  `vectors[0]`=summary embedding, `vectors[1:]` ↔ chunks 1:1; summary `None` → `vectors`
  ↔ chunks 1:1. `store()` raises `ValueError` on misalignment.
- TTL: per-key `EXPIRE MEMORY_TTL_SECONDS=604800` (0 disables) — M2 behavior, unchanged.
- Upsert: re-store deletes stale `chunk:{h}:*` via old `doc:{h}.num_chunks` — M2
  behavior; the freshness gate usually prevents re-store within 24 h anyway.

## 4. Protocol deltas (the only interface changes)

```python
class MemoryStore(Protocol):
    async def knn(self, vector: list[float], k: int) -> list[MemoryHit]: ...
    async def store(self, page: FetchedDoc, chunks: list[Chunk], vectors: list[list[float]],
                    source_query: str, flags: list[str]) -> list[str]: ...
    async def is_fresh(self, h: str) -> bool: ...        # M3 ADDITIVE (research D4)

class PageFetcher(Protocol):                              # M2 placeholder → M3 design signature
    async def fetch(self, urls: list[str]) -> list[FetchedDoc]: ...   # was: results: list[SearchResult]
```

`is_fresh` is hash-keyed (verified against the M2 implementation, store.py:140): True iff
`doc:{h}.fetched_at` exists and is younger than `FRESHNESS_WINDOW_SECONDS=86400`.
The `PageFetcher` replacement is pre-authorized by its placeholder docstring ("M3 fleshes
this out"); `fetch_pages` applies `filter_urls` and passes plain URLs (research D4
companion note; analyze I1).

## 5. New module-level constants (not Settings fields — research D7)

| Constant | Module | Value |
|---|---|---|
| `MIN_MARKDOWN_CHARS` / `MAX_MARKDOWN_CHARS` | `web/to_markdown.py` | `200` / `20_000` |
| `ALLOWED_SCHEMES` | `web/fetch.py` | `{"http", "https"}` |
| `ACCEPTED_CONTENT_TYPES` | `web/fetch.py` | `("text/html", "application/xhtml+xml", "text/plain")` |
| `JS_ONLY_DENYLIST` | `web/fetch.py` | `{youtube.com, youtu.be, x.com, twitter.com, facebook.com, instagram.com, tiktok.com}` |
| `USER_AGENT` | `web/fetch.py` | `memagent/1.0 (+https://github.com/muhammadyehiaelsayed/memory-first-agent)` |
| `SUMMARY_INPUT_CHARS` | `nodes/ingest.py` | `6000` |
| `SUMMARY_SYSTEM` | `nodes/ingest.py` | 5–8-sentence summarisation instruction (wording at implement time; M5 finalises) |
| `LOW_CONFIDENCE_DISCLAIMER` | `nodes/answer.py` | exact string prepended on the snippets-only path |

## 6. Settings fields consumed (all exist since M1 — zero new fields)

`TAVILY_API_KEY` (blank ⇒ keyless), `SEARCH_MAX_RESULTS=8`, `FETCH_TOP_N=5`,
`FETCH_CONCURRENCY=5`, `CONNECT_TIMEOUT_S=5`, `READ_TIMEOUT_S=10`, `PAGE_DEADLINE_S=20`,
`FETCH_MAX_BYTES=2500000`, `FRESHNESS_WINDOW_SECONDS=86400`, `CHUNK_SIZE_CHARS=1600`,
`CHUNK_OVERLAP_CHARS=200`, `MAX_CHUNKS_PER_PAGE=25`, `WEB_CONTEXT_CHUNKS_PER_PAGE=2`,
`MEMORY_TTL_SECONDS=604800`, `ANALYTICS_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`.
