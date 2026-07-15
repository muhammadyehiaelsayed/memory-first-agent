# Phase 1 Data Model: Milestone 2 — Memory Path

**Date**: 2026-07-05 · **Plan**: [plan.md](plan.md) · Verbatim sources:
`specs/milestone-2-memory-path.md` §6.2–§6.7 (PLAN §3.1/§2.1/§8.3/§4.2).

## Entity 1: `AgentState` (`src/memagent/state.py`) — the canonical per-turn record

TypedDict; single-writer fields unless a reducer is noted. LangGraph propagates ONLY keys
declared here.

| Field | Type | Writer / notes |
|---|---|---|
| turn_id | str | facade (uuid4) |
| session_id | str | facade |
| query | str | facade |
| history | list[dict] | facade — **always `[]` in M2** (REPL history is M4) |
| threshold | float | facade ← `settings.similarity_threshold` |
| guard_verdict | Literal["allow","flag","block"] | defaults "allow" (guard node = M5) |
| guardrail_events | Annotated[list[str], operator.add] | reducer: append |
| sanitized_query | str | facade — equals `query` in M2 (L1 = M5) |
| query_vector | list[float] \| None | `embed_query` |
| memory_hits | list[MemoryHit] | `memory_search` |
| top_similarity | float \| None | `memory_search` (max similarity or None) |
| search_results | list[SearchResult] | M3's `web_search` (empty in M2) |
| fetched_docs | list[FetchedDoc] | M3 (empty in M2) |
| chunks | list[Chunk] | M3 (empty in M2) |
| stored_chunk_ids | list[str] | M3 (empty in M2) |
| skip_store | bool | facade (False); M3/M5 honor it |
| route | Route | answer nodes |
| degradation | str \| None | "redis_down" \| "snippets_only" \| None (M3/M5) |
| answer | str \| None | answer nodes |
| sources | list[SourceRef] | answer nodes (deduped by URL) |
| errors | Annotated[list[StepError], operator.add] | reducer: append |
| latency_ms | Annotated[dict[str,int], merge] | reducer: dict-merge (timed() arrives M4) |
| analytics | QueryClassification \| None | M4's log_turn (None in M2) |
| tokens | Annotated[dict, merge] | reducer: dict-merge (usage plumbing M4) |
| **turn_started_at** | float \| None | facade (`perf_counter()`) — M2-added channel (research D2) |
| **search_provider** | str \| None | M3's web_search ("tavily"/"ddgs") — M2-added channel |

## Entity 2: Record types (`state.py`)

- **MemoryHit**: `doc_id, text, url, title, similarity (1−distance, attached in knn),
  stored_at (ISO-8601, converted from epoch at the store boundary), sanitizer_flags
  (list[str], csv-split), doc_type ("chunk"|"summary")`.
- **SearchResult**: `url, title, snippet, rank` (M3 fills).
- **FetchedDoc**: `url, title, markdown, summary (str|None), ok`.
- **Chunk**: `chunk_id, text, url, title, chunk_index`.
- **SourceRef**: `url, title, origin ∈ {"memory","web"}`.
- **StepError**: `node, error_type, detail` (minimal default — research D4).
- **Route** (closed Literal): `memory_hit | memory_miss_web_search | degraded_web |
  blocked | failed`.

## Entity 3: `QueryClassification` schema (`analytics/classify.py`, schema-only in M2)

`topic` (free-form 1–4 lowercase words) · `category` (9-enum: technology, science, health,
finance_business, travel_geography, entertainment_sports, history_politics, lifestyle,
other) · `question_type` (6-enum: factual, how_to, comparison, opinion, troubleshooting,
other) · `language` (ISO 639-1) · `confidence` (0..1). No `_missing_` hooks yet — M4
hardens in place (research D3). Exists so `AgentState.analytics` resolves at runtime.

## Entity 4: `TurnResult` (`app.py`)

`NamedTuple(route: str, answer: str | None, sources: list[SourceRef],
similarity: float | None)` — the facade's return; consumed by `ask` now, `chat` (M4),
e2e tests (M6).

## Entity 5: Stored-key layout (written by `RedisMemoryStore.store`)

```
chunk:{url_hash}:{i}        indexed HASH — 11 schema fields incl. embedding (vectors[i+1]
                            when a summary exists, vectors[i] otherwise)
chunk:{url_hash}:summary    indexed HASH — chunk_text = page summary, doc_type="summary",
                            embedding = vectors[0]; ONLY when page.summary is not None
doc:{url_hash}              NON-indexed meta — num_chunks, fetched_at, url
```

Vector-alignment contract (research D6): `len(vectors) == len(chunks) + (1 if summary else 0)`.
Each `chunk:` key gets `EXPIRE settings.memory_ttl_seconds` when > 0 (0 = no expiry).

**Upsert lifecycle**:

```
new page ──store()──▶ chunks 0..n-1 (+summary) + doc meta
re-store (fewer chunks) ──▶ delete old chunk:{hash}:* via doc.num_chunks, then write new
                            (no stale keys survive — FR-M2-12)
TTL expiry ──▶ chunk keys vanish independently; doc meta governs freshness (is_fresh)
```

## Validation rules (from FRs)

- `knn` returns ≤ k hits, descending similarity, **unfiltered**; empty index → `[]`.
- similarity = `distance_to_similarity(d) = 1.0 − d`; single site; 0.30 → 0.70.
- Hit ⇔ `top_similarity is not None and top_similarity >= threshold` (inclusive).
- Chunks: size ≤ 1600, overlap 200, floor 100 chars, cap 25/page, never empty, unicode-safe.
- Canonical URL: lowercase scheme+host, no fragment, no `utm_*`; hash = 16 hex chars.
- `sources` deduped by URL; every M2 source has `origin="memory"`.
- `AgentResources` is frozen — post-construction assignment raises.
