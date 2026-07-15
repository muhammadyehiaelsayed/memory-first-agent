# Contract: Answer from Web & Graph Rewiring — `nodes/answer.py` (EDIT), `graph.py`, `app.py`, `cli.py`

**FRs**: FR-028…FR-033 · **Seams**: Ruling B (temporary edge removed HERE), Ruling E
(prompts API fixed — `wrap_context(sources, origin="web")`), Ruling F (entry stays
`embed_query`; `blocked` unreachable until M5).

## `answer_from_web` node (added to `nodes/answer.py`; existing functions untouched)

**Normal path** (`fetched_docs` non-empty):

- Context per page: its `summary` (omit the line if `None` — FR-026 tolerance) + its
  first `WEB_CONTEXT_CHUNKS_PER_PAGE=2` chunks (by `chunk_index`, matched via page URL) —
  NEVER all chunks (FR-028). Fewer than 2 chunks ⇒ contribute what exists, no error.
- Wrap with `wrap_context(sources, origin="web")` (M2 API, FINAL); call
  `chat_llm.complete(build_system_prompt(), messages)`.
- Emit: `route="memory_miss_web_search"`, `answer` (ends with "Sources:" — the M2 system
  prompt enforces; append the block if the model omitted it, reusing M2's answer.py
  pattern), `sources=[SourceRef(url, title, origin="web")…]` deduped by URL (FR-029).

**Snippets-only degraded path** (`fetched_docs == []`, `search_results` non-empty —
reached via `route_after_fetch`):

- Context from `search_results` snippets; prepend `LOW_CONFIDENCE_DISCLAIMER` to the
  answer; emit `route="degraded_web"`, `degradation="snippets_only"`, sources from the
  snippet URLs with `origin="web"` (FR-030).

**Hard rule (FR-031)**: ZERO memory reads — no `memory.knn`, no Redis calls; context is
assembled exclusively from `state["fetched_docs"]` + `state["chunks"]` +
`state["search_results"]`. On chat-LLM failure: append StepError, emit `route="failed"`
+ the M2 FAILURE_APOLOGY (same containment pattern as `answer_from_memory`).

## `graph.py` rewiring (Ruling B — the pre-authorised remap)

```python
g.add_node("web_search", make_web_search(r))
g.add_node("fetch_pages", make_fetch_pages(r))
g.add_node("ingest_content", make_ingest_content(r))
g.add_node("answer_from_web", make_answer_from_web(r))

g.add_conditional_edges("memory_search", route_after_memory,
    {"answer_from_memory": "answer_from_memory", "web_search": "web_search"})  # temp edge GONE
g.add_conditional_edges("web_search", route_after_search,
    {"fetch_pages": "fetch_pages", "answer_failure": "answer_failure"})
g.add_conditional_edges("fetch_pages", route_after_fetch,
    {"ingest_content": "ingest_content", "answer_from_web": "answer_from_web"})
g.add_edge("ingest_content", "answer_from_web")
g.add_edge("answer_from_web", "log_turn")           # log_turn stays the M4 no-op stub
```

Entry stays `embed_query` (Ruling F). Structural acceptance (FR-032): compiles;
`draw_mermaid()` shows the 4 web nodes on the miss path; NO `memory_search → answer_failure`
edge remains; routes `memory_hit | memory_miss_web_search | degraded_web | failed` all
reachable (`blocked` arrives with M5's guard).

## `app.py` — `build_resources()` (call sites unchanged)

- Replace `_NoopSearcher()` → `FallbackProvider(settings)`; `_NoopFetcher()` →
  `HttpxPageFetcher(settings)`. Delete the two Noop classes; `_NoopTurnLogger` STAYS
  (M4's). Frozen `AgentResources` shape untouched.

## `cli.py` — `ask` miss banner + web sources (§6.13a; M3 is the sole owner)

- Miss branch: print canonical banner **`[MEMORY MISS → searching the web]`**
  (byte-identical string M4's chat REPL reuses) — replaces M2's bare `[MEMORY MISS]` and
  its temporariness comment (FR-033).
- Sources now print on BOTH outcomes: hit → `(memory) {title} <{url}>` (unchanged);
  miss → `(web) {title} <{url}>` from `TurnResult.sources`.
- Hit banner `[MEMORY HIT sim=X.XX]` unchanged. Key-missing and Redis-down guards
  unchanged.

## Demo capture (T-M3-13 / FR-034)

`docs/demo_transcript.md`: wipe → ask novel question (miss banner + web sources; Tavily
provider) → identical re-ask (hit banner sim≥0.70, memory sources, zero web calls).
Verbatim re-ask — paraphrases may miss at 0.70 (source §10; M3's summary docs improve
paraphrase altitude but the demo must not depend on it).
