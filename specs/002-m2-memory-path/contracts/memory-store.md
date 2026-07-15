# Contract: `memagent.memory` — store, chunking, urls (M2)

Consumers: `memory_search` node (M2), `seed_memory.py` (M2), M3's `ingest_content`,
M6's integration/e2e tests.

## `memory/store.py`

```python
def distance_to_similarity(distance: float) -> float:   # THE one conversion site (P-II)
    return 1.0 - distance
```

`RedisMemoryStore(settings, client)` implements `MemoryStore` over M1's schema/index:

- **`knn(vector, k) -> list[MemoryHit]`** — redisvl `VectorQuery` top-k by `embedding`,
  returning indexed fields + `vector_distance`. Per result: attach
  `similarity = distance_to_similarity(vector_distance)`; `fetched_at` epoch → ISO-8601
  `stored_at`; `sanitizer_flags` csv → list; build `MemoryHit`. Return **unfiltered**,
  descending similarity. Empty index → `[]` (never an error). Redis-down: may raise in
  M2 (M5 owns graceful degradation — do NOT build it here).
- **`store(page, chunks, vectors, source_query, flags) -> list[str]`** —
  `url_hash(page["url"])`; if `doc:{hash}` exists → delete all `chunk:{hash}:*` via old
  `num_chunks` (deterministic upsert, no SCAN); write `chunk:{hash}:{i}` with all 11
  schema fields; write `chunk:{hash}:summary` iff `page["summary"] is not None`; write
  `doc:{hash}` meta; `EXPIRE settings.memory_ttl_seconds` on every `chunk:` key when
  > 0 (0 disables). Returns stored chunk ids.
  **Vector alignment (binding for M3)**: summary present → `vectors[0]` = summary
  embedding, `vectors[1:]` ↔ chunks; absent → `vectors` ↔ chunks 1:1.
- **`is_fresh(url_hash) -> bool`** — `now − doc:{hash}.fetched_at <
  settings.freshness_window_seconds` (86400); missing doc → `False`. Consumed by M3.

Fallback note: redisvl 0.23.0's `load(ttl=)`/`array_to_buffer`/`VectorQuery` were verified
present at M1; if drift appears, the EXPIRE-pipeline fallback preserves the observable
behavior (per-key TTL) — FR-M2-10/11 assert behavior, not mechanism.

## `memory/chunking.py`

`chunk_markdown(text: str) -> list[str]` — `RecursiveCharacterTextSplitter`
(langchain-text-splitters), markdown separators (headings/paragraphs first),
`chunk_size=1600`, `chunk_overlap=200`; post-filter: drop `< 100` chars, drop
empty/whitespace-only, cap at 25. Invariants: never an empty string; unicode preserved;
short doc → ≤ 1 chunk.

## `memory/urls.py`

- `canonicalize(url) -> str` — lowercase scheme + host; drop fragment; drop every
  `utm_*` query param; keep other params; path/query case preserved (research D9).
- `url_hash(url) -> str` — `sha256(canonicalize(url).encode()).hexdigest()[:16]`.
- Equality example (FR-M2-15): `HTTP://Example.com/a?utm_source=x#frag` ≡
  `http://example.com/a` → same canonical string, same 16-char hash.
