# Contract: Ingest & Sanitize — `security/sanitizer.py` + `nodes/ingest.py`

**FRs**: FR-021…FR-027 · **Seams**: Ruling C (sanitizer internals → M5, `ingest_content`
FROZEN after M3), Ruling G (`skip_store` honoured from day one), Ruling D (summary via the
M2 thin analytics client — single call-site).

## `sanitize(text: str) -> tuple[str, list[str]]` — PASS-THROUGH STUB

```python
def sanitize(text: str) -> tuple[str, list[str]]:
    """L3 sanitize-before-store. M3 stub: pass-through.
    M5 replaces the internals (strip script/style/iframe, HTML comments, data: URIs,
    long base64, markdown images; neutralise injection phrases to
    '[removed-suspicious-instruction]'; return provenance flags).
    ingest_content must NOT change when M5 lands."""
    return text, []
```

The call SITE is the contract: strictly between markdown conversion and chunking
(FR-021 — the T3 defence is the ordering).

## `ingest_content` node (`nodes/ingest.py`, factory `make_ingest_content(resources)`)

Per `FetchedDoc` in `state["fetched_docs"]` — order is load-bearing:

1. **Sanitize**: `clean, flags = sanitize(doc["markdown"])`.
2. **Freshness gate** (FR-024): `h = url_hash(canonicalize(doc["url"]))`; if
   `await memory.is_fresh(h)` → skip steps 3, 5, 6 (summary/embed/store) for this page;
   **step 4 (chunking) ALWAYS runs** so the page's first chunks still serve the in-hand
   answer — a fresh page contributes chunks-only context (its `summary` stays `None`,
   same shape as the FR-026 tolerance path). Protocol delta: `is_fresh(h)` added
   additively (research D4). (Analyze I2: skipping chunking would make fresh pages
   contribute nothing to the answer.)
3. **Summary** (FR-022): `analytics_llm.complete(SUMMARY_SYSTEM,
   [{"role": "user", "content": clean[:SUMMARY_INPUT_CHARS]}])` → 5–8 sentences. On ANY
   exception: `summary = None`, continue (FR-026); no summary doc stored for the page.
4. **Chunk**: `chunk_texts = chunk_markdown(clean)` (M2: 1600/200, floor 100, cap 25) →
   wrap into `Chunk` records `chunk_id=f"{h}:{i}"` (strings→records conversion happens
   HERE; `store` takes `list[Chunk]`).
5. **Embed**: one batch — `([summary] if summary else []) + chunk_texts` — preserving the
   M2 vector-alignment contract (`vectors[0]`=summary iff present, remainder 1:1).
6. **Store** (FR-023, unless `skip_store`): `await memory.store(page=doc_with_summary,
   chunks=chunks, vectors=vectors, source_query=state["query"], flags=flags)` inside
   try/except — a store failure appends a StepError and continues (FR-027; answering
   never depends on persistence; the turn NEVER routes to `failed` because of storage).

Emits: `{"fetched_docs": <same docs, summary populated>, "chunks": <all pages' chunks>,
"stored_chunk_ids": <accumulated or []>}` (+ latency/tokens/errors reducers).

## Gating semantics

| Condition | Persist? | Summary/chunks in state? | Route effect |
|---|---|---|---|
| normal | yes | yes | none (answer_from_web decides) |
| `skip_store=True` (FR-025) | NO — zero Redis writes, `stored_chunk_ids=[]` | yes | none |
| fresh URL (< 24 h) | NO for that URL | chunks yes (always produced); `summary=None` | none |
| summary LLM fails (FR-026) | chunks only, no summary doc | chunks yes, `summary=None` | none |
| store fails (FR-027) | attempted, failed — caught | yes | none — never `failed` |

## Anti-churn guards

- NO distance→similarity math here (single conversion site is `store.py`; P-II).
- NO retry wrapping of the summary/store calls (M5).
- NO re-fetch or robots.txt logic.
- `SUMMARY_SYSTEM` wording is implement-time; M5's L2 pass finalises prompt text without
  changing this node (Ruling E analogue for the summary prompt).
